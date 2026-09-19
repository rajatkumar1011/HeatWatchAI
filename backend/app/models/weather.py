"""Location and weather data models (FR-02)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Location(db.Model):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("name", "state", name="uq_location_name_state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    country: Mapped[str] = mapped_column(String(80), nullable=False, default="India")
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    is_monitored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    timezone: Mapped[str] = mapped_column(String(60), nullable=False, default="Asia/Kolkata")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    observations: Mapped[list["WeatherObservation"]] = relationship(back_populates="location")

    @property
    def display_name(self) -> str:
        return f"{self.name}, {self.state}" if self.state else self.name

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state,
            "display_name": self.display_name,
            "country": self.country,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "is_monitored": self.is_monitored,
            "timezone": self.timezone,
        }


class WeatherObservation(db.Model):
    """A single normalized meteorological observation (SRS FR-02).

    Units: temperature in degrees Celsius, wind speed in km/h, pressure in hPa.
    ``heat_index_c`` follows the NWS Rothfusz regression and is only populated
    when its applicability conditions hold (see app/utils/heat.py); otherwise
    it stays NULL and the UI communicates that the value is unavailable.
    ``data_mode`` is ``live`` or ``demo`` — demonstration observations are
    never presented as real measurements.
    """

    __tablename__ = "weather_observations"
    __table_args__ = (
        UniqueConstraint("location_id", "provider", "observed_at", name="uq_weather_obs"),
        Index("ix_weather_loc_time", "location_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    feels_like_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float] = mapped_column(Float, nullable=False)
    heat_index_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_kph: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    wind_deg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pressure_hpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    condition_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condition_text: Mapped[str] = mapped_column(String(120), nullable=False, default="unknown")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    data_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="live")  # live|demo
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    location: Mapped[Location] = relationship(back_populates="observations")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "location_id": self.location_id,
            "temperature_c": self.temperature_c,
            "feels_like_c": self.feels_like_c,
            "humidity_pct": self.humidity_pct,
            "heat_index_c": self.heat_index_c,
            "wind_speed_kph": self.wind_speed_kph,
            "wind_deg": self.wind_deg,
            "pressure_hpa": self.pressure_hpa,
            "condition_code": self.condition_code,
            "condition_text": self.condition_text,
            "observed_at": self.observed_at.isoformat(),
            "ingested_at": self.ingested_at.isoformat(),
            "provider": self.provider,
            "data_mode": self.data_mode,
        }
