"""K-water 수문 운영 정보 수집기 (시간별)

방류량·유입량·강우량으로 담수 및 영양염 공급량 추정.
대상 댐: 장흥댐 (남해 서부 황백화 영향권)
API: data.go.kr/data/15099110
"""
import httpx
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from sqlalchemy import select
from app.config import settings
from app.db import AsyncSessionLocal
from app.models.dam import DamSluiceHourly

KWATER_URL = "http://apis.data.go.kr/B500001/dam/sluicePresentCondition/hourlist"

# 황백화 영향 댐 코드 목록
# 장흥댐(3013) — 탐진강 → 강진만 → 완도/진도 양식장 인근
DAM_TARGETS = [
    {"code": "3013", "name": "장흥댐"},
]


async def fetch_dam_hourly(
    dam_code: str,
    dam_name: str = "",
    days: int = 1,
) -> list[dict]:
    """K-water 시간별 수문 데이터 수집"""
    key = settings.service_key
    if not key:
        raise ValueError("ServiceKey 가 설정되지 않았습니다.")

    end_dt   = datetime.now()
    start_dt = end_dt - timedelta(days=days)

    params = {
        "serviceKey": key,
        "pageNo":     "1",
        "numOfRows":  str(days * 24 + 5),
        "damcode":    dam_code,
        "stdt":       start_dt.strftime("%Y-%m-%d"),
        "eddt":       end_dt.strftime("%Y-%m-%d"),
        "_type":      "json",
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(KWATER_URL, params=params)
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
        obs_at = _parse_dt(item.get("obsrdt", ""))
        if not obs_at:
            continue
        results.append({
            "observed_at":      obs_at,
            "dam_code":         dam_code,
            "dam_name":         dam_name,
            "water_level":      _safe_float(item.get("lowlevel")),
            "rainfall_mm":      _safe_float(item.get("rf")),
            "inflow_m3s":       _safe_float(item.get("inflowqy")),
            "total_release_m3s": _safe_float(item.get("totdcwtrqy")),
            "storage_m3":       _safe_float(item.get("rsvwtqy")),
            "storage_rate":     _safe_float(item.get("rsvwtrt")),
        })
    return results


async def collect_and_save(days: int = 1) -> int:
    """모든 대상 댐 수문 수집 → dam_sluice_hourly 저장"""
    total_saved = 0

    async with AsyncSessionLocal() as session:
        for dam in DAM_TARGETS:
            try:
                rows = await fetch_dam_hourly(
                    dam_code=dam["code"],
                    dam_name=dam["name"],
                    days=days,
                )
            except Exception as e:
                print(f"[kwater] {dam['name']} 수집 실패: {e}")
                continue

            for row in rows:
                exists = await session.execute(
                    select(DamSluiceHourly).where(
                        DamSluiceHourly.dam_code == row["dam_code"],
                        DamSluiceHourly.observed_at == row["observed_at"],
                    ).limit(1)
                )
                if exists.scalar_one_or_none():
                    continue

                session.add(DamSluiceHourly(**row))
                total_saved += 1

        await session.commit()
    return total_saved


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: str) -> datetime | None:
    """K-water obsrdt 형식: '10-01 01시' 또는 'YYYY-MM-DD HH시'"""
    if not value:
        return None
    # 연도 없는 형식 처리: "10-01 01시" → 현재 연도 붙이기
    value = value.strip().replace("시", ":00")
    year = datetime.now().year
    for fmt in (
        "%Y-%m-%d %H:%M",
        "%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            if fmt == "%m-%d %H:%M":
                return datetime.strptime(f"{year}-{value}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
