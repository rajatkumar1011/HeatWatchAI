"""Social media + sentiment endpoints (FR-03, FR-04)."""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, request
from sqlalchemy import select

from app.api import get_services
from app.auth import auth_required
from app.extensions import db
from app.models import Location, SentimentAggregate, SentimentResult, SocialPost
from app.utils.responses import ApiError, paginate, success_response
from app.utils.timeutils import as_utc, utcnow

bp = Blueprint("social", __name__, url_prefix="/api/v1/social")


def _location_or_404(location_id: int) -> Location:
    location = db.session.get(Location, location_id)
    if location is None:
        raise ApiError(404, "Location not found.")
    return location


@bp.get("/posts")
@auth_required
def list_posts():
    stmt = db.session.query(SocialPost).order_by(SocialPost.published_at.desc())
    location_id = request.args.get("location_id", type=int)
    if location_id:
        stmt = stmt.filter(SocialPost.location_id == location_id)
    elif request.args.get("located_only") in ("1", "true"):
        stmt = stmt.filter(SocialPost.location_id.isnot(None))
    sentiment = request.args.get("sentiment")
    heat_only = request.args.get("heat_related") in ("1", "true")

    if sentiment or heat_only:
        stmt = stmt.join(SentimentResult, SentimentResult.post_id == SocialPost.id)
        if sentiment in ("positive", "neutral", "negative"):
            stmt = stmt.filter(SentimentResult.label == sentiment)
        if heat_only:
            stmt = stmt.filter(SentimentResult.is_heat_related.is_(True))

    pagination = paginate(stmt, request.args.get("page", 1, type=int), request.args.get("per_page", 25, type=int))
    items = []
    for post in pagination.items:
        data = post.to_dict()
        if post.sentiment:
            data["sentiment"] = post.sentiment.to_dict()
        items.append(data)
    return success_response(items, meta={"page": pagination.page, "per_page": pagination.per_page, "total": pagination.total})


@bp.post("/collect")
@auth_required
def collect_posts():
    services = get_services()
    body = request.get_json(force=True, silent=True) or {}
    location = _location_or_404(body.get("location_id", 0))
    stored, duplicates, status = services["social"].collect(location, trigger="manual")
    if status == "provider_unavailable":
        raise ApiError(503, "The social media data source is currently unavailable. Try again later.")
    analyzed = services["sentiment"].analyze_pending(location_id=location.id)
    end = utcnow()
    aggregate = services["sentiment"].aggregate(location.id, end - timedelta(hours=24), end)
    return success_response({"stored": stored, "duplicates": duplicates, "analyzed": analyzed,
                             "aggregate": aggregate.to_dict()})


@bp.get("/summary")
@auth_required
def sentiment_summary():
    services = get_services()
    location = _location_or_404(request.args.get("location_id", type=int) or 0)
    hours = min(request.args.get("hours", 24, type=int), 24 * 30)
    end = utcnow()
    start = end - timedelta(hours=hours)
    summary = services["sentiment"].summary(location.id, start, end)
    return success_response(summary)


@bp.get("/trend")
@auth_required
def sentiment_trend():
    services = get_services()
    location = _location_or_404(request.args.get("location_id", type=int) or 0)
    days = min(request.args.get("days", 7, type=int), 60)
    rows = list(db.session.execute(
        select(SentimentAggregate)
        .where(SentimentAggregate.location_id == location.id)
        .order_by(SentimentAggregate.window_start.desc())
        .limit(days * 2)
    ).scalars())
    rows.reverse()
    return success_response([a.to_dict() for a in rows])
