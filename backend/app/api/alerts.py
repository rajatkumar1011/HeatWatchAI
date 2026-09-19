"""Alert endpoints (FR-06)."""
from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, request

from app.api import get_services
from app.auth import auth_required
from app.extensions import db
from app.models import Alert
from app.utils.responses import ApiError, audit, paginate, success_response
from app.utils.timeutils import as_utc, utcnow

bp = Blueprint("alerts", __name__, url_prefix="/api/v1/alerts")


@bp.get("")
@auth_required
def list_alerts():
    services = get_services()
    location_id = request.args.get("location_id", type=int)
    status = request.args.get("status") or None
    days = request.args.get("days", type=int)
    start = as_utc(utcnow() - timedelta(days=days)) if days else None
    alerts = services["alerts"].history(location_id=location_id, start=start, status=status)
    page = paginate(db.session.query(Alert).filter(Alert.id.in_([a.id for a in alerts] or [0])),
                    request.args.get("page", 1, type=int), request.args.get("per_page", 25, type=int))
    return success_response([a.to_dict() for a in page.items],
                            meta={"page": page.page, "per_page": page.per_page,
                                  "total": len(alerts), "active_count": sum(1 for a in alerts if a.status == "active")})


@bp.post("/<int:alert_id>/acknowledge")
@auth_required
def acknowledge_alert(alert_id: int):
    from flask_jwt_extended import current_user
    services = get_services()
    alert = db.session.get(Alert, alert_id)
    if alert is None:
        raise ApiError(404, "Alert not found.")
    alert = services["alerts"].acknowledge(alert, current_user.id)
    audit("alert.acknowledge", "alert", alert.id)
    return success_response(alert.to_dict())


@bp.post("/<int:alert_id>/resolve")
@auth_required
def resolve_alert(alert_id: int):
    services = get_services()
    alert = db.session.get(Alert, alert_id)
    if alert is None:
        raise ApiError(404, "Alert not found.")
    alert = services["alerts"].resolve(alert)
    audit("alert.resolve", "alert", alert.id)
    return success_response(alert.to_dict())
