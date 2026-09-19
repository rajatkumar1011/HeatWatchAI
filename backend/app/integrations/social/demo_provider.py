"""Social provider base class plus the demonstration adapter.

Real provider adapters (e.g. Reddit public search) live alongside this
module and follow the same normalized-post contract:

  external_id, source_platform, text, author_handle, published_at (UTC ISO),
  raw_location_label (provider-provided only), language, data_mode.
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.timeutils import utcnow


class SocialProviderError(Exception):
    pass


class SocialUnavailableError(SocialProviderError):
    pass


class SocialProvider(ABC):
    name: str = "base"
    data_mode: str = "live"

    @abstractmethod
    def search(self, keywords: list[str], location_label: str, since: datetime,
               until: datetime, limit: int = 100) -> list[dict[str, Any]]:
        """Return normalized public posts matching the parameters."""


def normalize_post(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate/clean one provider post; unusable records raise."""
    text = (raw.get("text") or "").strip()
    if not text or len(text) < 3:
        raise SocialProviderError("post text missing or too short")
    published = raw.get("published_at")
    if not isinstance(published, datetime):
        raise SocialProviderError("post missing valid publication timestamp")
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return {
        "external_id": raw.get("external_id"),
        "source_platform": raw.get("source_platform", raw.get("provider", "unknown")),
        "text": text,
        "author_handle": raw.get("author_handle"),
        "published_at": published,
        "raw_location_label": raw.get("raw_location_label"),
        "language": raw.get("language") or "en",
        "data_mode": raw.get("data_mode", "live"),
    }


class DemoSocialProvider(SocialProvider):
    """Clearly-labelled demonstration posts for offline evaluation.

    The template pools include heat-distress, neutral, positive, and
    off-topic negative examples so that general sentiment and heat-related
    distress can be distinguished in the UI. Posts are stored with
    data_mode='demo' and are never presented as real public posts.
    """

    name = "demo"
    data_mode = "demo"

    # {handle} placeholders are filled per location; sentiment-oriented text.
    DISTRESS_TEMPLATES = [
        "It's getting unbearable out here in {city} today. Can't stay outside for more than a few minutes. #heatwave",
        "Feeling dizzy and dehydrated after just 20 minutes in the {city} sun. This heat is dangerous. #HeatAlert",
        "Power cut again in {city} and the heat inside the house is suffocating. No fan, no relief. #heatwave",
        "Water shortage in our {city} area and this extreme heat. People are really struggling. #HeatWave #WaterCrisis",
        "An elderly neighbour collapsed from heat exhaustion in {city} today. Please check on the elderly. #heatwave",
        "Third day of extreme heat in {city}. Schools should be closed, kids are getting heat rashes. #HeatAlert",
        "My father had a heatstroke scare this afternoon in {city}. Please stay indoors if you can. #heatwave",
        "No water pressure since morning in {city} and 42 degrees outside. This is a public health emergency. #heatwave",
        "Ambulance took an hour to reach our lane in {city}. Heat cases are overwhelming the response teams. #HeatAlert",
        "Sweating through my shirt by 9 AM in {city}. Working outdoors in this is genuinely risky. #heatwave",
        "Two construction workers hospitalised for heatstroke near our site in {city}. Contractors must pause work. #heatwave",
        "The waiting room at the {city} clinic is full of dehydration cases this week. Stay safe everyone. #HeatAlert",
        "Slept at 3 AM — it's impossible to cool down in this {city} flat without power. Exhausted. #heatwave",
        "Locals say this is the harshest September spell {city} has seen in years. My grandmother hasn't stepped out since Monday. #HeatWave",
        "Car thermometer read 44 in {city} traffic today. Roads feel like furnaces. #extremeheat",
        "Water tankers arrive in our {city} ward only every second day now, and people queue in the blazing sun. #WaterCrisis",
    ]
    CONCERN_TEMPLATES = [
        "Heat advisory issued for {city}. Stay hydrated and avoid direct sunlight between 12 and 4. #heatwave",
        "The humidity in {city} makes it feel way hotter than the temperature says. Take care out there.",
        "Reports of power cuts in parts of {city} as the heat peaks. Hope the grid holds up. #HeatAlert",
        "Heatwave conditions likely to continue in {city} for two more days as per the forecast.",
        "Orange alert for {city} this weekend. Orange means serious — plan errands early morning. #heatwave",
        "Check the UV index before stepping out in {city}, it's extreme around noon.",
        "Community centres in {city} are opening cooling shelters during peak afternoon hours. Well done.",
        "Please keep a bottle of ORS at home this week, {city} doctors are recommending it. #heatwave",
    ]
    NEUTRAL_TEMPLATES = [
        "Checking the {city} weather update for the week. Staying prepared.",
        "The municipality said water tankers will operate on schedule in {city} this week.",
        "Sharing the new {city} metro timetable with my commute group.",
        "Weekly market in {city} moves to the community hall ground from tomorrow.",
        "New library reading room opens in {city} this Saturday, entry free.",
        "The {city} marathon organising committee published the revised route map today.",
        "Ward office in {city} announced tree plantation drive registration details.",
        "Train services on the harbour line through {city} run to schedule today, per the update.",
    ]
    POSITIVE_TEMPLATES = [
        "Evening breeze finally here in {city}. The parks look lovely at sunset. #goodvibes",
        "Great community volunteer drive in {city} today — distributing free buttermilk and water to pedestrians.",
        "Rain clouds on the horizon in {city}! Relief may be on the way. #monsoon",
        "Our society planted 50 new shade trees in {city} this weekend. Small steps for cooler summers.",
        "Cool morning walk by the {city} seafront before the heat set in. Small wins.",
        "The new shaded bus stops around {city} make waiting so much better. Kudos to the city team.",
        "Free drinking-water kiosks are up across {city} markets this week. Thoughtful initiative.",
        "Sunset after a hot day in {city} hits different. Rooftop, breeze, done. #simplejoys",
    ]
    OFF_TOPIC_NEGATIVE_TEMPLATES = [
        "Traffic on the Ring Road was absolutely maddening this morning. Two hours wasted. #commute",
        "The new movie everyone hyped turned out to be a total bore.",
        "My internet provider keeps dropping the connection every evening. So frustrating.",
        "Referee made a terrible call in last night's match. Robbed us of the win.",
        "Waited 40 minutes for a table at that new cafe. Not worth the hype at all.",
        "Lost my umbrella twice this week. Yesterday it finally stopped raining when I carried it. Typical.",
        "The parcel delivery app marked my order delivered when nothing arrived. Annoyed.",
        "My fantasy league team collapsed in the final over. Painful watch.",
    ]

    def search(self, keywords: list[str], location_label: str, since: datetime,
               until: datetime, limit: int = 100, distress_share: float | None = None) -> list[dict[str, Any]]:
        """Return demonstration posts for the window.

        ``distress_share`` controls the share of heat-distress templates
        (0-1). Callers running heatwave scenarios pass a higher share; the
        default reflects ordinary conditions.
        """
        city = (location_label or "the city").split(",")[0].strip()
        rng = random.Random(f"demo-social|{location_label}|{since.isoformat()}|{until.isoformat()}")
        share = 0.12 if distress_share is None else max(0.0, min(1.0, distress_share))
        remaining = 1.0 - share
        pools = [
            (self.DISTRESS_TEMPLATES, share),
            (self.CONCERN_TEMPLATES, remaining * 0.25),
            (self.POSITIVE_TEMPLATES, remaining * 0.25),
            (self.OFF_TOPIC_NEGATIVE_TEMPLATES, remaining * 0.25),
            (self.NEUTRAL_TEMPLATES, remaining * 0.25),
        ]
        posts: list[dict[str, Any]] = []
        span_seconds = max(1, int((until - since).total_seconds()))
        target = min(limit, 26)
        for i in range(target):
            pool = self._weighted_choice(rng, pools)
            template = rng.choice(pool)
            text = template.format(city=city)
            published = since + timedelta(seconds=rng.randint(0, span_seconds))
            posts.append(normalize_post({
                "external_id": f"demo-{location_label.replace(' ', '-').lower()}-{until.strftime('%Y%m%d%H')}-{i}",
                "source_platform": "demo",
                "text": text,
                "author_handle": f"@{city.lower().replace(' ', '_')}_voice{i % 7}",
                "published_at": published,
                "raw_location_label": location_label if rng.random() < 0.7 else None,
                "language": "en",
                "data_mode": self.data_mode,
            }))
        return posts

    @staticmethod
    def _weighted_choice(rng: random.Random, weighted: list[tuple[list[str], float]]) -> list[str]:
        total = sum(w for _, w in weighted)
        r = rng.random() * total
        cumulative = 0.0
        for pool, weight in weighted:
            cumulative += weight
            if r <= cumulative:
                return pool
        return weighted[-1][0]
