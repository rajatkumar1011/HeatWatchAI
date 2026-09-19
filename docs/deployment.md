# Deployment Guide

## 1. Topology

- **Web app:** Flask (Waitress on Windows, Gunicorn/uwsgi on Linux) behind a reverse
  proxy (nginx/IIS) that terminates HTTPS.
- **Scheduler:** `python run_scheduler.py` — a single dedicated process (never run more
  than one instance; jobs are idempotent but scheduling duplicates wastes API quota).
- **Database:** MySQL 8 (documented target). SQLite is a development fallback only.
- **Frontend:** `npm run build` produces `frontend/dist/`; serve it as static files from
  the reverse proxy, or keep the Vite dev server for local work only.

## 2. Production configuration checklist

1. Set strong `SECRET_KEY` and `JWT_SECRET_KEY` (32+ random bytes each).
2. `DATABASE_URL=mysql+pymysql://user:pass@host:3306/heatwatch?charset=utf8mb4`
3. `FLASK_ENV=production` (disables debug re-reraise paths, verbose logging).
4. `DATA_MODE=live` once real provider credentials are configured.
5. Restrict `CORS_ORIGINS` to the actual frontend origin.
6. Run `flask db upgrade`, then `create_admin.py`; **do not** run `seed_demo.py` in
   production, or clearly communicate that demo data is present.
7. Serve exclusively over HTTPS (SRS security requirement); the app itself is
   protocol-agnostic behind the proxy.
8. Schedule `mysqldump` backups (below) and test restores periodically.

## 3. MySQL

```sql
CREATE DATABASE heatwatch CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'heatwatch'@'%' IDENTIFIED BY 'strong-password';
GRANT ALL PRIVILEGES ON heatwatch.* TO 'heatwatch'@'%';
```

Then `flask db upgrade` applies the Alembic migration (engine-agnostic schema).

## 4. Backup & recovery

```bash
# daily backup (cron example: 02:30)
30 2 * * * mysqldump -u heatwatch -p'...' --single-transaction heatwatch | gzip > /backups/heatwatch-$(date +\%F).sql.gz

# restore
gunzip < heatwatch-YYYY-MM-DD.sql.gz | mysql -u heatwatch -p heatwatch
```

Retain N days of dumps off the database host. The generated reports directory
(`backend/generated_reports/`) should be included in file backups or moved to durable
object storage.

## 5. Session revocation note

Auth uses stateless JWTs (12 h expiry by default). Logout is client-side token
disclosure. If server-side revocation is required, add a token deny-list in a shared
store and check it in the JWT user-lookup callback.

## 6. Scaling notes

- The application is a modular monolith; scale by running more Waitress/Gunicorn
  workers behind the proxy. In-memory rate limiting is per-process — move it to Redis
  when running multiple workers.
- Scheduled collection must stay single-instance; workers must not embed APScheduler.
- Prediction inference loads one joblib artifact per process (small); reload happens on
  process restart after retraining.

## 7. What was verified on the delivering machine

- Full local run on Windows: migrations, admin bootstrap, model training, demo seeding,
  backend (Waitress), frontend (Vite), tests, browser walkthrough, PDF/CSV generation.
- **Not executed here** (tooling unavailable): Docker Compose stack (Docker Desktop not
  installed), MySQL server (not installed) — SQLAlchemy models/migrations are
  engine-agnostic and the compose file is provided; run `docker compose up --build` on
  a machine with Docker to validate.
