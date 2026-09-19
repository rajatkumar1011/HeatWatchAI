# HeatWatch AI

**AI-Based Climate Intelligence System for Heatwave Monitoring, Prediction, and Early Warning.**

HeatWatch AI is the working implementation of the OOSE Lab Mini Project (KJS-CES-01,
K. J. Somaiya School of Engineering). It integrates meteorological data with AI-based
sentiment analysis of public social media posts to assess heatwave severity, generate
early-warning alerts, and expose everything through a professional climate-intelligence
dashboard for disaster-management officers, government authorities, environmental
researchers, and system administrators.

The original project specification lives at `OOSE_Lab_Project.pdf` in the repository
root (untouched). `docs/traceability.md` maps every SRS requirement (FR-01 … FR-10)
to its implementation, API surface, database entity, and tests.

---

## 1. Problem statement

Traditional heatwave monitoring relies on meteorological parameters only. It misses the
real-time human impact that citizens report on social media (dehydration, power cuts,
water shortages, health emergencies) before official statistics appear. HeatWatch AI
fuses both signals — weather observations and heat-related public distress — into a
single early-warning workflow.

## 2. Core features

| # | Feature (SRS) | What is implemented |
|---|---------------|---------------------|
| FR-01 | User registration & authentication | JWT auth, bcrypt password hashing, duplicate prevention, 4 roles with backend RBAC, profile management, rate limiting, secure admin bootstrap |
| FR-02 | Weather data collection | OpenWeatherMap live adapter + labelled demo provider, NWS heat-index calculation with applicability envelope, validation, dedup, freshness tracking (LIVE/CACHED/DEMO), bounded retries (3× backoff) |
| FR-03 | Social media data collection | Replaceable provider interface, demo provider + Reddit public read-only adapter, keyword configuration, duplicate suppression, no fabricated geolocation |
| FR-04 | AI-based sentiment analysis | VADER (pretrained English social-media model) with per-post scores, plus a transparent heat-relevance/distress keyword layer that separates *general sentiment* from *heat distress* |
| FR-05 | Heatwave severity prediction | scikit-learn RandomForest severity model (reproducible training + evaluation) fused with sentiment through a documented bounded rule layer; full provenance (methodology, inputs, contributing factors) stored with every prediction |
| FR-06 | Alert generation | Configurable thresholds, cooldown + escalation dedup policy, auto-resolution on recovery, acknowledge workflow, alerts always labelled as application warnings (never official advisories) |
| FR-07 | Dashboard visualisation | Single-aggregate dashboard API; metric cards, risk gauge, sentiment panel, live post feed, advisory panel, emergency contacts, temperature/severity/sentiment/alert charts; every demo/cached record explicitly labelled |
| FR-08 | Historical report generation | Branded PDF (ReportLab) and CSV exports generated from the actual filtered database records, with provenance and methodology notes; report metadata persisted per user |
| FR-09 | Administration panel | User management (roles, activation, last-admin guard), alert thresholds & collection intervals, keyword configuration, advisory/contact management, system logs, audit trail, data/model status |
| FR-10 | Error handling & recovery | Consistent JSON error envelope, rate limits, retries with backoff, cached-data fallback on provider outage, structured SystemLog + AuditLog, health endpoints |

## 3. Technology stack

- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS v4, Recharts, react-router
- **Backend:** Python 3.10+, Flask 3, Flask-SQLAlchemy, Flask-Migrate (Alembic), Flask-JWT-Extended, Pydantic (request validation), Waitress (Windows-friendly WSGI server)
- **Database:** MySQL 8 (documented target, provided via docker-compose; PyMySQL driver). Local dev without a MySQL server falls back to SQLite via SQLAlchemy — real file persistence, same schema through migrations.
- **ML:** scikit-learn (RandomForest severity model), joblib artifacts, VADER sentiment (offline), pandas/numpy for the dataset builder
- **Reports:** ReportLab (PDF), csv module (CSV)
- **Scheduling:** APScheduler in a dedicated process (`run_scheduler.py`)
- **Tests:** pytest (66 backend/integration tests), vitest (frontend unit tests), API smoke script, browser E2E walkthrough

## 4. Architecture

```
Browser (React SPA, http://localhost:5173)
   │  /api/v1/* (JSON, JWT bearer)
   ▼
Flask backend (http://localhost:5000)
   ├─ api/         REST blueprints (auth, locations, weather, social, predictions,
   │               alerts, reports, admin, dashboard, health)
   ├─ services/    weather, social, sentiment, prediction+fusion, alerts, reports,
   │               monitoring orchestrator
   ├─ integrations/ weather + social provider adapters (live & demo)
   ├─ ml/          features, train_severity.py, inference, artifacts
   └─ models/      SQLAlchemy entities (15 tables)
   ▼
MySQL 8 / SQLite (SQLAlchemy + Alembic migrations)
```

The full monitoring pipeline (matching the behavioural UML diagrams) runs in
`app/services/monitoring_service.py`:

```
location → weather fetch → social collect → preprocess → sentiment analysis
        → sentiment aggregate → severity prediction → alert evaluation → persistence
```

## 5. Project layout

```
HeatWatchAI/
├── OOSE_Lab_Project.pdf        # original specification (untouched)
├── backend/
│   ├── app/
│   │   ├── api/                # REST endpoints (v1)
│   │   ├── auth/               # JWT helpers, role guards, validation
│   │   ├── integrations/       # weather + social provider adapters
│   │   ├── ml/                 # features, training, inference, artifacts/
│   │   ├── models/             # SQLAlchemy models
│   │   ├── services/           # business logic + monitoring pipeline
│   │   ├── utils/              # heat index, time, logging, rate limit
│   │   └── __init__.py         # app factory
│   ├── migrations/             # Alembic (Flask-Migrate)
│   ├── tests/                  # pytest suite (66 tests)
│   ├── api_smoke_test.py       # live end-to-end API checks (41 assertions)
│   ├── config.py  run.py  run_scheduler.py  seed_demo.py  create_admin.py
├── frontend/
│   ├── src/{api,components,context,pages,styles,types,utils}
│   ├── tests/                  # vitest unit tests
│   └── package.json  vite.config.ts  tsconfig*.json
├── docs/
│   ├── traceability.md         # FR-01…FR-10 ↔ code/tests matrix
│   ├── model/model_card.md     # severity + sentiment model documentation
│   ├── deployment.md           # deployment, MySQL, backups, HTTPS
│   ├── architecture.md  api.md
├── docker-compose.yml          # MySQL + backend + frontend stack
├── .env.example                # every supported environment variable
└── README.md
```

## 6. Local setup (Windows)

Prerequisites: Python 3.10+ (`py` launcher), Node.js 18+ (LTS), and optionally
MySQL 8 or Docker Desktop.

```bat
cd HeatWatchAI

:: 1. Python virtual environment + dependencies
py -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements.txt

:: 2. Configuration
copy .env.example backend\.env
:: edit backend\.env — set SECRET_KEY / JWT_SECRET_KEY at minimum

:: 3. Database schema through migrations (SQLite fallback if no DATABASE_URL)
cd backend
set FLASK_APP=run.py
..\.venv\Scripts\python -m flask db upgrade

:: 4. Initial administrator (secure bootstrap — never via public registration)
..\.venv\Scripts\python create_admin.py --username admin --email admin@example.com --password Your#Password

:: 5. Severity model (one-time; artifact is committed but retraining is reproducible)
..\.venv\Scripts\python -m app.ml.train_severity

:: 6. Demonstration data (clearly-labelled demo records, exercises the whole system)
..\.venv\Scripts\python seed_demo.py

:: 7. Start the backend (waitress, http://localhost:5000)
..\.venv\Scripts\python run.py

:: 8. Frontend (second terminal)
cd ..\frontend
npm install
npm run dev
```

Open **http://localhost:5173** and sign in. With the demo seed: `admin / Admin#12345`
(administrator) or `officer_verma`, `authority_rao`, `researcher_iyer` / `Demo#12345`.
Demo accounts are seeded demonstration fixtures — change or remove them for any real
deployment (they are marked `is_demo` in the database).

### Linux/macOS

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example backend/.env
cd backend && export FLASK_APP=run.py
flask db upgrade
python create_admin.py --username admin --email admin@example.com --password Your#Password
python -m app.ml.train_severity && python seed_demo.py
python run.py                # terminal 1
cd ../frontend && npm install && npm run dev   # terminal 2
```

### Docker (MySQL included)

```bash
docker compose up --build
```
This provisions MySQL 8, runs migrations + admin bootstrap + demo seed, and starts
both servers. See the note in `docker-compose.yml` about verification scope.

## 7. Database setup and migrations

Schema creation is reproducible through Flask-Migrate/Alembic (`backend/migrations/`).
Developers never create tables manually:

```bat
cd backend
set FLASK_APP=run.py
..\.venv\Scripts\python -m flask db upgrade     # apply
..\.venv\Scripts\python -m flask db migrate -m "change"   # autogenerate a new revision
```

**MySQL:** set `DATABASE_URL=mysql+pymysql://user:pass@host:3306/heatwatch?charset=utf8mb4`.
The migration and all models use engine-agnostic types and are compatible with MySQL 8
(utf8mb4, InnoDB, FKs, unique constraints, indexes).

**SQLite fallback (development):** without `DATABASE_URL` the app uses
`heatwatch_dev.db` — genuine file persistence for local runs, not an in-memory store.

### Backup & recovery

```bash
# MySQL (schedule daily via cron/Task Scheduler)
mysqldump -u heatwatch -p --single-transaction heatwatch > backup_$(date +%F).sql
# restore
mysql -u heatwatch -p heatwatch < backup_YYYY-MM-DD.sql
```

The SQLite dev database is a single file — copy it while the server is stopped.
Scheduling production backups is a deployment concern; see `docs/deployment.md`.

## 8. Environment configuration

Every supported variable, with placeholders and explanations, is in `.env.example`.
Highlights:

- `DATA_MODE=auto|live|demo` — `auto` uses live providers when credentials exist and
  the clearly-labelled demo providers otherwise; `live` refuses demo substitution;
  `demo` forces demonstration data everywhere.
- `OPENWEATHER_API_KEY` — server-side only; never shipped to the frontend.
- `SOCIAL_PROVIDER` — `auto` / `demo` / `reddit` (public read-only search).
- Alert thresholds can be edited live in the admin panel (stored in `app_settings`).

## 9. Initial administrator setup

Administrators are **never** creatable through public registration (new registrations
always become researchers). The controlled bootstrap:

```bat
cd backend
..\.venv\Scripts\python create_admin.py --username admin --email admin@example.com --password S3curePass
:: or via environment variables ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD
:: interactive: flask --app run.py create-admin
```

## 10. Demonstration mode vs live mode

- **Live mode** requires `OPENWEATHER_API_KEY` (weather) and an authorised social data
  source. Real observations/posts run through the genuine pipeline. On provider outage
  the system serves the newest cached observation labelled `CACHED DATA` — it never
  silently substitutes synthetic data.
- **Demonstration mode** seeds reproducible demo records (`seed_demo.py`): 5 Indian
  cities, 30 days of synthetic weather with a Mumbai heatwave episode, two weeks of
  public posts (analysed by the *real* VADER pipeline), daily aggregates, predictions,
  and a 4-day alert sequence. Every demo row carries `data_mode='demo'` and the UI,
  API, charts, and reports label it `DEMO DATA`. Demo records never claim to be real
  observations or real public posts.

## 11. ML training & inference

```bat
cd backend
:: rebuild + evaluate the weather severity model (writes artifacts + metadata)
..\.venv\Scripts\python -m app.ml.train_severity
:: after retraining, restart the backend so the new artifact is loaded
```

- **Severity model:** RandomForest trained on a reproducible synthetic grid whose
  labels follow the documented NWS heat-index banding. Metrics are reported honestly
  (they measure agreement with the banding, **not** validated real-world prediction —
  see `docs/model/model_card.md`).
- **Sentiment:** VADER pretrained lexicon (offline). No training required.
- **Fusion:** rule-based, bounded (+12 max), upward-only; documented in the API and
  model card. Sentiment can never silently downgrade a weather-based warning.
- Inference: `app/ml/inference.py` loads the artifact with the exact training-time
  feature builder; the admin panel exposes version + evaluation + limitations.

## 12. Running tests

```bat
:: backend + integration (66 tests, no external credentials required)
cd backend && ..\.venv\Scripts\python -m pytest

:: frontend unit tests
cd frontend && npm test

:: production build check
cd frontend && npm run build

:: live API smoke test (requires the backend running)
cd backend && ..\.venv\Scripts\python api_smoke_test.py
```

## 13. Generating reports

Dashboard quick actions, or the Historical Reports page (filters: location, start,
end; formats PDF/CSV). Reports are built from the actual filtered records, include
provenance (DEMO/LIVE), methodology notes, and the requesting user's metadata. The PDF
is styled with the application's design system (crimson brand masthead, navy headings,
colour-coded risk and alert tables, provenance callout, page-numbered footer) so exports
visually match the product.

## 14. Known limitations

1. **No real-world label validation.** The repository contains no labelled historical
   heatwave dataset. The severity model is a documented approximation of the NWS
   heat-index banding; its metrics reflect that banding, not validated outcomes.
2. **Sentiment ≠ severity.** Public sentiment is a complementary distress signal with
   a bounded, upward-only fusion rule. It does not scientifically predict heatwave
   severity by itself (enforced by design).
3. **Social data source.** Without licensed provider credentials, collection uses the
   labelled demo provider (or Reddit public search — best-effort, subject to Reddit
   availability and policies). A licensed adapter slots into `SocialProvider`.
4. **MySQL here.** The delivering machine has no MySQL Server/Docker; verification ran
   on the SQLite fallback with identical SQLAlchemy models + migrations. docker-compose
   is provided for the MySQL target.
5. **Session revocation.** JWT logout is client-side discard; server-side revocation
   would need a shared token store (documented in deployment notes).
6. **docker-compose.yml** was authored but not executed (no Docker on the delivering
   machine).
7. **English only** per the SRS scope; **no** satellite processing, sensors, ambulance
   dispatch, hospital management, or emergency calling (explicitly out of scope).

## 15. Deployment considerations

See `docs/deployment.md` for production hardening: MySQL provisioning, Gunicorn/
Waitress, HTTPS termination, CORS tightening, secret management, backup scheduling,
and the scheduler process. The scheduler (`run_scheduler.py`) must run as a single
instance alongside the web app.
