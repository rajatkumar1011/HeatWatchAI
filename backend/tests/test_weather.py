"""FR-02: weather provider validation, ingestion, dedup, freshness."""
from __future__ import annotations

import pytest

from app.integrations.weather.base import WeatherUnavailableError, validate_observation
from app.integrations.weather.demo_provider import DemoWeatherProvider, synthetic_weather
from app.utils.heat import compute_heat_index_c


def test_demo_provider_produces_valid_observation(location):
    provider = DemoWeatherProvider()
    raw = provider.get_current(location.latitude, location.longitude, location.display_name)
    assert raw["data_mode"] == "demo"
    assert -90 <= raw["temperature_c"] <= 60
    assert 0 <= raw["humidity_pct"] <= 100
    assert raw["observed_at"]


def test_heat_index_not_applicable_returns_none():
    assert compute_heat_index_c(15.0, 50.0) is None   # too cold
    assert compute_heat_index_c(35.0, 20.0) is None   # humidity too low


def test_heat_index_at_least_air_temperature():
    hi = compute_heat_index_c(38.0, 60.0)
    assert hi is not None and hi >= 38.0


def test_heat_index_danger_conditions():
    hi = compute_heat_index_c(43.0, 55.0)
    assert hi is not None and hi >= 43.0


def test_validate_observation_rejects_implausible_values():
    with pytest.raises(WeatherUnavailableError):
        validate_observation({"temperature_c": 120, "humidity_pct": 50, "observed_at": "2026-09-19T00:00:00+00:00"})
    with pytest.raises(WeatherUnavailableError):
        validate_observation({"temperature_c": 30, "humidity_pct": 150, "observed_at": "2026-09-19T00:00:00+00:00"})
    with pytest.raises(WeatherUnavailableError):
        validate_observation({"temperature_c": 30, "humidity_pct": 50})


def test_fetch_and_store_then_duplicate(services, location):
    obs1, status1 = services["weather"].fetch_and_store(location, trigger="test")
    assert status1 == "stored" and obs1 is not None
    assert obs1.data_mode == "demo"
    obs2, status2 = services["weather"].fetch_and_store(location, trigger="test")
    # Deterministic demo generator at the same hour -> same observation time.
    assert status2 in ("stored", "duplicate")
    if status2 == "duplicate":
        assert obs2 is None


def test_latest_freshness_labelled_demo(services, location):
    services["weather"].fetch_and_store(location, trigger="test")
    latest = services["weather"].latest(location)
    assert latest is not None
    assert latest["freshness"] == "demo"


def test_history_filter_by_date_range(services, location):
    from datetime import timedelta
    from app.utils.timeutils import utcnow
    services["weather"].fetch_and_store(location, trigger="test")
    rows = services["weather"].history(location.id, utcnow() - timedelta(hours=1), utcnow() + timedelta(hours=1))
    assert len(rows) >= 1
    empty = services["weather"].history(location.id, utcnow() - timedelta(days=365), utcnow() - timedelta(days=364))
    assert len(empty) == 0


def test_openweathermap_adapter_normalizes(monkeypatch):
    """Live adapter normalization is unit-tested with a stubbed HTTP call."""
    from app.integrations.weather.openweathermap import OpenWeatherMapProvider

    class FakeResp:
        status_code = 200
        def __init__(self, payload):
            self.payload = payload
        def json(self):
            return self.payload

    provider = OpenWeatherMapProvider(api_key="test-key", base_url="http://unit-test", timeout=1, max_retries=1)
    payload = {
        "main": {"temp": 36.0, "feels_like": 41.5, "humidity": 62, "pressure": 1006},
        "weather": [{"id": 800, "main": "Clear", "description": "clear sky"}],
        "wind": {"speed": 3.5, "deg": 250},
        "dt": 1726700000,
        "name": "Mumbai",
    }
    import app.integrations.weather.openweathermap as owm
    monkeypatch.setattr(owm.requests, "get", lambda *a, **k: FakeResp(payload))
    obs = provider.get_current(19.0, 72.8, "Mumbai")
    assert obs["temperature_c"] == 36.0
    assert obs["wind_speed_kph"] == 12.6          # m/s -> km/h
    assert obs["provider"] == "openweathermap"
    assert obs["data_mode"] == "live"
    # heat index computed separately from the provider feels-like value
    assert obs["heat_index_c"] is not None
    assert obs["feels_like_is_heat_index"] is False
    # heat index must be close to (>=) air temperature in these conditions
    assert obs["heat_index_c"] >= obs["temperature_c"]


def test_openweathermap_no_retry_on_401(monkeypatch):
    from app.integrations.weather.openweathermap import OpenWeatherMapProvider, WeatherUnavailableError

    calls = {"n": 0}

    class FakeResp:
        status_code = 401
        def json(self):
            return {}

    import app.integrations.weather.openweathermap as owm
    def fake_get(*a, **k):
        calls["n"] += 1
        return FakeResp()
    monkeypatch.setattr(owm.requests, "get", fake_get)

    provider = OpenWeatherMapProvider(api_key="bad", base_url="http://unit-test", timeout=1, max_retries=3)
    with pytest.raises(WeatherUnavailableError):
        provider.get_current(0, 0, "x")
    assert calls["n"] == 1  # permanent failure not retried
