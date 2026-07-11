"""한강홍수통제소 표준수문DB 수집기 — ML 전용 (DB 없음, DataFrame 반환).

장흥댐(탐진강) 일별 방류량 — 강진만 담수 유입 주경로
API: https://api.hrfco.go.kr/{KEY}/dam/list/1D/{obscd}/{start}/{end}.json
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import httpx
import pandas as pd

_BASE_URL = "https://api.hrfco.go.kr"

# 장흥댐 (탐진강 → 강진만)
_DAMS: dict[str, tuple[float, float, str]] = {
    "5101110": (34.68, 126.91, "장흥댐"),
}

_MAX_DAYS_PER_CALL = 365  # 안전을 위해 연도별 쪼개기


def _safe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_kwater_df(
    days: int = 365,
    api_key: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """HRFCO 장흥댐 일별 방류량 DataFrame.

    Columns: date, lat, lon, station_name, discharge_m3s
    실패 시 빈 DataFrame 반환 (0값 채우기 금지).
    """
    key = api_key or os.getenv("HRFCO_API_KEY", "")
    if not key:
        print("[hrfco_ml] ⚠️ HRFCO_API_KEY 없음 — discharge 수집 건너뜀")
        return _empty_df()

    end_dt   = datetime.fromisoformat(end_date)   if end_date   else datetime.now() - timedelta(days=1)
    start_dt = datetime.fromisoformat(start_date) if start_date else end_dt - timedelta(days=days)

    all_rows: list[dict] = []

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for obscd, (lat, lon, name) in _DAMS.items():
            rows = _fetch_dam(client, key, obscd, lat, lon, name, start_dt, end_dt)
            all_rows.extend(rows)

    if not all_rows:
        print("[hrfco_ml] ⚠️ 모든 댐 수집 실패 — discharge 채널 NaN 처리됨")
        return _empty_df()

    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _fetch_dam(
    client: httpx.Client,
    key: str,
    obscd: str,
    lat: float,
    lon: float,
    name: str,
    start_dt: datetime,
    end_dt: datetime,
) -> list[dict]:
    """댐 한 곳 전체 기간 수집 (연도별 청크 분할)."""
    rows: list[dict] = []

    # 연도별로 쪼개기
    chunk_start = start_dt
    while chunk_start <= end_dt:
        chunk_end = min(chunk_start + timedelta(days=_MAX_DAYS_PER_CALL - 1), end_dt)
        url = (
            f"{_BASE_URL}/{key}/dam/list/1D/{obscd}"
            f"/{chunk_start.strftime('%Y%m%d')}/{chunk_end.strftime('%Y%m%d')}.json"
        )
        try:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[hrfco_ml] {name} {chunk_start.date()}~{chunk_end.date()} 요청 실패: {e}")
            chunk_start = chunk_end + timedelta(days=1)
            continue

        content = data.get("content", [])
        if not isinstance(content, list):
            chunk_start = chunk_end + timedelta(days=1)
            continue

        for item in content:
            raw_date = str(item.get("ymdhm", "")).strip()
            try:
                obs_date = datetime.strptime(raw_date[:8], "%Y%m%d")
            except (ValueError, TypeError):
                continue
            discharge = _safe_float(item.get("tototf"))  # 총방류량 m³/s
            if discharge is None:
                continue
            rows.append({
                "date":          obs_date,
                "lat":           lat,
                "lon":           lon,
                "station_name":  name,
                "discharge_m3s": discharge,
            })

        chunk_start = chunk_end + timedelta(days=1)

    if rows:
        print(f"[hrfco_ml] {name}: {len(rows)}건 수집")
    return rows


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["date", "lat", "lon", "station_name", "discharge_m3s"])
