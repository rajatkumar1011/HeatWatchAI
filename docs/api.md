# API Summary (v1)

Base URL: `/api/v1` · JSON only · auth via `Authorization: Bearer <JWT>` (12 h expiry).

Success envelope: `{"data": ..., "meta"?}` — Error envelope:
`{"error": {"code", "message", "details"?}}`.

| Group | Endpoint | Auth | Purpose |
|---|---|---|---|
| Health | `GET /health` | public | liveness + mode hint |
| | `GET /health/detailed` | user | DB, providers, last collection runs |
| Auth | `POST /auth/register` | public | register (role=researcher, rate-limited) |
| | `POST /auth/login` | public | login (rate-limited) → JWT + user |
| | `POST /auth/logout` | user | client-side discard acknowledgement |
| | `GET /auth/me` / `PUT /auth/me` | user | profile read / update (email, password) |
| Locations | `GET /locations` (`?monitored=1`), `GET/POST/PUT/DELETE /locations/:id` | user / admin | monitored location management |
| Weather | `GET /weather/current?location_id` | user | latest observation + freshness |
| | `GET /weather/history?location_id&start&end` | user | filtered observations |
| | `POST /weather/refresh {location_id}` | user | run full monitoring pipeline |
| Social | `GET /social/posts?location_id&sentiment&heat_related&page` | user | posts + per-post sentiment |
| | `POST /social/collect {location_id}` | user | collect + analyse + aggregate |
| | `GET /social/summary?location_id&hours` · `GET /social/trend` | user | aggregates |
| Predictions | `GET /predictions/latest` · `GET /predictions/history?days` · `POST /predictions/run` | user | severity assessments with provenance |
| Alerts | `GET /alerts?location_id&status&days` | user | alert list + active count |
| | `POST /alerts/:id/acknowledge` · `POST /alerts/:id/resolve` | user | workflow actions |
| Reports | `POST /reports/generate {location_id, start_date, end_date, format}` | user | build PDF/CSV from DB records |
| | `GET /reports` · `GET /reports/:id/download` | user (owner/admin) | list/download |
| Dashboard | `GET /dashboard?location_id` | user | single aggregate: weather, prediction, sentiment, posts, alerts, advisory, contacts, 7-day series |
| Admin | `GET/PUT /admin/users`, `GET/PUT /admin/settings`, `GET /admin/logs`, `GET /admin/audit`, `GET /admin/data-stats`, `GET /admin/model-status`, `GET /admin/runs`, `GET/POST/DELETE /admin/advisories`, `GET/POST/DELETE /admin/contacts` | admin | FR-09 management surface (audited) |

Status codes: 200/201 success · 400/401/403/404/405/409/410/413/422 client errors ·
429 rate-limited · 500 logged internal · 503 external provider unavailable.
