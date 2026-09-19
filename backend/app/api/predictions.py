"""Prediction endpoints (FR-05)."""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, request
from sqlalchemy import select

from app.api import get_services
from app.auth import auth_required
from app.extensions import db
from app.models import Location, Prediction
from app.utils.responses import ApiError, success_response
from app.utils.timeutils import as_utc, utcnow

bp = Blueprint("predictions", __name__, url_prefix="/api/v1/predictions")


def _location_or_404(location_id: int) -> Location:
    location = db.session.get(Location, location_id)
    if location is None:
        raise ApiError(404, "Location not found.")
    return location


@bp.get("/latest")
@auth_required
def latest_prediction():
    services = get_services()
    location = _location_or_404(request.args.get("location_id", type=int) or 0)
    prediction = db.session.execute(
        select(Prediction).where(Prediction.location_id == location.id)
        .order_by(Prediction.predicted_at.desc()).limit(1)
    ).scalar_one_or_none()
    if prediction is None:
        return success_response({"available": False})
    return success_response(prediction.to_dict())


@bp.get("/history")
@auth_required
def prediction_history():
    services = get_services()
    location = _location_or_404(request.args.get("location_id", type=int) or 0)
    days = min(request.args.get("days", 7, type=int), 90)
    start = as_utc(utcnow() - timedelta(days=days))
    rows = services["predictions"].history(location.id, start, utcnow() + timedelta(minutes=1))
    return success_response([p.to_dict() for p in rows], meta={"count": len(rows)})


@bp.post("/run")
@auth_required
def run_prediction():
    services = get_services()
    body = request.get_json(force=True, silent=True) or {}
    location = _location_or_404(body.get("location_id", 0))
    prediction, status = services["predictions"].run(location, trigger="manual")
    if prediction is None:
        raise ApiError(409, "No weather observation is available for this location yet. Refresh the weather first.")
    return success_response({**prediction.to_dict(), "status": status})
