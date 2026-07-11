"""
KOSC(국가해양위성센터) GOCI-II 위성 데이터 수집기
황백화 라벨링용 Chl-a / NIR 지수 산출 + cloud masking

OPeNDAP: http://nosc.go.kr/opendap/hyrax/GOCI-II/

[실제 파일 구조 (카탈로그 직접 확인)]
GOCI-II/YYYY/MM/DD/L2/GK2_GC2_L2_YYYYMMDD_HHMMSS/
  └── GK2B_GOCI2_L2_YYYYMMDD_HHMMSS_LA_S000_AC.nc   (380MB, Rrs 12밴드 + flag)
  └── GK2B_GOCI2_L2_YYYYMMDD_HHMMSS_LA_S000_ACR.nc  (11MB, 대기보정 반사도)

[변수 구조]
  geophysical_data/Rrs/Rrs_XXX  → 원격반사도 12밴드 (380~865nm)
  geophysical_data/flag          → 구름/육지/불량 비트마스크
  navigation_data/latitude       → 위도
  navigation_data/longitude      → 경도

[Chl-a 산출]  Rrs 밴드에서 OC3 알고리즘으로 직접 계산
[NIR 지수]    Rrs_865 / Rrs_555 비율 → 황백화 시 NIR 상승

[Cloud Masking]
  flag 비트 AND 연산으로 구름·육지 픽셀 NaN 처리
  하루 10장 합성 → 픽셀별 중앙값 → cloud-free daily composite
"""

import os
import time
import logging
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import requests
import xarray as xr

logger = logging.getLogger(__name__)

# 서해안 김 양식 관심 영역
ROI = {
    "lat_min": 34.0,
    "lat_max": 36.8,
    "lon_min": 125.3,
    "lon_max": 128.0,
}

# ------------------------------------------------------------------ #
# GOCI-II flag 비트 정의
# AC.nc의 geophysical_data/flag 변수 기준
# ------------------------------------------------------------------ #
FLAG_BITS = {
    "LAND":         0x00000001,
    "CLOUD":        0x00000002,
    "CLOUD_SHADOW": 0x00000004,
    "STRAYLIGHT":   0x00000010,
    "HILT":         0x00000020,  # 포화
    "LOWLT":        0x00000080,  # 야간/박명
    "CLDICE":       0x00000100,  # 구름/얼음
    "THIN_CLOUD":   0x00000200,
}

BAD_PIXEL_MASK = (
    FLAG_BITS["LAND"]
    | FLAG_BITS["CLOUD"]
    | FLAG_BITS["CLOUD_SHADOW"]
    | FLAG_BITS["THIN_CLOUD"]
    | FLAG_BITS["CLDICE"]
    | FLAG_BITS["HILT"]
)

# ------------------------------------------------------------------ #
# 김 생육 캘린더
# ------------------------------------------------------------------ #
HARVEST_MONTHS = frozenset({11, 12, 1, 2, 3, 4, 5})  # 수확기
SEEDING_MONTHS = frozenset({9, 10})                    # 채묘기 → ignore
OFF_MONTHS     = frozenset({6, 7, 8})                  # 비수확기 → ignore

# ------------------------------------------------------------------ #
# 4단계 라벨 (젬또리 YoY-anomaly + 챗또리 transition-window 통합)
# ------------------------------------------------------------------ #
LABEL_NORMAL = 0   # 정상 수확기 (황백화 없는 해)
LABEL_WATCH  = 1   # 주의/초기  — 이벤트 시작 후 0~4주 (11월, 신호 미약)
LABEL_ACTIVE = 2   # 황백화 활성 — 이벤트 4~10주  (12월~1월 초)
LABEL_SEVERE = 3   # 황백화 심화 — 이벤트 10주+   (1월 중순~2월)
LABEL_IGNORE = -1  # 제외: 비수확기·채묘기·이벤트 전후 전이 구간

# 이벤트 내 단계 경계 (이벤트 시작일 기준 경과 주)
WATCH_END_WEEKS  = 4   # 0~4주: WATCH
ACTIVE_END_WEEKS = 10  # 4~10주: ACTIVE, 이후: SEVERE

# Chl-a 실측값 기반 임계값 (analyze_chl_nir.py 분석 결과)
CHL_THRESH_SEVERE = 2.0   # < 2.0  → 진행(3)
CHL_THRESH_ACTIVE = 2.7   # 2.0~2.7 → 경계(2)
CHL_THRESH_WATCH  = 3.8   # 2.7~3.8 → 초기(1), ≥3.8 → 정상(0)

# 이벤트 전후 ignore buffer
PRE_EVENT_BUFFER_DAYS  = 14  # 이벤트 시작 14일 전
POST_EVENT_BUFFER_DAYS = 21  # 이벤트 종료 21일 후 (회복 기간)

# ------------------------------------------------------------------ #
# 황백화 발생 이력
# GOCI-II 운영(2021~) 이전 이벤트는 참고용 — 실제 수집 시 위성 데이터 없음
# ------------------------------------------------------------------ #
HWANGBAEK_EVENTS = [
    {"start": "2010-10-01", "end": "2011-03-31", "regions": ["서천", "해남", "완도"]},
    {"start": "2016-11-01", "end": "2017-02-28", "regions": ["서천", "군산"]},
    {"start": "2017-11-01", "end": "2018-02-28", "regions": ["서천", "군산"]},
    {"start": "2022-01-01", "end": "2022-02-28", "regions": ["해남", "서천"]},
    {"start": "2023-11-01", "end": "2024-02-29", "regions": ["서천", "충남전역"]},
    {"start": "2025-11-01", "end": "2026-01-31", "regions": ["고흥", "군산", "서천"]},
]

# 정상 수확기 후보 (GOCI-II 운영 + 황백화 기록 없음)
# 챗또리 권고: 연도 편중 방지를 위해 월별 quota 샘플링 적용
NORMAL_HARVEST_SEASONS = [
    ("2022-11-15", "2023-05-31"),  # 가장 깔끔한 정상 수확기 (황백화 기록 없음)
    ("2021-11-01", "2021-12-31"),  # GOCI-II 초기 데이터 (보조)
]

# GOCI-II slot 번호
SLOT_KOREA = 2


class KOSCCollector:
    """KOSC GOCI-II 데이터 수집기 (OPeNDAP + cloud masking)"""

    META_API    = "http://nosc.go.kr/openapi/meta/search.do"
    OPENDAP_BASE = "http://nosc.go.kr/opendap/hyrax/GOCI-II"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("KOSC_API_KEY", "")
        if not self.api_key:
            logger.warning("KOSC_API_KEY 없음 — OPeNDAP 직접 접근만 가능")

    # ------------------------------------------------------------------ #
    # 카탈로그: 가용 관측 시각 목록
    # ------------------------------------------------------------------ #
    def list_timestamps(self, date: str) -> list[str]:
        """
        특정 날짜의 GOCI-II 가용 관측 시각 목록 반환.
        date: "YYYYMMDD" → ["001530", "011530", ...] (UTC)
        """
        yyyy, mm, dd = date[:4], date[4:6], date[6:]
        url = f"{self.OPENDAP_BASE}/{yyyy}/{mm}/{dd}/L2/catalog.xml"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            refs = root.findall(
                ".//{http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0}catalogRef"
            )
            timestamps = []
            for r in refs:
                name = r.attrib.get("{http://www.w3.org/1999/xlink}title", "")
                if name.startswith(f"GK2_GC2_L2_{date}_"):
                    timestamps.append(name.split("_")[-1])
            return sorted(timestamps)
        except Exception as e:
            logger.warning(f"카탈로그 조회 실패 ({date}): {e}")
            # 한국 낮 시간대 기본값 (UTC 00~08시 = KST 09~17시)
            return ["001530", "021530", "041530", "061530", "081530"]

    # 슬롯별 커버리지 (카탈로그+DAS 직접 확인)
    # 001530 UTC: S000~S005 (일본·동중국해 권역)
    # 031530+ UTC: S000~S011 확장, S007이 서해안 포함
    # S007: lat 30.7~39.3, lon 122.0~130.4 → 한국 서해안 완전 포함
    KOREA_SLOT = "S007"
    KOREA_SLOT_MIN_HOUR = "03"  # UTC 03시 이후 S007 슬롯 활성화

    def _opendap_url(self, date: str, hour: str, slot: str = None) -> str:
        """
        OPeNDAP URL 조립 (카탈로그 직접 확인한 실제 경로).
        slot 미지정 시 시각에 따라 자동 선택.
        """
        slot = slot or (self.KOREA_SLOT if hour[:2] >= self.KOREA_SLOT_MIN_HOUR else "S004")
        yyyy, mm, dd = date[:4], date[4:6], date[6:]
        folder   = f"GK2_GC2_L2_{date}_{hour}"
        filename = f"GK2B_GOCI2_L2_{date}_{hour}_LA_{slot}_AC.nc"
        return f"{self.OPENDAP_BASE}/{yyyy}/{mm}/{dd}/L2/{folder}/{filename}"

    # ------------------------------------------------------------------ #
    # Cloud Masking + Chl-a / NIR 지수 계산
    # ------------------------------------------------------------------ #
    @staticmethod
    def _compute_chl_oc3(b443: np.ndarray, b490: np.ndarray, b555: np.ndarray) -> np.ndarray:
        """
        OC3 알고리즘으로 Chl-a 계산. (O'Reilly et al. 2019)
        ACR_REF 밴드 비율은 Rrs 비율과 동일하므로 OC3 적용 가능.
        """
        with np.errstate(divide="ignore", invalid="ignore"):
            denom = np.where(b555 > 0, b555, np.nan)
            R = np.log10(np.maximum(b443, b490) / denom)
            chl = 10 ** (0.2424 - 2.7423*R + 1.8017*R**2 + 0.0015*R**3 - 1.2280*R**4)
        return np.where(np.isfinite(chl) & (chl > 0) & (chl < 200), chl, np.nan)

    @staticmethod
    def _compute_nir_index(b865: np.ndarray, b555: np.ndarray) -> np.ndarray:
        """
        NIR 지수: B865 / B555 비율.
        황백화·부유물질 증가 시 NIR 반사도 상승.
        """
        with np.errstate(divide="ignore", invalid="ignore"):
            nir = b865 / np.where(b555 > 0, b555, np.nan)
        return np.where(np.isfinite(nir), nir, np.nan)

    def _download_nc(self, date: str, hour: str, suffix: str = "ACR") -> Optional[str]:
        """
        ACR.nc(11MB) 직접 다운로드 → 임시 파일 경로 반환.
        suffix: "ACR"(경량 반사도) | "AC"(전체 산출물, 300MB+)
        """
        import tempfile
        slot = self.KOREA_SLOT if hour[:2] >= self.KOREA_SLOT_MIN_HOUR else "S004"
        yyyy, mm, dd = date[:4], date[4:6], date[6:]
        folder   = f"GK2_GC2_L2_{date}_{hour}"
        filename = f"GK2B_GOCI2_L2_{date}_{hour}_LA_{slot}_{suffix}.nc"
        url = f"{self.OPENDAP_BASE}/{yyyy}/{mm}/{dd}/L2/{folder}/{filename}"
        try:
            resp = requests.get(url, timeout=60, stream=True)
            if resp.status_code != 200:
                logger.debug(f"HTTP {resp.status_code}: {url}")
                return None
            with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as f:
                for chunk in resp.iter_content(chunk_size=512 * 1024):
                    f.write(chunk)
                return f.name
        except Exception as e:
            logger.debug(f"다운로드 실패 ({date} {hour}): {e}")
            return None

    def _apply_cloud_mask(self, flag: np.ndarray) -> np.ndarray:
        """flag 배열 → 맑은 픽셀 bool 마스크 (True = 맑음)"""
        clear = (flag & BAD_PIXEL_MASK) == 0
        pct = clear.mean() * 100
        logger.debug(f"cloud mask: 맑은 픽셀 {pct:.1f}%")
        return clear

    def _load_ac_pydap(self, date: str, hour: str) -> Optional[dict]:
        """
        AC.nc (신 포맷, 2024-09~) pydap OPeNDAP 원격 접근.
        저해상도 lat/lon(stride=50)으로 ROI 경계 찾고 해당 슬라이스만 다운.
        전체 파일(380MB) 다운 없이 ~22MB만 사용.
        """
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning)
        try:
            from pydap.client import open_url
        except ImportError:
            logger.debug("pydap 미설치 — AC.nc 접근 불가")
            return None

        slot   = self.KOREA_SLOT if hour[:2] >= self.KOREA_SLOT_MIN_HOUR else "S004"
        yyyy, mm, dd = date[:4], date[4:6], date[6:]
        folder = f"GK2_GC2_L2_{date}_{hour}"
        fname  = f"GK2B_GOCI2_L2_{date}_{hour}_LA_{slot}_AC.nc"
        url    = f"{self.OPENDAP_BASE}/{yyyy}/{mm}/{dd}/L2/{folder}/{fname}"

        STRIDE = 50
        FILL   = -100.0  # fill value threshold (실제값은 -999)

        try:
            ds = open_url(url)

            # 1) 저해상도 lat/lon → ROI 경계 탐지
            lat_lr = np.array(ds["/navigation_data/latitude"][::STRIDE, ::STRIDE].data)
            lon_lr = np.array(ds["/navigation_data/longitude"][::STRIDE, ::STRIDE].data)
            rows, cols = np.where(
                (lat_lr >= ROI["lat_min"]) & (lat_lr <= ROI["lat_max"]) &
                (lon_lr >= ROI["lon_min"]) & (lon_lr <= ROI["lon_max"])
            )
            if len(rows) == 0:
                logger.debug(f"{date} {hour}: AC.nc ROI 영역 없음")
                return None

            H_full = lat_lr.shape[0] * STRIDE
            W_full = lat_lr.shape[1] * STRIDE
            r0 = max(0, rows.min() * STRIDE - STRIDE)
            r1 = min(H_full, rows.max() * STRIDE + STRIDE)
            c0 = max(0, cols.min() * STRIDE - STRIDE)
            c1 = min(W_full, cols.max() * STRIDE + STRIDE)

            # 2) ROI 슬라이스만 다운로드
            lat  = np.array(ds["/navigation_data/latitude"][r0:r1, c0:c1].data)
            lon  = np.array(ds["/navigation_data/longitude"][r0:r1, c0:c1].data)
            flag = np.array(ds["/geophysical_data/flag"][r0:r1, c0:c1].data)
            b443 = np.array(ds["/geophysical_data/Rrs/Rrs_443"][r0:r1, c0:c1].data, dtype=float)
            b490 = np.array(ds["/geophysical_data/Rrs/Rrs_490"][r0:r1, c0:c1].data, dtype=float)
            b555 = np.array(ds["/geophysical_data/Rrs/Rrs_555"][r0:r1, c0:c1].data, dtype=float)
            b865 = np.array(ds["/geophysical_data/Rrs/Rrs_865"][r0:r1, c0:c1].data, dtype=float)

            # fill value → NaN
            for arr in (b443, b490, b555, b865):
                arr[arr < FILL] = np.nan

            roi   = ((lat >= ROI["lat_min"]) & (lat <= ROI["lat_max"]) &
                     (lon >= ROI["lon_min"]) & (lon <= ROI["lon_max"]))
            clear = self._apply_cloud_mask(flag.astype(np.int32)) & roi

            roi_size    = int(roi.sum())
            clear_ratio = float(clear.sum()) / max(1, roi_size)
            if clear_ratio < 0.003:
                logger.debug(f"{date} {hour}: 맑은 ROI 픽셀 0.3% 미만 ({clear_ratio:.1%})")
                return None

            chl = self._compute_chl_oc3(b443, b490, b555)
            nir = self._compute_nir_index(b865, b555)

            idx = np.where(clear & np.isfinite(chl))
            if len(idx[0]) == 0:
                return None

            return {
                "lat":         lat[idx],
                "lon":         lon[idx],
                "chl_a":       chl[idx],
                "nir_idx":     nir[idx],
                "clear_ratio": clear_ratio,
                "datetime":    f"{date}T{hour[:2]}:{hour[2:4]}Z",
            }
        except Exception as e:
            logger.debug(f"pydap AC.nc 실패 ({date} {hour}): {e}")
            return None

    def _parse_bands(self, ds, fmt: str) -> tuple:
        """
        포맷별 밴드 변수 추출.
        fmt="ACR": geophysical_data/ACR_REF_BAND_XXX (구 포맷, ~2024-05)
        fmt="AC" : geophysical_data/Rrs/Rrs_XXX      (신 포맷,  2024-09~)
        반환: (b443, b490, b555, b865, flag, lat, lon)
        """
        nav  = ds.groups["navigation_data"]
        geo  = ds.groups["geophysical_data"]
        lat  = nav.variables["latitude"][:]
        lon  = nav.variables["longitude"][:]
        flag = geo.variables["flag"][:]
        if fmt == "ACR":
            b443 = geo.variables["ACR_REF_BAND_443"][:]
            b490 = geo.variables["ACR_REF_BAND_490"][:]
            b555 = geo.variables["ACR_REF_BAND_555"][:]
            b865 = geo.variables["ACR_REF_BAND_865"][:]
        else:  # AC — Rrs nested group
            rrs  = geo.groups["Rrs"]
            b443 = rrs.variables["Rrs_443"][:]
            b490 = rrs.variables["Rrs_490"][:]
            b555 = rrs.variables["Rrs_555"][:]
            b865 = rrs.variables["Rrs_865"][:]
        return b443, b490, b555, b865, flag, lat, lon

    def _load_single_obs(self, date: str, hour: str) -> Optional[dict]:
        """
        ACR.nc(구 포맷) 다운로드 시도 → 실패 시 AC.nc OPeNDAP 원격 스트리밍(신 포맷).
        cloud mask → ROI → Chl-a/NIR 계산.
        반환: {"lat", "chl_a", "nir_idx", "clear_ratio", "datetime"} dict
        """
        import netCDF4 as nc4, os

        ds   = None
        fmt  = None
        tmp  = None

        # 1) ACR.nc 다운로드 시도 (구 포맷, 11MB)
        tmp = self._download_nc(date, hour, suffix="ACR")
        if tmp is not None:
            try:
                ds  = nc4.Dataset(tmp)
                fmt = "ACR"
            except Exception as e:
                logger.debug(f"ACR.nc 파싱 실패 ({date} {hour}): {e}")
                try: os.unlink(tmp)
                except: pass
                tmp = None

        # 2) AC.nc pydap 원격 접근 (신 포맷, 2024-09~, ROI 슬라이스만 다운)
        if ds is None:
            return self._load_ac_pydap(date, hour)

        try:
            b443, b490, b555, b865, flag, lat, lon = self._parse_bands(ds, fmt)
            ds.close()

            roi   = ((lat >= ROI["lat_min"]) & (lat <= ROI["lat_max"])
                     & (lon >= ROI["lon_min"]) & (lon <= ROI["lon_max"]))
            clear = self._apply_cloud_mask(np.array(flag)) & roi

            roi_size    = int(roi.sum())
            clear_ratio = float(clear.sum()) / max(1, roi_size)
            if clear_ratio < 0.003:
                logger.debug(f"{date} {hour}: 맑은 ROI 픽셀 0.3% 미만 스킵 ({clear_ratio:.1%})")
                return None

            chl = self._compute_chl_oc3(
                np.array(b443, float), np.array(b490, float), np.array(b555, float)
            )
            nir = self._compute_nir_index(np.array(b865, float), np.array(b555, float))

            idx = np.where(clear & np.isfinite(chl))
            if len(idx[0]) == 0:
                return None

            return {
                "lat":         np.array(lat)[idx],
                "lon":         np.array(lon)[idx],
                "chl_a":       chl[idx],
                "nir_idx":     nir[idx],
                "clear_ratio": clear_ratio,
                "datetime":    f"{date}T{hour[:2]}:{hour[2:4]}Z",
            }
        except Exception as e:
            logger.warning(f"파싱 실패 ({date} {hour}, fmt={fmt}): {e}")
            return None
        finally:
            if tmp:
                try: os.unlink(tmp)
                except: pass

    # ------------------------------------------------------------------ #
    # 일별 Cloud-Free Composite
    # ------------------------------------------------------------------ #
    def build_daily_composite(
        self,
        date: str,
        min_clear_ratio: float = 0.1,
    ) -> Optional[pd.DataFrame]:
        """
        하루 10장 관측을 합성해 픽셀별 cloud-free composite 생성.

        전략: 각 픽셀에서 맑은 관측 중 낮 시간대 중앙값 사용.
              중앙값은 이상값에 강건하고 황백화 지수 왜곡을 줄임.

        min_clear_ratio: 해당 날짜를 사용할 최소 맑은 픽셀 비율
                         (전체 ROI 기준, 이 미만이면 None 반환)
        """
        timestamps = self.list_timestamps(date)
        # S007(서해안) 슬롯은 UTC 03시 이후에만 활성화
        day_timestamps = [t for t in timestamps if "03" <= t[:2] <= "08"]
        if not day_timestamps:
            day_timestamps = timestamps  # 없으면 전체 사용

        logger.info(f"{date}: {len(day_timestamps)}개 관측 시각 합성 시작")

        obs_list = []
        for hour in day_timestamps:
            obs = self._load_single_obs(date, hour)
            if obs and obs["clear_ratio"] >= 0.003:
                obs_list.append(obs)
                logger.debug(f"  {hour}: 맑은 픽셀 {obs['clear_ratio']:.1%}, {len(obs['lat'])}개")
            time.sleep(0.3)

        if not obs_list:
            logger.warning(f"{date}: 맑은 관측 없음")
            return None

        # 모든 관측 합치기 → (lat,lon) 격자별 중앙값
        all_lats = np.concatenate([o["lat"] for o in obs_list])
        all_lons = np.concatenate([o["lon"] for o in obs_list])
        all_chl  = np.concatenate([o["chl_a"] for o in obs_list])
        all_nir  = np.concatenate([o["nir_idx"] for o in obs_list])

        df_all = pd.DataFrame({
            "lat": np.round(all_lats, 2),   # 0.01° 격자로 빈닝
            "lon": np.round(all_lons, 2),
            "chl_a":   all_chl,
            "nir_idx": all_nir,
        }).dropna(subset=["chl_a"])

        if df_all.empty:
            return None

        # 격자별 중앙값 합성
        df_comp = (
            df_all.groupby(["lat", "lon"])
            .median(numeric_only=True)
            .reset_index()
        )

        n_clear = len(df_comp)
        logger.info(f"{date}: 합성 완료 ({n_clear}개 격자 픽셀)")
        if n_clear < 10:
            logger.warning(f"{date}: 격자 픽셀 {n_clear}개 — min_clear_ratio 미달")
            return None

        df_comp["date"] = pd.to_datetime(date, format="%Y%m%d")
        df_comp["composite_method"] = "daily_median"
        return df_comp

    # ------------------------------------------------------------------ #
    # 단일 관측 (빠른 수집용)
    # ------------------------------------------------------------------ #
    def fetch_chl_fai(
        self,
        date: str,
        hour: Optional[str] = None,
        use_composite: bool = True,
    ) -> Optional[pd.DataFrame]:
        """
        Chl-a + FAI DataFrame 반환.
        use_composite=True(기본): 일별 cloud-free composite 생성
        use_composite=False: 단일 관측 시각만 가져옴 (빠름)
        """
        if use_composite:
            return self.build_daily_composite(date)

        # 단일 관측 모드
        if hour is None:
            timestamps = self.list_timestamps(date)
            hour = next(
                (t for t in timestamps if "03" <= t[:2] <= "06"),
                timestamps[0] if timestamps else "041530"
            )
            logger.info(f"{date} 단일 관측 시각: {hour}")

        obs = self._load_single_obs(date, hour)
        if obs is None:
            return None

        df = pd.DataFrame({k: obs[k] for k in ("lat", "lon", "chl_a", "nir_idx")})
        df["date"] = pd.to_datetime(date, format="%Y%m%d")
        df["composite_method"] = "single_obs"
        return df.dropna(subset=["chl_a"])

    # ------------------------------------------------------------------ #
    # 날짜 → 4단계 라벨 결정
    # ------------------------------------------------------------------ #
    @staticmethod
    def label_for_date(date: datetime) -> int:
        """
        김 생육 캘린더 + 황백화 이벤트 이력 기반 4단계 라벨 반환.

        반환값:
          LABEL_NORMAL (0) : 정상 수확기
          LABEL_WATCH  (1) : 황백화 초기/주의 (이벤트 0~4주)
          LABEL_ACTIVE (2) : 황백화 활성     (이벤트 4~10주)
          LABEL_SEVERE (3) : 황백화 심화     (이벤트 10주+)
          LABEL_IGNORE (-1): 비수확기·채묘기·전이 buffer
        """
        month = date.month

        # 비수확기 / 채묘기 → 무조건 ignore
        if month in OFF_MONTHS or month in SEEDING_MONTHS:
            return LABEL_IGNORE

        # 황백화 이벤트 체크
        for event in HWANGBAEK_EVENTS:
            ev_start = datetime.strptime(event["start"], "%Y-%m-%d")
            ev_end   = datetime.strptime(event["end"],   "%Y-%m-%d")
            pre_buf  = ev_start - timedelta(days=PRE_EVENT_BUFFER_DAYS)
            post_buf = ev_end   + timedelta(days=POST_EVENT_BUFFER_DAYS)

            if pre_buf <= date < ev_start:
                return LABEL_IGNORE  # 이벤트 직전 전이 구간
            if ev_end < date <= post_buf:
                return LABEL_IGNORE  # 이벤트 직후 회복 구간
            if ev_start <= date <= ev_end:
                weeks = (date - ev_start).days / 7
                if weeks < WATCH_END_WEEKS:
                    return LABEL_WATCH
                elif weeks < ACTIVE_END_WEEKS:
                    return LABEL_ACTIVE
                else:
                    return LABEL_SEVERE

        # 수확기이고 어떤 이벤트에도 해당 안 됨 → 정상
        return LABEL_NORMAL

    @staticmethod
    def label_from_chl(date: datetime, chl_a: float) -> int:
        """
        이벤트 기간 + Chl-a 실측값 기반 라벨 결정.

        이벤트 기간 밖 수확기  → LABEL_NORMAL (0)
        비수확기·채묘기        → LABEL_IGNORE (-1)
        이벤트 전후 buffer     → LABEL_IGNORE (-1)
        이벤트 기간 내         → Chl-a 임계값으로 단계 결정
        """
        month = date.month
        if month in OFF_MONTHS or month in SEEDING_MONTHS:
            return LABEL_IGNORE

        for event in HWANGBAEK_EVENTS:
            ev_start = datetime.strptime(event["start"], "%Y-%m-%d")
            ev_end   = datetime.strptime(event["end"],   "%Y-%m-%d")
            pre_buf  = ev_start - timedelta(days=PRE_EVENT_BUFFER_DAYS)
            post_buf = ev_end   + timedelta(days=POST_EVENT_BUFFER_DAYS)

            if pre_buf <= date < ev_start or ev_end < date <= post_buf:
                return LABEL_IGNORE
            if ev_start <= date <= ev_end:
                if np.isnan(chl_a):
                    return LABEL_IGNORE
                if chl_a < CHL_THRESH_SEVERE:
                    return LABEL_SEVERE
                elif chl_a < CHL_THRESH_ACTIVE:
                    return LABEL_ACTIVE
                elif chl_a < CHL_THRESH_WATCH:
                    return LABEL_WATCH
                else:
                    return LABEL_NORMAL

        return LABEL_NORMAL

    # ------------------------------------------------------------------ #
    # 발생 이력 기반 라벨 데이터 수집
    # ------------------------------------------------------------------ #
    def collect_labeled_dataset(
        self,
        days_per_event: int = 30,
        normal_ratio: float = 2.0,
        use_composite: bool = True,
    ) -> pd.DataFrame:
        """
        황백화 발생 이력 기반 4단계 라벨링 데이터셋 수집.

        label:
          0 = 정상, 1 = 주의(초기), 2 = 활성, 3 = 심화
          -1(ignore)은 수집 대상에서 제외됨

        days_per_event: 이벤트당 최대 수집 일수 (5일 간격)
        normal_ratio:   정상:황백화(1~3) 행 수 비율
        use_composite:  True면 일별 cloud-free composite 사용
        """
        records = []

        for event in HWANGBAEK_EVENTS:
            start = datetime.strptime(event["start"], "%Y-%m-%d")
            end   = datetime.strptime(event["end"],   "%Y-%m-%d")
            dates = pd.date_range(start, end, freq="5D")[:days_per_event]

            logger.info(f"황백화 이벤트: {event['start']} ~ {event['end']}")
            for d in dates:
                label = self.label_for_date(d.to_pydatetime())
                if label == LABEL_IGNORE:
                    logger.debug(f"  {d.date()} ignore (전이 구간)")
                    continue
                date_str = d.strftime("%Y%m%d")
                df = self.fetch_chl_fai(date_str, use_composite=use_composite)
                if df is not None:
                    df["label"] = label
                    df["event_region"] = ", ".join(event["regions"])
                    records.append(df)
                time.sleep(0.5)

        hwang_rows = sum(len(r) for r in records)
        logger.info(f"황백화 샘플(label 1~3): {hwang_rows}행")

        normal_dates = self._sample_normal_dates(int(hwang_rows * normal_ratio) // 50)
        for d in normal_dates:
            df = self.fetch_chl_fai(d, use_composite=use_composite)
            if df is not None:
                df["label"] = LABEL_NORMAL
                df["event_region"] = "none"
                records.append(df)
            time.sleep(0.5)

        if not records:
            logger.error("수집된 데이터 없음")
            return pd.DataFrame()

        result = pd.concat(records, ignore_index=True)
        result = result[result["label"] >= 0].copy()

        label_names = {0: "정상", 1: "주의", 2: "활성", 3: "심화"}
        for lv, name in label_names.items():
            cnt = (result["label"] == lv).sum()
            logger.info(f"  label={lv} ({name}): {cnt:,}행")
        return result

    def _sample_normal_dates(self, n: int) -> list[str]:
        """
        수확기(11~5월) 중 황백화 없는 기간에서 월별 균등 quota 샘플링.
        챗또리 권고: 연도·월 편중 방지.
        """
        # 후보 날짜 생성 (5일 간격)
        all_dates: list[datetime] = []
        for s, e in NORMAL_HARVEST_SEASONS:
            all_dates.extend(pd.date_range(s, e, freq="5D").to_pydatetime().tolist())

        # 황백화 이벤트 + buffer와 겹치는 날짜 제거
        def _is_safe(d: datetime) -> bool:
            for event in HWANGBAEK_EVENTS:
                ev_start = datetime.strptime(event["start"], "%Y-%m-%d") - timedelta(days=PRE_EVENT_BUFFER_DAYS)
                ev_end   = datetime.strptime(event["end"],   "%Y-%m-%d") + timedelta(days=POST_EVENT_BUFFER_DAYS)
                if ev_start <= d <= ev_end:
                    return False
            return True

        safe_dates = [d for d in all_dates if _is_safe(d)]

        # 월별 bucket으로 균등 분배
        by_month: dict[int, list[str]] = defaultdict(list)
        for d in safe_dates:
            by_month[d.month].append(d.strftime("%Y%m%d"))

        rng = np.random.RandomState(42)
        n_months = len(by_month)
        per_month = max(1, n // n_months) if n_months else 1

        result: list[str] = []
        for month_dates in by_month.values():
            chosen = rng.choice(
                month_dates,
                size=min(per_month, len(month_dates)),
                replace=False,
            )
            result.extend(chosen.tolist())

        rng.shuffle(result)
        return result[:n]

    # ------------------------------------------------------------------ #
    # REST API
    # ------------------------------------------------------------------ #
    def fetch_meta(self, date: str, slot: int = SLOT_KOREA) -> list[dict]:
        params = {
            "ServiceKey": self.api_key,
            "startDate":  date,
            "endDate":    date,
            "slot":       slot,
            "ResultType": "json",
        }
        try:
            resp = requests.get(self.META_API, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception as e:
            logger.error(f"메타 API 실패 ({date}): {e}")
            return []


# ------------------------------------------------------------------ #
# 테스트
# ------------------------------------------------------------------ #
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    collector = KOSCCollector()

    print("=== 4단계 라벨 검증 ===")
    test_cases = [
        ("2023-07-15", "비수확기(ignore 예상)"),
        ("2023-10-01", "채묘기(ignore 예상)"),
        ("2022-12-01", "정상 수확기(0 예상)"),
        ("2023-11-05", "황백화 초기 WATCH(1 예상)"),
        ("2023-12-10", "황백화 활성 ACTIVE(2 예상)"),
        ("2024-01-20", "황백화 심화 SEVERE(3 예상)"),
        ("2023-10-20", "이벤트 전 buffer(ignore 예상)"),
    ]
    label_names = {LABEL_NORMAL: "정상(0)", LABEL_WATCH: "주의(1)",
                   LABEL_ACTIVE: "활성(2)", LABEL_SEVERE: "심화(3)", LABEL_IGNORE: "ignore(-1)"}
    for date_str, desc in test_cases:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        lv = KOSCCollector.label_for_date(d)
        print(f"  {date_str}  {label_names[lv]:12s}  ← {desc}")

    print("\n=== composite 테스트 (정상 수확기) ===")
    df_comp = collector.build_daily_composite("20221201")
    if df_comp is not None:
        print(f"합성: {len(df_comp)}px | Chl-a median={df_comp['chl_a'].median():.3f}")
    else:
        print("합성 실패 (구름 덮임)")

    print("\n=== 정상 날짜 월별 분포 확인 ===")
    sample_dates = collector._sample_normal_dates(30)
    from collections import Counter
    month_dist = Counter(d[4:6] for d in sample_dates)
    for m, cnt in sorted(month_dist.items()):
        print(f"  {m}월: {cnt}개")
