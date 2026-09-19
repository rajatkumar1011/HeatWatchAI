# Architecture Notes

## Principles

- **Modular monolith** with strict internal layering (per the project brief: no
  microservices without genuine need).
- **Replaceable external adapters**: weather and social providers implement small
  interfaces (`WeatherProvider`, `SocialProvider`); live and demonstration providers are
  interchangeable without touching business logic.
- **Provenance everywhere**: every stored observation, post, aggregate, prediction,
  alert, and report row carries `data_mode` (`live` | `demo` | `mixed`). The UI, reports,
  and admin panel surface this — demo data is never presented as live.

## Layers

```
api/          HTTP concerns only: validation (pydantic), auth guards, response shapes
services/     business logic; unit-testable without HTTP
integrations/ outbound adapters (OpenWeatherMap, Reddit public, demo generators)
ml/           feature builder (shared train/inference), training script, inference
models/       SQLAlchemy entities; single source of schema truth for Alembic
utils/        cross-cutting: heat index, time (UTC canonical, IST display), logging,
              rate limiting
```

## Data flow (the essential workflow)

1. `MonitoringService.run_pipeline(location)`:
   weather fetch (retries ×3, cached fallback) → social collect (dedup) →
   `SentimentService.analyze_pending` (VADER + relevance/distress) →
   `SentimentService.aggregate` (daily window upsert) →
   `PredictionService.run` (severity model → bounded upward fusion → bands) →
   `AlertService.evaluate_prediction` (thresholds, cooldown/escalation, auto-resolve).
2. Duplicate suppression: identical provider observation → no new row; identical
   prediction inputs → reuse the stored prediction.
3. The scheduler process runs the same pipeline periodically for monitored locations;
   manual refresh uses the same code path.

## Key design decisions

| Decision | Rationale |
|---|---|
| SQLAlchemy dual-engine (MySQL target, SQLite dev fallback) | SRS requires MySQL; dev machines may lack a server. Same models/migrations for both. |
| Heat index computed in-house (NWS Rothfusz) with applicability envelope | Never silently substitute provider "feels like"; NULL + UI explanation when not applicable. |
| Severity model trained on the documented heat-index banding | No real labelled dataset exists; a transparent, reproducible approximation with honest metrics beats fabricated ground truth. |
| Rule-based bounded fusion (≤ +12, upward-only) | Sentiment must never silently override weather evidence; constraint enforced arithmetically. |
| JWT bearer auth | Simple SPA + API split; expiry-based sessions; revocation trade-off documented. |
| Single scheduler process | Idempotent jobs, no duplicate schedulers across web workers (per brief §18). |

## Entity relationships (SRS 2.6)

- User 1—N ReportRecord · WeatherObservation 1—N Prediction · Prediction 1—N Alert
- N SocialPost 1—1 SentimentResult; N SentimentResults → 1 SentimentAggregate (window)
- Prediction ← WeatherObservation + SentimentAggregate (+ location + timestamp)
- Supporting: Location, AppSetting, GovernmentAdvisory, EmergencyContact,
  ModelRegistry, CollectionRun, SystemLog, AuditLog
