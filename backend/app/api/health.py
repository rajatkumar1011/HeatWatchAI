"""Health and integration-status endpoints (FR-10)."""
from __future__ import annotations

from flask import Blueprint, current_app
from sqlalchemy import select, text

from app.api import get_services
from app.auth import auth_required
from app.extensions import db
from app.models import CollectionRun
from app.utils.responses import success_response
from app.utils.timeutils import utcnow

bp = Blueprint("health", __name__, url_prefix="/api/v1/health")


@bp.get("/detailed")
@auth_required
def detailed_health():
    config = current_app.config
    services = get_services()

    db_ok = True
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    weather = services["weather"]
    social = services["social"]
    last_weather = db.session.execute(
        select(CollectionRun).where(CollectionRun.job == "weather")
        .order_by(CollectionRun.started_at.desc()).limit(1)
    ).scalar_one_or_none()
    last_social = db.session.execute(
        select(CollectionRun).where(CollectionRun.job == "social")
        .order_by(CollectionRun.started_at.desc()).limit(1)
    ).scalar_one_or_none()

    weather_configured = bool(config["OPENWEATHER_API_KEY"]) or config["DATA_MODE"] == "demo"
    social_mode = config.get("SOCIAL_PROVIDER", "auto")

    return success_response({
        "status": "ok" if db_ok else "degraded",
        "database": {"ok": db_ok,
                     "engine": "mysql" if str(config["SQLALCHEMY_DATABASE_URI"]).startswith("mysql") else "sqlite (development fallback)"},
        "data_mode": config["DATA_MODE"],
        "providers": {
            "weather": {
                "configured": weather_configured,
                "active_provider": weather.active_provider_name(),
                "mode": config["DATA_MODE"],
            },
            "social": {
                "configured": social_mode in ("demo", "reddit") or config["DATA_MODE"] == "demo",
                "active_provider": social.active_provider_name(),
                "requested": social_mode,
            },
        },
        "last_runs": {
            "weather": {"status": last_weather.status, "at": last_weather.started_at.isoformat()} if last_weather else None,
            "social": {"status": last_social.status, "at": last_social.started_at.isoformat()} if last_social else None,
        },
        "time_utc": utcnow().isoformat(),
    })
