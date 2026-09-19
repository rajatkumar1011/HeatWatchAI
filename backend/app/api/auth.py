"""Authentication endpoints (FR-01)."""
from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import create_access_token, get_jwt, jwt_required
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.api import get_services  # noqa: F401  (availability for other modules)
from app.auth import validate_registration
from app.extensions import db
from app.models import ROLE_RESEARCHER, User
from app.utils.rate_limit import enforce_rate_limit
from app.utils.responses import ApiError, audit, error_response, log_event, success_response
from app.utils.timeutils import utcnow

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


class RegisterBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)
    password_confirm: str = Field(min_length=1, max_length=128)

    @field_validator("username", "email", "password")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()


class LoginBody(BaseModel):
    identifier: str = Field(min_length=1, max_length=255)  # username or email
    password: str = Field(min_length=1, max_length=128)


@bp.post("/register")
def register():
    from flask import current_app
    enforce_rate_limit(f"register:{request.remote_addr}",
                       current_app.config["AUTH_RATE_LIMIT"],
                       current_app.config["AUTH_RATE_LIMIT_WINDOW_MINUTES"] * 60)
    try:
        body = RegisterBody(**request.get_json(force=True, silent=True) or {})
    except Exception:
        raise ApiError(422, "Invalid request payload.")
    if body.password != body.password_confirm:
        raise ApiError(422, "Passwords do not match.", details={"password_confirm": "Passwords do not match."})

    errors = validate_registration(body.username, body.email, body.password)
    if errors:
        raise ApiError(422, "Please correct the highlighted fields.", details={"messages": errors})

    username, email = body.username.lower(), body.email.lower()
    if db.session.execute(select(User.id).where(User.username == username)).scalar_one_or_none():
        raise ApiError(409, "An account with this username already exists.")
    if db.session.execute(select(User.id).where(User.email == email)).scalar_one_or_none():
        raise ApiError(409, "An account with this email address already exists.")

    user = User(username=username, email=email, role=ROLE_RESEARCHER)
    user.set_password(body.password)
    db.session.add(user)
    db.session.commit()
    log_event("auth", f"New registration: {username}")
    return success_response({
        "user": user.to_dict(),
        "message": "Registration successful. You can now log in.",
    }, status=201)


def _issue_token(user: User) -> dict:
    token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role, "active": user.is_active, "username": user.username},
    )
    return {"access_token": token, "token_type": "bearer", "user": user.to_dict()}


@bp.post("/login")
def login():
    from flask import current_app
    enforce_rate_limit(f"login:{request.remote_addr}",
                       current_app.config["AUTH_RATE_LIMIT"],
                       current_app.config["AUTH_RATE_LIMIT_WINDOW_MINUTES"] * 60)
    try:
        body = LoginBody(**request.get_json(force=True, silent=True) or {})
    except Exception:
        raise ApiError(422, "Invalid request payload.")

    identifier = body.identifier.strip().lower()
    user = db.session.execute(
        select(User).where((User.username == identifier) | (User.email == identifier))
    ).scalar_one_or_none()

    if user is None or not user.check_password(body.password):
        raise ApiError(401, "Incorrect username/email or password.")
    if not user.is_active:
        raise ApiError(403, "This account has been deactivated. Contact an administrator.")

    user.last_login_at = utcnow()
    db.session.commit()
    return success_response(_issue_token(user))


@bp.post("/logout")
@jwt_required()
def logout():
    # Stateless JWT: the client discards the token. Claim-based revocation
    # would require a shared store; documented in the deployment notes.
    return success_response({"message": "Logged out."})


@bp.get("/me")
@jwt_required()
def me():
    from flask_jwt_extended import current_user
    return success_response({"user": current_user.to_dict()})


class ProfileUpdateBody(BaseModel):
    email: str | None = None
    current_password: str | None = None
    new_password: str | None = None


@bp.put("/me")
@jwt_required()
def update_me():
    from flask_jwt_extended import current_user
    try:
        body = ProfileUpdateBody(**(request.get_json(force=True, silent=True) or {}))
    except Exception:
        raise ApiError(422, "Invalid request payload.")

    if body.new_password:
        if not body.current_password or not current_user.check_password(body.current_password):
            raise ApiError(401, "Current password is incorrect.")
        errors = validate_registration(current_user.username, current_user.email, body.new_password)
        if errors:
            raise ApiError(422, "New password does not meet the requirements.", details={"messages": errors})
        current_user.set_password(body.new_password)

    if body.email and body.email.strip().lower() != current_user.email:
        from app.auth import EMAIL_RE
        new_email = body.email.strip().lower()
        if not EMAIL_RE.match(new_email):
            raise ApiError(422, "Please provide a valid email address.")
        exists = db.session.execute(select(User.id).where(User.email == new_email, User.id != current_user.id)).scalar_one_or_none()
        if exists:
            raise ApiError(409, "Another account already uses this email address.")
        current_user.email = new_email

    db.session.commit()
    return success_response({"user": current_user.to_dict(), "message": "Profile updated."})
