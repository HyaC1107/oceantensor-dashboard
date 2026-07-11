from sqlalchemy import Column, BigInteger, String, Float, SmallInteger, Text, Index, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from sqlalchemy.sql import func
from app.db import Base


class FeatureStore(Base):
    __tablename__ = "feature_store"

    feature_id = Column(BigInteger, primary_key=True, autoincrement=True)
    farm_id = Column(String(50), nullable=False)
    feature_ts = Column(DateTime(timezone=True), nullable=False)
    water_temp_surface = Column(Float)
    water_temp_bottom = Column(Float)
    do_surface = Column(Float)
    din = Column(Float)           # 황백화 핵심: DIN < 5 μmol/L 임계값
    dip = Column(Float)           # 황백화 핵심: DIP < 0.3 μmol/L 임계값
    din_dip_ratio = Column(Float) # N/P 비 ≤ 16 → 질소 제한 상태
    chlorophyll_a = Column(Float)
    salinity = Column(Float)
    turbidity = Column(Float)
    wind_speed = Column(Float)
    precipitation_3d = Column(Float)
    sst_anomaly = Column(Float)
    chl_satellite = Column(Float)
    image_path = Column(Text)
    embedding = Column(Vector(256))
    feature_version = Column(String(20))
    quality_flag = Column(SmallInteger, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_feature_farm_id", "farm_id"),
        Index("ix_feature_ts", "feature_ts"),
    )
