"""Shared pytest fixtures. Tests run against an in-memory SQLite database
with the demonstration providers (no external API credentials required).

IMPORTANT: the testing config class is passed INTO create_app so that the
in-memory URI is in place before Flask-SQLAlchemy creates its engines.
(Overriding app.config afterwards would leave the engines bound to the real
development database file — which previously caused the suite to create and
drop tables in heatwatch_dev.db.)
"""
from __future__ import annotations

import pytest

from app import create_app
from config import TestingConfig
from app.extensions import db as _db
from app.models import ROLE_ADMIN, ROLE_RESEARCHER, Location, User


@pytest.fixture()
def app():
    from app.utils.rate_limit import clear_rate_limits

    app = create_app(TestingConfig)
    # Rate limits are read from config at request time; raise the ceiling for
    # tests (the limiter itself is covered by a dedicated test).
    app.config["AUTH_RATE_LIMIT"] = 10000
    clear_rate_limits()
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()
    clear_rate_limits()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def services(app):
    from app.services.alert_service import AlertService
    from app.services.monitoring_service import MonitoringService
    from app.services.prediction_service import PredictionService
    from app.services.sentiment_service import SentimentService
    from app.services.social_service import SocialService
    from app.services.weather_service import WeatherService

    config = app.config
    alerts = AlertService(config)
    return {
        "weather": WeatherService(config),
        "social": SocialService(config),
        "sentiment": SentimentService(config),
        "alerts": alerts,
        "predictions": PredictionService(config, alerts),
        "monitoring": MonitoringService(config),
    }


@pytest.fixture()
def location(db):
    loc = Location(name="Mumbai", state="Maharashtra", latitude=19.0760, longitude=72.8777)
    db.session.add(loc)
    db.session.commit()
    return loc


@pytest.fixture()
def second_location(db):
    loc = Location(name="Nagpur", state="Maharashtra", latitude=21.1458, longitude=79.0882)
    db.session.add(loc)
    db.session.commit()
    return loc


def _make_user(db, username: str, role: str) -> User:
    user = User(username=username, email=f"{username}@test.local", role=role)
    user.set_password("Passw0rd1")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def admin_user(db):
    return _make_user(db, "admin_t", ROLE_ADMIN)


@pytest.fixture()
def normal_user(db):
    return _make_user(db, "user_t", ROLE_RESEARCHER)


def auth_header(client, username: str, password: str = "Passw0rd1") -> dict:
    resp = client.post("/api/v1/auth/login", json={"identifier": username, "password": password})
    assert resp.status_code == 200, resp.get_json()
    token = resp.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(client, admin_user):
    return auth_header(client, "admin_t")


@pytest.fixture()
def user_headers(client, normal_user):
    return auth_header(client, "user_t")
