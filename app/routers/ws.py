import asyncio
import random
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select, desc
from app.db import AsyncSessionLocal
from app.models.sensor import OceanSensorRaw
from app.config import settings

router = APIRouter()


def _generate_mock_payload() -> dict:
    din = round(random.uniform(2.0, 18.0), 2)
    dip = round(random.uniform(0.4, 1.2), 3)
    wbi = round(random.uniform(0.2, 0.9), 3)

    if wbi < 0.3:
        severity = "NORMAL"
    elif wbi < 0.6:
        severity = "CAUTION"
    elif wbi < 0.8:
        severity = "WARNING"
    else:
        severity = "DANGER"

    return {
        "farm_id": "A7",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "water_temp": round(random.uniform(13.5, 16.0), 2),
        "dissolved_oxygen": round(random.uniform(7.5, 9.0), 2),
        "din": din,
        "dip": dip,
        "np_ratio": round(din / dip, 2) if dip > 0 else 0.0,
        "salinity": round(random.uniform(31.5, 33.5), 2),
        "wbi_score": wbi,
        "severity": severity,
        "edge_status": "online",
        "mqtt_status": "connected",
        "inference_latency_ms": random.randint(18, 35),
    }


async def _get_latest_from_db() -> dict | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OceanSensorRaw).order_by(desc(OceanSensorRaw.observed_at)).limit(1)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        din = (row.no3_nitrogen or 0) + (row.nh4_nitrogen or 0)
        dip = 0.82  # DIP는 KOEM API에서 별도 수집
        wbi = round(min(1.0, max(0.0, (1 - din / 20))), 3) if din else 0.5
        return {
            "farm_id": "A7",
            "observed_at": row.observed_at.isoformat(),
            "water_temp": row.water_temp,
            "dissolved_oxygen": row.dissolved_oxygen,
            "din": din,
            "dip": dip,
            "np_ratio": round(din / dip, 2) if dip > 0 else 0.0,
            "salinity": row.salinity,
            "wbi_score": wbi,
            "severity": "CAUTION" if wbi >= 0.5 else "NORMAL",
            "edge_status": "online",
            "mqtt_status": "connected",
            "inference_latency_ms": 24,
        }


@router.websocket("/ws/sensor")
async def websocket_sensor(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            if settings.use_mock_data:
                payload = _generate_mock_payload()
            else:
                payload = await _get_latest_from_db() or _generate_mock_payload()

            await websocket.send_json(payload)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
