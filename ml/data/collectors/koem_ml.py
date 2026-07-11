"""KOEM 해양환경공단 수집기 — ML 전용 (DB 없음, DataFrame 반환).

해양환경측정망: DIN, DIP, SiO2, DO, 염분, pH, 탁도, Chl-a
API: getOceansNemo2 (B553931/service/OceansNemoService2)
  - 데이터는 연도순 정렬, totalCount 역산해서 최신 페이지 접근
  - obsr_year/obsr_mt 파라미터 미지원 → 역방향 페이지네이션
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode

import httpx
import pandas as pd

KOEM_STN_URL = (
    "http://apis.data.go.kr/B553931/service"
    "/OceansNemoInfoService1/getOceansNemoInfo1"
)
KOEM_OBS_URL = (
    "http://apis.data.go.kr/B553931/service"
    "/OceansNemoService2/getOceansNemo2"
)

# 서해/남해 서부 해역코드
TARGET_OCEANS = {"서해", "남해"}

# API 필드 → 표준 필드명 매핑 (표층 기준)
OBS_FIELD_MAP = {
    "wtrtmp_sfclyr": "water_temp",
    "salnt_sfclyr":  "salinity",
    "doxy_sfclyr":   "dissolved_oxygen",
    "no3n_sfclyr":   "no3_nitrogen",
    "nh4n_sfclyr":   "nh4_nitrogen",
    "dip_sfclyr":    "dip",
    "slcacd_si_sfclyr": "sio2",
    "ph_dnsty_sfclyr":  "ph",
    "fltng_mttr_sfclyr": "turbidity",
    "clrpla_sfclyr":    "chlorophyll_a",
}


def _safe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fetch_stations(key: str) -> dict[str, tuple[float, float]]:
    """정점코드 → (lat, lon) 매핑 조회."""
    qs = f"pageNo=1&numOfRows=500&resultType=json&ServiceKey={quote(key, safe='')}"
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(f"{KOEM_STN_URL}?{qs}")
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        print(f"[koem_ml] 정점 마스터 실패: {e}")
        return {}

    inner = data.get("getOceansNemoInfo", {})
    items = inner.get("item", [])
    if isinstance(items, dict):
        items = [items]

    result = {}
    for item in items:
        code = item.get("stnpnt_code")
        lat  = _safe_float(item.get("lat"))
        lon  = _safe_float(item.get("lon"))
        if code and lat and lon:
            result[str(code)] = (lat, lon)
    return result


def _get_total_count(key: str) -> int:
    """getOceansNemo2 전체 건수 조회."""
    qs = f"pageNo=1&numOfRows=1&resultType=json&ServiceKey={quote(key, safe='')}"
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as c:
            r = c.get(f"{KOEM_OBS_URL}?{qs}")
            r.raise_for_status()
            data = r.json()
        return int(data.get("getOceansNemo", {}).get("totalCount", 0))
    except Exception:
        return 0


def fetch_koem_df(days: int = 365, api_key: str | None = None,
                  start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
    """KOEM 측정망 최신 days일 데이터 → DataFrame.

    Columns: date, lat, lon, station_code,
             water_temp, salinity, dissolved_oxygen, no3_nitrogen,
             nh4_nitrogen, dip, sio2, ph, turbidity, chlorophyll_a
    """
    key = api_key or os.getenv("ServiceKey", "")
    if not key:
        print("[koem_ml] API 키 없음 — 빈 DataFrame 반환")
        return pd.DataFrame()

    station_coords = _fetch_stations(key)

    total = _get_total_count(key)
    if total == 0:
        print("[koem_ml] totalCount=0 — 빈 DataFrame 반환")
        return pd.DataFrame()

    cutoff  = datetime.fromisoformat(start_date) if start_date else datetime.now() - timedelta(days=days)
    end_dt  = datetime.fromisoformat(end_date)   if end_date   else datetime.now()
    per_page = 1000

    all_rows: list[dict] = []
    last_page = (total + per_page - 1) // per_page

    # start_date 지정(과거 특정 기간) → 정방향(page 1→)
    # 미지정(최신 N일)              → 역방향(last_page→) 최대 20페이지
    if start_date:
        page_range = range(1, last_page + 1)
    else:
        page_range = range(last_page, max(0, last_page - 20), -1)

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for page in page_range:
            if page < 1:
                break
            params = {"pageNo": str(page), "numOfRows": str(per_page), "resultType": "json"}
            qs = urlencode(params) + "&ServiceKey=" + quote(key, safe="")
            try:
                resp = client.get(f"{KOEM_OBS_URL}?{qs}")
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"[koem_ml] 페이지 {page} 요청 실패: {e}")
                continue

            items = data.get("getOceansNemo", {}).get("item", [])
            if isinstance(items, dict):
                items = [items]
            if not items:
                break

            newest_in_page = None
            oldest_in_page = None
            for item in items:
                yr = item.get("obsr_year")
                mt = item.get("obsr_mt")
                if yr and mt:
                    try:
                        d = datetime(int(yr), int(mt), 1)
                        if newest_in_page is None or d > newest_in_page:
                            newest_in_page = d
                        if oldest_in_page is None or d < oldest_in_page:
                            oldest_in_page = d
                    except (ValueError, TypeError):
                        pass

            for item in items:
                if item.get("ocean_nm") not in TARGET_OCEANS:
                    continue
                yr = item.get("obsr_year")
                mt = item.get("obsr_mt")
                if not (yr and mt):
                    continue
                try:
                    obs_date = datetime(int(yr), int(mt), 15)
                except (ValueError, TypeError):
                    continue

                if obs_date < cutoff or obs_date > end_dt:
                    continue

                stn = str(item.get("stnpnt_code", "")).strip()
                coords = station_coords.get(stn)
                if coords is None:
                    continue

                row: dict = {
                    "date": obs_date,
                    "lat":  coords[0],
                    "lon":  coords[1],
                    "station_code": stn,
                }
                for src, dst in OBS_FIELD_MAP.items():
                    v = item.get(src)
                    if v is not None:
                        row[dst] = _safe_float(v)
                all_rows.append(row)

            # 정방향: 이 페이지 최신 날짜가 end_dt 초과 → 이후 페이지 불필요
            if start_date and newest_in_page and newest_in_page > end_dt:
                break
            # 역방향: 이 페이지 최고 날짜가 cutoff 이전 → 더 볼 필요 없음
            if not start_date and oldest_in_page and oldest_in_page < cutoff:
                break

    if not all_rows:
        print("[koem_ml] 기간 내 데이터 없음 — 빈 DataFrame 반환")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["date"])
    print(f"[koem_ml] 수집 완료: {len(df)}건, {df['date'].min()} ~ {df['date'].max()}")
    return df.sort_values("date").reset_index(drop=True)
