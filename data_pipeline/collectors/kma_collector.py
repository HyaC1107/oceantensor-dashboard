"""KMA 기상청 일별 ASOS 수집기

강수량은 황백화 상관관계 1위 변수.
endDt는 반드시 전날까지 (당일 자료 미제공).
"""
import httpx
from datetime import date, datetime, timedelta
from urllib.parse import quote
from sqlalchemy import select
from app.config import settings
from app.db import AsyncSessionLocal
from app.models.weather import AsosDailyWeather

KMA_DAILY_URL = "https://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"

KEEP_FIELDS = {
    "tm":     "date",
    "stnId":  "station_id",
    "stnNm":  "station_name",
    "sumRn":  "precipitation_mm",
    "avgWs":  "avg_wind_speed",
    "avgTa":  "avg_temp",
    "avgRhm": "avg_humidity",
}

DEFAULT_STN_IDS = "156"   # 광주 (진도 인근 대표 관측소)


async def fetch_kma_daily(
    stn_ids: str = DEFAULT_STN_IDS,
    days: int = 7,
) -> list[dict]:
    """KMA ASOS 일별 기상 데이터 수집"""
    key = settings.service_key
    if not key:
        raise ValueError("ServiceKey 가 설정되지 않았습니다.")

    end_dt   = datetime.now() - timedelta(days=1)
    start_dt = end_dt - timedelta(days=days - 1)

    params = {
        "pageNo":    1,
        "numOfRows": days + 2,
        "dataType":  "JSON",
        "dataCd":    "ASOS",
        "dateCd":    "DAY",
        "startDt":   start_dt.strftime("%Y%m%d"),
        "endDt":     end_dt.strftime("%Y%m%d"),
        "stnIds":    stn_ids,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    qs += "&serviceKey=" + quote(key, safe="")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(f"{KMA_DAILY_URL}?{qs}")
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
            if dst in ("date", "station_id", "station_name"):
                row[dst] = raw
            else:
                row[dst] = _safe_float(raw)
        results.append(row)
    return results


async def collect_and_save(stn_ids: str = DEFAULT_STN_IDS, days: int = 7) -> int:
    """KMA 일별 기상 수집 → asos_daily_weather 저장"""
    rows = await fetch_kma_daily(stn_ids=stn_ids, days=days)
    if not rows:
        return 0

    saved = 0
    async with AsyncSessionLocal() as session:
        for row in rows:
            raw_date = row.get("date")
            if not raw_date:
                continue
            try:
                obs_date = datetime.strptime(str(raw_date).strip(), "%Y-%m-%d").date()
            except ValueError:
                continue

            stn = str(row.get("station_id", ""))

            exists = await session.execute(
                select(AsosDailyWeather).where(
                    AsosDailyWeather.station_id == stn,
                    AsosDailyWeather.observed_date == obs_date,
                ).limit(1)
            )
            if exists.scalar_one_or_none():
                continue

            session.add(AsosDailyWeather(
                observed_date=obs_date,
                station_id=stn,
                station_name=row.get("station_name"),
                precipitation_mm=row.get("precipitation_mm"),
                avg_wind_speed=row.get("avg_wind_speed"),
                avg_temp=row.get("avg_temp"),
                avg_humidity=row.get("avg_humidity"),
            ))
            saved += 1

        await session.commit()
    return saved


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
