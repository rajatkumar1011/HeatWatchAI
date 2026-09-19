"""FR-08: historical report generation tests (PDF + CSV)."""
from __future__ import annotations

from datetime import date, timedelta

from app.utils.timeutils import utcnow


def _seed_week(services, location):
    """Store a few days of observations, posts, sentiment, and predictions."""
    from app.models import WeatherObservation
    from app.utils.timeutils import utcnow as now
    for days_ago in (5, 4, 3):
        services["weather"]._store_normalized(location, {
            "temperature_c": 40.0 - days_ago, "humidity_pct": 60.0, "wind_speed_kph": 10.0,
            "heat_index_c": 50.0, "condition_text": "Clear", "provider": "demo",
            "data_mode": "demo",
            "observed_at": (now() - timedelta(days=days_ago)).isoformat()})
    services["social"].collect(location, trigger="test", window_hours=24 * 6)
    services["sentiment"].analyze_pending(location_id=location.id)
    end = now()
    agg = services["sentiment"].aggregate(location.id, end - timedelta(days=6), end)
    for obs in services["weather"].history(location.id, end - timedelta(days=6), end):
        services["predictions"].run(location, weather_obs=obs, aggregate=agg, trigger="test")


def test_pdf_report_generation_and_download(client, services, location, admin_headers):
    _seed_week(services, location)
    today = utcnow().date()
    resp = client.post("/api/v1/reports/generate", headers=admin_headers, json={
        "location_id": location.id, "start_date": (today - timedelta(days=7)).isoformat(),
        "end_date": today.isoformat(), "format": "pdf"})
    assert resp.status_code == 201, resp.get_json()
    report = resp.get_json()["data"]

    dl = client.get(f"/api/v1/reports/{report['id']}/download", headers=admin_headers)
    assert dl.status_code == 200
    assert dl.data[:4] == b"%PDF"
    assert "heatwatch" in dl.headers["Content-Disposition"].lower() or "pdf" in dl.headers["Content-Type"]


def test_csv_report_structure(client, services, location, admin_headers):
    _seed_week(services, location)
    today = utcnow().date()
    resp = client.post("/api/v1/reports/generate", headers=admin_headers, json={
        "location_id": location.id, "start_date": (today - timedelta(days=7)).isoformat(),
        "end_date": today.isoformat(), "format": "csv"})
    assert resp.status_code == 201
    report = resp.get_json()["data"]
    dl = client.get(f"/api/v1/reports/{report['id']}/download", headers=admin_headers)
    assert dl.status_code == 200
    lines = dl.data.decode("utf-8-sig").strip().splitlines()
    header = lines[0]
    for column in ("location", "observed_at_utc", "temperature_c", "humidity_pct",
                   "heat_index_c", "wind_speed_kph", "risk_category", "data_mode"):
        assert column in header
    assert len(lines) >= 4  # header + observation rows


def test_report_rejects_invalid_ranges(client, location, admin_headers):
    today = utcnow().date()
    # start after end
    resp = client.post("/api/v1/reports/generate", headers=admin_headers, json={
        "location_id": location.id, "start_date": today.isoformat(),
        "end_date": (today - timedelta(days=2)).isoformat(), "format": "csv"})
    assert resp.status_code == 422
    # future start
    resp = client.post("/api/v1/reports/generate", headers=admin_headers, json={
        "location_id": location.id, "start_date": (today + timedelta(days=1)).isoformat(),
        "end_date": (today + timedelta(days=2)).isoformat(), "format": "csv"})
    assert resp.status_code == 422
    # range too long
    resp = client.post("/api/v1/reports/generate", headers=admin_headers, json={
        "location_id": location.id, "start_date": (today - timedelta(days=400)).isoformat(),
        "end_date": today.isoformat(), "format": "csv"})
    assert resp.status_code == 422
    # bad format
    resp = client.post("/api/v1/reports/generate", headers=admin_headers, json={
        "location_id": location.id, "start_date": today.isoformat(),
        "end_date": today.isoformat(), "format": "xlsx"})
    assert resp.status_code == 422


def test_report_empty_dataset_rejected(client, location, admin_headers):
    resp = client.post("/api/v1/reports/generate", headers=admin_headers, json={
        "location_id": location.id, "start_date": "2001-01-01",
        "end_date": "2001-01-05", "format": "pdf"})
    assert resp.status_code == 422
    assert "No records" in resp.get_json()["error"]["message"]


def test_report_download_requires_ownership(client, services, location, admin_headers, user_headers):
    _seed_week(services, location)
    today = utcnow().date()
    resp = client.post("/api/v1/reports/generate", headers=admin_headers, json={
        "location_id": location.id, "start_date": (today - timedelta(days=7)).isoformat(),
        "end_date": today.isoformat(), "format": "csv"})
    report_id = resp.get_json()["data"]["id"]
    resp = client.get(f"/api/v1/reports/{report_id}/download", headers=user_headers)
    assert resp.status_code == 403  # another user's report


def test_report_records_persisted_with_user(client, services, location, admin_headers, admin_user):
    _seed_week(services, location)
    today = utcnow().date()
    client.post("/api/v1/reports/generate", headers=admin_headers, json={
        "location_id": location.id, "start_date": (today - timedelta(days=7)).isoformat(),
        "end_date": today.isoformat(), "format": "csv"})
    resp = client.get("/api/v1/reports", headers=admin_headers)
    reports = resp.get_json()["data"]
    assert reports and reports[0]["user_id"] == admin_user.id
