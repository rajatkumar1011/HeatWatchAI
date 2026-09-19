# SRS Traceability Matrix — FR-01 … FR-10

Status legend: ✅ implemented & verified (test/behaviour evidence) · 🔶 implemented with documented constraint.

| Req | Requirement | Backend modules | API endpoints | Frontend | Database entities | Tests | Status |
|---|---|---|---|---|---|---|---|
| FR-01 | User registration & authentication | `app/api/auth.py`, `app/auth/`, `models/user.py` (bcrypt) | `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET/PUT /auth/me` | Auth.tsx (login/register), AuthContext, protected routes, Profile page | `users` (unique email/username) | test_auth.py (13 tests) | ✅ |
| FR-02 | Weather data collection | `services/weather_service.py`, `integrations/weather/*` (OWM + demo), `utils/heat.py` | `GET /weather/current`, `GET /weather/history`, `POST /weather/refresh` | WeatherPage, dashboard metric cards | `locations`, `weather_observations` (unique provider obs, indexes) | test_weather.py (10) | ✅ |
| FR-03 | Social media data collection | `services/social_service.py`, `integrations/social/*` (demo + Reddit), keyword config | `GET /social/posts`, `POST /social/collect` | SentimentPage post feed, dashboard feed | `social_posts` (unique external id, locationless posts allowed) | test_social_sentiment.py (7) | 🔶 live provider requires credentials; labelled demo provider default |
| FR-04 | AI-based sentiment analysis | `services/sentiment_service.py` (VADER + relevance/distress layers) | `GET /social/summary`, `GET /social/trend` | SentimentPage, dashboard sentiment card | `sentiment_results`, `sentiment_aggregates` | test_social_sentiment.py (7) + pipeline | ✅ |
| FR-05 | Heatwave severity prediction | `services/prediction_service.py`, `app/ml/*` | `GET /predictions/latest`, `GET /predictions/history`, `POST /predictions/run` | PredictionsPage, dashboard prediction card + risk meter | `predictions` (FKs to weather + aggregate, provenance JSON) | test_prediction_alerts.py (9) | 🔶 model = documented heat-index banding approximation (see model card) |
| FR-06 | Alert generation | `services/alert_service.py` (thresholds, cooldown, escalation, auto-resolve) | `GET /alerts`, `POST /alerts/:id/acknowledge`, `POST /alerts/:id/resolve` | AlertsPage, dashboard alert banner | `alerts` (FK prediction/location/user) | test_prediction_alerts.py + integration | ✅ |
| FR-07 | Dashboard visualisation | `api/dashboard.py` (single aggregate endpoint) | `GET /dashboard` | DashboardPage (cards, gauge, charts, feed, advisory, contacts, quick actions) | reads all entities | api_smoke_test + integration + browser E2E | ✅ |
| FR-08 | Historical report generation | `services/report_service.py` (ReportLab PDF + CSV) | `POST /reports/generate`, `GET /reports`, `GET /reports/:id/download` | ReportsPage, dashboard quick actions | `report_records` (per-user metadata) | test_reports.py (6) | ✅ |
| FR-09 | Administrative panel | `api/admin.py` | `/admin/users`, `/admin/settings`, `/admin/logs`, `/admin/audit`, `/admin/data-stats`, `/admin/model-status`, `/admin/runs`, `/admin/advisories`, `/admin/contacts` | AdminPage (5 tabs) | `users`, `app_settings`, `system_logs`, `audit_logs`, `model_registry`, `government_advisories`, `emergency_contacts`, `collection_runs` | test_admin.py (11) | ✅ |
| FR-10 | Error handling & recovery | error handlers, `utils/responses.py`, `utils/rate_limit.py`, retries in integrations, cached fallback in monitoring | `/health`, `/health/detailed` | ErrorState/EmptyState/spinners, axios error mapping | `system_logs`, `audit_logs`, `collection_runs` | rate-limit test, provider-outage integration test, JSON-404/405 tests | ✅ |

## Permissions matrix (backend-enforced)

| Capability | admin | officer | authority | researcher | anonymous |
|---|---|---|---|---|---|
| Register public account | — | — | — | — | ✅ (role=researcher) |
| Login / profile | ✅ | ✅ | ✅ | ✅ | ❌ |
| View dashboard, weather, sentiment, predictions, alerts | ✅ | ✅ | ✅ | ✅ | ❌ |
| Trigger refresh / collect / predict | ✅ | ✅ | ✅ | ✅ | ❌ |
| Generate & download own reports | ✅ | ✅ | ✅ | ✅ | ❌ |
| Acknowledge alerts | ✅ | ✅ | ✅ | ✅ | ❌ |
| Download others' reports | ✅ | ❌ | ❌ | ❌ | ❌ |
| User management, settings, logs, advisories, contacts | ✅ | ❌ | ❌ | ❌ | ❌ |

## Behavioural UML ↔ implementation

| Diagram | Implementation evidence |
|---|---|
| Use case diagram | actor capabilities = permissions matrix above |
| Registration/login activity | `auth.py` register→validate→create→login→session; dashboard redirect (browser-verified) |
| Monitoring & alert activity | `monitoring_service.run_pipeline` (weather→social→sentiment→predict→alert) |
| Sequence diagram | dashboard request path: user→API→services→DB; external APIs via adapters |
| State machine | collection/prediction states recorded in `collection_runs` (running/success/failed) |
| Collaboration diagram | numbered interactions = service call graph in `services/` |

## Verification evidence summary

- `backend/tests/` — **66 pytest tests, all passing** (auth, weather, social, sentiment,
  prediction, alerts, reports, admin, integration pipeline, provider-outage recovery).
- `backend/api_smoke_test.py` — **41/41 live API checks** against a running server.
- `frontend/tests/` — **4/4 vitest tests**; `npm run build` production build succeeds.
- Browser E2E walkthrough (in-app Chromium, 1440×900): login → dashboard (Mumbai high-risk
  banner, metrics, charts, demo labelling) → location switch (Ahmedabad moderate) → alerts
  (history + acknowledge) → admin (users/providers/model/data tabs) → PDF report generated
  and downloaded through the UI.

## UI/UX redesign addendum

A full interface redesign was applied on top of the working system (no functional
regressions; suites re-run green afterwards):

- Design system: crimson `#BD1426` brand, navy `#111827` shell, Inter Variable with
  tabular numerals, unified component library (buttons, cards, pills, segmented controls,
  tabs, skeletons, toasts, confirm dialogs, professional icon set).
- Application shell: collapsible sidebar, contextual page-title header with user menu,
  mobile drawer navigation (verified at 1280/768/390 viewports).
- Dashboard: hero risk card with segmented severity scale (40/70 threshold markers),
  compact metric tiles, refined right intelligence panel, contextual actions.
- Charts: fixed duplicated/repeated timestamp ticks (span-aware formatting + seeder
  backdating of prediction timestamps), risk-threshold reference lines, corrected
  sentiment distribution pie (was overlapping stacked pies).
- Alerts/Predictions/Reports/Admin: compact operational layouts; prediction technical
  provenance moved into an expandable audit panel (information preserved); destructive
  admin actions behind confirmation dialogs.
- Targeted backend data-quality fixes: expanded demo post templates (duplicate text
  removed), heat-relevance-first dashboard feed ordering, demo prediction timestamps
  backdated to their assessment time.
- **PDF report restyled** to the design system: crimson masthead, navy section headings,
  colour-coded risk/alert/sentiment tables, violet DEMO provenance callout, temperature +
  heat-index trend chart, page-numbered footer (all prior content requirements retained).
