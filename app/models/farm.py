from sqlalchemy import Column, String, Float, Date, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from geoalchemy2 import Geometry
from sqlalchemy.sql import func
from app.db import Base


class FarmProfile(Base):
    __tablename__ = "farm_profile"

    farm_id = Column(String(50), primary_key=True)
    owner_name = Column(String(100), nullable=False)
    farm_name = Column(String(200))
    location_name = Column(String(100))
    geom = Column(Geometry("POLYGON", srid=4326))
    area_ha = Column(Float)
    seaweed_species = Column(String(50), server_default="nori")
    season_start = Column(Date)
    season_end = Column(Date)
    sensor_ids = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
