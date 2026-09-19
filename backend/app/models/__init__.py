"""All SQLAlchemy models. Importing this package registers every table."""
from app.models.user import ALL_ROLES, ROLE_ADMIN, ROLE_AUTHORITY, ROLE_OFFICER, ROLE_RESEARCHER, ROLE_LABELS, User
from app.models.weather import Location, WeatherObservation
from app.models.sentiment import (
    SENTIMENT_LABELS,
    SENTIMENT_NEGATIVE,
    SENTIMENT_NEUTRAL,
    SENTIMENT_POSITIVE,
    SentimentAggregate,
    SentimentResult,
    SocialPost,
)
from app.models.prediction import (
    RISK_CATEGORIES,
    RISK_HIGH,
    RISK_LOW,
    RISK_MODERATE,
    Alert,
    Prediction,
    ReportRecord,
)
from app.models.logs import (
    AppSetting,
    AuditLog,
    CollectionRun,
    EmergencyContact,
    GovernmentAdvisory,
    ModelRegistry,
    SystemLog,
)

__all__ = [
    "ALL_ROLES", "ROLE_ADMIN", "ROLE_AUTHORITY", "ROLE_OFFICER", "ROLE_RESEARCHER", "ROLE_LABELS", "User",
    "Location", "WeatherObservation",
    "SENTIMENT_LABELS", "SENTIMENT_NEGATIVE", "SENTIMENT_NEUTRAL", "SENTIMENT_POSITIVE",
    "SentimentAggregate", "SentimentResult", "SocialPost",
    "RISK_CATEGORIES", "RISK_HIGH", "RISK_LOW", "RISK_MODERATE", "Alert", "Prediction", "ReportRecord",
    "AppSetting", "AuditLog", "CollectionRun", "EmergencyContact", "GovernmentAdvisory", "ModelRegistry", "SystemLog",
]
