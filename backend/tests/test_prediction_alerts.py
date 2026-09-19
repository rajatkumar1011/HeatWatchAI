"""FR-05/FR-06: prediction engine, fusion, and alert engine tests."""
from __future__ import annotations

from datetime import timedelta

from app.ml.features import build_features, label_from_heat_index
from app.utils.timeutils import utcnow


def _weather_input(temp: float, humidity: float, wind: float = 10.0):
    return {"temperature_c": temp, "humidity_pct": humidity, "wind_speed_kph": wind,
            "observed_at": utcnow().isoformat()}


def test_label_definition_bands():
    assert label_from_heat_index(25.0) == "low"
    assert label_from_heat_index(35.0) == "moderate"
    assert label_from_heat_index(45.0) == "high"


def test_features_heat_index_fallback():
    # Humidity 20% -> heat index not applicable -> air temp used, flagged.
    feats = build_features(40.0, 20.0, None, 5.0)
    assert feats["heat_index_applicable"] is False
    assert feats["heat_index_c"] == 40.0


def test_severity_model_artifact_loads():
    from app.services.prediction_service import get_severity_predictor
    predictor = get_severity_predictor()
    assert predictor.available, "severity artifact must be trained before tests"
    result = predictor.weather_risk_score(42.0, 60.0, None, 8.0)
    assert result["predicted_class"] == "high"
    assert result["weather_score"] >= 70
    low = predictor.weather_risk_score(24.0, 40.0, None, 10.0)
    assert low["predicted_class"] == "low"
    # confidence is a real class probability (0-100)
    assert low["confidence"] is not None and 0 <= low["confidence"] <= 100


def test_prediction_run_and_reuse(services, location):
    services["weather"].fetch_and_store(location, trigger="test")
    p1, s1 = services["predictions"].run(location, trigger="test")
    assert s1 == "created" and p1 is not None
    p2, s2 = services["predictions"].run(location, trigger="test")
    assert s2 == "reused" and p2.id == p1.id  # identical inputs -> no duplicate row


def test_prediction_records_provenance(services, location):
    services["weather"].fetch_and_store(location, trigger="test")
    services["social"].collect(location, trigger="test", window_hours=24)
    services["sentiment"].analyze_pending(location_id=location.id)
    end = utcnow()
    agg = services["sentiment"].aggregate(location.id, end - timedelta(hours=24), end)
    prediction, _ = services["predictions"].run(location, aggregate=agg, trigger="test")
    assert "ml_severity_model" in prediction.methodology
    assert "rule_fusion_v1" in prediction.methodology
    assert prediction.data_mode == "demo"  # demo weather + demo social -> demo
    import json as _json
    inputs = _json.loads(prediction.inputs_json)
    assert "weather" in inputs and "fusion" in inputs


def test_sentiment_fusion_bounded_and_upward_only(services):
    from app.models import SentimentAggregate
    from app.services.prediction_service import PredictionService
    agg = SentimentAggregate(location_id=1, window_start=utcnow() - timedelta(hours=1),
                             window_end=utcnow(), post_count=20, positive_count=2,
                             neutral_count=4, negative_count=14, avg_score=-0.55,
                             heat_related_count=12, distress_count=10, data_mode="demo")
    adjustment, notes = PredictionService.sentiment_adjustment(agg)
    assert 0 <= adjustment <= 12.0
    assert notes
    # too few posts -> no adjustment
    agg.post_count = 3
    adjustment2, notes2 = PredictionService.sentiment_adjustment(agg)
    assert adjustment2 == 0.0 and notes2 == []


def test_high_risk_prediction_triggers_alert(services, location):
    services["weather"].fetch_and_store(location, trigger="test")
    services["social"].collect(location, trigger="test", window_hours=24,
                               since=utcnow() - timedelta(hours=24))
    services["sentiment"].analyze_pending(location_id=location.id)
    # Force a high-risk weather observation regardless of the generator phase.
    from app.models import WeatherObservation
    obs = WeatherObservation(
        location_id=location.id, temperature_c=43.0, feels_like_c=47.0, humidity_pct=60.0,
        heat_index_c=55.0, wind_speed_kph=8.0, condition_text="Clear",
        observed_at=utcnow(), provider="test", data_mode="demo")
    services["weather"]._store_normalized(location, {
        **_weather_input(43.0, 60.0, 8.0), "heat_index_c": 55.0, "provider": "test", "data_mode": "demo"})
    from sqlalchemy import select
    from app.models import Prediction
    obs = services["predictions"].latest_weather(location.id)
    prediction, status = services["predictions"].run(location, weather_obs=obs, trigger="test")
    assert prediction.risk_category == "high"
    alerts = services["alerts"].history(location_id=location.id)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.risk_level == "high"
    assert alert.prediction_id == prediction.id
    assert "not an official government advisory" in alert.message


def test_alert_cooldown_prevents_duplicates(services, location):
    from app.models import WeatherObservation
    for i, temp in enumerate((43.0, 43.5)):
        services["weather"]._store_normalized(location, {
            **_weather_input(temp, 60.0, 8.0), "heat_index_c": 55.0 + i,
            "provider": "test", "data_mode": "demo",
            "observed_at": (utcnow() + timedelta(minutes=i)).isoformat()})
    obs = services["predictions"].latest_weather(location.id)
    p1, _ = services["predictions"].run(location, weather_obs=obs, trigger="test")
    alerts = services["alerts"].history(location_id=location.id)
    assert len(alerts) == 1
    # same inputs again -> reuse path, no new alert
    p2, s2 = services["predictions"].run(location, weather_obs=obs, trigger="test")
    assert s2 == "reused"
    assert len(services["alerts"].history(location_id=location.id)) == 1


def test_escalation_and_auto_resolve(services, location):
    # A moderate alert first (alert_on_moderate enabled via setting)
    from app.extensions import db
    from app.models import AppSetting
    db.session.add(AppSetting(key="alert_on_moderate", value="true"))
    db.session.commit()
    services["weather"]._store_normalized(location, {
        **_weather_input(33.0, 60.0, 8.0), "heat_index_c": 38.5,
        "provider": "t1", "data_mode": "demo",
        "observed_at": (utcnow() - timedelta(hours=2)).isoformat()})
    p_mod, _ = services["predictions"].run(
        location, weather_obs=services["predictions"].latest_weather(location.id),
        trigger="test", alert_now_override=utcnow() - timedelta(hours=2))
    alerts = services["alerts"].history(location_id=location.id)
    assert any(a.risk_level == "moderate" for a in alerts)
    row = db.session.get(AppSetting, "alert_on_moderate")
    db.session.delete(row)
    db.session.commit()

    # Then a low prediction resolves active alerts (recovery behaviour)
    services["weather"]._store_normalized(location, {
        **_weather_input(24.0, 50.0, 8.0), "heat_index_c": None,
        "provider": "t2", "data_mode": "demo",
        "observed_at": (utcnow() - timedelta(minutes=10)).isoformat()})
    p_low, _ = services["predictions"].run(
        location, weather_obs=services["predictions"].latest_weather(location.id), trigger="test")
    assert p_low.risk_category == "low"
    statuses = [a.status for a in services["alerts"].history(location_id=location.id)]
    assert "resolved" in statuses or all(s != "active" for s in statuses)


def test_acknowledge_alert(services, location, admin_user):
    services["weather"]._store_normalized(location, {
        **_weather_input(43.0, 60.0, 8.0), "heat_index_c": 55.0,
        "provider": "test", "data_mode": "demo"})
    p, _ = services["predictions"].run(
        location, weather_obs=services["predictions"].latest_weather(location.id), trigger="test")
    alerts = services["alerts"].history(location_id=location.id)
    assert alerts and alerts[0].status == "active"
    acknowledged = services["alerts"].acknowledge(alerts[0], admin_user.id)
    assert acknowledged.status == "acknowledged"
    assert acknowledged.acknowledged_by == admin_user.id
