"""Reproducible DEMONSTRATION data seeder.

Populates the database with clearly-labelled demo records so the full
system (dashboard, sentiment, prediction, alerts, reports) can be exercised
without paid API credentials:

- 5 Indian locations,
- 30 days of synthetic weather history per location (deterministic; Mumbai
  runs a heatwave episode in the final days, Delhi a warm spell),
- ~2 weeks of demonstration public posts analysed by the REAL sentiment
  pipeline (VADER),
- daily sentiment aggregates, predictions, and threshold-triggered alerts,
- one clearly-labelled sample advisory + administrator-maintained national
  emergency contact references (public NDMA/GoI numbers),
- a demo administrator and demo users (documented demo passwords).

Everything created here carries data_mode='demo' / is_demo markers. Demo
records never claim to be real observations or real public posts.

Usage:  cd backend &&  .venv/Scripts/python seed_demo.py
Idempotent: re-running skips already-seeded rows via the normal duplicate
suppression paths.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app import create_app
from app.extensions import db
from app.models import (
    Alert,
    EmergencyContact,
    GovernmentAdvisory,
    Location,
    ModelRegistry,
    ROLE_AUTHORITY,
    ROLE_OFFICER,
    ROLE_RESEARCHER,
    User,
)
from app.utils.timeutils import as_utc, utcnow
from app.services.alert_service import AlertService
from app.services.prediction_service import PredictionService
from app.services.sentiment_service import SentimentService
from app.services.social_service import SocialService
from app.services.weather_service import WeatherService
from app.integrations.weather.demo_provider import synthetic_weather
from app.integrations.social.demo_provider import DemoSocialProvider

DEMO_PASSWORD = "Demo#12345"

LOCATIONS = [
    {"name": "Mumbai", "state": "Maharashtra", "latitude": 19.0760, "longitude": 72.8777},
    {"name": "Delhi", "state": "Delhi", "latitude": 28.6139, "longitude": 77.2090},
    {"name": "Nagpur", "state": "Maharashtra", "latitude": 21.1458, "longitude": 79.0882},
    {"name": "Chennai", "state": "Tamil Nadu", "latitude": 13.0827, "longitude": 80.2707},
    {"name": "Ahmedabad", "state": "Gujarat", "latitude": 23.0225, "longitude": 72.5714},
]

# Public national reference numbers (NDMA/GoI), administrator-maintained.
EMERGENCY_CONTACTS = [
    {"name": "National Emergency Helpline", "phone": "112", "category": "national", "notes": "All-in-one national emergency number (India)"},
    {"name": "Ambulance Service", "phone": "108", "category": "medical", "notes": "Free emergency ambulance response service"},
    {"name": "Police Helpline", "phone": "100", "category": "police", "notes": None},
    {"name": "Fire & Rescue", "phone": "101", "category": "fire", "notes": None},
    {"name": "Health Helpline", "phone": "104", "category": "medical", "notes": "Public health advice and information"},
    {"name": "NDMA Helpline", "phone": "1078", "category": "disaster", "notes": "National Disaster Management Authority"},
]


def seed(force_alerts: bool = True) -> None:
    app = create_app()
    with app.app_context():
        config = dict(app.config)
        weather_service = WeatherService(config)
        social_service = SocialService(config)
        sentiment_service = SentimentService(config)
        alerts_service = AlertService(config)
        predictions_service = PredictionService(config, alerts_service)

        # ---------------------------------------------------------------- users
        from create_admin import create_admin
        admin = create_admin("admin", "admin@heatwatch.local", "Admin#12345")

        demo_users = [
            ("officer_verma", "officer@heatwatch.local", ROLE_OFFICER),
            ("authority_rao", "authority@heatwatch.local", ROLE_AUTHORITY),
            ("researcher_iyer", "researcher@heatwatch.local", ROLE_RESEARCHER),
        ]
        for username, email, role in demo_users:
            if not db.session.query(User).filter(User.username == username).first():
                user = User(username=username, email=email, role=role, is_demo=True)
                user.set_password(DEMO_PASSWORD)
                db.session.add(user)
        db.session.commit()

        # ------------------------------------------------------------ locations
        location_map = {}
        for spec in LOCATIONS:
            location = db.session.query(Location).filter(
                Location.name == spec["name"], Location.state == spec["state"]).first()
            if location is None:
                location = Location(**spec)
                db.session.add(location)
                db.session.flush()
            location_map[spec["name"]] = location
        db.session.commit()

        # ------------------------------------------------------------- weather
        now = datetime.now(timezone.utc)
        history_days = 30
        created_weather = 0
        for location in location_map.values():
            for day_offset in range(history_days, -1, -1):
                for hour in (6, 9, 12, 15, 18):
                    when = now - timedelta(days=day_offset, hours=now.hour - hour, minutes=now.minute)
                    when = min(when, now)  # never seed future-dated observations
                    raw = synthetic_weather(location.latitude, location.longitude, location.display_name, when)
                    obs = weather_service.store_synthetic(location, raw)
                    if obs is not None:
                        created_weather += 1
        print(f"Weather observations ensured ({created_weather} new).")

        # --------------------------------------------------------------- posts
        provider = DemoSocialProvider()

        def distress_share_for(city: str, day_offset: int) -> float:
            """Heatwave scenario cities see much more distress posting."""
            from app.integrations.weather.demo_provider import DEMO_SCENARIOS, SCENARIO_LENGTH
            offsets = DEMO_SCENARIOS.get(city, [])
            day_idx = SCENARIO_LENGTH - 1 - day_offset
            bump = offsets[day_idx] if 0 <= day_idx < len(offsets) else 0.0
            if bump >= 5.0:
                return 0.55
            if bump >= 1.0:
                return 0.30
            return 0.08

        created_posts = 0
        for location in location_map.values():
            city = location.name.split(",")[0].strip()
            for day_offset in range(13, -1, -1):
                end = now - timedelta(days=day_offset)
                start = end - timedelta(days=1)
                posts = provider.search([], location.display_name, start, end, limit=14,
                                        distress_share=distress_share_for(city, day_offset))
                for raw in posts:
                    post, inserted = social_service.insert_post(
                        source_platform=raw["source_platform"],
                        text=raw["text"],
                        published_at=raw["published_at"],
                        external_id=raw["external_id"],
                        author_handle=raw["author_handle"],
                        location_id=location.id if raw.get("raw_location_label") else None,
                        raw_location_label=raw.get("raw_location_label"),
                        data_mode="demo",
                    )
                    if inserted:
                        created_posts += 1
        db.session.commit()
        print(f"Demonstration posts ensured ({created_posts} new).")

        # ----------------------------------------------------------- sentiment
        analyzed = sentiment_service.analyze_pending(limit=100000)
        print(f"Sentiment analyzed for {analyzed} posts.")

        # ---------------------------------------------------------- aggregates
        for location in location_map.values():
            sentiment_service.aggregate_daily(location.id, days=14, data_mode="demo")
        print("Daily sentiment aggregates ensured (14 days).")

        # ------------------------------------------------- predictions + alerts
        created_predictions = 0
        for location in location_map.values():
            from sqlalchemy import select
            from app.models import SentimentAggregate, WeatherObservation
            aggregates = list(db.session.execute(
                select(SentimentAggregate).where(SentimentAggregate.location_id == location.id)
                .order_by(SentimentAggregate.window_end.asc())
            ).scalars())
            for aggregate in aggregates:
                noon_target = aggregate.window_start + timedelta(hours=9)
                day_obs = db.session.execute(
                    select(WeatherObservation).where(
                        WeatherObservation.location_id == location.id,
                        WeatherObservation.observed_at >= aggregate.window_start,
                        WeatherObservation.observed_at < aggregate.window_end,
                    )
                ).scalars().all()
                if not day_obs:
                    continue
                obs = min(day_obs, key=lambda o: abs((o.observed_at - noon_target).total_seconds()))
                prediction_time = min(now, as_utc(obs.observed_at) + timedelta(hours=1))
                prediction, status = predictions_service.run(
                    location, weather_obs=obs, aggregate=aggregate, trigger="seed",
                    alert_now_override=prediction_time)
                if status == "created":
                    created_predictions += 1
                # Backdate the prediction and its alerts to the assessment
                # time so severity history reflects when each condition
                # occurred (not the seeding wall-clock moment).
                db.session.expire_all()
                prediction.predicted_at = prediction_time
                for alert in db.session.execute(
                    select(Alert).where(Alert.prediction_id == prediction.id)
                ).scalars().all():
                    alert.generated_at = as_utc(prediction_time)
                db.session.commit()
        print(f"Predictions ensured ({created_predictions} created).")

        # ------------------------------------------------------------ advisory
        if not db.session.query(GovernmentAdvisory).first():
            advisory = GovernmentAdvisory(
                title="[DEMO] Sample advisory — Heatwave conditions likely to continue",
                body=("Demonstration content: heatwave conditions are likely to continue. Avoid direct sunlight, "
                      "stay hydrated, wear light clothing, and check on elderly neighbours and children. "
                      "This is sample content seeded for demonstration purposes and is NOT an official "
                      "government advisory."),
                source_name="HeatWatch AI demonstration seed (not an official source)",
                published_at=now - timedelta(hours=6),
                is_demo=True,
            )
            db.session.add(advisory)

        # ------------------------------------------------------------ contacts
        if not db.session.query(EmergencyContact).first():
            for contact in EMERGENCY_CONTACTS:
                db.session.add(EmergencyContact(**contact, is_active=True))

        # ------------------------------------------------------ model registry
        from app.ml.train_severity import META_PATH
        if META_PATH.exists():
            meta = json.loads(META_PATH.read_text(encoding="utf-8"))
            if not db.session.query(ModelRegistry).filter(ModelRegistry.name == "severity").first():
                db.session.add(ModelRegistry(
                    name="severity", version=meta["model_version"],
                    artifact_path=str(meta.get("artifact_path") or ""),
                    trained_at=datetime.fromisoformat(meta["trained_at"]),
                    metrics=json.dumps(meta.get("evaluation", {})),
                    notes="Weather-based RandomForest trained on the documented heat-index banding dataset.",
                    is_active=True,
                ))
        db.session.commit()
        print("Advisory, emergency contacts, and model registry ensured.")
        print("\nDemo accounts: admin/Admin#12345, officer_verma, authority_rao, researcher_iyer (Demo#12345)")
        print("NOTE: all seeded data is DEMONSTRATION data (data_mode='demo').")


if __name__ == "__main__":
    from sqlalchemy import text  # noqa: F401
    seed()
