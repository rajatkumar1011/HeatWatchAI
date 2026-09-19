"""FR-03/FR-04: social ingestion dedup + sentiment pipeline tests."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.integrations.social.demo_provider import DemoSocialProvider
from app.services.sentiment_service import analyze_text, heat_relevance, model_metadata
from app.utils.timeutils import utcnow


def _collect_window(services, location, hours: int = 24):
    end = utcnow()
    return services["social"].collect(location, trigger="test", window_hours=hours)


def test_demo_collection_stores_posts(services, location):
    stored, duplicates, status = _collect_window(services, location)
    assert status == "collected" and stored > 0 and duplicates == 0


def test_collection_deduplicates(services, location):
    _collect_window(services, location)
    stored, duplicates, status = _collect_window(services, location)
    assert stored == 0 and duplicates > 0  # same deterministic window -> duplicates


def test_posts_without_location_label_stored_locationless(services, location):
    services["social"].collect(location, trigger="test", window_hours=24)
    from app.models import SocialPost
    located = SocialPost.query.filter(SocialPost.location_id == location.id).count()
    unlocated = SocialPost.query.filter(SocialPost.location_id.is_(None)).count()
    assert located > 0
    assert unlocated > 0  # demo provider omits location hints for some posts


def test_malformed_post_rejected():
    from datetime import datetime, timezone
    from app.integrations.social.demo_provider import normalize_post, SocialProviderError
    with pytest.raises(SocialProviderError):
        normalize_post({"text": "", "published_at": datetime.now(timezone.utc)})
    with pytest.raises(SocialProviderError):
        normalize_post({"text": "hello there", "published_at": "not-a-date"})


# ------------------------------------------------------------------ FR-04

def test_vader_positive_negative_neutral():
    pos = analyze_text("What a wonderful and lovely surprise today! Absolutely delightful :)")
    neg = analyze_text("This is terrible, horrible and devastating. I hate it.")
    neu = analyze_text("The meeting is scheduled for 3 PM near the library.")
    assert pos["label"] == "positive" and pos["score"] > 0.05
    assert neg["label"] == "negative" and neg["score"] < -0.05
    assert neu["label"] == "neutral"


def test_heat_relevance_flags_heat_posts_but_not_traffic():
    heat_text = "Extreme heatwave in the city today, feeling dehydrated and dizzy."
    traffic_text = "Terrible traffic jam on the highway, totally frustrating commute."
    is_heat, score, distress = heat_relevance(heat_text)
    assert is_heat and distress
    is_heat2, score2, distress2 = heat_relevance(traffic_text)
    assert not is_heat2 and not distress2


def test_distress_requires_heat_relevance():
    # Negative health vocabulary alone without heat context is not distress.
    _, _, distress = heat_relevance("My grandmother is in hospital after a fall.")
    assert distress is False


def test_model_metadata_present():
    meta = model_metadata()
    assert meta["model_name"] == "vader"
    assert "English" in meta["input_language"]
    assert meta["known_limitations"]


def test_analyze_pending_and_aggregate(services, location):
    services["social"].collect(location, trigger="test", window_hours=24)
    analyzed = services["sentiment"].analyze_pending(location_id=location.id)
    assert analyzed > 0
    end = utcnow()
    aggregate = services["sentiment"].aggregate(
        location.id, end - timedelta(hours=24), end)
    assert aggregate.post_count == analyzed
    assert aggregate.positive_count + aggregate.neutral_count + aggregate.negative_count == aggregate.post_count
    assert -1.0 <= aggregate.avg_score <= 1.0

    # Re-aggregating refreshes rather than duplicating.
    again = services["sentiment"].aggregate(location.id, end - timedelta(hours=24), end)
    assert again.id == aggregate.id


def test_heatwave_scenario_rises_distress(services, location):
    """Posts during a heatwave scenario carry more distress signals."""
    from app.integrations.social.demo_provider import DemoSocialProvider
    from datetime import datetime, timezone
    provider = DemoSocialProvider()
    start = datetime(2026, 9, 10, tzinfo=timezone.utc)
    end = datetime(2026, 9, 11, tzinfo=timezone.utc)
    crisis = provider.search([], "Mumbai, Maharashtra", start, end, distress_share=0.55)
    normal = provider.search([], "Mumbai, Maharashtra", start, end, distress_share=0.08)
    def distress_ratio(posts):
        flags = [heat_relevance(p["text"])[2] for p in posts]
        return sum(flags) / max(1, len(flags))
    assert distress_ratio(crisis) > distress_ratio(normal)
