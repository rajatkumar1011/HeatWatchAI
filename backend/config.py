"""Application configuration for HeatWatch AI.

All secrets and environment-specific values are read from environment
variables (or a .env file) — never hardcoded. See .env.example at the
repository root.
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Config:
    """Base configuration shared by all environments."""

    APP_NAME = "HeatWatch AI"
    APP_TAGLINE = "AI-Based Climate Intelligence for Heatwave Monitoring, Prediction, and Early Warning"

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-only-change-me")

    # ------------------------------------------------------------- database
    # MySQL is the documented production target (SRS section 2.3.3).
    # When DATABASE_URL is not provided the app falls back to a local SQLite
    # file so the system still runs with genuine persistence on machines
    # without a MySQL server. docker-compose.yml provisions MySQL 8.
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(BASE_DIR / 'heatwatch_dev.db').as_posix()}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # ------------------------------------------------------------------ JWT
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=_int("JWT_ACCESS_TOKEN_HOURS", 12))
    JWT_ERROR_MESSAGE_KEY = "message"

    # ------------------------------------------------------------- data mode
    # "auto": use live providers when their credentials exist, otherwise the
    #         clearly-labelled demonstration providers.
    # "live": require live providers (fail loudly if unconfigured).
    # "demo": force demonstration providers for everything.
    DATA_MODE = os.getenv("DATA_MODE", "auto").strip().lower()

    # ----------------------------------------------------------------- APIs
    OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
    OPENWEATHER_BASE_URL = os.getenv("OPENWEATHER_BASE_URL", "https://api.openweathermap.org/data/2.5")
    WEATHER_TIMEOUT_SECONDS = _float("WEATHER_TIMEOUT_SECONDS", 10.0)
    API_MAX_RETRIES = _int("API_MAX_RETRIES", 3)  # SRS 2.5.1: retry up to three times

    SOCIAL_PROVIDER = os.getenv("SOCIAL_PROVIDER", "auto").strip().lower()  # auto|demo|reddit
    REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "HeatWatchAI/1.0 (student research project)")
    SOCIAL_TIMEOUT_SECONDS = _float("SOCIAL_TIMEOUT_SECONDS", 10.0)

    # --------------------------------------------------------- collection
    WEATHER_COLLECTION_MINUTES = _int("WEATHER_COLLECTION_MINUTES", 30)
    SOCIAL_COLLECTION_MINUTES = _int("SOCIAL_COLLECTION_MINUTES", 60)
    WEATHER_FRESH_MINUTES = _int("WEATHER_FRESH_MINUTES", 90)

    # ------------------------------------------------------------- alerts
    ALERT_HIGH_THRESHOLD = _float("ALERT_HIGH_THRESHOLD", 70.0)      # severity score 0-100
    ALERT_MODERATE_THRESHOLD = _float("ALERT_MODERATE_THRESHOLD", 40.0)
    ALERT_COOLDOWN_MINUTES = _int("ALERT_COOLDOWN_MINUTES", 180)
    ALERTS_ENABLED = _bool("ALERTS_ENABLED", "true")

    # ------------------------------------------------------- rate limiting
    AUTH_RATE_LIMIT = _int("AUTH_RATE_LIMIT", 10)  # attempts per window per IP
    AUTH_RATE_LIMIT_WINDOW_MINUTES = _int("AUTH_RATE_LIMIT_WINDOW_MINUTES", 15)
    MAX_JSON_BODY_BYTES = _int("MAX_JSON_BODY_BYTES", 256 * 1024)

    # ------------------------------------------------------------- reports
    REPORT_OUTPUT_DIR = Path(os.getenv("REPORT_OUTPUT_DIR", str(BASE_DIR / "generated_reports")))
    REPORT_MAX_ROWS_CSV = _int("REPORT_MAX_ROWS_CSV", 100000)

    # --------------------------------------------------------- presentation
    DISPLAY_TIMEZONE = os.getenv("DISPLAY_TIMEZONE", "Asia/Kolkata")

    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]

    DEMO_MODE_DEFAULT = _bool("DEMO_MODE_DEFAULT", "true")


class DevelopmentConfig(Config):
    DEBUG = _bool("FLASK_DEBUG", "true")


class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite://")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    REPORT_OUTPUT_DIR = Path(BASE_DIR / "tests" / "_generated_reports")
    DATA_MODE = "demo"
    ALERTS_ENABLED = True


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False


_CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config() -> type[Config]:
    env = os.getenv("FLASK_ENV", "development").strip().lower()
    return _CONFIGS.get(env, DevelopmentConfig)
