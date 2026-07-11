"""KMA 기상청 ASOS 시간자료 수집기

강수량(시간별)은 황백화 상관관계 1위 변수.
endDt/endHh는 반드시 전날까지 (당일 자료 미제공).
"""
import httpx
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from sqlalchemy import select
from app.config import settings
from app.db import AsyncSessionLocal
from app.models.weather import AsosHourlyWeather

KMA_HOURLY_URL = "https://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList"

KEEP_FIELDS = {
    "tm":    "observed_at",
    "stnId": "station_id",
    "stnNm": "station_name",
    "rn":    "precipitation_mm",
    "ws":    "wind_speed",
    "wd":    "wind_direction",
    "ta":    "temperature",
    "hm":    "humidity",
    "pa":    "pressure",
}

DEFAULT_STN_IDS = "156"   # 광주 (진도 인근 대표 관측소)


async def fetch_kma_hourly(
    stn_ids: str = DEFAULT_STN_IDS,
    hours: int = 24,
) -> list[dict]:
    """KMA ASOS 시간별 기상 데이터 수집"""
    key = settings.service_key
    if not key:
        raise ValueError("ServiceKey 가 설정되지 않았습니다.")

    end_dt   = datetime.now() - timedelta(days=1)
    start_dt = end_dt - timedelta(hours=hours - 1)

    qs = (
        f"pageNo=1&numOfRows={hours + 5}&dataType=JSON"
        f"&dataCd=ASOS&dateCd=HR"
        f"&startDt={start_dt.strftime('%Y%m%d')}&startHh={start_dt.strftime('%H')}"
        f"&endDt={end_dt.strftime('%Y%m%d')}&endHh=23"
        f"&stnIds={stn_ids}"
        f"&ServiceKey={quote(key, safe='')}"
    )

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(f"{KMA_HOURLY_URL}?{qs}")
        resp.raise_for_status()
        data = resp.json()

    items = (
        data.get("response", {})
        .get("body", {})
        .get("items", {})
        .get("item", [])
    )
    if isinstance(items, dict):
        items = [items]

    results = []
    for item in items:
        row = {}
        for src, dst in KEEP_FIELDS.items():
            raw = item.get(src)
            if dst in ("observed_at", "station_id", "station_name", "wind_direction"):
                row[dst] = raw
            else:
                row[dst] = _safe_float(raw)
        results.append(row)
    return results


async def collect_and_save(stn_ids: str = DEFAULT_STN_IDS, hours: int = 24) -> int:
    """KMA 시간 기상 수집 → asos_hourly_weather 저장"""
    rows = await fetch_kma_hourly(stn_ids=stn_ids, hours=hours)
    if not rows:
        return 0

    saved = 0
    async with AsyncSessionLocal() as session:
        for row in rows:
            raw_tm = row.get("observed_at")
            if not raw_tm:
                continue
            obs_at = _parse_dt(raw_tm)
            if not obs_at:
                continue

            stn = str(row.get("station_id", ""))

            exists = await session.execute(
                select(AsosHourlyWeather).where(
                    AsosHourlyWeather.station_id == stn,
                    AsosHourlyWeather.observed_at == obs_at,
                ).limit(1)
            )
            if exists.scalar_one_or_none():
                continue

            session.add(AsosHourlyWeather(
                observed_at=obs_at,
                station_id=stn,
                station_name=row.get("station_name"),
                precipitation_mm=row.get("precipitation_mm"),
                wind_speed=row.get("wind_speed"),
                wind_direction=row.get("wind_direction"),
                temperature=row.get("temperature"),
                humidity=row.get("humidity"),
                pressure=row.get("pressure"),
            ))
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
    for fmt in ("%Y-%m-%d %H:%M", "%Y%m%d%H%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(value).strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
