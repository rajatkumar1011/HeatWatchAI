"""Prediction, alert, and report models (FR-05, FR-06, FR-08)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

RISK_LOW = "low"
RISK_MODERATE = "moderate"
RISK_HIGH = "high"
RISK_CATEGORIES = (RISK_LOW, RISK_MODERATE, RISK_HIGH)


class Prediction(db.Model):
    """A heatwave severity assessment produced by the prediction engine.

    ``methodology`` records exactly how this prediction was produced (e.g.
    ``ml_severity_model_v1 + rule_fusion_v1``), ``inputs_json`` snapshots the
    weather/sentiment inputs actually used, and ``contributing_factors`` is a
    human-readable explanation. ``data_mode`` reflects the provenance of the
    underlying data (live or demonstration).
    """

    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_prediction_loc_time", "location_id", "predicted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    weather_observation_id: Mapped[int | None] = mapped_column(ForeignKey("weather_observations.id", ondelete="SET NULL"), nullable=True)
    sentiment_aggregate_id: Mapped[int | None] = mapped_column(ForeignKey("sentiment_aggregates.id", ondelete="SET NULL"), nullable=True)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    risk_category: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    severity_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0-100 fused score
    weather_model_risk: Mapped[float | None] = mapped_column(Float, nullable=True)  # weather-only score 0-100
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # only when the model supports it
    methodology: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(60), nullable=False)
    sentiment_adjustment: Mapped[float | None] = mapped_column(Float, nullable=True)  # points contributed by fusion
    contributing_factors: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    inputs_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON snapshot
    data_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="live")

    location = relationship("Location")
    weather_observation = relationship("WeatherObservation")
    sentiment_aggregate = relationship("SentimentAggregate")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="prediction")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "location_id": self.location_id,
            "weather_observation_id": self.weather_observation_id,
            "sentiment_aggregate_id": self.sentiment_aggregate_id,
            "predicted_at": self.predicted_at.isoformat(),
            "risk_category": self.risk_category,
            "severity_score": self.severity_score,
            "weather_model_risk": self.weather_model_risk,
            "confidence": self.confidence,
            "methodology": self.methodology,
            "model_version": self.model_version,
            "sentiment_adjustment": self.sentiment_adjustment,
            "contributing_factors": self.contributing_factors,
            "inputs": self.inputs_json,
            "data_mode": self.data_mode,
        }


class Alert(db.Model):
    """A recorded heatwave early-warning alert (SRS FR-06).

    Application-generated warnings are always distinguishable from official
    government advisories: they are stored and displayed as HeatWatch AI
    system alerts, never presented as official notifications.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alert_loc_time", "location_id", "generated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[int | None] = mapped_column(ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    severity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(255), nullable=False, default="severity >= high threshold")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)  # active|acknowledged|resolved
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="live")

    prediction = relationship("Prediction", back_populates="alerts")
    location = relationship("Location")
    acknowledged_by_user = relationship("User")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "prediction_id": self.prediction_id,
            "location_id": self.location_id,
            "location_name": self.location.display_name if self.location else None,
            "risk_level": self.risk_level,
            "severity_score": self.severity_score,
            "message": self.message,
            "triggered_by": self.triggered_by,
            "status": self.status,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "generated_at": self.generated_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "data_mode": self.data_mode,
        }


class ReportRecord(db.Model):
    """Metadata about a generated historical report (SRS FR-08).

    One user may generate multiple reports (SRS 2.6.2); each record is tied
    to the requesting user and the exact query parameters used.
    """

    __tablename__ = "report_records"
    __table_args__ = (
        Index("ix_report_user_time", "user_id", "generated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf|csv
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    params_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    data_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="live")

    user = relationship("User")
    location = relationship("Location")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.user.username if self.user else None,
            "location_id": self.location_id,
            "location_name": self.location.display_name if self.location else None,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "format": self.format,
            "status": self.status,
            "generated_at": self.generated_at.isoformat(),
            "data_mode": self.data_mode,
        }
