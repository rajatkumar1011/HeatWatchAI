"""FR-01: registration, authentication, authorization tests."""
from __future__ import annotations

from tests.conftest import auth_header

REGISTER = "/api/v1/auth/register"


def test_register_success(client):
    resp = client.post(REGISTER, json={
        "username": "newuser", "email": "new@example.com",
        "password": "Passw0rd1", "password_confirm": "Passw0rd1"})
    assert resp.status_code == 201
    body = resp.get_json()["data"]
    assert body["user"]["role"] == "researcher"  # public registration never grants admin


def test_register_password_mismatch(client):
    resp = client.post(REGISTER, json={
        "username": "newuser", "email": "new@example.com",
        "password": "Passw0rd1", "password_confirm": "Different1"})
    assert resp.status_code == 422


def test_register_validation_errors(client):
    resp = client.post(REGISTER, json={
        "username": "x", "email": "not-an-email", "password": "short", "password_confirm": "short"})
    assert resp.status_code == 422
    details = resp.get_json()["error"]["details"]
    assert len(details["messages"]) >= 2


def test_duplicate_username_and_email(client):
    payload = {"username": "dup", "email": "dup@example.com",
               "password": "Passw0rd1", "password_confirm": "Passw0rd1"}
    assert client.post(REGISTER, json=payload).status_code == 201
    resp = client.post(REGISTER, json={**payload, "email": "other@example.com"})
    assert resp.status_code == 409
    resp = client.post(REGISTER, json={**payload, "username": "other"})
    assert resp.status_code == 409


def test_login_success_and_me(client):
    client.post(REGISTER, json={"username": "loginuser", "email": "l@example.com",
                                "password": "Passw0rd1", "password_confirm": "Passw0rd1"})
    resp = client.post("/api/v1/auth/login", json={"identifier": "loginuser", "password": "Passw0rd1"})
    assert resp.status_code == 200
    headers = {"Authorization": f"Bearer {resp.get_json()['data']['access_token']}"}
    resp = client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["user"]["username"] == "loginuser"


def test_login_by_email(client):
    client.post(REGISTER, json={"username": "emailuser", "email": "by@example.com",
                                "password": "Passw0rd1", "password_confirm": "Passw0rd1"})
    resp = client.post("/api/v1/auth/login", json={"identifier": "by@example.com", "password": "Passw0rd1"})
    assert resp.status_code == 200


def test_login_wrong_password(client):
    client.post(REGISTER, json={"username": "badpw", "email": "badpw@example.com",
                                "password": "Passw0rd1", "password_confirm": "Passw0rd1"})
    resp = client.post("/api/v1/auth/login", json={"identifier": "badpw", "password": "WrongPass1"})
    assert resp.status_code == 401
    assert "error" in resp.get_json()


def test_protected_endpoint_requires_token(client):
    resp = client.get("/api/v1/locations")
    assert resp.status_code == 401


def test_admin_endpoint_forbidden_for_normal_user(client, user_headers):
    resp = client.get("/api/v1/admin/users", headers=user_headers)
    assert resp.status_code == 403


def test_admin_can_access_admin_endpoints(client, admin_headers):
    resp = client.get("/api/v1/admin/users", headers=admin_headers)
    assert resp.status_code == 200


def test_deactivated_user_cannot_login(client, admin_user, admin_headers, db, normal_user):
    normal_user.is_active = False
    db.session.commit()
    resp = client.post("/api/v1/auth/login", json={"identifier": "user_t", "password": "Passw0rd1"})
    assert resp.status_code == 403


def test_profile_update_password(client, normal_user):
    headers = auth_header(client, "user_t")
    # wrong current password
    resp = client.put("/api/v1/auth/me", headers=headers,
                      json={"current_password": "nope", "new_password": "NewPass99"})
    assert resp.status_code == 401
    resp = client.put("/api/v1/auth/me", headers=headers,
                      json={"current_password": "Passw0rd1", "new_password": "NewPass99"})
    assert resp.status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": "user_t", "password": "NewPass99"}).status_code == 200


def test_passwords_never_stored_plaintext(client, db):
    client.post(REGISTER, json={"username": "hashcheck", "email": "hash@example.com",
                                "password": "Passw0rd1", "password_confirm": "Passw0rd1"})
    from app.models import User
    user = db.session.query(User).filter(User.username == "hashcheck").first()
    assert user.password_hash != "Passw0rd1"
    assert user.password_hash.startswith("$2b$")  # bcrypt


def test_login_rate_limiting(client):
    """FR-10: brute-force attempts are rate limited (SRS security attrs)."""
    from app.utils.rate_limit import clear_rate_limits

    clear_rate_limits()
    client.application.config["AUTH_RATE_LIMIT"] = 3
    try:
        for _ in range(3):
            client.post("/api/v1/auth/login", json={"identifier": "nobody", "password": "Whatever1"})
        resp = client.post("/api/v1/auth/login", json={"identifier": "nobody", "password": "Whatever1"})
        assert resp.status_code == 429
    finally:
        clear_rate_limits()
        client.application.config["AUTH_RATE_LIMIT"] = 10000
