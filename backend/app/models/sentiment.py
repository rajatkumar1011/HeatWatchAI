"""Social media post, sentiment, and aggregate models (FR-03, FR-04)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

SENTIMENT_POSITIVE = "positive"
SENTIMENT_NEUTRAL = "neutral"
SENTIMENT_NEGATIVE = "negative"
SENTIMENT_LABELS = (SENTIMENT_POSITIVE, SENTIMENT_NEUTRAL, SENTIMENT_NEGATIVE)


class SocialPost(db.Model):
    """A collected public post (SRS FR-03). Read-only ingestion only.

    ``external_id`` is the provider's identifier when available and is used
    together with ``source_platform`` for duplicate suppression. Posts with
    no resolvable location keep ``location_id = NULL`` — the system never
    invents geography.
    """

    __tablename__ = "social_posts"
    __table_args__ = (
        UniqueConstraint("source_platform", "external_id", name="uq_social_post_external"),
        Index("ix_social_loc_time", "location_id", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_platform: Mapped[str] = mapped_column(String(60), nullable=False)  # demo|reddit|...
    text: Mapped[str] = mapped_column(Text, nullable=False)
    author_handle: Mapped[str | None] = mapped_column(String(120), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    raw_location_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(12), nullable=False, default="en")
    data_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="live")
    analysis_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending|analyzed|skipped

    sentiment: Mapped["SentimentResult | None"] = relationship(back_populates="post", uselist=False)

    def to_dict(self, include_text: bool = True) -> dict:
        data = {
            "id": self.id,
            "external_id": self.external_id,
            "source_platform": self.source_platform,
            "author_handle": self.author_handle,
            "published_at": self.published_at.isoformat(),
            "collected_at": self.collected_at.isoformat(),
            "location_id": self.location_id,
            "raw_location_label": self.raw_location_label,
            "language": self.language,
            "data_mode": self.data_mode,
            "analysis_status": self.analysis_status,
        }
        if include_text:
            data["text"] = self.text
        return data


class SentimentResult(db.Model):
    """Per-post NLP sentiment classification output (SRS FR-04)."""

    __tablename__ = "sentiment_results"
    __table_args__ = (
        Index("ix_sentiment_post", "post_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("social_posts.id", ondelete="CASCADE"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)  # compound score in [-1, 1]
    positive_proba: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    neutral_proba: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    negative_proba: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_heat_related: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    heat_relevance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    distress_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    post: Mapped[SocialPost] = relationship(back_populates="sentiment")

    def to_dict(self) -> dict:
        return {
            "post_id": self.post_id,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "label": self.label,
            "score": self.score,
            "positive_proba": self.positive_proba,
            "neutral_proba": self.neutral_proba,
            "negative_proba": self.negative_proba,
            "is_heat_related": self.is_heat_related,
            "heat_relevance_score": self.heat_relevance_score,
            "distress_flag": self.distress_flag,
            "analyzed_at": self.analyzed_at.isoformat(),
        }


class SentimentAggregate(db.Model):
    """Aggregated sentiment for one location over one time window.

    Multiple posts contribute to a single aggregate row (SRS 2.6.2). Feeds
    the prediction engine; unique per (location, window_start, window_end).
    """

    __tablename__ = "sentiment_aggregates"
    __table_args__ = (
        UniqueConstraint("location_id", "window_start", "window_end", name="uq_sentiment_aggregate"),
        Index("ix_sentiment_agg_loc_start", "location_id", "window_start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    post_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    positive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    neutral_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    heat_related_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    distress_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="live")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "location_id": self.location_id,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "post_count": self.post_count,
            "positive_count": self.positive_count,
            "neutral_count": self.neutral_count,
            "negative_count": self.negative_count,
            "avg_score": self.avg_score,
            "heat_related_count": self.heat_related_count,
            "distress_count": self.distress_count,
            "data_mode": self.data_mode,
            "computed_at": self.computed_at.isoformat(),
        }
