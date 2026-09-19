"""Report generation endpoints (FR-08)."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, current_app, request, send_file
from pydantic import BaseModel, Field

from app.api import get_services
from app.auth import auth_required
from app.extensions import db
from app.models import Location, ReportRecord
from app.utils.responses import ApiError, audit, paginate, success_response

bp = Blueprint("reports", __name__, url_prefix="/api/v1/reports")


class ReportBody(BaseModel):
    location_id: int
    start_date: str = Field(min_length=10, max_length=10)
    end_date: str = Field(min_length=10, max_length=10)
    format: str = Field(pattern="^(pdf|csv)$")


@bp.post("/generate")
@auth_required
def generate_report():
    from flask_jwt_extended import current_user
    services = get_services()
    try:
        body = ReportBody(**request.get_json(force=True, silent=True) or {})
    except Exception:
        raise ApiError(422, "Invalid report request. Required: location_id, start_date (YYYY-MM-DD), end_date, format (pdf|csv).")

    location = db.session.get(Location, body.location_id)
    if location is None:
        raise ApiError(404, "Location not found.")
    try:
        start = date.fromisoformat(body.start_date)
        end = date.fromisoformat(body.end_date)
    except ValueError:
        raise ApiError(422, "Dates must use the YYYY-MM-DD format.")

    try:
        record = services["reports"].generate(current_user, location, start, end, body.format)
    except ValueError as exc:
        raise ApiError(422, str(exc))
    audit("report.generate", "report", record.id, {"format": record.format})
    return success_response(record.to_dict(), status=201)


@bp.get("")
@auth_required
def list_reports():
    from flask_jwt_extended import current_user, get_jwt
    stmt = db.session.query(ReportRecord).order_by(ReportRecord.generated_at.desc())
    if get_jwt().get("role") != "admin":
        stmt = stmt.filter(ReportRecord.user_id == current_user.id)
    pagination = paginate(stmt, request.args.get("page", 1, type=int), request.args.get("per_page", 20, type=int))
    return success_response([r.to_dict() for r in pagination.items],
                            meta={"page": pagination.page, "per_page": pagination.per_page, "total": pagination.total})


@bp.get("/<int:report_id>/download")
@auth_required
def download_report(report_id: int):
    from flask_jwt_extended import current_user, get_jwt
    record = db.session.get(ReportRecord, report_id)
    if record is None:
        raise ApiError(404, "Report not found.")
    if get_jwt().get("role") != "admin" and record.user_id != current_user.id:
        raise ApiError(403, "You can only download your own reports.")
    try:
        path, mime, filename = get_services()["reports"].read_record(record)
    except FileNotFoundError:
        raise ApiError(410, "The report file is no longer available in storage.")
    return send_file(path, mimetype=mime, as_attachment=True, download_name=filename)
