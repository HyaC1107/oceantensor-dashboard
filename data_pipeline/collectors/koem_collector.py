"""KOEM 해양환경공단 수집기

- 해양환경측정망 정점조회 : OceansNemoInfoService1/getOceansNemoInfo1 (정점 마스터)
- 해양환경측정망 관측서비스: OceansNemoService1/getOceansNemo1 (실측값)
  └ DIN, DIP, DO, 수온, 염분, pH, CHL-A 포함

data.go.kr/data/15059973  — 관측 실측값
data.go.kr/data/15059966  — 정점 마스터
"""
import httpx
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from sqlalchemy import select
from app.config import settings
from app.db import AsyncSessionLocal
from app.models.sensor import OceanSensorRaw

KOEM_STN_URL = (
    "http://apis.data.go.kr/B553931/service"
    "/OceansNemoInfoService1/getOceansNemoInfo1"
)
KOEM_OBS_URL = (
    "http://apis.data.go.kr/B553931/service"
    "/OceansNemoService1/getOceansNemo1"
)

# 황백화 분석에 필요한 실측값 필드 매핑 (표층 기준)
# 실제 응답 필드명은 첫 호출 시 로그에서 확인 후 조정
OBS_FIELD_MAP = {
    "wtemS":    "water_temp",       # 표층 수온
    "slntS":    "salinity",         # 표층 염분
    "doxS":     "dissolved_oxygen", # 표층 DO
    "no3nS":    "no3_nitrogen",     # 표층 질산성질소
    "nh4nS":    "nh4_nitrogen",     # 표층 암모니아성질소
    "phS":      "ph",               # 표층 pH
    "trbS":     "turbidity",        # 표층 탁도
    # 한글 필드명 후보 (API 응답 확인 후 실제 이름으로 교체)
    "수온":      "water_temp",
    "염분":      "salinity",
    "용존산소":   "dissolved_oxygen",
    "질산성질소": "no3_nitrogen",
    "암모니아성질소": "nh4_nitrogen",
    "수소이온농도": "ph",
}


async def fetch_koem_stations() -> list[dict]:
    """정점 마스터 조회 (위치·측정망 종류)"""
    key = settings.service_key
    if not key:
        raise ValueError("ServiceKey 가 설정되지 않았습니다.")

    qs = "pageNo=1&numOfRows=100&resultType=json"
    qs += "&ServiceKey=" + quote(key, safe="")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(f"{KOEM_STN_URL}?{qs}")
        resp.raise_for_status()
        data = resp.json()

    # 실제 응답 구조: {"getOceansNemoInfo": {"header": ..., "item": [...]}}
    # 또는 표준 구조: {"response": {"body": {"items": {"item": [...]}}}}
    inner = data.get("getOceansNemoInfo", {})
    items = inner.get("item", [])
    if not items:
        # 표준 응답 구조 시도
        items = (
            data.get("response", {})
            .get("body", {})
            .get("items", {})
            .get("item", [])
        )
    if isinstance(items, dict):
        items = [items]

    return [
        {
            "stnpnt_code":  item.get("stnpnt_code"),
            "station_name": item.get("mre_msnt_sta_korn_nm"),
            "ocean":        item.get("ocean_nm"),
            "network":      item.get("mre_wtch_iem_nm"),
            "lon":          item.get("lon"),
            "lat":          item.get("lat"),
        }
        for item in items
    ]


async def fetch_koem_observations(
    ocean_nm: str = "남해 서부",
    days: int = 30,
) -> list[dict]:
    """해양환경측정망 실측값 조회 (DIN/DIP/DO/수온/염분)

    Args:
        ocean_nm: 해역명 (e.g. '남해 서부', '남해 동부', '서해')
        days: 수집 기간 (일)
    """
    key = settings.service_key
    if not key:
        raise ValueError("ServiceKey 가 설정되지 않았습니다.")

    end = datetime.now()
    start = end - timedelta(days=days)

    params = {
        "ServiceKey": key,
        "pageNo": "1",
        "numOfRows": "100",
        "해역명": ocean_nm,
        "조사시작일": start.strftime("%Y%m%d"),
        "조사종료일": end.strftime("%Y%m%d"),
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(KOEM_OBS_URL, params=params)
        resp.raise_for_status()

        # XML 또는 JSON 응답 처리
        ct = resp.headers.get("content-type", "")
        if "xml" in ct:
            return _parse_koem_xml(resp.text)

        data = resp.json()

    # 응답 구조 탐색 (첫 호출 시 키 확인용 로그)
    print(f"[koem] 관측 응답 최상위 키: {list(data.keys())[:10]}")

    # 표준 구조 시도
    items = (
        data.get("response", {})
        .get("body", {})
        .get("items", {})
        .get("item", [])
    )
    if not items:
        # 비표준 구조 시도
        for key_name in data:
            candidate = data[key_name]
            if isinstance(candidate, dict):
                sub = candidate.get("item", candidate.get("items", []))
                if sub:
                    items = sub
                    break
    if isinstance(items, dict):
        items = [items]

    if items:
        print(f"[koem] 관측 응답 item 키: {list(items[0].keys())[:15]}")

    return items


def _parse_koem_obs_item(item: dict) -> dict | None:
    """KOEM 관측 item → OceanSensorRaw 저장용 dict"""
    # 관측일자 파싱 시도 (필드명 미확인)
    obs_at = None
    for dt_field in ("obsrvDt", "obsrDt", "surDt", "조사일자", "관측일시"):
        raw = item.get(dt_field)
        if raw:
            obs_at = _parse_dt(str(raw))
            if obs_at:
                break

    if not obs_at:
        obs_at = datetime.now(tz=timezone.utc)

    stn = item.get("stnpnt_code") or item.get("stnpntCode") or item.get("정점코드", "UNKNOWN")
    sensor_id = f"KOEM-OBS-{stn}"

    row: dict = {"sensor_id": sensor_id, "observed_at": obs_at, "raw_status": "raw"}

    for src_key, dst_key in OBS_FIELD_MAP.items():
        val = item.get(src_key)
        if val is not None and dst_key not in row:
            row[dst_key] = _safe_float(val)

    return row


def _parse_koem_xml(xml_text: str) -> list[dict]:
    """XML 응답 파싱 (표준 공공데이터 포맷)"""
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_text)
        items = []
        for item_el in root.iter("item"):
            row = {child.tag: child.text for child in item_el}
            items.append(row)
        return items
    except Exception as e:
        print(f"[koem] XML 파싱 실패: {e}")
        return []


async def collect_and_save(ocean_nm: str = "남해 서부", days: int = 30) -> int:
    """KOEM 실측값 수집 → ocean_sensor_raw 저장"""
    try:
        items = await fetch_koem_observations(ocean_nm=ocean_nm, days=days)
    except Exception as e:
        print(f"[koem] 관측 수집 실패: {e}")
        # 정점 마스터만 반환
        stations = await fetch_koem_stations()
        return len(stations)

    if not items:
        return 0

    saved = 0
    async with AsyncSessionLocal() as session:
        for item in items:
            row = _parse_koem_obs_item(item)
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
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y%m%d%H%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(str(value).strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
