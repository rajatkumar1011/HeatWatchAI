"""Weather endpoints (FR-02)."""
from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, current_app, request

from app.api import get_services
from app.auth import auth_required
from app.extensions import db
from app.models import Location
from app.utils.responses import ApiError, success_response
from app.utils.timeutils import as_utc, utcnow

bp = Blueprint("weather", __name__, url_prefix="/api/v1/weather")


def _location_or_404(location_id: int) -> Location:
    location = db.session.get(Location, location_id)
    if location is None:
        raise ApiError(404, "Location not found.")
    return location


def _parse_date_range(default_days: int = 7):
    end = request.args.get("end")
    start = request.args.get("start")
    end_date = date.fromisoformat(end) if end else utcnow().date()
    start_date = date.fromisoformat(start) if start else end_date - timedelta(days=default_days)
    if start_date > end_date:
        raise ApiError(422, "Start date must be on or before the end date.")
    if (end_date - start_date).days > 366:
        raise ApiError(422, "Date range cannot exceed 366 days.")
    return start_date, end_date


@bp.get("/current")
@auth_required
def current_weather():
    services = get_services()
    location = _location_or_404(request.args.get("location_id", type=int) or 0)
    latest = services["weather"].latest(location)
    if latest is None:
        return success_response({"available": False, "message": "No weather observations stored for this location yet."})
    latest["location"] = location.to_dict()
    return success_response(latest)


@bp.get("/history")
@auth_required
def weather_history():
    services = get_services()
    location = _location_or_404(request.args.get("location_id", type=int) or 0)
    start, end = _parse_date_range()
    start_dt = as_utc(__import__("datetime").datetime(start.year, start.month, start.day))
    end_dt = as_utc(__import__("datetime").datetime(end.year, end.month, end.day)) + timedelta(days=1) - timedelta(seconds=1)
    rows = services["weather"].history(location.id, start_dt, end_dt)
    return success_response([w.to_dict() for w in rows], meta={"count": len(rows), "location": location.display_name})


@bp.post("/refresh")
@auth_required
def refresh_weather():
    """Manual refresh: triggers the full monitoring pipeline for one location."""
    services = get_services()
    location = _location_or_404((request.get_json(force=True, silent=True) or {}).get("location_id", 0))
    result = services["monitoring"].run_pipeline(location, trigger="manual")
    return success_response(result)
