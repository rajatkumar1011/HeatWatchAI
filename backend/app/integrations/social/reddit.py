"""Reddit public search adapter (optional live provider for FR-03).

Uses Reddit's public, read-only search endpoint with a descriptive
User-Agent, honouring provider limits and only retrieving public posts —
consistent with Reddit's terms. It requires no credentials for basic public
search; if Reddit blocks the request or changes availability, the adapter
raises SocialUnavailableError and the system communicates that instead of
falling back to demonstration data silently.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

from app.integrations.social.demo_provider import (
    SocialProvider,
    SocialProviderError,
    SocialUnavailableError,
    normalize_post,
)

SEARCH_URL = "https://www.reddit.com/search.json"


class RedditPublicProvider(SocialProvider):
    name = "reddit"
    data_mode = "live"

    def __init__(self, user_agent: str, timeout: float = 10.0, max_retries: int = 3):
        if not user_agent:
            raise SocialProviderError("Reddit adapter requires a descriptive User-Agent.")
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries

    def search(self, keywords: list[str], location_label: str, since: datetime,
               until: datetime, limit: int = 100) -> list[dict[str, Any]]:
        query = " OR ".join(f'"{k}"' for k in keywords[:8])
        params = {
            "q": query,
            "sort": "new",
            "limit": min(int(limit), 100),
            "after": int(since.timestamp()),
            "before": int(until.timestamp()),
            "type": "link",
        }
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.get(SEARCH_URL, params=params, headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = SocialUnavailableError(f"Social provider unreachable: {exc.__class__.__name__}")
            else:
                if resp.status_code == 200:
                    return self._normalize_response(resp.json())
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = SocialUnavailableError(f"Social provider error (HTTP {resp.status_code}).")
                else:
                    raise SocialUnavailableError(f"Social provider rejected the request (HTTP {resp.status_code}).")
            if attempt < self.max_retries:
                time.sleep(min(2 ** attempt, 8))
        raise last_error or SocialUnavailableError("Social provider unavailable.")

    def _normalize_response(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        posts: list[dict[str, Any]] = []
        try:
            children = payload["data"]["children"]
        except (KeyError, TypeError) as exc:
            raise SocialUnavailableError("Unrecognized social provider response.") from exc

        for child in children:
            d = child.get("data", {})
            try:
                published = datetime.fromtimestamp(int(d["created_utc"]), tz=timezone.utc)
            except (KeyError, TypeError, ValueError):
                continue
            text = f"{d.get('title', '')}".strip()
            body = (d.get("selftext") or "").strip()
            if body:
                text = f"{text}. {body}"
            # Use only provider-provided geographic hints; never infer location.
            raw_loc = d.get("subreddit_name_prefixed")
            try:
                posts.append(normalize_post({
                    "external_id": f"t3_{d.get('id')}",
                    "source_platform": "reddit",
                    "text": text,
                    "author_handle": d.get("author"),
                    "published_at": published,
                    "raw_location_label": None,  # subreddit != verified location
                    "language": "en",
                    "data_mode": self.data_mode,
                }))
            except SocialProviderError:
                continue  # skip malformed/empty records
        return posts
