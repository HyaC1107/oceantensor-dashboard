"""NIFS 정선해양관측정보 (sooList) 수집기

정선해양관측: 동해/서해/남해/동중국해 정기 순회 관측
- 수온, 염분, 용존산소, 질산염, pH, 탁도, 좌표 포함
- sdate/edate 파라미터 필수 (없으면 에러코드 04)
- 관측 주기: 분기 1회 (계절별 조사)
"""
import httpx
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from geoalchemy2.elements import WKTElement
from app.config import settings
from app.db import AsyncSessionLocal
from app.models.sensor import OceanSensorRaw

NIFS_API_BASE = "https://www.nifs.go.kr/OpenAPI_json"

SOO_FIELD_MAP = {
    "wtr_tmp":    "water_temp",
    "sal":        "salinity",
    "dox":        "dissolved_oxygen",
    "nut_no3_n":  "no3_nitrogen",
    "nut_ph":     "ph",
    "wtr_trn":    "turbidity",
}


async def fetch_soo_survey(days: int = 365) -> list[dict]:
    """정선해양관측 수집 (날짜 범위 필수)"""
    key = settings.nifs_api_key_soolist
    if not key:
        raise ValueError("NIFS_API_KEY_sooList 가 설정되지 않았습니다.")

    end = datetime.now()
    start = end - timedelta(days=days)
    params = {
        "id": "sooList",
        "key": key,
        "sdate": start.strftime("%Y%m%d"),
        "edate": end.strftime("%Y%m%d"),
    }

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(NIFS_API_BASE, params=params)
        resp.raise_for_status()
        data = resp.json()

    body = data.get("body") or data.get("Body") or data
    items = body.get("item") or data.get("Item") or []
    if isinstance(items, dict):
        items = [items]
    return items


def _parse_soo_item(item: dict) -> dict | None:
    """sooList 항목 → OceanSensorRaw 저장용 dict"""
    obs_dtm = item.get("obs_dtm", "")
    obs_at = _parse_dt(obs_dtm)
    if not obs_at:
        return None

    sta_cde = item.get("sta_cde", "UNKNOWN")
    gru_nam = item.get("gru_nam", "")
    wtr_dep = item.get("wtr_dep", "")
    sensor_id = f"NIFS-SOO-{sta_cde}-{wtr_dep}m".replace(" ", "_")

    row: dict = {"sensor_id": sensor_id, "observed_at": obs_at, "raw_status": "raw"}

    for src_key, dst_key in SOO_FIELD_MAP.items():
        row[dst_key] = _safe_float(item.get(src_key))

    # 좌표 → PostGIS POINT
    try:
        lat = float(item.get("lat", "") or 0)
        lon = float(item.get("lon", "") or 0)
        if lat and lon:
            row["geom"] = WKTElement(f"POINT({lon} {lat})", srid=4326)
    except (TypeError, ValueError):
        pass

    return row


async def collect_soo_and_save(days: int = 365) -> int:
    """sooList 수집 → ocean_sensor_raw 저장 (중복 제외)"""
    items = await fetch_soo_survey(days=days)
    if not items:
        return 0

    saved = 0
    async with AsyncSessionLocal() as session:
        for item in items:
            row = _parse_soo_item(item)
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


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M", "%Y%m%d"):
        try:
            return datetime.strptime(str(value).strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
