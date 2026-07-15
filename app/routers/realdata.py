"""실데이터(Bronze) 센서 서빙 — 어장 최근접 관측소의 실측값.

기존 대시보드는 어장 센서값을 프론트 더미(farmDummy)로 채웠다. 이 라우터는
네이버클라우드 `oceantensor_db`의 **원천 관측 테이블(Bronze)**에서 실측값을 읽어
어장(F01~F79) 좌표에 가장 가까운 관측소의 최신 관측을 반환한다.

소스
  - KOEM 해양환경측정망 (`koem_observation` + `koem_station`)
      표층: 수온·염분·DO·DIN·DIP·엽록소·부유물질  ※ 분기 관측 → 최신이 수개월 전일 수 있음
  - KMA ASOS (`kma_asos_hourly` + `kma_station`) : 강수량 (최신)

⚠️ 단위 변환: KOEM 영양염은 **μg/L**, 우리 WBI 공식/라벨러는 **μmol/L** 기준이다.
   DIN μg/L ÷ 14.007(N) , DIP μg/L ÷ 30.974(P) → μmol/L
   변환 없이 쓰면 위험도가 완전히 뒤틀린다. raw(μg/L)도 함께 반환해 HUD 카드(μg/L 임계)와 양립.

⚠️ 관측일(observed_at)을 반드시 함께 노출한다. 영양염은 기관 QC 지연으로 수개월 전 값이 최신이며,
   이를 '실시간'처럼 보여주면 심사/사용자를 오도한다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db

router = APIRouter()

FARMS_PATH = Path(__file__).parents[1] / "data" / "farms_geo.json"

# 원자량 — μg/L → μmol/L 변환
N_ATOMIC = 14.007
P_ATOMIC = 30.974


@lru_cache(maxsize=1)
def _farms() -> dict[str, dict]:
    if not FARMS_PATH.exists():
        return {}
    with open(FARMS_PATH, encoding="utf-8") as f:
        return {x["id"]: x for x in json.load(f)}


# 최근접 KOEM 관측소의 '최신 유효 관측' (표층)
_KOEM_SQL = text("""
WITH st AS (
    SELECT stnpnt_code, stnpnt_korean_nm,
           ST_Distance(geom::geography,
                       ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) / 1000.0 AS km
    FROM koem_station
    WHERE geom IS NOT NULL
    ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
    LIMIT 1
)
SELECT st.stnpnt_korean_nm AS station, st.km,
       o.obsr_de AS observed_on,
       o.wtrtmp_sfclyr AS water_temp,
       o.salnt_sfclyr  AS salinity,
       o.doxy_sfclyr   AS dissolved_oxygen,
       o.din_sfclyr    AS din_ugl,
       o.dip_sfclyr    AS dip_ugl,
       o.clrpla_sfclyr AS chlorophyll_a,
       o.fltng_mttr_sfclyr AS suspended_solids,
       o.ph_dnsty_sfclyr   AS ph
FROM st
JOIN koem_observation o ON o.stnpnt_code = st.stnpnt_code
WHERE o.wtrtmp_sfclyr IS NOT NULL
ORDER BY o.obsr_de DESC
LIMIT 1
""")

# 최근접 KMA 관측소의 최신 강수 (24h 누적)
_KMA_SQL = text("""
WITH st AS (
    SELECT stn_id, stn_nm,
           ST_Distance(geom::geography,
                       ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) / 1000.0 AS km
    FROM kma_station
    WHERE geom IS NOT NULL
    ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
    LIMIT 1
)
SELECT st.stn_nm AS station, st.km,
       max(a.tm) AS observed_at,
       COALESCE(sum(a.rn), 0) AS precipitation_24h,
       (SELECT ws FROM kma_asos_hourly w
         WHERE w.stn_id = st.stn_id AND w.ws IS NOT NULL
         ORDER BY w.tm DESC LIMIT 1) AS wind_speed,
       (SELECT wd FROM kma_asos_hourly w
         WHERE w.stn_id = st.stn_id AND w.wd IS NOT NULL
         ORDER BY w.tm DESC LIMIT 1) AS wind_dir
FROM st
JOIN kma_asos_hourly a ON a.stn_id = st.stn_id
WHERE a.tm >= (SELECT max(tm) FROM kma_asos_hourly) - INTERVAL '24 hours'
GROUP BY st.stn_nm, st.km, st.stn_id
""")


def _f(v) -> Optional[float]:
    """Decimal/None → float/None."""
    return None if v is None else float(v)


async def _fetch_real(db: AsyncSession, lat: float, lon: float) -> Optional[dict]:
    koem = (await db.execute(_KOEM_SQL, {"lat": lat, "lon": lon})).mappings().first()
    if not koem:
        return None

    din_ugl = _f(koem["din_ugl"])
    dip_ugl = _f(koem["dip_ugl"])
    # μg/L → μmol/L (WBI 공식·라벨러 기준 단위)
    din = round(din_ugl / N_ATOMIC, 2) if din_ugl is not None else None
    dip = round(dip_ugl / P_ATOMIC, 3) if dip_ugl is not None else None
    np_ratio = round(din / dip, 2) if (din is not None and dip) else None

    # 강수·풍속은 별도 소스(KMA) — 없으면 0/None
    precip, kma_station, kma_at = 0.0, None, None
    wind_speed, wind_dir = None, None
    try:
        kma = (await db.execute(_KMA_SQL, {"lat": lat, "lon": lon})).mappings().first()
        if kma:
            precip = round(_f(kma["precipitation_24h"]) or 0.0, 1)
            kma_station = kma["station"]
            kma_at = kma["observed_at"]
            ws_v = _f(kma["wind_speed"]); wd_v = _f(kma["wind_dir"])
            wind_speed = round(ws_v, 1) if ws_v is not None else None
            wind_dir = round(wd_v) if wd_v is not None else None
    except Exception:
        pass  # KMA 실패는 치명적이지 않음 — 나머지 값은 그대로 서빙

    sensor_vals = {
        "water_temp":       _f(koem["water_temp"]),
        "dissolved_oxygen": _f(koem["dissolved_oxygen"]),
        "din":              din,          # μmol/L
        "dip":              dip,          # μmol/L
        "np_ratio":         np_ratio,
        "salinity":         _f(koem["salinity"]),
        "chlorophyll_a":    _f(koem["chlorophyll_a"]),   # μg/L ≈ mg/m³
        "turbidity":        _f(koem["suspended_solids"]),  # 부유물질(SS) 대용
        "precipitation":    precip,
        "wind_speed":       wind_speed,   # m/s (KMA, 최신)
        "wind_dir":         wind_dir,     # deg
    }
    return {
        "sensor_vals": sensor_vals,
        # HUD 카드가 쓰는 μg/L 원값도 함께 (임계 체계가 달라 변환값과 혼용 금지)
        "raw_ugl": {"din": din_ugl, "dip": dip_ugl},
        "provenance": {
            "source": "KOEM 해양환경측정망 (실측)",
            "station": koem["station"],
            "distance_km": round(_f(koem["km"]) or 0.0, 1),
            "observed_on": str(koem["observed_on"]),
            "precip_source": f"KMA {kma_station}" if kma_station else None,
            "precip_observed_at": str(kma_at) if kma_at else None,
            "note": "영양염은 기관 QC 절차로 발행이 지연되어 최신 관측이 수개월 전일 수 있음",
        },
    }


# 모델 격자(서·남해) 밖 어장 — 경기·인천(화성·안산·옹진) 21개.
# v13 예측팩 meta.out_of_grid_farms 와 정확히 일치함(2026-07-11 검증).
OUT_OF_GRID_REGIONS = {"화성", "안산", "옹진"}


@router.get("/sensor/{farm_id}")
async def real_sensor(farm_id: str, db: AsyncSession = Depends(get_db)):
    """어장(F01~F79) 최근접 관측소의 실측 센서값."""
    farm = _farms().get(farm_id)
    if not farm:
        raise HTTPException(404, f"어장 없음: {farm_id} (F01~F79)")
    try:
        data = await _fetch_real(db, farm["lat"], farm["lon"])
    except Exception as e:
        raise HTTPException(503, f"실데이터 DB 조회 실패: {type(e).__name__}")
    if not data:
        raise HTTPException(404, f"{farm_id} 인근 관측 데이터 없음")
    out_of_grid = farm.get("region") in OUT_OF_GRID_REGIONS
    if out_of_grid:
        data["provenance"]["warning"] = "모델 격자(서·남해) 밖 어장 — v13 예측 신뢰도 낮음"
    return {"farm_id": farm_id, "farm_name": farm["name"], "region": farm.get("region"),
            "out_of_grid": out_of_grid,
            "lat": farm["lat"], "lon": farm["lon"], **data}


@router.get("/sensor")
async def real_sensor_by_latlon(
    lat: float = Query(...), lon: float = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """임의 좌표(지도 폴리곤 클릭 등) 최근접 관측소의 실측 센서값."""
    try:
        data = await _fetch_real(db, lat, lon)
    except Exception as e:
        raise HTTPException(503, f"실데이터 DB 조회 실패: {type(e).__name__}")
    if not data:
        raise HTTPException(404, "인근 관측 데이터 없음")
    return {"lat": lat, "lon": lon, **data}


@router.get("/health")
async def real_health(db: AsyncSession = Depends(get_db)):
    """실데이터 DB 연결 + 소스별 최신 관측일."""
    try:
        r = (await db.execute(text("""
            SELECT (SELECT max(obsr_de)::text FROM koem_observation) AS koem,
                   (SELECT max(tm)::text      FROM kma_asos_hourly)  AS kma,
                   (SELECT count(*)           FROM koem_station)     AS koem_stations
        """))).mappings().first()
        return {"connected": True, "latest": dict(r)}
    except Exception as e:
        return {"connected": False, "error": type(e).__name__}
