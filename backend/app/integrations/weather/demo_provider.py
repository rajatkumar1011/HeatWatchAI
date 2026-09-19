"""Demonstration weather provider (FR-02 demo mode).

Produces clearly-labelled synthetic observations using a deterministic
generator so that demonstrations are reproducible. Records created from this
provider are always stored with data_mode='demo' and displayed as DEMO DATA —
they never represent real meteorological measurements.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from app.integrations.weather.base import WeatherProvider, validate_observation
from app.utils.heat import compute_heat_index_c

# Deterministic demonstration scenarios (offsets relative to the current date
# so a demo always contains an active episode). Values are temperature bumps
# in degC applied per day-of-episode.
DEMO_SCENARIOS: dict[str, list[float]] = {
    "Mumbai": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5.0, 8.0, 9.5, 10.0],
    "Delhi": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1.0, 1.5, 2.0, 1.5, 1.0],
}
SCENARIO_LENGTH = 31  # days of history the scenario covers

# Plausible early-autumn baselines and typical humidity profiles for the
# default demo cities (base humidity falls ~1.5% per degC above baseline).
DEMO_BASELINES: dict[str, float] = {
    "Mumbai": 28.5, "Delhi": 30.5, "Nagpur": 28.5, "Chennai": 29.0, "Ahmedabad": 31.0,
}
DEMO_HUMIDITY_BASE: dict[str, float] = {
    "Mumbai": 76.0, "Delhi": 55.0, "Nagpur": 40.0, "Chennai": 71.0, "Ahmedabad": 50.0,
}


def _day_index(when: datetime) -> int:
    return (when.replace(hour=0, minute=0, second=0, microsecond=0) -
            (datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=SCENARIO_LENGTH - 1))).days


def synthetic_weather(latitude: float, longitude: float, location_name: str,
                      when: datetime | None = None) -> dict[str, Any]:
    """Deterministic synthetic weather for a location and instant."""
    when = when or datetime.now(timezone.utc)
    seed = f"{location_name}|{latitude:.3f}|{when.strftime('%Y%m%d%H')}"
    rng = random.Random(seed)

    base = DEMO_BASELINES.get(location_name.split(",")[0].strip())
    if base is None:
        # Simple latitude-based fallback baseline.
        base = 40.0 - abs(latitude) * 0.55
    humidity_base = DEMO_HUMIDITY_BASE.get(location_name.split(",")[0].strip(), 60.0)

    day_idx = _day_index(when)
    scenario_bump = 0.0
    if location_name.split(",")[0].strip() in DEMO_SCENARIOS:
        offsets = DEMO_SCENARIOS[location_name.split(",")[0].strip()]
        if 0 <= day_idx < len(offsets):
            scenario_bump = offsets[day_idx]

    hour = when.hour + when.minute / 60.0
    diurnal = 3.2 * math.sin(math.pi * max(0.0, (hour - 6.0)) / 14.0) if 6.0 <= hour <= 20.0 else -2.2
    temperature = base + diurnal + scenario_bump + rng.uniform(-0.8, 0.8)

    # Humidity falls as temperature rises above the location baseline.
    humidity = max(18.0, min(96.0, humidity_base - (temperature - base) * 1.5 + rng.uniform(-5, 5)))
    wind_kph = max(2.0, 14.0 + rng.uniform(-6, 8) - scenario_bump * 0.4)
    condition = "Clear"
    if temperature > 38:
        condition = "Haze" if rng.random() < 0.4 else "Clear"
    elif rng.random() < 0.25:
        condition = "Clouds"

    observed_at = when.astimezone(timezone.utc)
    heat_index = compute_heat_index_c(round(temperature, 2), round(humidity, 2))
    obs = {
        "temperature_c": round(temperature, 2),
        "feels_like_c": round(temperature + 1.2, 2),
        "humidity_pct": round(humidity, 1),
        "heat_index_c": heat_index,
        "wind_speed_kph": round(wind_kph, 1),
        "wind_deg": rng.randint(0, 359),
        "pressure_hpa": round(1008.0 + rng.uniform(-4, 4), 0),
        "condition_code": 800 if condition == "Clear" else (721 if condition == "Haze" else 802),
        "condition_text": condition,
        "observed_at": observed_at.isoformat(),
        "provider": "demo",
        "data_mode": "demo",
        "feels_like_is_heat_index": False,
        "heat_index_available": heat_index is not None,
    }
    return validate_observation(obs)


class DemoWeatherProvider(WeatherProvider):
    name = "demo"
    data_mode = "demo"

    def get_current(self, latitude: float, longitude: float, location_name: str = "") -> dict[str, Any]:
        return synthetic_weather(latitude, longitude, location_name)
