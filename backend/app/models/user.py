"""User model and role definitions (FR-01)."""
from __future__ import annotations

from datetime import datetime

import bcrypt
import flask
from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db

BCRYPT_ROUNDS = 12

# Roles from the SRS intended-user list. Permissions are enforced in the API
# layer; see docs/traceability.md for the permissions matrix.
ROLE_ADMIN = "admin"                    # System Administrator
ROLE_OFFICER = "officer"                # Disaster Management Officer
ROLE_AUTHORITY = "authority"            # Government Authority
ROLE_RESEARCHER = "researcher"          # Environmental Researcher
ALL_ROLES = (ROLE_ADMIN, ROLE_OFFICER, ROLE_AUTHORITY, ROLE_RESEARCHER)
ROLE_LABELS = {
    ROLE_ADMIN: "System Administrator",
    ROLE_OFFICER: "Disaster Management Officer",
    ROLE_AUTHORITY: "Government Authority",
    ROLE_RESEARCHER: "Environmental Researcher",
}


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default=ROLE_RESEARCHER, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def set_password(self, password: str) -> None:
        # Full bcrypt cost in normal runs; reduced when the app runs under
        # pytest so the suite stays fast (still a real bcrypt hash).
        rounds = 4 if flask.current_app.config.get("TESTING") else BCRYPT_ROUNDS
        self.password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("utf-8")

    def check_password(self, password: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), self.password_hash.encode("utf-8"))
        except ValueError:
            return False

    def to_dict(self, include_email: bool = True) -> dict:
        data = {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "role_label": ROLE_LABELS.get(self.role, self.role),
            "is_active": self.is_active,
            "is_demo": self.is_demo,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }
        if include_email:
            data["email"] = self.email
        return data
