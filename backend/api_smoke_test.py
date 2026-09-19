"""End-to-end API smoke test against the running backend (dev DB)."""
import json
import urllib.request

BASE = "http://127.0.0.1:5000/api/v1"


def call(method: str, path: str, body: dict | None = None, token: str | None = None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def main():
    failures = []

    def check(name, cond, detail=""):
        print(("PASS" if cond else "FAIL"), name, detail if not cond else "")
        if not cond:
            failures.append(name)

    # public health
    s, b = call("GET", "/health")
    check("health", s == 200 and b["status"] == "ok")

    # unauthenticated access blocked
    s, b = call("GET", "/dashboard")
    check("dashboard requires auth", s == 401)

    # bad login
    s, b = call("POST", "/auth/login", {"identifier": "admin", "password": "wrong"})
    check("bad login rejected", s == 401)

    # register validation
    s, b = call("POST", "/auth/register", {"username": "x", "email": "bad", "password": "short", "password_confirm": "short"})
    check("register validation", s == 422)

    # register + duplicate (idempotent re-run: 409 is acceptable)
    s, b = call("POST", "/auth/register", {"username": "smoke_user", "email": "smoke@example.com", "password": "Passw0rd1", "password_confirm": "Passw0rd1"})
    check("register works", s in (201, 409), str(b))
    s, b = call("POST", "/auth/register", {"username": "smoke_user", "email": "smoke2@example.com", "password": "Passw0rd1", "password_confirm": "Passw0rd1"})
    check("duplicate username blocked", s == 409)

    # login as admin
    s, b = call("POST", "/auth/login", {"identifier": "admin", "password": "Admin#12345"})
    check("admin login", s == 200)
    admin_token = b["data"]["access_token"]

    # me
    s, b = call("GET", "/auth/me", token=admin_token)
    check("me", s == 200 and b["data"]["user"]["role"] == "admin")

    # locations
    s, b = call("GET", "/locations", token=admin_token)
    check("locations list", s == 200 and len(b["data"]) >= 5)
    mumbai = next(l for l in b["data"] if l["name"] == "Mumbai")
    nagpur = next(l for l in b["data"] if l["name"] == "Nagpur")

    # dashboard (Mumbai - should have prediction + alert)
    s, b = call("GET", f"/dashboard?location_id={mumbai['id']}", token=admin_token)
    d = b["data"]
    check("dashboard payload", s == 200)
    check("dashboard weather", d["weather"].get("available") is not False)
    check("dashboard weather demo-labelled", d["weather"].get("data_mode") == "demo" or d["weather"].get("freshness") == "demo")
    check("dashboard prediction", d["prediction"].get("available") is not False)
    check("dashboard prediction provenance", "ml_severity" in d["prediction"]["methodology"] or "rule" in d["prediction"]["methodology"])
    check("dashboard sentiment", d["sentiment"].get("available") is True and d["sentiment"]["post_count"] > 0)
    check("dashboard posts", len(d["posts"]) > 0)
    check("dashboard advisory demo-labelled", d["advisory"].get("is_demo") is True)
    check("dashboard emergency contacts", len(d["emergency_contacts"]) >= 4)
    check("dashboard series", len(d["series"]["weather"]) > 10 and len(d["series"]["predictions"]) > 0)

    # Nagpur should be low risk
    s, b = call("GET", f"/predictions/latest?location_id={nagpur['id']}", token=admin_token)
    check("nagpur low risk", b["data"]["risk_category"] == "low", str(b["data"].get("risk_category")))

    # alerts
    s, b = call("GET", f"/alerts?location_id={mumbai['id']}", token=admin_token)
    check("mumbai has alerts", s == 200 and b["meta"]["total"] > 0)
    alert_id = b["data"][0]["id"]
    s, b = call("POST", f"/alerts/{alert_id}/acknowledge", token=admin_token)
    check("acknowledge alert", s == 200 and b["data"]["status"] == "acknowledged")

    # weather refresh (demo provider -> stored)
    s, b = call("POST", "/weather/refresh", {"location_id": mumbai["id"]}, token=admin_token)
    check("refresh pipeline", s == 200 and b["data"]["steps"]["prediction"]["status"] in ("created", "reused"), str(b))

    # social collect (second run: all posts already exist -> duplicates)
    s, b = call("POST", "/social/collect", {"location_id": mumbai["id"]}, token=admin_token)
    check("social collect", s == 200 and b["data"]["stored"] + b["data"]["duplicates"] > 0)

    # sentiment trend
    s, b = call("GET", f"/social/trend?location_id={mumbai['id']}", token=admin_token)
    check("sentiment trend", s == 200 and len(b["data"]) > 3)

    # report generation (PDF + CSV) and download
    s, b = call("POST", "/reports/generate", {"location_id": mumbai["id"], "start_date": "2026-09-05", "end_date": "2026-09-19", "format": "pdf"}, token=admin_token)
    check("pdf report generated", s == 201, str(b))
    pdf_id = b["data"]["id"] if s == 201 else None
    s, b = call("POST", "/reports/generate", {"location_id": mumbai["id"], "start_date": "2026-09-05", "end_date": "2026-09-19", "format": "csv"}, token=admin_token)
    check("csv report generated", s == 201)
    csv_id = b["data"]["id"] if s == 201 else None

    s, b = call("POST", "/reports/generate", {"location_id": mumbai["id"], "start_date": "2026-09-19", "end_date": "2026-09-05", "format": "csv"}, token=admin_token)
    check("invalid date range rejected", s == 422)
    s, b = call("POST", "/reports/generate", {"location_id": mumbai["id"], "start_date": "2001-01-01", "end_date": "2001-01-02", "format": "csv"}, token=admin_token)
    check("empty dataset rejected", s == 422)

    if pdf_id:
        req = urllib.request.Request(f"{BASE}/reports/{pdf_id}/download")
        req.add_header("Authorization", f"Bearer {admin_token}")
        with urllib.request.urlopen(req) as resp:
            head = resp.read(5)
        check("pdf downloads", head[:4] == b"%PDF")
    if csv_id:
        req = urllib.request.Request(f"{BASE}/reports/{csv_id}/download")
        req.add_header("Authorization", f"Bearer {admin_token}")
        with urllib.request.urlopen(req) as resp:
            line = resp.readline().decode()
        check("csv downloads with header", "temperature_c" in line)

    # non-admin restrictions
    s, b = call("POST", "/auth/login", {"identifier": "researcher_iyer", "password": "Demo#12345"})
    check("demo user login", s == 200)
    user_token = b["data"]["access_token"]
    s, b = call("GET", "/admin/users", token=user_token)
    check("admin endpoint blocked for non-admin", s == 403)

    # admin panel
    s, b = call("GET", "/admin/users", token=admin_token)
    check("admin users list", s == 200 and b["meta"]["total"] >= 4)
    s, b = call("GET", "/admin/data-stats", token=admin_token)
    check("admin data stats", s == 200 and b["data"]["counts"]["predictions"] > 0)
    s, b = call("GET", "/admin/model-status", token=admin_token)
    check("admin model status", s == 200 and b["data"]["severity_model"]["loaded"] is True)
    s, b = call("GET", "/admin/logs?category=alert", token=admin_token)
    check("admin logs", s == 200)
    s, b = call("PUT", "/admin/settings", {"alert_high_threshold": 75}, token=admin_token)
    check("settings update", s == 200)
    s, b = call("PUT", "/admin/settings", {"alert_high_threshold": 500}, token=admin_token)
    check("settings validation", s == 422)

    # last-admin guard: try demoting self
    s, b = call("GET", "/auth/me", token=admin_token)
    admin_id = b["data"]["user"]["id"]
    s, b = call("PUT", f"/admin/users/{admin_id}", {"role": "researcher"}, token=admin_token)
    check("last-admin demotion blocked", s == 409)

    # detailed health
    s, b = call("GET", "/health/detailed", token=admin_token)
    check("detailed health", s == 200 and b["data"]["database"]["ok"] is True)

    print()
    if failures:
        print("FAILURES:", failures)
        raise SystemExit(1)
    print("ALL API SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
