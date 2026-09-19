"""Weather provider adapters (FR-02).

Each provider normalizes observations to the internal schema:
  temperature_c (degC), feels_like_c, humidity_pct (%), heat_index_c (degC,
  NULL when not applicable), wind_speed_kph (km/h), wind_deg, pressure_hpa,
  condition_code, condition_text, observed_at (UTC ISO timestamp),
  provider (name), data_mode ('live'|'demo').
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.utils.responses import ApiError


class WeatherProviderError(Exception):
    """Base class for weather provider failures."""


class WeatherUnavailableError(WeatherProviderError):
    """Provider could not be reached or returned an unusable response."""


class WeatherRateLimitedError(WeatherUnavailableError):
    """Provider signalled a rate limit."""


class WeatherProvider(ABC):
    name: str = "base"
    data_mode: str = "live"

    @abstractmethod
    def get_current(self, latitude: float, longitude: float, location_name: str = "") -> dict[str, Any]:
        """Return a normalized current-weather dictionary."""


def validate_observation(obs: dict[str, Any]) -> dict[str, Any]:
    """Sanity-validate a normalized observation; raises on malformed data."""
    try:
        temp = float(obs["temperature_c"])
        humidity = float(obs["humidity_pct"])
        observed_at = obs["observed_at"]
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherUnavailableError(f"Malformed weather payload: {exc}") from exc

    if not -90.0 <= temp <= 60.0:
        raise WeatherUnavailableError(f"Implausible temperature {temp} degC rejected.")
    if not 0.0 <= humidity <= 100.0:
        raise WeatherUnavailableError(f"Implausible humidity {humidity}% rejected.")
    if not observed_at:
        raise WeatherUnavailableError("Weather payload missing observation timestamp.")

    obs["temperature_c"] = temp
    obs["humidity_pct"] = humidity
    obs.setdefault("wind_speed_kph", 0.0)
    obs.setdefault("condition_text", "unknown")
    obs.setdefault("provider", "unknown")
    obs.setdefault("data_mode", "live")
    return obs
