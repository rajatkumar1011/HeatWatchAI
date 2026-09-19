"""Monitoring pipeline orchestrator.

Implements the end-to-end workflow from the behavioural UML diagrams:
location selection -> weather retrieval -> social retrieval -> preprocessing
-> sentiment analysis -> prediction -> alert evaluation -> persistence.
Used by the scheduler, the manual refresh endpoint, the demo seeder, and
the integration test suite.
"""
from __future__ import annotations

import json
import time
from typing import Any

from app.extensions import db
from app.models import CollectionRun, Location
from app.services.alert_service import AlertService
from app.services.prediction_service import PredictionService
from app.services.sentiment_service import SentimentService
from app.services.social_service import SocialService
from app.services.weather_service import WeatherService
from app.utils.timeutils import utcnow


class MonitoringService:
    def __init__(self, config):
        self.config = config
        self.weather = WeatherService(config)
        self.social = SocialService(config)
        self.sentiment = SentimentService(config)
        self.alerts = AlertService(config)
        self.predictions = PredictionService(config, self.alerts)

    def run_pipeline(self, location: Location, trigger: str = "manual",
                     collect_social: bool = True) -> dict[str, Any]:
        """Run the full pipeline for one location. Never raises outward —
        per-step failures are reported in the structured result."""
        run = CollectionRun(job="pipeline", location_id=location.id, trigger=trigger)
        db.session.add(run)
        db.session.commit()
        started = utcnow()
        started_perf = time.perf_counter()
        result: dict[str, Any] = {"location_id": location.id, "steps": {}}

        # 1. Weather collection (FR-02); on provider failure fall back to the
        # newest stored observation (labelled cached/stale downstream).
        obs, weather_status = self.weather.fetch_and_store(location, trigger=trigger)
        result["steps"]["weather"] = {"status": weather_status,
                                      "observation_id": obs.id if obs else None}
        if obs is None:
            from sqlalchemy import select
            from app.models import WeatherObservation
            obs = db.session.execute(
                select(WeatherObservation)
                .where(WeatherObservation.location_id == location.id)
                .order_by(WeatherObservation.observed_at.desc())
                .limit(1)
            ).scalar_one_or_none()

        # 2. Social collection (FR-03)
        if collect_social:
            stored, duplicates, social_status = self.social.collect(location, trigger=trigger)
        else:
            stored = duplicates = 0
            social_status = "skipped"
        result["steps"]["social"] = {"status": social_status, "stored": stored, "duplicates": duplicates}

        # 3. Sentiment analysis + aggregation (FR-04)
        analyzed = self.sentiment.analyze_pending(location_id=location.id)
        aggregate = None
        if stored or analyzed:
            end = utcnow()
            aggregate = self.sentiment.aggregate(location.id, end.replace(hour=0, minute=0, second=0, microsecond=0), end)
        result["steps"]["sentiment"] = {"analyzed": analyzed, "aggregated": aggregate is not None}

        # 4. Prediction + alerts (FR-05, FR-06)
        prediction, prediction_status = (None, "insufficient_data")
        if obs is not None:
            prediction, prediction_status = self.predictions.run(
                location, weather_obs=obs, aggregate=aggregate, trigger=trigger)
        result["steps"]["prediction"] = {
            "status": prediction_status,
            "risk_category": prediction.risk_category if prediction else None,
            "severity_score": prediction.severity_score if prediction else None,
        }

        result["status"] = "success" if prediction is not None else "partial"
        run.status = result["status"]
        run.finished_at = utcnow()
        run.duration_ms = (time.perf_counter() - started_perf) * 1000.0
        run.result = json.dumps(result, default=str)
        db.session.commit()
        return result
