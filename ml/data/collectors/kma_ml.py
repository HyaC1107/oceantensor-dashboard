"""KMA 기상청 수집기 — ML 전용 (DB 없음, DataFrame 반환).

ASOS 일별: 강수량, 풍속, 풍향, 기온
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from urllib.parse import quote

import httpx
import pandas as pd

KMA_DAILY_URL = "https://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"

# 서해안 김 양식 지역 주요 ASOS 관측소 (station_id → (lat, lon, name))
ASOS_STATIONS: dict[str, tuple[float, float, str]] = {
    "156": (35.17, 126.89, "광주"),
    "165": (34.82, 126.38, "목포"),
    "170": (34.39, 126.70, "완도"),
    "232": (36.75, 126.30, "태안"),
    "236": (36.33, 126.55, "보령"),
    "243": (35.73, 126.72, "부안"),
    "245": (35.82, 127.15, "전주"),
    "261": (34.48, 126.27, "진도"),
    "268": (34.68, 126.91, "장흥"),
    "277": (34.76, 127.66, "여수"),
    "289": (35.28, 126.51, "영광"),
}

DEFAULT_STATIONS = ",".join(ASOS_STATIONS.keys())


def _safe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_kma_df(days: int = 365, api_key: str | None = None,
                 start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
    """KMA ASOS 일별 → DataFrame (관측소별 개별 요청).

    Columns: date, lat, lon, station_id, station_name,
             precipitation_mm, avg_wind_speed, wind_dir_deg, avg_temp,
             solar_radiation_mjm2
    """
    key = api_key or os.getenv("ServiceKey", "")
    if not key:
        print("[kma_ml] API 키 없음 — 빈 DataFrame 반환")
        return pd.DataFrame()

    end_dt   = datetime.fromisoformat(end_date)   if end_date   else datetime.now() - timedelta(days=1)
    start_dt = datetime.fromisoformat(start_date) if start_date else end_dt - timedelta(days=days - 1)

    # KMA API numOfRows 상한 우회 — 365일 청크로 분할
    CHUNK_DAYS = 365
    chunks: list[tuple[datetime, datetime]] = []
    chunk_s = start_dt
    while chunk_s <= end_dt:
        chunk_e = min(chunk_s + timedelta(days=CHUNK_DAYS - 1), end_dt)
        chunks.append((chunk_s, chunk_e))
        chunk_s = chunk_e + timedelta(days=1)

    all_rows = []

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for chunk_start, chunk_end in chunks:
            chunk_len = (chunk_end - chunk_start).days + 1
            for stn_id, coords in ASOS_STATIONS.items():
                params = {
                    "pageNo":    1,
                    "numOfRows": min(chunk_len + 5, 999),
                    "dataType":  "JSON",
                    "dataCd":    "ASOS",
                    "dateCd":    "DAY",
                    "startDt":   chunk_start.strftime("%Y%m%d"),
                    "endDt":     chunk_end.strftime("%Y%m%d"),
                    "stnIds":    stn_id,
                }
                qs = "&".join(f"{k}={v}" for k, v in params.items())
                qs += "&serviceKey=" + quote(key, safe="")

                try:
                    resp = client.get(f"{KMA_DAILY_URL}?{qs}")
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    print(f"[kma_ml] 관측소 {stn_id} {chunk_start.date()} 요청 실패: {e}")
                    continue

                items = (
                    data.get("response", {})
                    .get("body", {})
                    .get("items", {})
                    .get("item", [])
                )
                if isinstance(items, dict):
                    items = [items]

                for item in items:
                    raw_date = item.get("tm", "")
                    try:
                        obs_date = datetime.strptime(str(raw_date).strip(), "%Y-%m-%d")
                    except ValueError:
                        continue

                    wd_str = str(item.get("maxWd") or item.get("avgWd") or "")
                    wind_dir = _wind_str_to_deg(wd_str)

                    all_rows.append({
                        "date":             obs_date,
                        "lat":              coords[0],
                        "lon":              coords[1],
                        "station_id":       stn_id,
                        "station_name":     coords[2],
                        "precipitation_mm":      _safe_float(item.get("sumRn")) or 0.0,
                        "avg_wind_speed":        _safe_float(item.get("avgWs")),
                        "wind_dir_deg":          wind_dir,
                        "avg_temp":              _safe_float(item.get("avgTa")),
                        "solar_radiation_mjm2":  _safe_float(item.get("sumGsr")),
                    })

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _wind_str_to_deg(wd: str) -> float | None:
    mapping = {
        "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5,
        "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
        "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5,
        "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
        "북": 0, "북북동": 22.5, "북동": 45, "동북동": 67.5,
        "동": 90, "동남동": 112.5, "남동": 135, "남남동": 157.5,
        "남": 180, "남남서": 202.5, "남서": 225, "서남서": 247.5,
        "서": 270, "서북서": 292.5, "북서": 315, "북북서": 337.5,
    }
    v = mapping.get(wd.strip().upper()) or mapping.get(wd.strip())
    if v is not None:
        return float(v)
    return _safe_float(wd)
