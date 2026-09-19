"""AI-based sentiment analysis service (FR-04).

Sentiment model: VADER (Valence Aware Dictionary and sEntiment Reasoner) —
a pretrained, lexicon-and-rule English sentiment model designed for social
media text. It runs fully offline (bundled lexicon), produces a compound
score in [-1, 1] and class proportions.

Scientific separation (required by the product brief):
- General sentiment: the VADER classification of a post.
- Heat-related relevance: keyword evidence that the post is actually about
  heat conditions (a negative post about traffic is NOT heat distress).
- Heat-related distress: heat-relevant AND negative AND containing
  health/discomfort impact vocabulary (dehydration, dizziness, heatstroke,
  power cuts during heat, etc.).

The keyword lists are transparent heuristics, maintained via configuration,
and are reported as such — they are not an ML model.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models import (
    SENTIMENT_NEGATIVE,
    SENTIMENT_NEUTRAL,
    SENTIMENT_POSITIVE,
    AppSetting,
    SentimentAggregate,
    SentimentResult,
    SocialPost,
)
from app.utils.timeutils import as_utc, utcnow

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except ImportError as _exc:  # pragma: no cover
    raise RuntimeError("vaderSentiment package is required for sentiment analysis") from _exc

_analyzer = SentimentIntensityAnalyzer()
SENTIMENT_MODEL_NAME = "vader"
SENTIMENT_MODEL_VERSION = "3.3.2"

HEAT_RELEVANCE_KEYWORDS_SETTING = "heat_relevance_keywords"
DISTRESS_KEYWORDS_SETTING = "distress_keywords"

HEAT_RELEVANCE_KEYWORDS = [
    "heatwave", "heat wave", "extreme heat", "heat alert", "heat alert", "hot weather",
    "high temperature", "heatwave warning", "heat index", "heat stress", "heatwave conditions",
    "rising temperature", "temperature soaring", "heatwave alert", "summer heat", "heat",
    "loog", "loo", "sunstroke", "heatstroke",
]
DISTRESS_KEYWORDS = [
    "dehydration", "dehydrated", "dizzy", "dizziness", "fainted", "faint", "unconscious",
    "heatstroke", "sun stroke", "sunstroke", "heat exhaustion", "exhausted", "exhaustion",
    "heat rash", "prickly heat", "cramps", "hospital", "collapsed", "collapsing",
    "can't breathe", "cant breathe", "suffocating", "suffocation", "vomiting", "nausea",
    "no water", "water shortage", "water crisis", "power cut", "no electricity", "power cuts",
    "unbearable", "dangerous heat", "dying from heat", "heat deaths", "health emergency",
    "elderly", "kids", "children", "infant",
]


def _setting_keywords(key: str, defaults: list[str]) -> list[str]:
    try:
        row = db.session.get(AppSetting, key)
    except RuntimeError:
        # No application context (e.g. unit-testing the heuristics directly):
        # fall back to the built-in keyword lists.
        return defaults
    if row and row.value:
        try:
            data = json.loads(row.value)
            if isinstance(data, list) and data:
                return [str(k).lower() for k in data if str(k).strip()]
        except json.JSONDecodeError:
            pass
    return defaults


def model_metadata() -> dict[str, Any]:
    return {
        "model_identifier": "VADER (Hutto & Gilbert, 2014) via vaderSentiment",
        "model_name": SENTIMENT_MODEL_NAME,
        "model_version": SENTIMENT_MODEL_VERSION,
        "input_language": "English only (SRS scope)",
        "labels": [SENTIMENT_NEGATIVE, SENTIMENT_NEUTRAL, SENTIMENT_POSITIVE],
        "score_interpretation": "compound score in [-1, 1]; >= 0.05 positive, <= -0.05 negative, otherwise neutral",
        "known_limitations": [
            "Lexicon-based model; sarcasm and context beyond n-grams may be misclassified.",
            "General sentiment is not the same as heat-related distress; relevance and "
            "distress indicators are separate keyword-based heuristics.",
            "Social media posters are not a representative population sample.",
        ],
    }


def preprocess_text(text: str) -> str:
    """Light preprocessing: keep emoji/punctuation (VADER uses them), trim URLs."""
    tokens = [t for t in text.split() if not t.startswith(("http://", "https://", "www."))]
    return " ".join(tokens).strip()


def analyze_text(text: str) -> dict[str, Any]:
    """Run the VADER model on one text; returns raw classification output."""
    cleaned = preprocess_text(text)
    if not cleaned:
        raise ValueError("empty text after preprocessing")
    scores = _analyzer.polarity_scores(cleaned)
    compound = float(scores["compound"])
    if compound >= 0.05:
        label = SENTIMENT_POSITIVE
    elif compound <= -0.05:
        label = SENTIMENT_NEGATIVE
    else:
        label = SENTIMENT_NEUTRAL
    total = scores["pos"] + scores["neu"] + scores["neg"]
    return {
        "label": label,
        "score": round(compound, 4),
        "positive_proba": round(scores["pos"] / total, 4) if total else 0.0,
        "neutral_proba": round(scores["neu"] / total, 4) if total else 0.0,
        "negative_proba": round(scores["neg"] / total, 4) if total else 0.0,
    }


def heat_relevance(text: str) -> tuple[bool, float, bool]:
    """Transparent keyword heuristics for heat relevance and distress.

    Returns (is_heat_related, relevance_score, distress_flag).
    """
    lowered = " " + preprocess_text(text).lower() + " "
    heat_kw = _setting_keywords(HEAT_RELEVANCE_KEYWORDS_SETTING, HEAT_RELEVANCE_KEYWORDS)
    distress_kw = _setting_keywords(DISTRESS_KEYWORDS_SETTING, DISTRESS_KEYWORDS)

    heat_hits = sum(1 for kw in heat_kw if kw in lowered)
    distress_hits = sum(1 for kw in distress_kw if kw in lowered)
    is_heat_related = heat_hits > 0
    relevance_score = min(1.0, heat_hits / 3.0)
    distress_flag = is_heat_related and distress_hits > 0
    return is_heat_related, round(relevance_score, 3), distress_flag


class SentimentService:
    def __init__(self, config):
        self.config = config

    # ------------------------------------------------------------ analysis
    def analyze_post(self, post: SocialPost) -> SentimentResult:
        result = analyze_text(post.text)
        is_heat, relevance, distress = heat_relevance(post.text)
        row = SentimentResult(
            post_id=post.id,
            model_name=SENTIMENT_MODEL_NAME,
            model_version=SENTIMENT_MODEL_VERSION,
            label=result["label"],
            score=result["score"],
            positive_proba=result["positive_proba"],
            neutral_proba=result["neutral_proba"],
            negative_proba=result["negative_proba"],
            is_heat_related=is_heat,
            heat_relevance_score=relevance,
            distress_flag=distress,
        )
        post.analysis_status = "analyzed"
        db.session.add(row)
        return row

    def analyze_pending(self, location_id: int | None = None, limit: int = 2000) -> int:
        """Analyze all pending posts (optionally for one location). Returns count."""
        stmt = select(SocialPost).where(SocialPost.analysis_status == "pending").limit(limit)
        if location_id is not None:
            stmt = stmt.where(SocialPost.location_id == location_id)
        posts = list(db.session.execute(stmt).scalars())
        analyzed = 0
        for post in posts:
            try:
                self.analyze_post(post)
                analyzed += 1
            except Exception:
                post.analysis_status = "skipped"
        db.session.commit()
        return analyzed

    # ---------------------------------------------------------- aggregates
    def aggregate(self, location_id: int, window_start: datetime, window_end: datetime,
                  data_mode: str | None = None) -> SentimentAggregate:
        """Compute (or refresh) the sentiment aggregate for a location window."""
        window_start, window_end = as_utc(window_start), as_utc(window_end)
        rows = list(db.session.execute(
            select(SentimentResult, SocialPost)
            .join(SocialPost, SentimentResult.post_id == SocialPost.id)
            .where(
                SocialPost.location_id == location_id,
                SocialPost.published_at >= window_start,
                SocialPost.published_at < window_end,
            )
        ).all())

        counts = {SENTIMENT_POSITIVE: 0, SENTIMENT_NEUTRAL: 0, SENTIMENT_NEGATIVE: 0}
        scores: list[float] = []
        heat_related = distress = 0
        mode = data_mode
        for result, post in rows:
            counts[result.label] += 1
            scores.append(result.score)
            heat_related += 1 if result.is_heat_related else 0
            distress += 1 if result.distress_flag else 0
            mode = mode or post.data_mode

        aggregate = db.session.execute(
            select(SentimentAggregate).where(
                SentimentAggregate.location_id == location_id,
                SentimentAggregate.window_start == window_start,
                SentimentAggregate.window_end == window_end,
            )
        ).scalar_one_or_none()
        if aggregate is None:
            aggregate = SentimentAggregate(location_id=location_id, window_start=window_start, window_end=window_end)
            db.session.add(aggregate)

        aggregate.post_count = len(rows)
        aggregate.positive_count = counts[SENTIMENT_POSITIVE]
        aggregate.neutral_count = counts[SENTIMENT_NEUTRAL]
        aggregate.negative_count = counts[SENTIMENT_NEGATIVE]
        aggregate.avg_score = round(sum(scores) / len(scores), 4) if scores else None
        aggregate.heat_related_count = heat_related
        aggregate.distress_count = distress
        aggregate.data_mode = mode or "live"
        aggregate.computed_at = utcnow()
        db.session.commit()
        return aggregate

    def aggregate_daily(self, location_id: int, days: int, data_mode: str | None = None) -> list[SentimentAggregate]:
        """Aggregate the trailing `days` calendar-day windows ending now."""
        end = utcnow()
        start_of_window = (end - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        aggregates = []
        cursor = start_of_window
        while cursor < end:
            aggregates.append(self.aggregate(location_id, cursor, min(cursor + timedelta(days=1), end), data_mode))
            cursor += timedelta(days=1)
        return aggregates

    # ---------------------------------------------------------------- reads
    def summary(self, location_id: int, window_start: datetime, window_end: datetime) -> dict[str, Any]:
        aggregate = db.session.execute(
            select(SentimentAggregate).where(
                SentimentAggregate.location_id == location_id,
                SentimentAggregate.window_start >= window_start,
                SentimentAggregate.window_end <= window_end,
            ).order_by(SentimentAggregate.window_end.desc())
        ).scalars().all()
        if not aggregate:
            return {"available": False, "post_count": 0}
        latest = aggregate[0]
        data = latest.to_dict()
        data["available"] = True
        return data
