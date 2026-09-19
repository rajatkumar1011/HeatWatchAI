"""Heatwave severity prediction service (FR-05).

Pipeline per assessment:
  1. inputs = latest weather observation + latest 24h sentiment aggregate
  2. weather-only risk from the severity model (ML artifact or documented
     rule fallback)
  3. transparent rule-based fusion: heat-related distress signals can RAISE
     the score (bounded); they can never lower the weather-based assessment
  4. fused score -> risk category bands (< 40 low, 40-69 moderate, >= 70 high)
  5. persist Prediction with full provenance, then trigger alert evaluation

Duplicate avoidance: when neither input changed since the newest stored
prediction, that prediction is returned instead of creating a new row.
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.ml.inference import SeverityPredictor
from app.models import (
    Prediction,
    SentimentAggregate,
    WeatherObservation,
)
from app.utils.timeutils import as_utc, utcnow

_predictor: SeverityPredictor | None = None


def get_severity_predictor() -> SeverityPredictor:
    global _predictor
    if _predictor is None:
        _predictor = SeverityPredictor()
    return _predictor


def reset_severity_predictor() -> None:
    """Force reload of the artifact (used after training)."""
    global _predictor
    _predictor = None


FUSION_VERSION = "rule_fusion_v1"


class PredictionService:
    def __init__(self, config, alert_service):
        self.config = config
        self.alert_service = alert_service

    # ------------------------------------------------------------- helpers
    def latest_weather(self, location_id: int) -> WeatherObservation | None:
        return db.session.execute(
            select(WeatherObservation)
            .where(WeatherObservation.location_id == location_id)
            .order_by(WeatherObservation.observed_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def latest_aggregate(self, location_id: int, max_age_hours: int = 48) -> SentimentAggregate | None:
        cutoff = utcnow() - timedelta(hours=max_age_hours)
        return db.session.execute(
            select(SentimentAggregate)
            .where(
                SentimentAggregate.location_id == location_id,
                SentimentAggregate.window_end >= cutoff,
            )
            .order_by(SentimentAggregate.window_end.desc())
            .limit(1)
        ).scalar_one_or_none()

    # ------------------------------------------------------------ fusion
    @staticmethod
    def sentiment_adjustment(aggregate: SentimentAggregate | None) -> tuple[float, list[str]]:
        """Documented heuristic fusion: bounded upward adjustment only.

        - Requires at least 5 posts in the window to act.
        - distress_ratio (distress posts / total) contributes up to +8.
        - strong negative average sentiment contributes up to +2.
        - heat-related post share contributes up to +2.
        Total is capped at +12 and never negative.

        Design constraint: with the moderate weather-model baseline score of
        ~55, the maximum +12 adjustment cannot by itself escalate a moderate
        assessment to the high band (>= 70). Sentiment therefore refines or
        confirms an elevated weather assessment; it never overrides it.
        """
        if aggregate is None or aggregate.post_count < 5:
            return 0.0, []
        notes: list[str] = []
        total = max(1, aggregate.post_count)
        distress_ratio = aggregate.distress_count / total
        heat_ratio = aggregate.heat_related_count / total
        avg = aggregate.avg_score if aggregate.avg_score is not None else 0.0

        adj = 0.0
        d_component = min(8.0, distress_ratio * 25.0)
        if d_component > 0:
            adj += d_component
            notes.append(f"Heat-related distress signals: {aggregate.distress_count} of "
                         f"{aggregate.post_count} analysed posts (+{d_component:.1f}).")
        n_component = min(2.0, max(0.0, -avg) * 2.5)
        if n_component > 0:
            adj += n_component
            notes.append(f"Negative average sentiment ({avg:+.2f}) (+{n_component:.1f}).")
        h_component = min(2.0, heat_ratio * 3.0)
        if h_component > 0:
            adj += h_component
            notes.append(f"Heat-related post share: {aggregate.heat_related_count} of "
                         f"{aggregate.post_count} (+{h_component:.1f}).")
        return round(min(12.0, adj), 1), notes

    # -------------------------------------------------------------- run
    def run(self, location, weather_obs: WeatherObservation | None = None,
            aggregate: SentimentAggregate | None = None, trigger: str = "manual",
            alert_now_override=None) -> tuple[Prediction | None, str]:
        """Produce (or reuse) a prediction for the location's latest inputs.

        Returns (prediction_or_None, status): status in
        'created' | 'reused' | 'insufficient_data'.
        """
        weather_obs = weather_obs or self.latest_weather(location.id)
        aggregate = aggregate or self.latest_aggregate(location.id)
        if weather_obs is None:
            return None, "insufficient_data"

        # Duplicate avoidance: identical inputs -> return the existing row.
        existing = db.session.execute(
            select(Prediction)
            .where(
                Prediction.location_id == location.id,
                Prediction.weather_observation_id == weather_obs.id,
                Prediction.sentiment_aggregate_id == (aggregate.id if aggregate else None),
            )
            .order_by(Prediction.predicted_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            return existing, "reused"

        weather = get_severity_predictor().weather_risk_score(
            weather_obs.temperature_c,
            weather_obs.humidity_pct,
            weather_obs.heat_index_c,
            weather_obs.wind_speed_kph,
        )
        adjustment, fusion_notes = self.sentiment_adjustment(aggregate)
        fused_score = round(min(100.0, weather["weather_score"] + adjustment), 1)

        if fused_score >= 70:
            category = "high"
        elif fused_score >= 40:
            category = "moderate"
        else:
            category = "low"

        contributing = list(fusion_notes)
        hi = weather_obs.heat_index_c
        contributing.insert(0, f"Weather-based risk ({weather['methodology']}): "
                               f"score {weather['weather_score']:.0f}/100, class '{weather['predicted_class']}'.")
        if hi is None:
            contributing.append("Heat index not applicable for this observation "
                                "(NWS envelope); air temperature used as proxy.")
        else:
            contributing.append(f"Computed heat index {hi:.1f} degC.")
        if adjustment == 0.0:
            contributing.append("Sentiment fusion contributed no adjustment "
                                "(insufficient posts or no distress signals).")
        if aggregate is not None and aggregate.post_count > 0:
            contributing.append(f"Sentiment basis: {aggregate.post_count} posts analysed "
                                f"in the trailing 24h window (avg score {aggregate.avg_score}).")

        # Provenance: never blend live and demo data silently.
        modes = {weather_obs.data_mode} | ({aggregate.data_mode} if aggregate else set())
        data_mode = modes.pop() if len(modes) == 1 else "mixed"

        methodology = f"{weather['methodology']} + {FUSION_VERSION}"
        prediction = Prediction(
            location_id=location.id,
            weather_observation_id=weather_obs.id,
            sentiment_aggregate_id=aggregate.id if aggregate else None,
            risk_category=category,
            severity_score=fused_score,
            weather_model_risk=weather["weather_score"],
            confidence=weather["confidence"],
            methodology=methodology,
            model_version=weather["model_version"],
            sentiment_adjustment=adjustment,
            contributing_factors=json.dumps(contributing),
            inputs_json=json.dumps({
                "weather": weather_obs.to_dict(),
                "weather_model": {k: v for k, v in weather.items() if k != "features"},
                "sentiment_aggregate": aggregate.to_dict() if aggregate else None,
                "fusion": {"version": FUSION_VERSION, "adjustment": adjustment, "notes": fusion_notes},
                "trigger": trigger,
            }, default=str),
            data_mode=data_mode,
        )
        db.session.add(prediction)
        db.session.commit()

        self.alert_service.evaluate_prediction(prediction, now_override=alert_now_override)
        return prediction, "created"

    def history(self, location_id: int, start, end, limit: int = 2000) -> list[Prediction]:
        return list(db.session.execute(
            select(Prediction)
            .where(
                Prediction.location_id == location_id,
                Prediction.predicted_at >= as_utc(start),
                Prediction.predicted_at <= as_utc(end),
            )
            .order_by(Prediction.predicted_at.asc())
            .limit(limit)
        ).scalars())
