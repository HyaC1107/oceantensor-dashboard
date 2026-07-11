from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class SensorResponse(BaseModel):
    id: Optional[int] = None
    sensor_id: str
    observed_at: datetime
    water_temp: Optional[float] = None
    dissolved_oxygen: Optional[float] = None
    no3_nitrogen: Optional[float] = None
    nh4_nitrogen: Optional[float] = None
    ph: Optional[float] = None
    salinity: Optional[float] = None
    turbidity: Optional[float] = None
    raw_status: Optional[str] = None

    model_config = {"from_attributes": True}


class WSSensorPayload(BaseModel):
    farm_id: str
    observed_at: str
    water_temp: float
    dissolved_oxygen: float
    din: float
    dip: float
    np_ratio: float
    salinity: float
    wbi_score: float
    severity: str          # NORMAL / CAUTION / WARNING / DANGER
    edge_status: str
    mqtt_status: str
    inference_latency_ms: int
