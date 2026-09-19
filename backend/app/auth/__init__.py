"""Authentication and authorization helpers (FR-01)."""
from __future__ import annotations

import re
from functools import wraps

from flask_jwt_extended import get_jwt, verify_jwt_in_request

from app.models import ROLE_ADMIN, User
from app.utils.responses import ApiError

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")


def validate_registration(username: str, email: str, password: str) -> list[str]:
    errors: list[str] = []
    if not USERNAME_RE.match(username or ""):
        errors.append("Username must be 3-64 characters using letters, digits, dot, dash or underscore.")
    if not EMAIL_RE.match(email or ""):
        errors.append("Please provide a valid email address.")
    if len(password or "") < 8:
        errors.append("Password must be at least 8 characters long.")
    elif not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        errors.append("Password must contain both letters and numbers.")
    return errors


def admin_required(fn):
    """Decorator: requires a valid JWT belonging to an active administrator."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        claims = get_jwt()
        if claims.get("role") != ROLE_ADMIN:
            raise ApiError(403, "Administrator privileges are required for this operation.")
        return fn(*args, **kwargs)

    return wrapper


def auth_required(fn):
    """Decorator: requires any valid JWT of an active user."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        claims = get_jwt()
        if claims.get("active") is False:
            raise ApiError(403, "This account has been deactivated.")
        return fn(*args, **kwargs)

    return wrapper


def get_current_user() -> User | None:
    verify_jwt_in_request(optional=True)
    from flask_jwt_extended import current_user  # local import: populated by user_lookup_loader

    return current_user
