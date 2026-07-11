from sqlalchemy import Column, BigInteger, String, Float, DateTime, Index, PrimaryKeyConstraint
from geoalchemy2 import Geometry
from sqlalchemy.sql import func
from app.db import Base


class OceanSensorRaw(Base):
    __tablename__ = "ocean_sensor_raw"

    id = Column(BigInteger, autoincrement=True)
    sensor_id = Column(String(50), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    water_temp = Column(Float)
    dissolved_oxygen = Column(Float)
    no3_nitrogen = Column(Float)
    nh4_nitrogen = Column(Float)
    ph = Column(Float)
    salinity = Column(Float)
    turbidity = Column(Float)
    geom = Column(Geometry("POINT", srid=4326))
    raw_status = Column(String(30), server_default="raw")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        PrimaryKeyConstraint("id", "observed_at"),
        Index("ix_sensor_id", "sensor_id"),
        Index("ix_observed_at", "observed_at"),
    )
