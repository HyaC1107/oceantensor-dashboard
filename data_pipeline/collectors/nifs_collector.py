"""NIFS 국립수산과학원 수집기

- femoSeaList : 어장환경관측자료 (DIN/DIP/DO/염분/CHL — 핵심) 2~3개월 주기
- risaList    : 실시간어장정보 (수온 30분 주기)
"""
import httpx
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.config import settings
from app.db import AsyncSessionLocal
from app.models.sensor import OceanSensorRaw

NIFS_API_BASE = "https://www.nifs.go.kr/OpenAPI_json"

# 황백화 분석에 필요한 femoSeaList 수집 컬럼 (표층 기준)
FEMO_FIELD_MAP = {
    "TEMP_S":   "water_temp",
    "SAL_S":    "salinity",
    "DO_S":     "dissolved_oxygen",
    "NO3_N_S":  "no3_nitrogen",
    "NH4_N_S":  "nh4_nitrogen",
    "PH_S":     "ph",
}


# ──────────────────────────────────────────────
# femoSeaList  (어장환경관측 — DIN/DIP 핵심 데이터)
# ──────────────────────────────────────────────

async def fetch_femo_survey(days: int = 365) -> list[dict]:
    """어장환경관측자료 수집 (날짜 범위 필수)"""
    key = settings.nifs_api_key_femosealist
    if not key:
        raise ValueError("NIFS_API_KEY_femoSeaList 가 설정되지 않았습니다.")

    end = datetime.now()
    start = end - timedelta(days=days)
    params = {
        "id": "femoSeaList",
        "key": key,
        "sdate": start.strftime("%Y%m%d"),
        "edate": end.strftime("%Y%m%d"),
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(NIFS_API_BASE, params=params)
        resp.raise_for_status()
        data = resp.json()

    body = data.get("body") or data.get("Body") or data
    items = body.get("item") or data.get("Item") or []
    if isinstance(items, dict):
        items = [items]
    return items


def _parse_femo_item(item: dict) -> dict | None:
    """femoSeaList 항목 → OceanSensorRaw 저장용 dict"""
    try:
        year  = int(item.get("DATE_Y", 0))
        month = int(item.get("DATE_M", 0))
        day   = int(item.get("DATE_D", 0))
        hour  = int(item.get("TIME_H", 0))
        minute = int(item.get("TIME_I", 0))
        if not (year and month and day):
            return None
        obs_at = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None

    fishery  = item.get("FISHERY", "")
    loc_pt   = item.get("LOCATION_POINT", "")
    sensor_id = f"NIFS-FEMO-{fishery}-{loc_pt}".replace(" ", "_")

    row = {"sensor_id": sensor_id, "observed_at": obs_at, "raw_status": "raw"}
    for src_key, dst_key in FEMO_FIELD_MAP.items():
        row[dst_key] = _safe_float(item.get(src_key))
    return row


async def collect_femo_and_save(days: int = 365) -> int:
    """femoSeaList 수집 → ocean_sensor_raw 저장 (중복 제외)"""
    items = await fetch_femo_survey(days=days)
    if not items:
        return 0

    saved = 0
    async with AsyncSessionLocal() as session:
        for item in items:
            row = _parse_femo_item(item)
            if not row:
                continue

            exists = await session.execute(
                select(OceanSensorRaw).where(
                    OceanSensorRaw.sensor_id == row["sensor_id"],
                    OceanSensorRaw.observed_at == row["observed_at"],
                ).limit(1)
            )
            if exists.scalar_one_or_none():
                continue

            session.add(OceanSensorRaw(**row))
            saved += 1

        await session.commit()
    return saved


# ──────────────────────────────────────────────
# risaList  (실시간어장정보 — 수온 30분 주기)
# ──────────────────────────────────────────────

async def fetch_nifs_realtime() -> list[dict]:
    """실시간 수온 수집"""
    key = settings.nifs_api_key_risalist
    if not key:
        raise ValueError("NIFS_API_KEY_risaList 가 설정되지 않았습니다.")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(NIFS_API_BASE, params={"id": "risaList", "key": key})
        resp.raise_for_status()
        data = resp.json()

    body = data.get("body") or data.get("Body") or {}
    items = body.get("item") or data.get("Item") or []
    if isinstance(items, dict):
        items = [items]

    results = []
    for item in items:
        # repair_gbn == '1' : 정상 데이터
        if item.get("repair_gbn") != "1":
            continue
        obs_date = item.get("obs_dat", "")
        obs_time = item.get("obs_tim", "00:00:00")
        results.append({
            "sensor_id":         f"NIFS-RISA-{item.get('sta_cde', 'UNKNOWN')}",
            "observed_at":       _parse_dt(f"{obs_date} {obs_time[:5]}"),
            "water_temp":        _safe_float(item.get("wtr_tmp")),
            "dissolved_oxygen":  None,
            "salinity":          None,
        })
    return results


async def collect_and_save() -> int:
    """risaList 수온 수집 → ocean_sensor_raw 저장 (1시간 주기 스케줄러 연결)"""
    rows = await fetch_nifs_realtime()
    if not rows:
        return 0

    saved = 0
    async with AsyncSessionLocal() as session:
        for row in rows:
            if not row.get("observed_at"):
                continue

            exists = await session.execute(
                select(OceanSensorRaw).where(
                    OceanSensorRaw.sensor_id == row["sensor_id"],
                    OceanSensorRaw.observed_at == row["observed_at"],
                ).limit(1)
            )
            if exists.scalar_one_or_none():
                continue

            session.add(OceanSensorRaw(
                sensor_id=row["sensor_id"],
                observed_at=row["observed_at"],
                water_temp=row.get("water_temp"),
                dissolved_oxygen=row.get("dissolved_oxygen"),
                salinity=row.get("salinity"),
                raw_status="raw",
            ))
            saved += 1

        await session.commit()
    return saved


# ──────────────────────────────────────────────
# 공통 유틸
# ──────────────────────────────────────────────

def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y%m%d%H%M", "%Y%m%d"):
        try:
            return datetime.strptime(str(value).strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
