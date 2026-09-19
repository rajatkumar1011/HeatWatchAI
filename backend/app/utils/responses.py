"""Consistent JSON API responses and structured application logging (FR-10)."""
from __future__ import annotations

import json
import logging
from typing import Any

from flask import jsonify, request

from app.extensions import db
from app.models import AuditLog, SystemLog
from app.utils.timeutils import utcnow

std_logger = logging.getLogger("heatwatch")


class ApiError(Exception):
    """An error with an HTTP status and a safe, user-facing message."""

    def __init__(self, status: int, message: str, details: Any = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details
        self.code = code or {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
                             409: "conflict", 422: "validation_error", 429: "rate_limited",
                             503: "service_unavailable"}.get(status, "error")


_DEFAULT_CODES = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
    405: "method_not_allowed", 409: "conflict", 410: "gone", 413: "payload_too_large",
    422: "validation_error", 429: "rate_limited", 500: "internal_error",
    503: "service_unavailable",
}


def error_response(status: int, message: str, details: Any = None, code: str | None = None):
    body: dict[str, Any] = {"error": {"code": code or _DEFAULT_CODES.get(status, "error"),
                                      "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return jsonify(body), status


def success_response(data: Any, status: int = 200, meta: dict | None = None):
    body: dict[str, Any] = {"data": data}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), status


def log_event(category: str, message: str, level: str = "info", details: Any = None) -> None:
    """Persist a structured system log row (best-effort; never raises)."""
    try:
        entry = SystemLog(
            level=level,
            category=category,
            message=message[:2000],
            details=json.dumps(details, default=str)[:4000] if details is not None else None,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:  # pragma: no cover - logging must never break requests
        db.session.rollback()
        std_logger.exception("failed to persist system log")


def audit(action: str, entity: str = "", entity_id: Any = "", details: Any = None) -> None:
    """Record an administrative/audit event with the acting user when known."""
    try:
        from flask_jwt_extended import verify_jwt_in_request, current_user  # local import avoids cycles

        user_id = None
        try:
            verify_jwt_in_request(optional=True)
            user_id = current_user.id if current_user else None
        except Exception:
            user_id = None
        entry = AuditLog(
            user_id=user_id,
            action=action[:120],
            entity=entity[:80],
            entity_id=str(entity_id)[:80],
            details=json.dumps(details, default=str)[:4000] if details is not None else None,
            ip_address=request.remote_addr if request else None,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:  # pragma: no cover
        db.session.rollback()
        std_logger.exception("failed to persist audit log")


def paginate(query, page: int, per_page: int, max_per_page: int = 200):
    page = max(1, page)
    per_page = min(max(1, per_page), max_per_page)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return pagination
