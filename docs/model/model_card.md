# Model Card — HeatWatch AI ML Components

## 1. Weather-based heatwave severity model

| Field | Value |
|---|---|
| Model name | `heatwave_severity_random_forest` |
| Version | `severity-rf-v1.0.0` |
| Algorithm | RandomForestClassifier (300 trees, `min_samples_leaf=2`, `class_weight="balanced"`) |
| Library | scikit-learn, serialized with joblib (`backend/app/ml/artifacts/severity_model.joblib`) |
| Features | `temperature_c`, `humidity_pct`, `heat_index_c`, `wind_speed_kph` (heat index via NWS Rothfusz regression; when not applicable, air temperature is used and flagged) |
| Labels | `low` (HI < 32 °C) · `moderate` (32 ≤ HI < 41 °C) · `high` (HI ≥ 41 °C) — documented NWS heat-index bands (bands "danger"/"extreme danger" merged into `high`; "extreme caution" → `moderate`) |
| Training data | Reproducible synthetic grid: temperature 20–50 °C × humidity 5–100 % × wind 2–25 km/h; each (temp, humidity) pair appears exactly once (no leakage across splits); 9,516 rows |
| Split | Stratified random 75/25 (`random_state=42`) |
| Trained at | Stored in `severity_model_meta.json` and the `model_registry` table |

### Evaluation (held-out 25 %)

accuracy **1.000** · precision_macro **1.000** · recall_macro **1.000** · f1_macro **1.000**
· recall_high_risk **1.000** · confusion matrix diagonal.

### Honest interpretation of the metrics

The label is a deterministic function of the computed heat index, and the features
contain the heat index. A perfect score therefore means **the model reproduces the
documented banding function** — it does *not* constitute validated real-world heatwave
prediction. No labelled historical heatwave dataset exists in this repository; fabricating
one was explicitly ruled out. The model's value: calibrated class probabilities (used for
the confidence display), a versioned artifact, and a reproducible pipeline ready to be
retrained on genuine labelled data when available.

### Limitations

- Approximates the heat-index banding; not trained on or validated against real outcomes.
- Assesses **current-condition** heat stress; it is not a future forecast.
- Sentiment is **not** a model input; it enters through the fusion layer below.

## 2. Sentiment model (FR-04)

| Field | Value |
|---|---|
| Model | VADER (Valence Aware Dictionary and sEntiment Reasoner; Hutto & Gilbert 2014) via `vaderSentiment` 3.3.2 |
| Type | Pretrained lexicon-and-rule sentiment model for social media; runs fully offline |
| Input language | English only (SRS scope) |
| Output | compound score in [-1, 1]; label thresholds: ≥ 0.05 positive, ≤ −0.05 negative, else neutral; class proportions pos/neu/neg |
| Known limitations | Lexicon-based; sarcasm/long-context nuance may be missed; posters are not a representative population sample |

### Heat relevance and distress (separate transparent heuristics)

General negative sentiment is **not** the same as heat-related distress. Two keyword
layers (administrator-configurable via `app_settings`):

- `is_heat_related` — post mentions heat-context vocabulary (heatwave, extreme heat, …).
- `distress_flag` — heat-relevant **and** contains impact vocabulary (dehydration, heatstroke,
  power cut, water shortage, collapsed, …).

These are heuristics, reported as such. Aggregates feed the dashboard and the fusion layer
only as counts/ratios, never as raw truth.

## 3. Weather + sentiment fusion layer (FR-05)

A **rule-based, transparent, provisional** mechanism (`rule_fusion_v1`) — *not* a learned
model, because no aligned weather+sentiment+label dataset exists:

- Inputs: weather-model score (0–100 from class probabilities: low=20, moderate=55, high=90)
  and the trailing 24 h sentiment aggregate.
- Adjustment (upward only, capped at **+12**): distress share up to +8, strongly negative
  average score up to +2, heat-related share up to +2; requires ≥ 5 posts.
- Bands: < 40 low · 40–69 moderate · ≥ 70 high.
- **Design constraint:** with the moderate baseline score (~55), the maximum +12 cannot
  escalate a moderate weather assessment to high by itself. Sentiment refines or confirms
  an elevated weather assessment; it never overrides weather evidence downward.

Every prediction stores its methodology string, model version, sentiment adjustment,
inputs snapshot, and contributing-factor explanations, exposed via the API and the admin
panel. Retraining: `python -m app.ml.train_severity` (from `backend/`), then restart.
