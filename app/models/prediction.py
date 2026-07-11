from sqlalchemy import Column, BigInteger, String, Float, Boolean, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.db import Base


class PredictionResult(Base):
    __tablename__ = "prediction_result"

    pred_id = Column(BigInteger, primary_key=True, autoincrement=True)
    farm_id = Column(String(50), nullable=False)
    predicted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    model_version = Column(String(30), nullable=False, server_default="v0.1.0-mock")
    anomaly_score = Column(Float, nullable=False)
    severity_pct = Column(Float)
    hwangbaek_flag = Column(Boolean)
    attention_map_json = Column(JSONB)
    top_causes = Column(JSONB)
    latency_ms = Column(Float)
    device = Column(String(30))
