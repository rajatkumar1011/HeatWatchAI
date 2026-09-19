"""Time helpers. Canonical timestamps are stored in UTC; the user-facing
display timezone defaults to Asia/Kolkata (SRS FR-07 data presentation)."""
from __future__ import annotations

from datetime import datetime, timezone

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

DEFAULT_DISPLAY_TZ = "Asia/Kolkata"


def utcnow() -> datetime:
    """Timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC.

    Naive datetimes coming from the database are interpreted as UTC, which
    is the canonical storage convention for this application.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_display_tz(dt: datetime, tz_name: str = DEFAULT_DISPLAY_TZ) -> datetime:
    return as_utc(dt).astimezone(ZoneInfo(tz_name))


def format_display(dt: datetime | None, tz_name: str = DEFAULT_DISPLAY_TZ, with_seconds: bool = False) -> str | None:
    if dt is None:
        return None
    fmt = "%d %b %Y, %I:%M:%S %p" if with_seconds else "%d %b %Y, %I:%M %p"
    return to_display_tz(dt, tz_name).strftime(fmt)
