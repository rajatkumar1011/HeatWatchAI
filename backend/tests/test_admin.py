"""FR-09: administration panel tests + FR-10 error handling checks."""
from __future__ import annotations

import json


def test_user_search_and_filter(client, admin_headers, admin_user, normal_user):
    resp = client.get("/api/v1/admin/users?search=user_t", headers=admin_headers)
    users = resp.get_json()["data"]
    assert len(users) == 1 and users[0]["username"] == "user_t"
    resp = client.get("/api/v1/admin/users?role=admin", headers=admin_headers)
    assert all(u["role"] == "admin" for u in resp.get_json()["data"])


def test_role_change_and_activate_deactivate(client, admin_headers, admin_user, normal_user, db):
    resp = client.put(f"/api/v1/admin/users/{normal_user.id}", headers=admin_headers,
                      json={"role": "officer"})
    assert resp.get_json()["data"]["role"] == "officer"
    resp = client.put(f"/api/v1/admin/users/{normal_user.id}", headers=admin_headers,
                      json={"is_active": False})
    assert resp.get_json()["data"]["is_active"] is False


def test_cannot_deactivate_last_admin(client, admin_headers, admin_user):
    resp = client.put(f"/api/v1/admin/users/{admin_user.id}", headers=admin_headers,
                      json={"is_active": False})
    assert resp.status_code == 409


def test_cannot_demote_last_admin(client, admin_headers, admin_user):
    resp = client.put(f"/api/v1/admin/users/{admin_user.id}", headers=admin_headers,
                      json={"role": "researcher"})
    assert resp.status_code == 409


def test_settings_roundtrip_and_validation(client, admin_headers):
    resp = client.get("/api/v1/admin/settings", headers=admin_headers)
    assert resp.status_code == 200
    defaults = resp.get_json()["data"]
    assert "alert_high_threshold" in defaults
    resp = client.put("/api/v1/admin/settings", headers=admin_headers,
                      json={"alert_cooldown_minutes": 240})
    assert resp.status_code == 200
    resp = client.get("/api/v1/admin/settings", headers=admin_headers)
    assert resp.get_json()["data"]["alert_cooldown_minutes"] == 240
    # out of range
    resp = client.put("/api/v1/admin/settings", headers=admin_headers,
                      json={"alert_cooldown_minutes": -5})
    assert resp.status_code == 422
    # unknown key
    resp = client.put("/api/v1/admin/settings", headers=admin_headers,
                      json={"not_a_setting": 1})
    assert resp.status_code == 422


def test_keyword_configuration(client, admin_headers):
    resp = client.put("/api/v1/admin/settings", headers=admin_headers,
                      json={"social_keywords": ["heatwave", "looo"], "distress_keywords": ["dehydration"]})
    assert resp.status_code == 200
    resp = client.get("/api/v1/admin/settings", headers=admin_headers)
    data = resp.get_json()["data"]
    assert data["social_keywords"] == ["heatwave", "looo"]


def test_advisory_and_contact_management(client, admin_headers):
    resp = client.post("/api/v1/admin/advisories", headers=admin_headers, json={
        "title": "Sample", "body": "Text", "source_name": "Test Source", "is_demo": True})
    assert resp.status_code == 201
    advisory_id = resp.get_json()["data"]["id"]
    assert client.delete(f"/api/v1/admin/advisories/{advisory_id}", headers=admin_headers).status_code == 200

    resp = client.post("/api/v1/admin/contacts", headers=admin_headers, json={
        "name": "Test Helpline", "phone": "12345", "category": "test"})
    assert resp.status_code == 201
    contact_id = resp.get_json()["data"]["id"]
    assert client.delete(f"/api/v1/admin/contacts/{contact_id}", headers=admin_headers).status_code == 200


def test_logs_and_audit_listing(client, admin_headers):
    resp = client.get("/api/v1/admin/logs", headers=admin_headers)
    assert resp.status_code == 200
    resp = client.get("/api/v1/admin/audit", headers=admin_headers)
    assert resp.status_code == 200


def test_data_stats_and_model_status(client, admin_headers):
    resp = client.get("/api/v1/admin/data-stats", headers=admin_headers)
    stats = resp.get_json()["data"]["counts"]
    for key in ("users", "locations", "weather_observations", "social_posts",
                "sentiment_results", "predictions", "alerts"):
        assert key in stats
    resp = client.get("/api/v1/admin/model-status", headers=admin_headers)
    body = resp.get_json()["data"]
    assert body["severity_model"]["loaded"] is True
    assert body["severity_model"]["evaluation"]


def test_settings_never_expose_passwords(client, admin_headers, db):
    resp = client.get("/api/v1/admin/users", headers=admin_headers)
    for user in resp.get_json()["data"]:
        assert "password_hash" not in user
        assert "password" not in user


# ---------------------------------------------------------- FR-10 behaviour

def test_unknown_route_returns_json_404(client):
    resp = client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "not_found"


def test_malformed_json_returns_422(client, admin_headers):
    resp = client.post("/api/v1/auth/login", data="{not json",
                       content_type="application/json")
    assert resp.status_code in (400, 415, 422)


def test_method_not_allowed_json(client):
    resp = client.delete("/api/v1/health")
    assert resp.status_code == 405
