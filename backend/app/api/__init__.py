"""REST API v1 (/api/v1). All endpoints return JSON {data, meta} or
{error: {code, message}} shapes with consistent status codes."""
from __future__ import annotations

from functools import lru_cache

from flask import current_app

from app.services.alert_service import AlertService
from app.services.monitoring_service import MonitoringService
from app.services.prediction_service import PredictionService
from app.services.report_service import ReportService
from app.services.sentiment_service import SentimentService
from app.services.social_service import SocialService
from app.services.weather_service import WeatherService


def get_services():
    config = current_app.config
    alerts = AlertService(config)
    predictions = PredictionService(config, alerts)
    return {
        "weather": WeatherService(config),
        "social": SocialService(config),
        "sentiment": SentimentService(config),
        "alerts": alerts,
        "predictions": predictions,
        "monitoring": MonitoringService(config),
        "reports": ReportService(config),
    }


from app.api.auth import bp as auth_bp  # noqa: E402
from app.api.locations import bp as locations_bp  # noqa: E402
from app.api.weather import bp as weather_bp  # noqa: E402
from app.api.social import bp as social_bp  # noqa: E402
from app.api.predictions import bp as predictions_bp  # noqa: E402
from app.api.alerts import bp as alerts_bp  # noqa: E402
from app.api.reports import bp as reports_bp  # noqa: E402
from app.api.admin import bp as admin_bp  # noqa: E402
from app.api.dashboard import bp as dashboard_bp  # noqa: E402
from app.api.health import bp as health_bp  # noqa: E402

ALL_BLUEPRINTS = [
    auth_bp, locations_bp, weather_bp, social_bp,
    predictions_bp, alerts_bp, reports_bp, admin_bp, dashboard_bp, health_bp,
]
