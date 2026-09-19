"""OpenWeatherMap current-weather adapter with bounded retries (SRS 2.5.1).

Requires OPENWEATHER_API_KEY via environment configuration; the key is never
hardcoded or exposed to clients. Retries temporary failures up to three times
with exponential backoff; permanent failures (401, invalid request) are not
retried.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

from app.integrations.weather.base import (
    WeatherProvider,
    WeatherProviderError,
    WeatherRateLimitedError,
    WeatherUnavailableError,
    validate_observation,
)
from app.utils.heat import compute_heat_index_c

CONDITION_GROUPS = {
    2: "Thunderstorm", 3: "Drizzle", 5: "Rain", 6: "Snow", 7: "Atmosphere",
    800: "Clear", 80: "Clouds",
}


def _condition_text(code: int, fallback: str) -> str:
    if code == 800:
        return "Clear"
    if 801 <= code <= 804:
        return "Clouds"
    if 200 <= code <= 232:
        return "Thunderstorm"
    if 300 <= code <= 321:
        return "Drizzle"
    if 500 <= code <= 531:
        return "Rain"
    if 600 <= code <= 622:
        return "Snow"
    if 700 <= code <= 781:
        return "Atmosphere"
    return fallback or "unknown"


class OpenWeatherMapProvider(WeatherProvider):
    name = "openweathermap"
    data_mode = "live"

    def __init__(self, api_key: str, base_url: str, timeout: float, max_retries: int = 3):
        if not api_key:
            raise WeatherProviderError("OpenWeatherMap API key is not configured.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def get_current(self, latitude: float, longitude: float, location_name: str = "") -> dict[str, Any]:
        url = f"{self.base_url}/weather"
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.get(
                    url,
                    params={"lat": latitude, "lon": longitude, "appid": self.api_key, "units": "metric"},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = WeatherUnavailableError(f"Weather service unreachable: {exc.__class__.__name__}")
            else:
                if resp.status_code == 200:
                    return self._normalize(resp.json())
                if resp.status_code in (429,) or resp.status_code >= 500:
                    last_error = (
                        WeatherRateLimitedError("Weather service rate limit reached.")
                        if resp.status_code == 429
                        else WeatherUnavailableError(f"Weather service error (HTTP {resp.status_code}).")
                    )
                elif resp.status_code in (400, 401, 403, 404):
                    # Permanent failures are not retried.
                    detail = "Invalid or unauthorized weather API credentials." if resp.status_code in (401, 403) else "Weather request rejected."
                    raise WeatherUnavailableError(detail)
                else:
                    last_error = WeatherUnavailableError(f"Weather service error (HTTP {resp.status_code}).")

            if attempt < self.max_retries:
                time.sleep(min(2 ** attempt, 8))  # exponential backoff, capped

        raise last_error or WeatherUnavailableError("Weather service unavailable.")

    def _normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            main = payload["main"]
            weather = (payload.get("weather") or [{}])[0]
            wind = payload.get("wind") or {}
            temperature = float(main["temp"])
            humidity = float(main["humidity"])
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherUnavailableError(f"Unrecognized weather payload: {exc}") from exc

        observed_epoch = payload.get("dt")
        observed_at = (
            datetime.fromtimestamp(observed_epoch, tz=timezone.utc).isoformat()
            if observed_epoch else datetime.now(timezone.utc).isoformat()
        )

        heat_index = compute_heat_index_c(temperature, humidity)
        obs = {
            "temperature_c": round(temperature, 2),
            "feels_like_c": round(float(main.get("feels_like", temperature)), 2) if main.get("feels_like") is not None else None,
            "humidity_pct": humidity,
            # Heat index is computed here (not silently substituted with the
            # provider's feels-like value) and is NULL when not applicable.
            "heat_index_c": heat_index,
            "wind_speed_kph": round(float(wind.get("speed", 0.0)) * 3.6, 2),  # m/s -> km/h
            "wind_deg": wind.get("deg"),
            "pressure_hpa": main.get("pressure"),
            "condition_code": weather.get("id"),
            "condition_text": _condition_text(int(weather.get("id") or 0), weather.get("main", "")),
            "observed_at": observed_at,
            "provider": self.name,
            "data_mode": self.data_mode,
            "feels_like_is_heat_index": False,
            "heat_index_available": heat_index is not None,
        }
        return validate_observation(obs)
