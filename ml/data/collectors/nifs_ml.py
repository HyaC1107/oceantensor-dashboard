"""NIFS 수집기 — ML 전용 (DB 없음, DataFrame 반환).

femoSeaList  : 어장환경관측 (DIN/DIP/DO/염분 — 분기 조사)
risaList     : 실시간수온 (30분 주기)
fetch_kodc_current_df : KODC 월평균 해류 (ROMS 기반, 1/12도)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx
import numpy as np
import pandas as pd

NIFS_BASE = "https://www.nifs.go.kr/OpenAPI_json"

# KODC 해양기후 평년자료 OPeNDAP (서해 월평균 해류, ROMS 기반)
# 실제 경로 확인 필요: https://kodc.nifs.go.kr 에서 '해양기후 평년자료 > 해류' 메뉴
KODC_CURRENT_URL = "https://kodc.nifs.go.kr/opendap/OcClimatol/MonthlyMean_UV.nc"

# 주요 어장 좌표 (fishery 이름 → (lat, lon))
# NIFS femoSeaList 응답의 FISHERY 필드 기반
FISHERY_COORDS: dict[str, tuple[float, float]] = {
    "완도":    (34.32, 126.76),
    "진도":    (34.48, 126.27),
    "해남":    (34.57, 126.60),
    "강진":    (34.64, 126.77),
    "장흥":    (34.68, 126.91),
    "고흥":    (34.60, 127.28),
    "보성":    (34.77, 127.08),
    "여수":    (34.76, 127.66),
    "부안":    (35.73, 126.72),
    "고창":    (35.43, 126.70),
    "신안":    (34.83, 126.10),
    "무안":    (34.99, 126.48),
    "영광":    (35.28, 126.51),
    "서산":    (36.78, 126.45),
    "태안":    (36.75, 126.30),
    "보령":    (36.33, 126.55),
    "홍성":    (36.60, 126.66),
    "당진":    (36.89, 126.63),
}

# NIFS 실시간어장정보 station → (lat, lon)
RISA_STATION_COORDS: dict[str, tuple[float, float]] = {
    "WANDO": (34.32, 126.76),
    "JINDO": (34.48, 126.27),
    "HAENAM": (34.57, 126.60),
    "BUAN":  (35.73, 126.72),
    "TAEAN": (36.75, 126.30),
    "BORYEONG": (36.33, 126.55),
    "SINAN": (34.83, 126.10),
}


def _safe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_nifs_df(days: int = 365, api_key: str | None = None,
                  start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
    """NIFS femoSeaList → DataFrame.

    Columns: date, lat, lon, water_temp, salinity, dissolved_oxygen,
             no3_nitrogen, nh4_nitrogen, ph
    date 컬럼은 UTC date (daily 기준).
    """
    key = api_key or os.getenv("NIFS_API_KEY_femoSeaList", "")
    if not key:
        print("[nifs_ml] API 키 없음 — 빈 DataFrame 반환")
        return pd.DataFrame()

    end   = datetime.fromisoformat(end_date)   if end_date   else datetime.now()
    start = datetime.fromisoformat(start_date) if start_date else end - timedelta(days=days)
    params = {
        "id": "femoSeaList",
        "key": key,
        "sdate": start.strftime("%Y%m%d"),
        "edate": end.strftime("%Y%m%d"),
    }

    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(NIFS_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        print(f"[nifs_ml] 요청 실패: {e}")
        return pd.DataFrame()

    body = data.get("body") or data.get("Body") or data
    items = body.get("item") or data.get("Item") or []
    if isinstance(items, dict):
        items = [items]

    rows = []
    for item in items:
        fishery = item.get("FISHERY", "").strip()
        coords = FISHERY_COORDS.get(fishery)
        if coords is None:
            # 부분 매칭 시도
            for k, v in FISHERY_COORDS.items():
                if k in fishery or fishery in k:
                    coords = v
                    break
        if coords is None:
            continue

        try:
            year  = int(item.get("DATE_Y", 0))
            month = int(item.get("DATE_M", 0))
            day   = int(item.get("DATE_D", 0))
            if not (year and month and day):
                continue
            obs_date = datetime(year, month, day, tzinfo=timezone.utc).date()
        except (ValueError, TypeError):
            continue

        rows.append({
            "date":             obs_date,
            "lat":              coords[0],
            "lon":              coords[1],
            "fishery":          fishery,
            "water_temp":       _safe_float(item.get("TEMP_S")),
            "salinity":         _safe_float(item.get("SAL_S")),
            "dissolved_oxygen": _safe_float(item.get("DO_S")),
            "no3_nitrogen":     _safe_float(item.get("NO3_N_S")),
            "nh4_nitrogen":     _safe_float(item.get("NH4_N_S")),
            "ph":               _safe_float(item.get("PH_S")),
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def fetch_kodc_current_df(
    local_nc: str | None = None,
    opendap_url: str = KODC_CURRENT_URL,
    roi_lat: tuple[float, float] = (33.0, 38.5),
    roi_lon: tuple[float, float] = (124.0, 130.0),
) -> pd.DataFrame:
    """KODC 해양기후 평년자료 — 서해 월평균 해류.

    ROMS 기반 1/12도 격자, 12개월 기후값.
    local_nc 경로를 우선 시도, 실패 시 opendap_url로 접근.

    Returns
    -------
    DataFrame with columns:
        month (int 1-12), lat, lon, current_u (m/s), current_v (m/s)
    date가 아닌 month 컬럼 — channel_builder에서 date.month로 조회.
    """
    try:
        import netCDF4 as nc_lib
    except ImportError:
        print("[nifs_ml] netCDF4 미설치 — `uv add netCDF4`")
        return pd.DataFrame()

    src = local_nc or opendap_url
    try:
        ds = nc_lib.Dataset(src)
    except Exception as e:
        print(f"[nifs_ml] KODC 접근 실패 ({src}): {e}")
        return pd.DataFrame()

    try:
        vars_ = list(ds.variables.keys())
        lat_key = next((k for k in ["lat", "latitude", "LAT", "Latitude"] if k in vars_), None)
        lon_key = next((k for k in ["lon", "longitude", "LON", "Longitude"] if k in vars_), None)
        u_key   = next((k for k in ["u", "U", "uo", "ucur", "u_curr"] if k in vars_), None)
        v_key   = next((k for k in ["v", "V", "vo", "vcur", "v_curr"] if k in vars_), None)

        if not all([lat_key, lon_key, u_key, v_key]):
            print(f"[nifs_ml] KODC 변수 매핑 실패. 가용 변수: {vars_}")
            ds.close()
            return pd.DataFrame()

        lats = np.array(ds.variables[lat_key][:])
        lons = np.array(ds.variables[lon_key][:])
        lat_mask = (lats >= roi_lat[0]) & (lats <= roi_lat[1])
        lon_mask = (lons >= roi_lon[0]) & (lons <= roi_lon[1])

        rows = []
        for month_idx in range(12):
            u_grid = np.ma.filled(ds.variables[u_key][month_idx], np.nan)
            v_grid = np.ma.filled(ds.variables[v_key][month_idx], np.nan)

            lat_idxs = np.where(lat_mask)[0]
            lon_idxs = np.where(lon_mask)[0]
            la_grid, lo_grid = np.meshgrid(lat_idxs, lon_idxs, indexing="ij")

            for i, j in zip(la_grid.ravel(), lo_grid.ravel()):
                u_val = float(u_grid[i, j])
                v_val = float(v_grid[i, j])
                if np.isnan(u_val) or np.isnan(v_val):
                    continue
                rows.append({
                    "month":     month_idx + 1,
                    "lat":       float(lats[i]),
                    "lon":       float(lons[j]),
                    "current_u": u_val,
                    "current_v": v_val,
                })
        ds.close()
    except Exception as e:
        print(f"[nifs_ml] KODC 파싱 오류: {e}")
        return pd.DataFrame()

    if not rows:
        print("[nifs_ml] KODC ROI 내 유효 픽셀 없음")
        return pd.DataFrame()

    print(f"[nifs_ml] KODC 해류 로드 완료: {len(rows)}포인트 × 12개월")
    return pd.DataFrame(rows)
