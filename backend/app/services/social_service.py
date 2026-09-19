"""Social media collection service (FR-03).

Handles provider selection, keyword configuration, duplicate suppression,
and persistence of public posts. Posts with no resolvable location are
stored without a location rather than assigned one by inference.
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.integrations.social.demo_provider import DemoSocialProvider, SocialProvider, SocialUnavailableError
from app.integrations.social.reddit import RedditPublicProvider
from app.models import AppSetting, CollectionRun, Location, SocialPost
from app.utils.responses import log_event
from app.utils.timeutils import as_utc, utcnow

DEFAULT_KEYWORDS = [
    "heatwave", "extreme heat", "high temperature", "dehydration",
    "heat exhaustion", "power cut", "water shortage", "hot weather", "heat stress",
]
KEYWORDS_SETTING_KEY = "social_keywords"


def get_keywords() -> list[str]:
    row = db.session.get(AppSetting, KEYWORDS_SETTING_KEY)
    if row and row.value:
        try:
            data = json.loads(row.value)
            if isinstance(data, list) and data:
                return [str(k).strip() for k in data if str(k).strip()]
        except json.JSONDecodeError:
            pass
    return list(DEFAULT_KEYWORDS)


class SocialService:
    def __init__(self, config):
        self.config = config

    # ------------------------------------------------------------- provider
    def provider_name(self) -> str:
        mode = self.config.get("SOCIAL_PROVIDER", "auto")
        if mode == "demo":
            return "demo"
        if mode == "reddit":
            return "reddit"
        if mode == "reddit_if_public":
            return "reddit"
        return "demo" if self.config["DATA_MODE"] == "demo" else "demo"

    def get_provider(self) -> SocialProvider:
        requested = self.config.get("SOCIAL_PROVIDER", "auto")
        if requested == "reddit":
            return RedditPublicProvider(user_agent=self.config["REDDIT_USER_AGENT"],
                                        timeout=self.config["SOCIAL_TIMEOUT_SECONDS"],
                                        max_retries=self.config["API_MAX_RETRIES"])
        if requested == "auto" and self.config["DATA_MODE"] == "live":
            # Live data mode without a configured licensed social API cannot
            # be satisfied; the caller surfaces the unavailability.
            return RedditPublicProvider(user_agent=self.config["REDDIT_USER_AGENT"],
                                        timeout=self.config["SOCIAL_TIMEOUT_SECONDS"],
                                        max_retries=self.config["API_MAX_RETRIES"])
        return DemoSocialProvider()

    def active_provider_name(self) -> str:
        try:
            return self.get_provider().name
        except Exception:
            return "unconfigured"

    # ------------------------------------------------------------ ingestion
    def collect(self, location: Location, trigger: str = "manual",
                window_hours: int = 24, since: Any = None, until: Any = None,
                limit: int = 100) -> tuple[int, int, str]:
        """Collect posts for a location.

        Returns (stored_count, duplicate_count, status).
        """
        run = CollectionRun(job="social", location_id=location.id, trigger=trigger)
        db.session.add(run)
        db.session.commit()
        started = utcnow()
        try:
            until_dt = as_utc(until) if until else utcnow()
            since_dt = as_utc(since) if since else until_dt - timedelta(hours=window_hours)
            provider = self.get_provider()
            keywords = get_keywords()
            raw_posts = provider.search(keywords, location.display_name, since_dt, until_dt, limit=limit)

            stored = duplicates = 0
            for raw in raw_posts:
                external_id = raw.get("external_id")
                if external_id:
                    exists = db.session.execute(
                        select(SocialPost.id).where(
                            SocialPost.source_platform == raw["source_platform"],
                            SocialPost.external_id == external_id,
                        )
                    ).scalar_one_or_none()
                    if exists is not None:
                        duplicates += 1
                        continue
                # Attach the queried location only when the provider itself
                # supplies a location hint; otherwise store without location.
                location_id = location.id if raw.get("raw_location_label") else None
                post = SocialPost(
                    external_id=external_id,
                    source_platform=raw["source_platform"],
                    text=raw["text"][:4000],
                    author_handle=raw.get("author_handle"),
                    published_at=raw["published_at"],
                    location_id=location_id,
                    raw_location_label=raw.get("raw_location_label"),
                    language=raw.get("language", "en"),
                    data_mode=raw.get("data_mode", "live"),
                    analysis_status="pending",
                )
                db.session.add(post)
                stored += 1
            db.session.commit()
            self._finish_run(run, "success", started, {"stored": stored, "duplicates": duplicates})
            return stored, duplicates, "collected"
        except SocialUnavailableError as exc:
            db.session.rollback()
            self._finish_run(run, "failed", started, {"error": str(exc)})
            log_event("social", f"Social collection failed for {location.display_name}: {exc}",
                      level="warning", details={"location_id": location.id})
            return 0, 0, "provider_unavailable"
        except Exception as exc:
            db.session.rollback()
            self._finish_run(run, "failed", started, {"error": str(exc)})
            log_event("social", f"Social collection error for {location.display_name}: {exc}",
                      level="error", details={"location_id": location.id})
            return 0, 0, "provider_unavailable"

    def insert_post(self, source_platform: str, text: str, published_at, external_id: str | None = None,
                    author_handle: str | None = None, location_id: int | None = None,
                    raw_location_label: str | None = None, data_mode: str = "demo") -> tuple[SocialPost | None, bool]:
        """Seeder/dataset ingestion helper with duplicate suppression."""
        if external_id:
            exists = db.session.execute(
                select(SocialPost).where(
                    SocialPost.source_platform == source_platform,
                    SocialPost.external_id == external_id,
                )
            ).scalar_one_or_none()
            if exists is not None:
                return None, False
        post = SocialPost(
            external_id=external_id,
            source_platform=source_platform,
            text=text[:4000],
            author_handle=author_handle,
            published_at=as_utc(published_at),
            location_id=location_id,
            raw_location_label=raw_location_label,
            language="en",
            data_mode=data_mode,
            analysis_status="pending",
        )
        db.session.add(post)
        db.session.flush()
        return post, True

    def _finish_run(self, run: CollectionRun, status: str, started, result: dict) -> None:
        run.status = status
        run.finished_at = utcnow()
        run.duration_ms = (utcnow() - started).total_seconds() * 1000.0
        run.result = json.dumps(result, default=str)
        db.session.commit()
