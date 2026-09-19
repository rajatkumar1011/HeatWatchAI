"""Weather data collection service (FR-02).

Responsibilities:
- select the configured provider (live OpenWeatherMap or labelled demo),
- fetch + validate + normalize observations,
- persist them with duplicate suppression (same provider observation is
  never stored twice),
- expose freshness-aware reads: LIVE / CACHED / DEMO / UNAVAILABLE.

The service never silently switches from live mode to demonstration mode:
in live mode an outage surfaces as an unavailable state (with the newest
cached observation where present), never as synthetic data.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.integrations.weather.base import WeatherProvider, WeatherUnavailableError
from app.integrations.weather.demo_provider import DemoWeatherProvider
from app.integrations.weather.openweathermap import OpenWeatherMapProvider
from app.models import CollectionRun, Location, WeatherObservation
from app.utils.responses import log_event
from app.utils.timeutils import as_utc, utcnow


class WeatherService:
    def __init__(self, config):
        self.config = config

    # ------------------------------------------------------------- provider
    def provider_configured(self) -> bool:
        if self.config["DATA_MODE"] == "demo":
            return False
        if self.config["DATA_MODE"] == "live":
            return bool(self.config["OPENWEATHER_API_KEY"])
        return True  # auto: demo fallback is an explicit, labelled choice

    def get_provider(self) -> WeatherProvider:
        mode = self.config["DATA_MODE"]
        has_key = bool(self.config["OPENWEATHER_API_KEY"])
        if mode == "live":
            if not has_key:
                raise WeatherUnavailableError("Live weather mode requires OPENWEATHER_API_KEY.")
            return self._live_provider()
        if mode == "demo":
            return DemoWeatherProvider()
        # auto mode: live provider when credentials exist, else the
        # explicitly-labelled demonstration provider.
        return self._live_provider() if has_key else DemoWeatherProvider()

    def _live_provider(self) -> WeatherProvider:
        return OpenWeatherMapProvider(
            api_key=self.config["OPENWEATHER_API_KEY"],
            base_url=self.config["OPENWEATHER_BASE_URL"],
            timeout=self.config["WEATHER_TIMEOUT_SECONDS"],
            max_retries=self.config["API_MAX_RETRIES"],
        )

    def active_provider_name(self) -> str:
        try:
            return self.get_provider().name
        except Exception:
            return "unconfigured"

    # ------------------------------------------------------------ ingestion
    def fetch_and_store(self, location: Location, trigger: str = "manual") -> tuple[WeatherObservation | None, str]:
        """Fetch current weather for a location and persist it.

        Returns (observation_or_None, status) where status describes what
        happened: 'stored' | 'duplicate' | 'provider_unavailable'.
        """
        run = CollectionRun(job="weather", location_id=location.id, trigger=trigger)
        db.session.add(run)
        db.session.commit()
        started = utcnow()
        try:
            provider = self.get_provider()
            raw = provider.get_current(location.latitude, location.longitude, location.display_name)
            observation = self._store_normalized(location, raw)
            self._finish_run(run, "success", started, {"observation_id": observation.id if observation else None})
            return observation, ("duplicate" if observation is None else "stored")
        except WeatherUnavailableError as exc:
            self._finish_run(run, "failed", started, {"error": str(exc)})
            log_event("weather", f"Weather fetch failed for {location.display_name}: {exc}",
                      level="warning", details={"location_id": location.id})
            return None, "provider_unavailable"
        except Exception as exc:  # unexpected — logged, surfaced as failure
            self._finish_run(run, "failed", started, {"error": str(exc)})
            log_event("weather", f"Weather fetch error for {location.display_name}: {exc}",
                      level="error", details={"location_id": location.id})
            return None, "provider_unavailable"

    def _store_normalized(self, location: Location, raw: dict[str, Any]) -> WeatherObservation | None:
        observed_at = as_utc(datetime.fromisoformat(raw["observed_at"].replace("Z", "+00:00")))
        existing = db.session.execute(
            select(WeatherObservation).where(
                WeatherObservation.location_id == location.id,
                WeatherObservation.provider == raw.get("provider", "unknown"),
                WeatherObservation.observed_at == observed_at,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return None  # duplicate provider observation — do not store again

        obs = WeatherObservation(
            location_id=location.id,
            temperature_c=raw["temperature_c"],
            feels_like_c=raw.get("feels_like_c"),
            humidity_pct=raw["humidity_pct"],
            heat_index_c=raw.get("heat_index_c"),
            wind_speed_kph=raw.get("wind_speed_kph", 0.0),
            wind_deg=raw.get("wind_deg"),
            pressure_hpa=raw.get("pressure_hpa"),
            condition_code=raw.get("condition_code"),
            condition_text=raw.get("condition_text", "unknown"),
            observed_at=observed_at,
            provider=raw.get("provider", "unknown"),
            data_mode=raw.get("data_mode", "live"),
        )
        db.session.add(obs)
        db.session.commit()
        return obs

    def store_synthetic(self, location: Location, raw: dict[str, Any]) -> WeatherObservation | None:
        """Used by the demo seeder to backfill history (already DEMO-labelled)."""
        return self._store_normalized(location, raw)

    # ---------------------------------------------------------------- reads
    def freshness(self, obs: WeatherObservation) -> str:
        """Classify an observation's freshness: live | cached | demo."""
        age = utcnow() - as_utc(obs.observed_at)
        if obs.data_mode == "demo":
            return "demo"
        if age <= timedelta(minutes=self.config["WEATHER_FRESH_MINUTES"]):
            return "live"
        return "cached"

    def latest(self, location: Location) -> dict[str, Any] | None:
        obs = db.session.execute(
            select(WeatherObservation)
            .where(WeatherObservation.location_id == location.id)
            .order_by(WeatherObservation.observed_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if obs is None:
            return None
        data = obs.to_dict()
        data["freshness"] = self.freshness(obs)
        return data

    def history(self, location_id: int, start: datetime, end: datetime, limit: int = 5000) -> list[WeatherObservation]:
        return list(db.session.execute(
            select(WeatherObservation)
            .where(
                WeatherObservation.location_id == location_id,
                WeatherObservation.observed_at >= start,
                WeatherObservation.observed_at <= end,
            )
            .order_by(WeatherObservation.observed_at.asc())
            .limit(limit)
        ).scalars())

    def _finish_run(self, run: CollectionRun, status: str, started: datetime, result: dict) -> None:
        run.status = status
        run.finished_at = utcnow()
        run.duration_ms = (utcnow() - started).total_seconds() * 1000.0
        import json
        run.result = json.dumps(result, default=str)
        db.session.commit()
