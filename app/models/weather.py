from sqlalchemy import Column, BigInteger, String, Float, Date, DateTime, Index, UniqueConstraint
from sqlalchemy.sql import func
from app.db import Base


class AsosDailyWeather(Base):
    __tablename__ = "asos_daily_weather"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    observed_date = Column(Date, nullable=False)
    station_id = Column(String(10), nullable=False)
    station_name = Column(String(50))
    precipitation_mm = Column(Float)
    avg_wind_speed = Column(Float)
    avg_temp = Column(Float)
    avg_humidity = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("station_id", "observed_date", name="uq_asos_daily"),
        Index("ix_asos_daily_date", "observed_date"),
    )


class AsosHourlyWeather(Base):
    __tablename__ = "asos_hourly_weather"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    station_id = Column(String(10), nullable=False)
    station_name = Column(String(50))
    precipitation_mm = Column(Float)
    wind_speed = Column(Float)
    wind_direction = Column(String(10))
    temperature = Column(Float)
    humidity = Column(Float)
    pressure = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("station_id", "observed_at", name="uq_asos_hourly"),
        Index("ix_asos_hourly_at", "observed_at"),
    )
