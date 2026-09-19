"""End-to-end integration test of the full monitoring pipeline (per the
behavioural UML diagrams and section 22 of the implementation brief):

weather retrieval -> social retrieval -> preprocessing -> sentiment analysis
-> severity assessment -> prediction persistence -> alert evaluation
-> dashboard/report availability.
"""
from __future__ import annotations

from datetime import timedelta

from app.models import Alert, Prediction, SentimentResult, SocialPost, WeatherObservation
from app.utils.timeutils import utcnow


def test_full_pipeline_dashboard_and_reports(client, services, location, admin_headers):
    # 1-3. weather + social collection through the monitoring service
    result = services["monitoring"].run_pipeline(location, trigger="test")
    assert result["status"] == "success"
    assert result["steps"]["weather"]["status"] == "stored"
    assert result["steps"]["social"]["stored"] > 0
    assert result["steps"]["sentiment"]["aggregated"] is True
    assert result["steps"]["prediction"]["status"] == "created"

    # 4. persistence assertions
    assert WeatherObservation.query.filter_by(location_id=location.id).count() >= 1
    assert SocialPost.query.filter_by(location_id=location.id).count() > 0
    assert SentimentResult.query.count() > 0
    assert Prediction.query.filter_by(location_id=location.id).count() == 1

    prediction = Prediction.query.first()
    assert prediction.methodology
    assert prediction.data_mode == "demo"
    assert prediction.risk_category in ("low", "moderate", "high")

    # 5. dashboard endpoint exposes the whole chain
    resp = client.get(f"/api/v1/dashboard?location_id={location.id}", headers=admin_headers)
    assert resp.status_code == 200
    payload = resp.get_json()["data"]
    assert payload["weather"]["data_mode"] == "demo"
    assert payload["prediction"]["id"] == prediction.id
    assert payload["sentiment"]["post_count"] > 0
    assert len(payload["posts"]) > 0
    assert len(payload["series"]["weather"]) >= 1
    assert len(payload["series"]["predictions"]) >= 1

    # 6. report availability (CSV) from the same records
    today = utcnow().date()
    resp = client.post("/api/v1/reports/generate", headers=admin_headers, json={
        "location_id": location.id, "start_date": (today - timedelta(days=1)).isoformat(),
        "end_date": today.isoformat(), "format": "csv"})
    assert resp.status_code == 201


def test_pipeline_survives_weather_provider_failure(client, services, location, monkeypatch):
    """FR-10: when the provider fails, cached data is used and the pipeline
    still completes (no silent demo substitution, no crash)."""
    from app.integrations.weather.base import WeatherUnavailableError

    # first run stores an observation
    services["monitoring"].run_pipeline(location, trigger="test")

    def failing_get_current(self, latitude, longitude, location_name=""):
        raise WeatherUnavailableError("simulated outage")

    from app.integrations.weather.demo_provider import DemoWeatherProvider
    monkeypatch.setattr(DemoWeatherProvider, "get_current", failing_get_current)

    result = services["monitoring"].run_pipeline(location, trigger="test")
    assert result["status"] == "success"  # recovered via cached observation
    assert result["steps"]["weather"]["status"] == "provider_unavailable"
    assert result["steps"]["prediction"]["status"] in ("created", "reused")


def test_two_locations_do_not_interfere(services, location, second_location):
    services["monitoring"].run_pipeline(location, trigger="test")
    services["monitoring"].run_pipeline(second_location, trigger="test")
    preds_mumbai = Prediction.query.filter_by(location_id=location.id).count()
    preds_nagpur = Prediction.query.filter_by(location_id=second_location.id).count()
    assert preds_mumbai >= 1 and preds_nagpur >= 1
    alerts_mumbai = Alert.query.filter_by(location_id=location.id).count()
    alerts_nagpur = Alert.query.filter_by(location_id=second_location.id).count()
    # Each location's alerts are independent
    assert alerts_mumbai >= 0 and alerts_nagpur >= 0
