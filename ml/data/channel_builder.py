"""채널 빌더 — 수집된 포인트 데이터 → [T, H, W, C] 채널 그리드.

1. 공통 일별 날짜 인덱스 생성
2. 채널별 IDW 공간 보간 → (H, W) 격자
3. 결측 처리 (forward-fill → 전체 평균)
4. 파생 채널 계산 (N:P, WBI, SST_anomaly 등)
5. 정적 채널 계산 (하구거리, 수심 근사)

출력: cube [T, H, W, C], labels [T, H, W], channel_names list, norm_stats dict

build_channels_to_zarr(): 스트리밍 버전 — 날짜별 즉시 Zarr 기록, 메모리 ~35MB/day
"""
from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy.interpolate import griddata
from scipy.spatial import cKDTree

# ─── 연구 영역 (서해안 김 양식 지역) ──────────────────────────────────────
LAT_MIN, LAT_MAX = 34.0, 36.8
LON_MIN, LON_MAX = 125.3, 128.0

# 금강 하구 좌표 (하구거리 계산 기준)
GEUMGANG_ESTUARY = (36.02, 126.83)

# ─── 채널 정의 (모듈 레벨 — build_channels / build_channels_to_zarr 공유) ──
CHANNEL_NAMES = [
    # Tier0 — 직접 원인 (3)
    "sst",              #  0  수온 °C                        NIFS+KOEM
    "din",              #  1  용존무기질소 μmol/L              NIFS+KOEM
    "dip",              #  2  용존무기인 μmol/L               KOEM
    # Tier1 — 핵심 forcing (5)
    "sio2",             #  3  규산염 μmol/L                   KOEM
    "np_ratio",         #  4  N:P 비율 [파생: ch1÷ch2]
    "salinity",         #  5  염분 psu                        NIFS+KOEM
    "precipitation",    #  6  강수량 mm/day                   KMA
    "solar_radiation",  #  7  일사량 MJ/m²/day               KMA
    # Tier2 — 보조 환경장 (8)
    "chlorophyll_a",    #  8  Chl-a mg/m³                    GOCI-II+KOEM
    "dissolved_oxygen", #  9  DO mg/L                         NIFS+KOEM
    "current_u",        # 10  동서류 m/s                      CMEMS 일별
    "current_v",        # 11  남북류 m/s                      CMEMS 일별
    "sst_anomaly",      # 12  수온 편차 °C [파생: ch0-30d mean]
    "sst_7d_avg",       # 13  7일 평균수온 °C [파생]
    "days_since_rain",  # 14  강우 후 경과일 [파생: ch6]
    "turbidity",        # 15  탁도 NTU                        KOEM
    # Tier3 — 운영/기상 보조 (7)
    "wind_speed",       # 16  풍속 크기 m/s                   KMA
    "wind_dir_sin",     # 17  풍향 sin                        KMA
    "wind_dir_cos",     # 18  풍향 cos                        KMA
    "air_temp",         # 19  기온 °C                         KMA
    "ph",               # 20  pH                              KOEM
    "no3_nitrogen",     # 21  NO3 μmol/L                      NIFS+KOEM
    "nh4_nitrogen",     # 22  NH4 μmol/L                      NIFS+KOEM
    # Tier4 — 파생/위성 (9)
    "sst_gradient",     # 23  수온 경사 °C/km [파생: ch0 공간미분]
    "nir_idx",          # 24  NIR 지수 (B865/B555)             GOCI-II
    "month_sin",        # 25  월 순환 sin [파생]
    "month_cos",        # 26  월 순환 cos [파생]
    "current_speed",    # 27  해류 속도 m/s [파생: sqrt(u²+v²)]
    "chl_7d_avg",       # 28  Chl-a 7일 평균 [파생]
    "nir_7d_avg",       # 29  NIR 7일 평균 [파생]
    "sst_30d_avg",      # 30  SST 30일 평균 [파생]
    "mld",              # 31  혼합층 깊이 m                   CMEMS
]

# ─── WBI 공식 (predict.py 미러) ────────────────────────────────────────────
def _wbi_formula(din: np.ndarray, water_temp: np.ndarray,
                 np_ratio: np.ndarray, do: np.ndarray,
                 salinity: np.ndarray) -> np.ndarray:
    din_risk  = np.clip(1.0 - din / 5.0, 0, 1)
    temp_risk = np.clip((water_temp - 20.0) / 10.0, 0, 1)
    np_risk   = np.clip(1.0 - np_ratio / 10.0, 0, 1)
    do_risk   = np.clip(1.0 - do / 5.0, 0, 1)
    sal_risk  = np.clip((32.0 - salinity) / 4.0, 0, 1)
    wbi = (0.38 * din_risk + 0.27 * temp_risk + 0.19 * np_risk
           + 0.10 * do_risk + 0.06 * sal_risk)
    return np.clip(wbi, 0, 1)


def _wbi_to_stage(wbi: np.ndarray) -> np.ndarray:
    stage = np.zeros_like(wbi, dtype=np.int8)
    stage[wbi >= 0.2] = 1
    stage[wbi >= 0.4] = 2
    stage[wbi >= 0.6] = 3
    stage[wbi >= 0.8] = 4
    return stage


# ─── ADI 기반 라벨 (v7) ────────────────────────────────────────────────────
# 실제 황백화 발생 이력 + 수온 가중 누적 빈영양 지수(ADI)로 라벨 결정.
# 황백화는 빈영양이 6일 이상 지속돼야 발생 → 당일 DIN 단독 판단 부정확.
# Labels: -1=IGNORE, 0=정상, 1=위험(ADI≥1), 2=발생(ADI≥5), 3=심화(ADI≥8)

from datetime import datetime as _dt, timedelta as _td  # noqa: E402

_HWANGBAEK_EVENTS = [
    {"start": "2010-10-01", "end": "2011-03-31"},
    {"start": "2016-11-01", "end": "2017-02-28"},
    {"start": "2017-11-01", "end": "2018-02-28"},
    {"start": "2022-01-01", "end": "2022-02-28"},
    {"start": "2023-11-01", "end": "2024-02-29"},
    {"start": "2025-11-01", "end": "2026-01-31"},
]
_EVENT_BUFFER_DAYS = 14   # 이벤트 경계 ±2주 IGNORE
_ADI_WINDOW        = 10   # ADI 누적 윈도우 (일)
_DIN_THRESH_UGL    = 70.0  # μg/L 단위 기준 (≈ 5.0 μmol/L) 황백화 임계 DIN
_CHL_CHANNEL_IDX   = 8    # chlorophyll_a 채널 인덱스 (하위 호환용)


def _is_harvest_season(date: "pd.Timestamp") -> bool:
    """수확기 여부. 11~5월=True, 6~10월=False(IGNORE)."""
    return date.month not in (6, 7, 8, 9, 10)


def _event_info(date: "pd.Timestamp") -> tuple[bool, bool]:
    """(이벤트_기간_내, IGNORE_버퍼_구간) 반환."""
    d = date.to_pydatetime().replace(tzinfo=None)
    buf = _td(days=_EVENT_BUFFER_DAYS)
    for ev in _HWANGBAEK_EVENTS:
        s = _dt.fromisoformat(ev["start"])
        e = _dt.fromisoformat(ev["end"])
        if s <= d <= e:
            in_buf = (d < s + buf) or (d > e - buf)
            return True, in_buf
        if (s - buf) <= d < s or e < d <= (e + buf):
            return False, True
    return False, False


def _sst_weight(sst_mean: float) -> float:
    """수온 → ADI 가중치. 고수온일수록 황백화 진행 가속."""
    if sst_mean >= 15.0:
        return 1.5
    if sst_mean >= 10.0:
        return 1.0
    return 0.7


class AdiLabeler:
    """ADI(누적 빈영양 지수) 기반 라벨러 — 날짜별 스트리밍 처리용.

    비대칭적 회복(Asymmetric Recovery) 메커니즘을 반영하여
    DIN이 충족되면 누적된 ADI 값을 급격히 삭감(Decay)한다.
    """

    def __init__(self, window: int = _ADI_WINDOW, decay_factor: float = 0.2):
        self.window = window
        self.decay_factor = decay_factor
        self.adi: np.ndarray | None = None

    def step(
        self,
        date: "pd.Timestamp",
        din_grid: np.ndarray,   # (H, W) μg/L — NaN 허용
        sst_grid: np.ndarray,   # (H, W) °C    — NaN 허용
    ) -> np.ndarray:
        """날짜 + DIN/SST 그리드 → (H, W) int8 라벨."""
        shape = din_grid.shape

        # 1. 비수확기는 버퍼 비우고 IGNORE 반환
        if not _is_harvest_season(date):
            self.adi = None
            return np.full(shape, -1, dtype=np.int8)

        if self.adi is None:
            self.adi = np.zeros(shape, dtype=np.float32)

        # 2. 수확기인 경우 매일 버퍼에 빈영양 결핍 축적 (버퍼 유지)
        # DIN NaN → 이벤트 기간 중 미관측 = 빈영양으로 보수적으로 간주
        deficit = np.where(
            np.isnan(din_grid),
            np.ones(shape, dtype=np.float32),
            (din_grid <= _DIN_THRESH_UGL).astype(np.float32),
        )
        sst_mean = float(np.nanmean(sst_grid)) if np.any(np.isfinite(sst_grid)) else 12.0
        weight = _sst_weight(sst_mean)

        # [비대칭 회복 적용] Deficit=1 이면 누적치 상승 (최대 10.0 한도) / Deficit=0 이면 어제치 * 0.2로 급감
        self.adi = np.where(
            deficit == 1.0,
            np.clip(self.adi + deficit * weight, 0.0, 10.0),
            self.adi * self.decay_factor
        )

        # 3. 라벨 분기 반환 (버퍼는 누적 상태 유지)
        in_event, in_buf = _event_info(date)

        # [전조구간 살리기] 이벤트 기간 내 또는 이벤트 시작 전후 ±14일 버퍼(in_buf)인 경우 ADI 기반 라벨 적용
        if in_event or in_buf:
            lbl = np.zeros(shape, dtype=np.int8)
            lbl[self.adi >= 1.0] = 1
            lbl[self.adi >= 5.0] = 2
            lbl[self.adi >= 8.0] = 3
            return lbl
        else:
            # 완전한 평년(비이벤트 기간)은 정상(0) 처리하여 False Positive 방지
            return np.zeros(shape, dtype=np.int8)


# ─── 공간 보간 ──────────────────────────────────────────────────────────────
def _idw_to_grid(
    points_lat: np.ndarray,
    points_lon: np.ndarray,
    values: np.ndarray,
    grid_lat: np.ndarray,
    grid_lon: np.ndarray,
    power: float = 2.0,
) -> np.ndarray:
    """Inverse Distance Weighting 보간 → (H, W) grid."""
    mask = ~np.isnan(values)
    if mask.sum() == 0:
        return np.full(grid_lat.shape, np.nan)

    pts = np.column_stack([points_lat[mask], points_lon[mask]])
    vals = values[mask]

    # 위치 중복 제거
    _, unique_idx = np.unique(pts, axis=0, return_index=True)
    pts  = pts[unique_idx]
    vals = vals[unique_idx]
    gp   = np.column_stack([grid_lat.ravel(), grid_lon.ravel()])

    if len(pts) < 3:
        # unique 포인트 3개 미만: Delaunay 불가 → pure IDW
        diff = gp[:, None, :] - pts[None, :, :]
        dist = np.maximum(np.sqrt((diff ** 2).sum(axis=2)), 1e-6)
        w    = 1.0 / (dist ** power)
        return (w * vals[None, :]).sum(axis=1).reshape(grid_lat.shape).astype(np.float32) / w.sum(axis=1).reshape(grid_lat.shape)

    # 먼저 scipy linear 보간 (외삽 영역은 NaN)
    result = griddata(pts, vals, gp, method="linear")

    # 외삽 영역(NaN)은 KDTree K-NN IDW로 채우기
    # pairwise 행렬(N_nan × N_pts)은 512×512에서 수백 GB → KDTree로 O(N_nan × K) 로 제한
    nan_mask = np.isnan(result)
    if nan_mask.any():
        K = min(10, len(pts))
        tree = cKDTree(pts)
        nan_gp = gp[nan_mask]
        dist, idx = tree.query(nan_gp, k=K)   # (N_nan, K)
        if K == 1:
            dist = dist[:, np.newaxis]
            idx  = idx[:, np.newaxis]
        dist = np.maximum(dist, 1e-6)
        w    = 1.0 / (dist ** power)           # (N_nan, K)
        result[nan_mask] = (w * vals[idx]).sum(axis=1) / w.sum(axis=1)

    return result.reshape(grid_lat.shape).astype(np.float32)


# ─── 정적 채널 (1회 계산) ──────────────────────────────────────────────────
def _make_static_channels(grid_lat: np.ndarray, grid_lon: np.ndarray
                          ) -> dict[str, np.ndarray]:
    """위도·경도 격자 → 정적 채널 dict."""
    # 하구거리 (km) — 위경도 간이 거리
    dlat = (grid_lat - GEUMGANG_ESTUARY[0]) * 111.0
    dlon = (grid_lon - GEUMGANG_ESTUARY[1]) * 111.0 * np.cos(np.radians(grid_lat))
    dist_km = np.sqrt(dlat**2 + dlon**2).astype(np.float32)

    # 수심 근사 (간이 모델 — 실 수심도 확보 시 교체)
    # 서해 평균 수심 44m, 해안에서 멀수록 깊어짐
    depth = (20.0 + dist_km * 0.1).clip(5, 100).astype(np.float32)

    return {
        "dist_estuary_km": dist_km,
        "water_depth_m":   depth,
    }


# ─── 메인 빌더 ─────────────────────────────────────────────────────────────
def build_channels(
    nifs_df:   pd.DataFrame,
    kma_df:    pd.DataFrame,
    koem_df:   pd.DataFrame,
    kwater_df: pd.DataFrame,
    kosc_df:     pd.DataFrame | None = None,  # GOCI-II: chl_a, nir_idx
    kodc_df:     pd.DataFrame | None = None,  # CMEMS 일별 해류: date, lat, lon, current_u/v
    sentinel_df: pd.DataFrame | None = None,  # Sentinel-2 NDCI: date, lat, lon, chl_a_s2
    start_date: str | None = None,
    end_date:   str | None = None,
    grid_h: int = 128,
    grid_w: int = 128,
) -> dict[str, Any]:
    """포인트 DataFrame → [T, H, W, C] OceanTensorCube 채널 그리드.

    Returns dict:
        cube      [T, H, W, C] float32
        labels    [T, H, W]    int8
        dates     list[str]    길이 T
        channel_names list[str] 길이 C
        norm_stats    dict {ch_name: {mean, std, min, max}}
        grid_meta  dict {lat_min, lat_max, lon_min, lon_max, H, W}
    """
    if kosc_df is None:
        kosc_df = pd.DataFrame()
    if kodc_df is None:
        kodc_df = pd.DataFrame()

    # ── 날짜 인덱스 ──
    all_dates: list[pd.Timestamp] = []
    for df in [nifs_df, kma_df, koem_df, kwater_df, kosc_df]:
        if not df.empty and "date" in df.columns:
            all_dates.extend(df["date"].tolist())

    if not all_dates:
        raise ValueError("수집된 데이터가 없습니다.")

    if start_date:
        t_start = pd.Timestamp(start_date)
    else:
        t_start = min(all_dates)

    if end_date:
        t_end = pd.Timestamp(end_date)
    else:
        t_end = max(all_dates)

    date_index = pd.date_range(t_start, t_end, freq="D")
    T = len(date_index)
    print(f"[channel_builder] 날짜 범위: {t_start.date()} ~ {t_end.date()} ({T}일)")

    # ── 격자 생성 ──
    lats = np.linspace(LAT_MIN, LAT_MAX, grid_h)
    lons = np.linspace(LON_MIN, LON_MAX, grid_w)
    grid_lon, grid_lat = np.meshgrid(lons, lats)  # (H, W)

    static = _make_static_channels(grid_lat, grid_lon)

    # ── 채널 정의 순서 ──
    # 젬또리+챗또리 검토 반영 (2026-06-13, 2026-06-22):
    #   - WQI 제거 (구성요소와 공선성 + PM 결정)
    #   - ch12/13 wind_u/v → current_u/v (2026-06-13), 이후 ch10/11로 재배치 + CMEMS 일별로 교체
    #   - par_proxy → solar_radiation (직접 측정값, 다중공선성 제거, 2026-06-22)
    #   - tn_proxy 제거 (DIN×1.3 선형 중복, 2026-06-22)
    #   - exposure_time 제거 (수심만의 정적 bucket, water_depth 중복, 2026-06-22)
    #   - growth_stage 제거 → month_sin/month_cos 순환 대체 (2026-06-22)
    #   - sentinel_ndci 제거 (5일 revisit + 구름, 결측 극심, 2026-06-22)
    #   - nir_idx 유지 (GOCI-II 정지궤도, 결측 낮음, 황백화 proxy 유효)
    CHANNEL_NAMES = globals()["CHANNEL_NAMES"]   # 전역과 동기화
    C = len(CHANNEL_NAMES)
    assert C == 32, f"채널 수 오류: {C}"

    # ── 포인트 데이터를 날짜별로 집계 (lat/lon 보존) ──
    def _daily_agg(df: pd.DataFrame, value_cols: list[str]) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()
        keep = ["date", "lat", "lon"] + [c for c in value_cols if c in df.columns]
        return df[keep].copy()

    nifs_agg   = _daily_agg(nifs_df,  ["water_temp", "salinity", "dissolved_oxygen",
                                        "no3_nitrogen", "nh4_nitrogen", "ph"])
    kma_agg    = _daily_agg(kma_df,   ["precipitation_mm", "avg_wind_speed",
                                        "wind_dir_deg", "avg_temp"])
    koem_agg   = _daily_agg(koem_df,  ["water_temp", "salinity", "dissolved_oxygen",
                                        "no3_nitrogen", "nh4_nitrogen", "dip",
                                        "sio2", "ph", "turbidity", "chlorophyll_a"])
    kwater_agg = _daily_agg(kwater_df, ["discharge_m3s"])
    kosc_agg     = _daily_agg(kosc_df,     ["chl_a", "nir_idx"])     # GOCI-II composite
    sentinel_agg = _daily_agg(sentinel_df if sentinel_df is not None
                              else pd.DataFrame(), ["chl_a_s2"])     # Sentinel-2 NDCI

    # CMEMS 해류: date 컬럼 기반 — _get_pts(tol_days=7)로 날짜 루프 내 조회

    # ── 날짜 루프: 각 날짜마다 IDW 보간 ──
    cube = np.zeros((T, grid_h, grid_w, C), dtype=np.float32)
    cube[:] = np.nan  # 일단 NaN으로 채워두기

    print(f"[channel_builder] 보간 중... (T={T}, H={grid_h}, W={grid_w}, C={C})")

    for ti, date in enumerate(date_index):
        d_str = date.strftime("%Y-%m-%d")

        def _get_pts(df: pd.DataFrame, col: str, tol_days: int = 90):
            """날짜 ±tol_days 이내 포인트 추출."""
            if df.empty or col not in df.columns:
                return np.array([]), np.array([]), np.array([])
            mask = (abs((df["date"] - date).dt.days) <= tol_days) & df[col].notna()
            sub = df[mask]
            if sub.empty:
                return np.array([]), np.array([]), np.array([])
            return sub["lat"].values, sub["lon"].values, sub[col].values

        def _interp(lat, lon, val):
            if len(val) == 0:
                return np.full((grid_h, grid_w), np.nan, dtype=np.float32)
            return _idw_to_grid(lat, lon, val, grid_lat, grid_lon)

        # 원시 채널 보간
        nifs_koem = (pd.concat([nifs_agg, koem_agg], ignore_index=True)
                     if not koem_agg.empty and not nifs_agg.empty
                     else (nifs_agg if not nifs_agg.empty else koem_agg))

        # ch00 sst
        lat, lon, val = _get_pts(nifs_koem, "water_temp")
        sst = _interp(lat, lon, val)
        cube[ti, :, :, 0] = sst

        # ch01 din = NO3 + NH4
        lat, lon, val = _get_pts(koem_agg, "no3_nitrogen", tol_days=90)
        no3 = _interp(lat, lon, val)
        lat2, lon2, val2 = _get_pts(koem_agg, "nh4_nitrogen", tol_days=90)
        nh4 = _interp(lat2, lon2, val2)
        din = np.where(np.isnan(no3), 0, no3) + np.where(np.isnan(nh4), 0, nh4)
        din = np.where(np.isnan(no3) & np.isnan(nh4), np.nan, din)
        cube[ti, :, :, 1] = din

        # ch02 dip
        lat, lon, val = _get_pts(koem_agg, "dip", tol_days=90)
        cube[ti, :, :, 2] = _interp(lat, lon, val)

        # ch03 sio2
        lat, lon, val = _get_pts(koem_agg, "sio2", tol_days=90)
        cube[ti, :, :, 3] = _interp(lat, lon, val)

        # ch04 np_ratio [파생]
        dip_g = cube[ti, :, :, 2]
        cube[ti, :, :, 4] = np.where(dip_g > 0, din / dip_g, np.nan)

        # ch05 salinity
        lat, lon, val = _get_pts(nifs_koem, "salinity")
        cube[ti, :, :, 5] = _interp(lat, lon, val)

        # ch06 precipitation
        lat, lon, val = _get_pts(kma_agg, "precipitation_mm", tol_days=1)
        cube[ti, :, :, 6] = _interp(lat, lon, val) if len(val) > 0 else 0.0

        # ch07 solar_radiation [KMA 일사량 MJ/m²/day]
        lat, lon, val = _get_pts(kma_agg, "solar_radiation_mjm2", tol_days=1)
        cube[ti, :, :, 7] = _interp(lat, lon, val) if len(val) > 0 else np.nan

        # ch08 chlorophyll_a
        lat, lon, val = _get_pts(koem_agg, "chlorophyll_a", tol_days=90)
        cube[ti, :, :, 8] = _interp(lat, lon, val)

        # ch09 dissolved_oxygen
        lat, lon, val = _get_pts(nifs_koem, "dissolved_oxygen")
        cube[ti, :, :, 9] = _interp(lat, lon, val)

        # ch10/11 current_u/v [CMEMS 일별 표층 해류, ±7일 IDW]
        lat_c, lon_c, cur_u = _get_pts(kodc_df, "current_u", tol_days=7)
        _,     _,     cur_v = _get_pts(kodc_df, "current_v", tol_days=7)
        if len(cur_u) > 0:
            cube[ti, :, :, 10] = _idw_to_grid(lat_c, lon_c, cur_u, grid_lat, grid_lon)
            cube[ti, :, :, 11] = _idw_to_grid(lat_c, lon_c, cur_v, grid_lat, grid_lon)

        # ch15 turbidity
        lat, lon, val = _get_pts(koem_agg, "turbidity", tol_days=90)
        cube[ti, :, :, 15] = _interp(lat, lon, val)

        # ch16/17/18 wind [KMA]
        lat, lon, spd  = _get_pts(kma_agg, "avg_wind_speed", tol_days=1)
        lat, lon, wdir = _get_pts(kma_agg, "wind_dir_deg",   tol_days=1)
        if len(spd) > 0 and len(wdir) > 0:
            n = min(len(spd), len(wdir))
            cube[ti, :, :, 16] = _idw_to_grid(lat[:n], lon[:n], spd[:n], grid_lat, grid_lon)
            cube[ti, :, :, 17] = _idw_to_grid(lat[:n], lon[:n], np.sin(np.radians(wdir[:n])), grid_lat, grid_lon)
            cube[ti, :, :, 18] = _idw_to_grid(lat[:n], lon[:n], np.cos(np.radians(wdir[:n])), grid_lat, grid_lon)

        # ch19 air_temp
        lat, lon, val = _get_pts(kma_agg, "avg_temp", tol_days=1)
        cube[ti, :, :, 19] = _interp(lat, lon, val)

        # ch20 ph
        lat, lon, val = _get_pts(koem_agg, "ph", tol_days=90)
        cube[ti, :, :, 20] = _interp(lat, lon, val)

        # ch21/22 no3/nh4
        lat, lon, val = _get_pts(koem_agg, "no3_nitrogen", tol_days=90)
        cube[ti, :, :, 21] = _interp(lat, lon, val)
        lat, lon, val = _get_pts(koem_agg, "nh4_nitrogen", tol_days=90)
        cube[ti, :, :, 22] = _interp(lat, lon, val)

        # ch24 nir_idx [GOCI-II B865/B555]
        lat, lon, val = _get_pts(kosc_agg, "nir_idx", tol_days=1)
        cube[ti, :, :, 24] = _interp(lat, lon, val) if len(val) > 0 else np.nan

        # ch25/26 month_sin/cos
        angle = 2.0 * np.pi * (date.month - 1) / 12.0
        cube[ti, :, :, 25] = float(np.sin(angle))
        cube[ti, :, :, 26] = float(np.cos(angle))

        # ch27 current_speed [파생: sqrt(u²+v²)]
        cube[ti, :, :, 27] = np.sqrt(cube[ti, :, :, 10]**2 + cube[ti, :, :, 11]**2)

        # ch31 mld [CMEMS 혼합층 깊이, ±7일 IDW]
        lat_m, lon_m, mld_v = _get_pts(kodc_df, "mld", tol_days=7)
        if len(mld_v) > 0:
            cube[ti, :, :, 31] = _idw_to_grid(lat_m, lon_m, mld_v, grid_lat, grid_lon)

    # ── 시간 축 파생 채널 ──────────────────────────────────────────────────
    sst_cube = cube[:, :, :, 0].copy()

    # ch12 sst_anomaly / ch13 sst_7d_avg / ch30 sst_30d_avg
    sst_30d = np.full_like(sst_cube, np.nan)
    sst_7d  = np.full_like(sst_cube, np.nan)
    for ti in range(T):
        w30 = sst_cube[max(0, ti-30):ti+1]
        w7  = sst_cube[max(0, ti-7):ti+1]
        sst_30d[ti] = np.nanmean(w30, axis=0)
        sst_7d[ti]  = np.nanmean(w7,  axis=0)
    cube[:, :, :, 12] = sst_cube - sst_30d
    cube[:, :, :, 13] = sst_7d
    cube[:, :, :, 30] = sst_30d

    # ch14 days_since_rain
    precip_cube = cube[:, :, :, 6]
    days_since_rain = np.zeros((T, grid_h, grid_w), dtype=np.float32)
    for ti in range(1, T):
        rained = precip_cube[ti] > 0.5
        days_since_rain[ti] = np.where(rained, 0.0, days_since_rain[ti-1] + 1.0)
    cube[:, :, :, 14] = days_since_rain

    # ch23 sst_gradient [공간 미분]
    for ti in range(T):
        sst_t = cube[ti, :, :, 0].copy()
        sst_t = np.where(np.isnan(sst_t), np.nanmean(sst_t), sst_t)
        gy, gx = np.gradient(sst_t)
        cube[ti, :, :, 23] = np.sqrt(gy**2 + gx**2).astype(np.float32)

    # ch28 chl_7d_avg / ch29 nir_7d_avg
    chl_cube = cube[:, :, :, 8].copy()
    nir_cube = cube[:, :, :, 24].copy()
    chl_7d = np.full_like(chl_cube, np.nan)
    nir_7d = np.full_like(nir_cube, np.nan)
    for ti in range(T):
        chl_7d[ti] = np.nanmean(chl_cube[max(0, ti-7):ti+1], axis=0)
        nir_7d[ti] = np.nanmean(nir_cube[max(0, ti-7):ti+1], axis=0)
    cube[:, :, :, 28] = chl_7d
    cube[:, :, :, 29] = nir_7d

    # ── 결측 처리: forward-fill → 전체 평균 ──────────────────────────────
    for c in range(C):
        ch = cube[:, :, :, c]
        for ti in range(1, T):
            still_nan = np.isnan(ch[ti])
            if still_nan.any():
                ch[ti] = np.where(still_nan, ch[ti-1], ch[ti])
        global_mean = np.nanmean(ch)
        if np.isnan(global_mean):
            global_mean = 0.0
        cube[:, :, :, c] = np.where(np.isnan(ch), global_mean, ch)

    # ── ADI 라벨 계산 (v7) ───────────────────────────────────────────────
    _labeler = AdiLabeler()
    labels = np.stack(
        [_labeler.step(date, cube[ti, :, :, 1], cube[ti, :, :, 0])
         for ti, date in enumerate(date_index)], axis=0
    ).astype(np.int8)  # (T, H, W) — -1=IGNORE 0=정상 1=위험 2=발생 3=심화

    # ── 정규화 통계 ──────────────────────────────────────────────────────
    norm_stats: dict[str, dict] = {}
    for c, name in enumerate(CHANNEL_NAMES):
        ch = cube[:, :, :, c].ravel()
        norm_stats[name] = {
            "mean": float(np.nanmean(ch)),
            "std":  float(np.nanstd(ch) + 1e-8),
            "min":  float(np.nanmin(ch)),
            "max":  float(np.nanmax(ch)),
        }

    print(f"[channel_builder] 완료: cube={cube.shape}, labels={labels.shape}")
    _flat = labels.ravel()
    lbl_dist = np.bincount(_flat[_flat >= 0].astype(np.uint8), minlength=4)
    ignore_n = int((_flat == -1).sum())
    print(f"[channel_builder] 라벨 분포: IGNORE={ignore_n}, " +
          str(dict(zip(['정상','위험','발생','심화'], lbl_dist.tolist()))))

    return {
        "cube":          cube,
        "labels":        labels,
        "dates":         [d.strftime("%Y-%m-%d") for d in date_index],
        "channel_names": CHANNEL_NAMES,
        "norm_stats":    norm_stats,
        "grid_meta": {
            "lat_min": LAT_MIN, "lat_max": LAT_MAX,
            "lon_min": LON_MIN, "lon_max": LON_MAX,
            "H": grid_h, "W": grid_w,
        },
    }


# ─── 스트리밍 버전 (OOM 방지) ────────────────────────────────────────────────
def build_channels_to_zarr(
    nifs_df:   pd.DataFrame,
    kma_df:    pd.DataFrame,
    koem_df:   pd.DataFrame,
    kwater_df: pd.DataFrame,
    zarr_data_path:   str,
    zarr_labels_path: str,
    kosc_df:     pd.DataFrame | None = None,
    kodc_df:     pd.DataFrame | None = None,
    sentinel_df: pd.DataFrame | None = None,
    start_date: str | None = None,
    end_date:   str | None = None,
    grid_h: int = 128,
    grid_w: int = 128,
) -> dict[str, Any]:
    """날짜별 즉시 Zarr 기록 — 메모리 13GB → ~35MB.

    build_channels()와 동일한 채널/라벨을 생성하되,
    전체 cube를 메모리에 올리지 않고 하루 슬라이스씩 Zarr에 씀.
    rolling 버퍼로 시계열 파생채널(ch15/16/17/28)을 인라인 처리.
    """
    import zarr

    if kosc_df is None:
        kosc_df = pd.DataFrame()
    if kodc_df is None:
        kodc_df = pd.DataFrame()

    # ── 날짜 인덱스 ──
    all_dates: list[pd.Timestamp] = []
    for df in [nifs_df, kma_df, koem_df, kwater_df, kosc_df]:
        if not df.empty and "date" in df.columns:
            all_dates.extend(df["date"].tolist())
    if not all_dates:
        raise ValueError("수집된 데이터가 없습니다.")

    t_start = pd.Timestamp(start_date) if start_date else min(all_dates)
    t_end   = pd.Timestamp(end_date)   if end_date   else max(all_dates)
    date_index = pd.date_range(t_start, t_end, freq="D")
    T = len(date_index)
    print(f"[channel_builder] 날짜 범위: {t_start.date()} ~ {t_end.date()} ({T}일)")

    # ── 격자 ──
    lats = np.linspace(LAT_MIN, LAT_MAX, grid_h)
    lons = np.linspace(LON_MIN, LON_MAX, grid_w)
    grid_lon, grid_lat = np.meshgrid(lons, lats)
    static = _make_static_channels(grid_lat, grid_lon)

    C = len(CHANNEL_NAMES)

    # ── Zarr 사전 할당 (디스크에만, 메모리 0) ──
    z_data   = zarr.open(zarr_data_path,   mode="w",
                         shape=(T, grid_h, grid_w, C), dtype="float32",
                         chunks=(1, grid_h, grid_w, C))
    z_labels = zarr.open(zarr_labels_path, mode="w",
                         shape=(T, grid_h, grid_w), dtype="int8",
                         chunks=(1, grid_h, grid_w))

    # ── 집계 ──
    def _daily_agg(df, value_cols):
        if df.empty:
            return pd.DataFrame()
        keep = ["date", "lat", "lon"] + [c for c in value_cols if c in df.columns]
        return df[keep].copy()

    nifs_agg   = _daily_agg(nifs_df,  ["water_temp","salinity","dissolved_oxygen","no3_nitrogen","nh4_nitrogen","ph"])
    kma_agg    = _daily_agg(kma_df,   ["precipitation_mm","avg_wind_speed","wind_dir_deg","avg_temp","solar_radiation_mjm2"])
    koem_agg   = _daily_agg(koem_df,  ["water_temp","salinity","dissolved_oxygen","no3_nitrogen","nh4_nitrogen","dip","sio2","ph","turbidity","chlorophyll_a"])
    kwater_agg = _daily_agg(kwater_df, ["discharge_m3s"])
    kosc_agg   = _daily_agg(kosc_df,   ["chl_a","nir_idx"])
    sentinel_agg = _daily_agg(sentinel_df if sentinel_df is not None else pd.DataFrame(), ["chl_a_s2"])

    # kosc 공간 집계: 0.05° 격자로 평균 → 포인트 수 52K/일 → ~3K/일 (IDW ~17배 가속)
    if not kosc_agg.empty:
        kosc_agg["lat"] = (kosc_agg["lat"] * 20).round() / 20
        kosc_agg["lon"] = (kosc_agg["lon"] * 20).round() / 20
        kosc_agg = kosc_agg.groupby(["date", "lat", "lon"], as_index=False).mean()
        print(f"[channel_builder] kosc 공간집계 완료: {len(kosc_agg):,}행")

    # kosc 날짜 검색 최적화: searchsorted로 O(log n) 탐색
    if not kosc_agg.empty:
        kosc_agg = kosc_agg.sort_values("date").reset_index(drop=True)
        _kosc_dates_np = kosc_agg["date"].values
    else:
        _kosc_dates_np = np.array([], dtype="datetime64[ns]")

    # CMEMS 해류: date 컬럼 기반 — _get_pts(tol_days=7)로 날짜 루프 내 조회

    nifs_koem = (pd.concat([nifs_agg, koem_agg], ignore_index=True)
                 if not koem_agg.empty and not nifs_agg.empty
                 else (nifs_agg if not nifs_agg.empty else koem_agg))

    # ── 롤링 버퍼 ──
    sst_ring    = deque(maxlen=31)   # ch12/13/30: sst_anomaly, sst_7d_avg, sst_30d_avg
    adi_labeler = AdiLabeler()       # ADI 기반 라벨러 (롤링 버퍼 내부 유지)
    chl_ring = deque(maxlen=7)    # ch28: chl_7d_avg
    nir_ring = deque(maxlen=7)    # ch29: nir_7d_avg
    days_since_rain_g = np.zeros((grid_h, grid_w), dtype=np.float32)
    prev_slice: np.ndarray | None = None  # forward-fill용

    # ── 온라인 통계 ──
    stat_n    = np.zeros(C, dtype=np.int64)
    stat_sum  = np.zeros(C, dtype=np.float64)
    stat_sum2 = np.zeros(C, dtype=np.float64)
    stat_min  = np.full(C,  np.inf,  dtype=np.float64)
    stat_max  = np.full(C, -np.inf,  dtype=np.float64)

    print(f"[channel_builder] 스트리밍 보간 시작 (T={T}, H={grid_h}, W={grid_w}, C={C})")

    for ti, date in enumerate(date_index):

        def _get_pts(df: pd.DataFrame, col: str, tol_days: int = 90):
            if df.empty or col not in df.columns:
                return np.array([]), np.array([]), np.array([])
            # kosc는 22M행 — searchsorted로 O(log n) 날짜 범위 탐색
            if df is kosc_agg and _kosc_dates_np.size > 0:
                dt  = date.to_datetime64()
                tol = np.timedelta64(tol_days, "D")
                lo  = int(np.searchsorted(_kosc_dates_np, dt - tol))
                hi  = int(np.searchsorted(_kosc_dates_np, dt + tol, side="right"))
                sub = kosc_agg.iloc[lo:hi]
                sub = sub[sub[col].notna()]
            else:
                mask = (abs((df["date"] - date).dt.days) <= tol_days) & df[col].notna()
                sub  = df[mask]
            if sub.empty:
                return np.array([]), np.array([]), np.array([])
            return sub["lat"].values, sub["lon"].values, sub[col].values

        def _interp(lat, lon, val):
            if len(val) == 0:
                return np.full((grid_h, grid_w), np.nan, dtype=np.float32)
            return _idw_to_grid(lat, lon, val, grid_lat, grid_lon)

        s = np.full((grid_h, grid_w, C), np.nan, dtype=np.float32)

        # ch00 sst
        lat, lon, val = _get_pts(nifs_koem, "water_temp")
        s[:, :, 0] = _interp(lat, lon, val)

        # ch01 din
        lat, lon, val  = _get_pts(koem_agg, "no3_nitrogen", 90)
        lat2,lon2,val2 = _get_pts(koem_agg, "nh4_nitrogen", 90)
        no3 = _interp(lat, lon, val); nh4 = _interp(lat2, lon2, val2)
        s[:, :, 1] = np.where(np.isnan(no3) & np.isnan(nh4), np.nan,
                               np.where(np.isnan(no3), 0, no3) + np.where(np.isnan(nh4), 0, nh4))

        # ch02 dip
        lat, lon, val = _get_pts(koem_agg, "dip", 90)
        s[:, :, 2] = _interp(lat, lon, val)

        # ch03 sio2
        lat, lon, val = _get_pts(koem_agg, "sio2", 90)
        s[:, :, 3] = _interp(lat, lon, val)

        # ch04 np_ratio
        s[:, :, 4] = np.where(s[:, :, 2] > 0, s[:, :, 1] / s[:, :, 2], np.nan)

        # ch05 salinity
        lat, lon, val = _get_pts(nifs_koem, "salinity")
        s[:, :, 5] = _interp(lat, lon, val)

        # ch06 precipitation
        lat, lon, val = _get_pts(kma_agg, "precipitation_mm", 1)
        s[:, :, 6] = _interp(lat, lon, val) if len(val) > 0 else 0.0

        # ch07 solar_radiation [KMA 일사량 MJ/m²/day]
        lat, lon, val = _get_pts(kma_agg, "solar_radiation_mjm2", 1)
        if len(val) > 0:
            s[:, :, 7] = _interp(lat, lon, val)

        # ch08 chlorophyll_a
        lat, lon, val = _get_pts(koem_agg, "chlorophyll_a", 90)
        s[:, :, 8] = _interp(lat, lon, val)

        # ch09 dissolved_oxygen
        lat, lon, val = _get_pts(nifs_koem, "dissolved_oxygen")
        s[:, :, 9] = _interp(lat, lon, val)

        # ch10/11 current_u/v [CMEMS 일별 표층 해류, ±7일 IDW]
        lat_c, lon_c, cur_u = _get_pts(kodc_df, "current_u", tol_days=7)
        _,     _,     cur_v = _get_pts(kodc_df, "current_v", tol_days=7)
        if len(cur_u) > 0:
            s[:, :, 10] = _idw_to_grid(lat_c, lon_c, cur_u, grid_lat, grid_lon)
            s[:, :, 11] = _idw_to_grid(lat_c, lon_c, cur_v, grid_lat, grid_lon)

        # ch12 sst_anomaly / ch13 sst_7d_avg — rolling buffer
        sst_ring.append(s[:, :, 0].copy())
        stack30 = np.stack(sst_ring)
        s[:, :, 12] = s[:, :, 0] - np.nanmean(stack30, axis=0)
        w7 = list(sst_ring)[-min(7, len(sst_ring)):]
        s[:, :, 13] = np.nanmean(np.stack(w7), axis=0)

        # ch14 days_since_rain — running counter
        if ti > 0:
            rained = s[:, :, 6] > 0.5
            days_since_rain_g = np.where(rained, 0.0, days_since_rain_g + 1.0)
        s[:, :, 14] = days_since_rain_g

        # ch15 turbidity
        lat, lon, val = _get_pts(koem_agg, "turbidity", 90)
        s[:, :, 15] = _interp(lat, lon, val)

        # ch16/17/18 wind
        lat, lon, spd  = _get_pts(kma_agg, "avg_wind_speed", 1)
        lat, lon, wdir = _get_pts(kma_agg, "wind_dir_deg",   1)
        if len(spd) > 0 and len(wdir) > 0:
            n = min(len(spd), len(wdir))
            s[:, :, 16] = _idw_to_grid(lat[:n], lon[:n], spd[:n], grid_lat, grid_lon)
            s[:, :, 17] = _idw_to_grid(lat[:n], lon[:n], np.sin(np.radians(wdir[:n])), grid_lat, grid_lon)
            s[:, :, 18] = _idw_to_grid(lat[:n], lon[:n], np.cos(np.radians(wdir[:n])), grid_lat, grid_lon)

        # ch19 air_temp
        lat, lon, val = _get_pts(kma_agg, "avg_temp", 1)
        s[:, :, 19] = _interp(lat, lon, val)

        # ch20 ph
        lat, lon, val = _get_pts(koem_agg, "ph", 90)
        s[:, :, 20] = _interp(lat, lon, val)

        # ch21/22 no3/nh4
        lat, lon, val = _get_pts(koem_agg, "no3_nitrogen", 90)
        s[:, :, 21] = _interp(lat, lon, val)
        lat, lon, val = _get_pts(koem_agg, "nh4_nitrogen", 90)
        s[:, :, 22] = _interp(lat, lon, val)

        # ch23 sst_gradient (공간 미분)
        sst_t = s[:, :, 0].copy()
        _fill = float(np.nanmean(sst_t)) if not np.all(np.isnan(sst_t)) else 0.0
        sst_t = np.where(np.isnan(sst_t), _fill, sst_t)
        gy, gx = np.gradient(sst_t)
        s[:, :, 23] = np.sqrt(gy**2 + gx**2).astype(np.float32)

        # ch24 nir_idx [GOCI-II B865/B555 — cloud-free daily composite]
        lat, lon, val = _get_pts(kosc_agg, "nir_idx", 1)
        if len(val) > 0:
            s[:, :, 24] = _interp(lat, lon, val)

        # ch25/26 month_sin/cos [순환 계절성]
        angle = 2.0 * np.pi * (date.month - 1) / 12.0
        s[:, :, 25] = float(np.sin(angle))
        s[:, :, 26] = float(np.cos(angle))

        # ch27 current_speed [파생: sqrt(u²+v²)]
        s[:, :, 27] = np.sqrt(s[:, :, 10]**2 + s[:, :, 11]**2)

        # ch28 chl_7d_avg [파생: Chl-a 7일 이동평균]
        chl_ring.append(s[:, :, 8].copy())
        s[:, :, 28] = np.nanmean(np.stack(chl_ring), axis=0)

        # ch29 nir_7d_avg [파생: NIR 7일 이동평균]
        nir_ring.append(s[:, :, 24].copy())
        s[:, :, 29] = np.nanmean(np.stack(nir_ring), axis=0)

        # ch30 sst_30d_avg [파생: SST 30일 이동평균]
        s[:, :, 30] = np.nanmean(stack30, axis=0)

        # ch31 mld [CMEMS 혼합층 깊이, ±7일 IDW]
        lat_m, lon_m, mld_v = _get_pts(kodc_df, "mld", tol_days=7)
        if len(mld_v) > 0:
            s[:, :, 31] = _idw_to_grid(lat_m, lon_m, mld_v, grid_lat, grid_lon)

        # forward-fill (이전 날 값으로 NaN 채우기)
        if prev_slice is not None:
            for c in range(C):
                nan_mask = np.isnan(s[:, :, c])
                if nan_mask.any():
                    s[:, :, c] = np.where(nan_mask, prev_slice[:, :, c], s[:, :, c])

        # ADI 기반 라벨 (v7)
        z_labels[ti] = adi_labeler.step(date, s[:, :, 1], s[:, :, 0])

        # Zarr에 즉시 기록 (메모리 해제)
        z_data[ti] = s

        # 롤링 상태 갱신
        prev_slice = s.copy()

        # 온라인 통계 누적
        for c in range(C):
            vals = s[:, :, c].ravel()
            valid = vals[np.isfinite(vals)]
            if len(valid) > 0:
                stat_n[c]    += len(valid)
                stat_sum[c]  += float(valid.sum())
                stat_sum2[c] += float((valid ** 2).sum())
                if float(valid.min()) < stat_min[c]:
                    stat_min[c] = float(valid.min())
                if float(valid.max()) > stat_max[c]:
                    stat_max[c] = float(valid.max())

        if (ti + 1) % 30 == 0 or ti == T - 1:
            print(f"[channel_builder] {ti+1}/{T}일 완료")

    # ── 2차 결측 보정: 전체 평균으로 잔여 NaN 채우기 ──
    global_means = np.where(stat_n > 0, stat_sum / np.maximum(stat_n, 1), 0.0)
    print("[channel_builder] 2차 결측 보정 중...")
    for ti in range(T):
        day = z_data[ti][:]
        changed = False
        for c in range(C):
            nan_mask = np.isnan(day[:, :, c])
            if nan_mask.any():
                day[:, :, c] = np.where(nan_mask, float(global_means[c]), day[:, :, c])
                changed = True
        if changed:
            z_data[ti] = day
            # ADI 라벨은 1차 패스에서 이미 확정 — 2차 결측 보정 후 재계산 불필요

    # ── 정규화 통계 ──
    norm_stats: dict[str, dict] = {}
    for c, name in enumerate(CHANNEL_NAMES):
        if stat_n[c] > 0:
            mean = stat_sum[c] / stat_n[c]
            std  = max(float(np.sqrt(max(stat_sum2[c] / stat_n[c] - mean ** 2, 0.0))), 1e-8)
        else:
            mean, std = 0.0, 1e-8
        norm_stats[name] = {
            "mean": float(mean),
            "std":  float(std),
            "min":  float(stat_min[c]) if stat_n[c] > 0 else 0.0,
            "max":  float(stat_max[c]) if stat_n[c] > 0 else 0.0,
        }

    _flat = z_labels[:].ravel().astype(np.int8)
    lbl_dist = np.bincount(_flat[_flat >= 0].astype(np.uint8), minlength=4)
    ignore_n = int((_flat == -1).sum())
    print(f"[channel_builder] 완료: zarr=({T},{grid_h},{grid_w},{C})")
    print(f"[channel_builder] 라벨 분포: IGNORE={ignore_n}, " +
          str(dict(zip(['정상','위험','발생','심화'], lbl_dist.tolist()))))

    return {
        "zarr_data_path":   zarr_data_path,
        "zarr_labels_path": zarr_labels_path,
        "dates":            [d.strftime("%Y-%m-%d") for d in date_index],
        "channel_names":    CHANNEL_NAMES,
        "norm_stats":       norm_stats,
        "label_distribution": dict(zip(["IGNORE","정상","위험","발생","심화"],
                                       [ignore_n] + lbl_dist.tolist())),
        "grid_meta": {
            "lat_min": LAT_MIN, "lat_max": LAT_MAX,
            "lon_min": LON_MIN, "lon_max": LON_MAX,
            "H": grid_h, "W": grid_w,
        },
    }
