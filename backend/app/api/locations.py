"""Location management endpoints."""
from __future__ import annotations

from flask import Blueprint, request
from pydantic import BaseModel, Field

from app.auth import admin_required, auth_required
from app.extensions import db
from app.models import Location
from app.utils.responses import ApiError, audit, paginate, success_response

bp = Blueprint("locations", __name__, url_prefix="/api/v1/locations")


def _get_location(location_id: int) -> Location:
    location = db.session.get(Location, location_id)
    if location is None:
        raise ApiError(404, "Location not found.")
    return location


@bp.get("")
@auth_required
def list_locations():
    stmt = db.session.query(Location).order_by(Location.name.asc())
    if request.args.get("monitored") in ("1", "true"):
        stmt = stmt.filter(Location.is_monitored.is_(True))
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 100, type=int)
    pagination = paginate(stmt, page, per_page, max_per_page=500)
    return success_response(
        [loc.to_dict() for loc in pagination.items],
        meta={"page": pagination.page, "per_page": pagination.per_page, "total": pagination.total},
    )


@bp.get("/<int:location_id>")
@auth_required
def get_location(location_id: int):
    return success_response(_get_location(location_id).to_dict())


class LocationBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    state: str = Field(default="", max_length=120)
    country: str = Field(default="India", max_length=80)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    is_monitored: bool = True


@bp.post("")
@admin_required
def create_location():
    try:
        body = LocationBody(**request.get_json(force=True, silent=True) or {})
    except Exception:
        raise ApiError(422, "Invalid location payload.")
    location = Location(**body.model_dump())
    db.session.add(location)
    db.session.commit()
    audit("location.create", "location", location.id, body.model_dump())
    return success_response(location.to_dict(), status=201)


@bp.put("/<int:location_id>")
@admin_required
def update_location(location_id: int):
    location = _get_location(location_id)
    try:
        body = LocationBody(**request.get_json(force=True, silent=True) or {})
    except Exception:
        raise ApiError(422, "Invalid location payload.")
    for field, value in body.model_dump().items():
        setattr(location, field, value)
    db.session.commit()
    audit("location.update", "location", location.id, body.model_dump())
    return success_response(location.to_dict())


@bp.delete("/<int:location_id>")
@admin_required
def delete_location(location_id: int):
    location = _get_location(location_id)
    db.session.delete(location)
    db.session.commit()
    audit("location.delete", "location", location.id)
    return success_response({"message": "Location deleted."})
