"""Dashboard aggregate endpoint (FR-07).

A single authenticated call returning everything the main dashboard needs:
latest weather (with freshness), latest prediction, sentiment summary,
recent posts, active alerts, advisory, emergency contacts, and the chart
series. Keeps dashboard load to one round trip (SRS 5-second target).
"""
from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, request
from sqlalchemy import select

from app.api import get_services
from app.auth import auth_required
from app.extensions import db
from app.models import (
    Alert,
    EmergencyContact,
    GovernmentAdvisory,
    Location,
    Prediction,
    SentimentAggregate,
    SentimentResult,
    SocialPost,
    WeatherObservation,
)
from app.utils.responses import ApiError, success_response
from app.utils.timeutils import as_utc, utcnow

bp = Blueprint("dashboard", __name__, url_prefix="/api/v1/dashboard")


@bp.get("")
@auth_required
def dashboard():
    services = get_services()
    location_id = request.args.get("location_id", type=int)
    location = db.session.get(Location, location_id) if location_id else db.session.execute(
        select(Location).where(Location.is_monitored.is_(True)).order_by(Location.name.asc()).limit(1)
    ).scalar_one_or_none()
    if location is None:
        raise ApiError(404, "No monitored locations are configured.")

    now = utcnow()
    payload: dict = {"location": location.to_dict(), "generated_at": now.isoformat()}

    # --- weather (freshness-aware) ---
    latest = services["weather"].latest(location)
    payload["weather"] = latest or {"available": False}

    # --- prediction ---
    prediction = db.session.execute(
        select(Prediction).where(Prediction.location_id == location.id)
        .order_by(Prediction.predicted_at.desc()).limit(1)
    ).scalar_one_or_none()
    payload["prediction"] = prediction.to_dict() if prediction else {"available": False}

    # --- sentiment (latest 24h aggregate) ---
    aggregate = db.session.execute(
        select(SentimentAggregate).where(SentimentAggregate.location_id == location.id)
        .order_by(SentimentAggregate.window_end.desc()).limit(1)
    ).scalar_one_or_none()
    payload["sentiment"] = {**aggregate.to_dict(), "available": True} if aggregate else {"available": False, "post_count": 0}

    # --- recent posts with sentiment ---
    # Fetch a broader window, then order: distress → heat-related → newest, so
    # the dashboard panel leads with the most operationally relevant posts.
    post_rows = db.session.execute(
        select(SocialPost, SentimentResult)
        .outerjoin(SentimentResult, SentimentResult.post_id == SocialPost.id)
        .where(SocialPost.location_id == location.id)
        .order_by(SocialPost.published_at.desc())
        .limit(40)
    ).all()

    def post_rank(pair) -> tuple:
        result = pair[1]
        return (
            1 if (result and result.distress_flag) else 0,
            1 if (result and result.is_heat_related) else 0,
            pair[0].published_at,
        )

    post_rows = sorted(post_rows, key=post_rank, reverse=True)[:12]
    payload["posts"] = [{
        **post.to_dict(),
        "sentiment": result.to_dict() if result else None,
    } for post, result in post_rows]

    # --- active alerts ---
    alerts = db.session.execute(
        select(Alert)
        .where(Alert.location_id == location.id, Alert.status.in_(("active", "acknowledged")))
        .order_by(Alert.generated_at.desc()).limit(5)
    ).scalars().all()
    payload["alerts"] = [a.to_dict() for a in alerts]

    # --- advisory + emergency contacts ---
    advisory = db.session.execute(
        select(GovernmentAdvisory)
        .where(GovernmentAdvisory.is_active.is_(True))
        .order_by(GovernmentAdvisory.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    payload["advisory"] = {**advisory.to_dict(), "available": True} if advisory else {"available": False,
        "message": "No verified government advisory source is configured. Content shown here is "
                   "administrator-maintained and clearly labelled."}
    contacts = db.session.execute(
        select(EmergencyContact).where(EmergencyContact.is_active.is_(True)).order_by(EmergencyContact.id.asc())
    ).scalars().all()
    payload["emergency_contacts"] = [c.to_dict() for c in contacts]

    # --- chart series: trailing 7 days ---
    week_ago = now - timedelta(days=7)
    weather_rows = services["weather"].history(location.id, as_utc(week_ago), now)
    payload["series"] = {
        "weather": [w.to_dict() for w in weather_rows][-500:],
        "predictions": [p.to_dict() for p in db.session.execute(
            select(Prediction).where(
                Prediction.location_id == location.id, Prediction.predicted_at >= as_utc(week_ago))
            .order_by(Prediction.predicted_at.asc()).limit(500)
        ).scalars()],
        "sentiment_aggregates": [a.to_dict() for a in db.session.execute(
            select(SentimentAggregate).where(
                SentimentAggregate.location_id == location.id,
                SentimentAggregate.window_start >= as_utc(week_ago))
            .order_by(SentimentAggregate.window_start.asc()).limit(100)
        ).scalars()],
    }
    # alert frequency per day (trailing 7 days)
    alert_rows = db.session.execute(
        select(Alert).where(Alert.generated_at >= as_utc(week_ago)).order_by(Alert.generated_at.asc())
    ).scalars().all()
    freq: dict[str, int] = {}
    for a in alert_rows:
        day = a.generated_at.date().isoformat()
        freq[day] = freq.get(day, 0) + 1
    payload["series"]["alert_frequency"] = [{"day": d, "count": c} for d, c in sorted(freq.items())]

    return success_response(payload)
