"""Administration endpoints (FR-09). Admin-only, audited."""
from __future__ import annotations

import json

from flask import Blueprint, request
from pydantic import BaseModel
from sqlalchemy import func, select

from app.auth import admin_required
from app.extensions import db
from app.models import (
    ALL_ROLES,
    ROLE_ADMIN,
    Alert,
    AppSetting,
    AuditLog,
    CollectionRun,
    EmergencyContact,
    GovernmentAdvisory,
    Location,
    ModelRegistry,
    Prediction,
    SentimentAggregate,
    SentimentResult,
    SocialPost,
    SystemLog,
    User,
    WeatherObservation,
)
from app.utils.responses import ApiError, audit, paginate, success_response
from app.utils.timeutils import utcnow

bp = Blueprint("admin", __name__, url_prefix="/api/v1/admin")

# ---------------------------------------------------------------- users


@bp.get("/users")
@admin_required
def list_users():
    stmt = db.session.query(User).order_by(User.created_at.asc())
    search = (request.args.get("search") or "").strip().lower()
    if search:
        stmt = stmt.filter(
            (func.lower(User.username).contains(search)) |
            (func.lower(User.email).contains(search))
        )
    role = request.args.get("role")
    if role in ALL_ROLES:
        stmt = stmt.filter(User.role == role)
    pagination = paginate(stmt, request.args.get("page", 1, type=int), request.args.get("per_page", 20, type=int))
    return success_response([u.to_dict() for u in pagination.items],
                            meta={"page": pagination.page, "per_page": pagination.per_page, "total": pagination.total})


class UserUpdateBody(BaseModel):
    role: str | None = None
    is_active: bool | None = None


@bp.put("/users/<int:user_id>")
@admin_required
def update_user(user_id: int):
    try:
        body = UserUpdateBody(**(request.get_json(force=True, silent=True) or {}))
    except Exception:
        raise ApiError(422, "Invalid user update payload.")
    user = db.session.get(User, user_id)
    if user is None:
        raise ApiError(404, "User not found.")

    from flask_jwt_extended import get_jwt

    acting_is_self = int(get_jwt()["sub"]) == user.id
    if body.role is not None:
        if body.role not in ALL_ROLES:
            raise ApiError(422, f"Role must be one of: {', '.join(ALL_ROLES)}.")
        if acting_is_self and user.role == ROLE_ADMIN and body.role != ROLE_ADMIN:
            # Prevent removing your own admin role when no other admin exists.
            other_admins = db.session.execute(
                select(func.count(User.id)).where(User.role == ROLE_ADMIN, User.id != user.id, User.is_active.is_(True))
            ).scalar()
            if not other_admins:
                raise ApiError(409, "Cannot demote the last active administrator.")
        user.role = body.role
    if body.is_active is not None:
        if acting_is_self and user.is_active and not body.is_active:
            other_admins = db.session.execute(
                select(func.count(User.id)).where(User.role == ROLE_ADMIN, User.id != user.id, User.is_active.is_(True))
            ).scalar()
            if user.role == ROLE_ADMIN and not other_admins:
                raise ApiError(409, "Cannot deactivate the last active administrator.")
        user.is_active = body.is_active
    db.session.commit()
    audit("user.update", "user", user.id, body.model_dump(exclude_none=True))
    return success_response(user.to_dict())


# ------------------------------------------------------------ settings

SETTING_KEYS = {
    "alert_high_threshold": (float, 0, 100),
    "alert_moderate_threshold": (float, 0, 100),
    "alert_cooldown_minutes": (int, 1, 10080),
    "alerts_enabled": (bool, None, None),
    "alert_on_moderate": (bool, None, None),
    "weather_collection_minutes": (int, 5, 1440),
    "social_collection_minutes": (int, 15, 10080),
}


@bp.get("/settings")
@admin_required
def get_settings():
    rows = {r.key: r for r in db.session.execute(select(AppSetting)).scalars()}
    from flask import current_app
    result = {}
    for key, (typ, _lo, _hi) in SETTING_KEYS.items():
        if key in rows and rows[key].value is not None:
            try:
                result[key] = typ(json.loads(rows[key].value))
            except (json.JSONDecodeError, ValueError):
                result[key] = current_app.config.get(key.upper(), None)
        else:
            cfg_key = key.upper()
            result[key] = current_app.config.get(cfg_key, None)
    # keyword configuration passthrough
    from app.services.social_service import get_keywords
    from app.services.sentiment_service import (
        DISTRESS_KEYWORDS_SETTING,
        HEAT_RELEVANCE_KEYWORDS_SETTING,
        _setting_keywords,
        DISTRESS_KEYWORDS,
        HEAT_RELEVANCE_KEYWORDS,
    )
    result["social_keywords"] = get_keywords()
    result["heat_relevance_keywords"] = _setting_keywords(HEAT_RELEVANCE_KEYWORDS_SETTING, HEAT_RELEVANCE_KEYWORDS)
    result["distress_keywords"] = _setting_keywords(DISTRESS_KEYWORDS_SETTING, DISTRESS_KEYWORDS)
    return success_response(result)


@bp.put("/settings")
@admin_required
def update_settings():
    from flask_jwt_extended import current_user
    payload = request.get_json(force=True, silent=True) or {}
    if not isinstance(payload, dict):
        raise ApiError(422, "Settings payload must be an object.")
    updated = []
    for key, value in payload.items():
        if key in ("social_keywords", "heat_relevance_keywords", "distress_keywords"):
            if not isinstance(value, list) or not all(isinstance(k, str) for k in value):
                raise ApiError(422, f"{key} must be a list of strings.")
            row = db.session.get(AppSetting, key)
            if row is None:
                row = AppSetting(key=key, description=f"{key} list")
                db.session.add(row)
            row.value = json.dumps(value)
            row.updated_by = current_user.id
            updated.append(key)
        elif key in SETTING_KEYS:
            typ, lo, hi = SETTING_KEYS[key]
            try:
                value = typ(value)
                if lo is not None and not (lo <= value <= hi):
                    raise ValueError
            except (TypeError, ValueError):
                raise ApiError(422, f"{key} must be {typ.__name__} in range [{lo}, {hi}].")
            row = db.session.get(AppSetting, key)
            if row is None:
                row = AppSetting(key=key, description=key.replace("_", " "))
                db.session.add(row)
            row.value = json.dumps(value)
            row.updated_by = current_user.id
            updated.append(key)
        else:
            raise ApiError(422, f"Unknown setting '{key}'.")
    db.session.commit()
    audit("settings.update", "setting", ",".join(updated), payload)
    return success_response({"updated": updated})


# ------------------------------------------------------------ logs, stats

@bp.get("/logs")
@admin_required
def list_logs():
    stmt = db.session.query(SystemLog).order_by(SystemLog.created_at.desc())
    category = request.args.get("category")
    if category:
        stmt = stmt.filter(SystemLog.category == category)
    level = request.args.get("level")
    if level:
        stmt = stmt.filter(SystemLog.level == level)
    pagination = paginate(stmt, request.args.get("page", 1, type=int), request.args.get("per_page", 50, type=int))
    return success_response([l.to_dict() for l in pagination.items],
                            meta={"page": pagination.page, "per_page": pagination.per_page, "total": pagination.total})


@bp.get("/audit")
@admin_required
def list_audit():
    stmt = db.session.query(AuditLog).order_by(AuditLog.created_at.desc())
    pagination = paginate(stmt, request.args.get("page", 1, type=int), request.args.get("per_page", 50, type=int))
    return success_response([a.to_dict() for a in pagination.items],
                            meta={"page": pagination.page, "per_page": pagination.per_page, "total": pagination.total})


@bp.get("/data-stats")
@admin_required
def data_stats():
    counts = {}
    for name, model in [("users", User), ("locations", Location), ("weather_observations", WeatherObservation),
                        ("social_posts", SocialPost), ("sentiment_results", SentimentResult),
                        ("sentiment_aggregates", SentimentAggregate), ("predictions", Prediction),
                        ("alerts", Alert)]:
        counts[name] = db.session.execute(select(func.count(model.id))).scalar()
    by_mode = {}
    for row in db.session.execute(
        select(WeatherObservation.data_mode, func.count(WeatherObservation.id)).group_by(WeatherObservation.data_mode)
    ).all():
        by_mode[f"weather_{row[0]}"] = row[1]
    for row in db.session.execute(
        select(SocialPost.data_mode, func.count(SocialPost.id)).group_by(SocialPost.data_mode)
    ).all():
        by_mode[f"social_{row[0]}"] = row[1]
    return success_response({"counts": counts, "by_data_mode": by_mode})


@bp.get("/model-status")
@admin_required
def model_status():
    rows = list(db.session.execute(select(ModelRegistry).order_by(ModelRegistry.created_at.desc())).scalars())
    from app.services.prediction_service import get_severity_predictor
    predictor = get_severity_predictor()
    return success_response({
        "severity_model": {
            "loaded": predictor.available,
            "version": predictor.version if predictor.available else "rule-based fallback",
            "evaluation": predictor.meta.get("evaluation") if predictor.available else None,
            "limitations": predictor.meta.get("limitations") if predictor.available else [
                "No model artifact present; the documented rule-based heat-index fallback is in use."],
        },
        "registry": [r.to_dict() for r in rows],
    })


@bp.get("/runs")
@admin_required
def collection_runs():
    stmt = db.session.query(CollectionRun).order_by(CollectionRun.started_at.desc())
    job = request.args.get("job")
    if job:
        stmt = stmt.filter(CollectionRun.job == job)
    pagination = paginate(stmt, request.args.get("page", 1, type=int), request.args.get("per_page", 30, type=int))
    return success_response([{
        "id": r.id, "job": r.job, "location_id": r.location_id, "trigger": r.trigger,
        "status": r.status, "duration_ms": r.duration_ms, "result": r.result,
        "started_at": r.started_at.isoformat(), "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    } for r in pagination.items],
        meta={"page": pagination.page, "per_page": pagination.per_page, "total": pagination.total})


# ---------------------------------------------------- advisories & contacts


class AdvisoryBody(BaseModel):
    title: str
    body: str
    source_name: str
    source_url: str | None = None
    is_demo: bool = False
    location_id: int | None = None
    is_active: bool = True


@bp.get("/advisories")
@admin_required
def list_advisories():
    rows = list(db.session.execute(select(GovernmentAdvisory).order_by(GovernmentAdvisory.created_at.desc())).scalars())
    return success_response([a.to_dict() for a in rows])


@bp.post("/advisories")
@admin_required
def create_advisory():
    try:
        body = AdvisoryBody(**(request.get_json(force=True, silent=True) or {}))
    except Exception:
        raise ApiError(422, "Invalid advisory payload.")
    advisory = GovernmentAdvisory(**body.model_dump())
    db.session.add(advisory)
    db.session.commit()
    audit("advisory.create", "advisory", advisory.id)
    return success_response(advisory.to_dict(), status=201)


@bp.delete("/advisories/<int:advisory_id>")
@admin_required
def delete_advisory(advisory_id: int):
    advisory = db.session.get(GovernmentAdvisory, advisory_id)
    if advisory is None:
        raise ApiError(404, "Advisory not found.")
    db.session.delete(advisory)
    db.session.commit()
    audit("advisory.delete", "advisory", advisory_id)
    return success_response({"message": "Advisory deleted."})


class ContactBody(BaseModel):
    name: str
    phone: str
    category: str = "general"
    notes: str | None = None
    is_active: bool = True


@bp.get("/contacts")
@admin_required
def list_contacts():
    rows = list(db.session.execute(select(EmergencyContact).order_by(EmergencyContact.category)).scalars())
    return success_response([c.to_dict() for c in rows])


@bp.post("/contacts")
@admin_required
def create_contact():
    try:
        body = ContactBody(**(request.get_json(force=True, silent=True) or {}))
    except Exception:
        raise ApiError(422, "Invalid contact payload.")
    contact = EmergencyContact(**body.model_dump())
    db.session.add(contact)
    db.session.commit()
    audit("contact.create", "contact", contact.id)
    return success_response(contact.to_dict(), status=201)


@bp.delete("/contacts/<int:contact_id>")
@admin_required
def delete_contact(contact_id: int):
    contact = db.session.get(EmergencyContact, contact_id)
    if contact is None:
        raise ApiError(404, "Contact not found.")
    db.session.delete(contact)
    db.session.commit()
    audit("contact.delete", "contact", contact_id)
    return success_response({"message": "Contact deleted."})
