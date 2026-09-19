"""Initial administrator setup (secure bootstrap, FR-01).

Administrators are NEVER created through public registration. This script
is the controlled setup path:

    cd backend
    .venv/Scripts/python create_admin.py --username admin --email admin@example.com --password 'S3curePass'

If arguments are omitted it falls back to ADMIN_USERNAME / ADMIN_EMAIL /
ADMIN_PASSWORD environment variables; passwords are never committed.
"""
from __future__ import annotations

import argparse
import os
import sys

from app import create_app
from app.extensions import db
from app.models import ROLE_ADMIN, User


def create_admin(username: str, email: str, password: str) -> User:
    app = create_app()
    with app.app_context():
        existing = db.session.query(User).filter(
            (User.username == username.lower()) | (User.email == email.lower())
        ).first()
        if existing is not None:
            if existing.role == ROLE_ADMIN:
                print(f"Administrator '{existing.username}' already exists — nothing to do.")
                return existing
            existing.role = ROLE_ADMIN
            db.session.commit()
            print(f"Existing user '{existing.username}' promoted to administrator.")
            return existing
        user = User(username=username.lower(), email=email.lower(), role=ROLE_ADMIN)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"Administrator '{user.username}' created.")
        return user


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create the initial HeatWatch AI administrator.")
    parser.add_argument("--username", default=os.getenv("ADMIN_USERNAME"))
    parser.add_argument("--email", default=os.getenv("ADMIN_EMAIL"))
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD"))
    args = parser.parse_args()
    if not (args.username and args.email and args.password):
        parser.error("--username, --email and --password are required (or set ADMIN_USERNAME/ADMIN_EMAIL/ADMIN_PASSWORD).")
    sys.exit(0 if create_admin(args.username, args.email, args.password) else 1)
