"""Simple in-memory sliding-window rate limiter for sensitive endpoints.

A full deployment would use a shared store (e.g. Redis); for this
single-process deployment an in-process limiter is sufficient and documented.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.utils.responses import ApiError

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)


def enforce_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    now = time.monotonic()
    with _lock:
        bucket = _hits[key]
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            raise ApiError(429, "Too many attempts. Please try again later.")
        bucket.append(now)


def clear_rate_limits() -> None:
    with _lock:
        _hits.clear()
