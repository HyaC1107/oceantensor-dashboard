from sqlalchemy import Column, BigInteger, String, Float, DateTime, Index, UniqueConstraint
from sqlalchemy.sql import func
from app.db import Base


class DamSluiceHourly(Base):
    __tablename__ = "dam_sluice_hourly"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    dam_code = Column(String(20), nullable=False)
    dam_name = Column(String(100))
    water_level = Column(Float)       # 댐수위 (m)
    rainfall_mm = Column(Float)       # 강우량 (mm)
    inflow_m3s = Column(Float)        # 유입량 (m³/s)
    total_release_m3s = Column(Float) # 총방류량 (m³/s)
    storage_m3 = Column(Float)        # 저수량 (백만m³)
    storage_rate = Column(Float)      # 저수율 (%)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("dam_code", "observed_at", name="uq_dam_hourly"),
        Index("ix_dam_hourly_at", "observed_at"),
    )
