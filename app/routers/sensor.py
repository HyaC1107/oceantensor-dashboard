import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, timezone
from typing import Optional
from app.db import get_db
from app.models.sensor import OceanSensorRaw
from app.schemas.sensor import SensorResponse
from app.config import settings

router = APIRouter()

_PREDICTIONS_PATH = Path(__file__).parent.parent / "data" / "farm_predictions.json"

@lru_cache(maxsize=1)
def _load_predictions() -> dict:
    if not _PREDICTIONS_PATH.exists():
        return {}
    with open(_PREDICTIONS_PATH, encoding="utf-8") as f:
        return json.load(f)

MOCK_SENSORS = [
    {
        "id": 1,
        "sensor_id": "KOEM-JINDO-01",
        "observed_at": "2026-05-26T06:00:00+00:00",
        "water_temp": 14.7,
        "dissolved_oxygen": 8.2,
        "no3_nitrogen": 12.1,
        "nh4_nitrogen": 2.3,
        "ph": 7.8,
        "salinity": 32.5,
        "turbidity": 1.2,
        "raw_status": "mock",
    }
]


@router.get("/recent", response_model=list[SensorResponse])
async def get_recent_sensors(
    farm_id: str = Query("A7"),
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
):
    if settings.use_mock_data:
        return MOCK_SENSORS

    result = await db.execute(
        select(OceanSensorRaw)
        .order_by(desc(OceanSensorRaw.observed_at))
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/", response_model=list[SensorResponse])
async def get_sensors(
    farm_id: str = Query("A7"),
    start_ts: Optional[datetime] = None,
    end_ts: Optional[datetime] = None,
    limit: int = Query(500, le=5000),
    db: AsyncSession = Depends(get_db),
):
    if settings.use_mock_data:
        return MOCK_SENSORS

    query = select(OceanSensorRaw).order_by(desc(OceanSensorRaw.observed_at))
    if start_ts:
        query = query.where(OceanSensorRaw.observed_at >= start_ts)
    if end_ts:
        query = query.where(OceanSensorRaw.observed_at <= end_ts)
    query = query.limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


def _entry_to_response(entry: dict) -> dict:
    ch = entry.get("channel_vals", {})
    din = ch.get("din", 0.0)
    dip = max(ch.get("dip", 0.82), 1e-6)
    sensor_vals = {
        "water_temp":       round(ch.get("sst", 15.0), 2),
        "dissolved_oxygen": round(ch.get("dissolved_oxygen", 8.0), 2),
        "din":              round(din, 2),
        "dip":              round(dip, 3),
        "np_ratio":         round(din / dip, 2),
        "salinity":         round(ch.get("salinity", 32.0), 2),
        "chlorophyll_a":    round(ch.get("chlorophyll_a", 3.0), 2),
        "turbidity":        round(ch.get("turbidity", 1.0), 2),
        "ph":               round(ch.get("ph", 7.8), 2),
    }
    return {
        "gid":             entry["gid"],
        "lat":             entry["lat"],
        "lon":             entry["lon"],
        "pred_label":      entry["pred_label"],
        "pred_label_name": entry["pred_label_name"],
        "class_probs":     entry["class_probs"],
        "anomaly_score":   entry["anomaly_score"],
        "cube_date":       entry["cube_date"],
        "model_version":   entry["model_version"],
        "sensor_vals":     sensor_vals,
        "channel_vals":    ch,
        "data_source":     "cube_v5_real",
    }


@router.get("/by-latlon")
async def get_farm_sensor_by_latlon(
    lat: float = Query(..., description="어장 위도"),
    lon: float = Query(..., description="어장 경도"),
):
    """lat/lon 좌표 → 가장 가까운 어장 예측 반환 (farmGeoData.js 어장 클릭 연동용)."""
    predictions = _load_predictions()
    if not predictions:
        raise HTTPException(status_code=503, detail="farm_predictions.json 없음")

    # 유클리드 거리로 가장 가까운 픽셀 찾기
    best_entry = None
    best_dist = float("inf")
    for entry in predictions.values():
        d = (entry["lat"] - lat) ** 2 + (entry["lon"] - lon) ** 2
        if d < best_dist:
            best_dist = d
            best_entry = entry

    if best_entry is None:
        raise HTTPException(status_code=404, detail="매칭 어장 없음")

    return _entry_to_response(best_entry)


@router.get("/{gid}")
async def get_farm_sensor(gid: int):
    """어장 GID → cube_v5 실데이터 + v10 모델 예측 반환."""
    predictions = _load_predictions()
    entry = predictions.get(str(gid))
    if not entry:
        raise HTTPException(status_code=404, detail=f"GID {gid} 없음 (범위 밖 또는 미수록)")
    return _entry_to_response(entry)
