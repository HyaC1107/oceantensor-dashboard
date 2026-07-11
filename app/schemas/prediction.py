from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any


class PredictRequest(BaseModel):
    farm_id: str = "A7"
    use_image: bool = False
    # 프론트가 어장별 결정론적 더미 센서값을 직접 전달 → predict/explain 일관성 확보
    # sensor_vals 가 있으면 what-if(공식) 경로, 없으면 v13 사전계산 팩 우선 서빙
    sensor_vals: Optional[dict] = None
    # v13 팩 조회 기준 날짜 (YYYY-MM-DD, 생략 시 팩 최신 날짜)
    date: Optional[str] = None
    # "formula" → WBI 물리 공식 강제 (시뮬레이터용 — untrained Tiny 추론 배제)
    engine: Optional[str] = None


class LLMReportRequest(BaseModel):
    farm_id: str = "A7"
    farm_name: Optional[str] = None
    region: Optional[str] = None
    stage: Optional[int] = None
    anomaly_score: Optional[float] = None
    sensor_vals: Optional[dict] = None
    top_causes: Optional[list[Any]] = None


class PredictResponse(BaseModel):
    pred_id: Optional[int] = None
    farm_id: str
    predicted_at: datetime
    model_version: str
    anomaly_score: float
    severity_pct: Optional[float] = None
    hwangbaek_flag: Optional[bool] = None
    top_causes: Optional[Any] = None
    latency_ms: Optional[float] = None
    stage: Optional[int] = None
    # v13 팩 서빙 시 추가 필드 (공식/Tiny 경로에서는 None)
    warn: Optional[float] = None       # P(7일 내 max ADI >= 5)
    severe: Optional[float] = None     # P(7일 내 max ADI >= 8)
    adi7: Optional[list[float]] = None # 미래 7일 ADI 궤적 (0~10)
    source_date: Optional[str] = None  # 팩 조회 기준 날짜

    model_config = {"from_attributes": True}


class ExplainResponse(BaseModel):
    pred_id: int
    attention_map_json: Optional[Any] = None
    top_causes: Optional[Any] = None
    heatmap_base64: Optional[str] = None
