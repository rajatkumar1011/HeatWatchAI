"""Reproducible training pipeline for the weather-based heatwave severity
model (FR-05, Phase 5 of the implementation plan).

Dataset: no aligned historical weather+sentiment dataset with heatwave
labels exists in this repository. Instead of fabricating "real" labels, this
script builds a reproducible synthetic training set from the documented
NWS heat-index risk banding (see app/ml/features.py:label_from_heat_index):

    rows = full grid over plausible temperature/humidity/wind conditions,
    heat index computed with the NWS Rothfusz regression (app/utils/heat.py),
    label = band of the computed heat index.

Every (temperature, humidity) pair appears exactly once, so a random
stratified split cannot leak duplicates between train and test.

The resulting model therefore *approximates a documented, transparent
risk-banding function*. It is a genuine scikit-learn classifier with honest
evaluation metrics — but its accuracy reflects agreement with the heat-index
banding, NOT validated real-world heatwave prediction. This limitation is
stated in the model card, in the API responses (methodology string), and in
the admin model-information panel.

Usage:
    py -m app.ml.train_severity          (from the backend directory)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split

from app.ml.features import FEATURE_NAMES, build_features, label_from_heat_index
from app.utils.heat import compute_heat_index_c

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "severity_model.joblib"
META_PATH = ARTIFACT_DIR / "severity_model_meta.json"

MODEL_VERSION = "severity-rf-v1.0.0"
RANDOM_STATE = 42


def build_dataset() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build the grid dataset; returns (X, y, heat_index_column)."""
    temps = np.arange(20.0, 50.5, 0.5)
    humids = np.arange(5.0, 100.5, 2.5)
    winds = np.array([2.0, 8.0, 15.0, 25.0])

    rows: list[list[float]] = []
    labels: list[str] = []
    his: list[float] = []
    for t in temps:
        for h in humids:
            hi = compute_heat_index_c(float(t), float(h))
            effective_hi = hi if hi is not None else float(t)
            for w in winds:
                feats = build_features(float(t), float(h), hi, float(w))
                rows.append([feats[name] for name in FEATURE_NAMES])
                labels.append(label_from_heat_index(effective_hi))
                his.append(effective_hi)
    return np.array(rows), np.array(labels), np.array(his)


def train() -> dict:
    """Train, evaluate, serialize the model, and write metadata."""
    X, y, _his = build_dataset()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=RANDOM_STATE, stratify=y,
    )

    model = RandomForestClassifier(
        n_estimators=300,
        min_samples_leaf=2,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        class_weight="balanced",
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    metrics = {
        "n_samples": int(X.shape[0]),
        "n_train": int(X_train.shape[0]),
        "n_test": int(X_test.shape[0]),
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "precision_macro": round(float(precision_score(y_test, y_pred, average="macro", zero_division=0)), 4),
        "recall_macro": round(float(recall_score(y_test, y_pred, average="macro", zero_division=0)), 4),
        "f1_macro": round(float(f1_score(y_test, y_pred, average="macro", zero_division=0)), 4),
        "confusion_matrix": confusion_matrix(y_test, y_pred, labels=model.classes_).tolist(),
        "classes": [str(c) for c in model.classes_],
    }
    # High-risk recall matters most for early warning (per the brief).
    high_idx = metrics["classes"].index("high") if "high" in metrics["classes"] else None
    if high_idx is not None:
        cm = metrics["confusion_matrix"]
        metrics["recall_high_risk"] = round(
            cm[high_idx][high_idx] / max(1, sum(cm[high_idx])), 4
        )

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)

    meta = {
        "model_name": "heatwave_severity_random_forest",
        "model_version": MODEL_VERSION,
        "algorithm": "RandomForestClassifier(n_estimators=300, min_samples_leaf=2, class_weight=balanced)",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "random_state": RANDOM_STATE,
        "features": FEATURE_NAMES,
        "label_definition": (
            "NWS heat-index bands: low < 32degC <= moderate < 41degC <= high "
            "(computed with the Rothfusz regression in app/utils/heat.py)"
        ),
        "dataset_provenance": (
            "Synthetic, reproducible grid over temperature 20-50degC x humidity 5-100% x "
            "wind 2-25km/h; labels derived from the computed heat index. NOT real-world "
            "labelled heatwave observations."
        ),
        "evaluation": metrics,
        "limitations": [
            "The model approximates the documented heat-index risk banding; it is not "
            "trained on, nor validated against, real historical heatwave outcomes.",
            "It assesses current-condition heat stress; it is not a future forecast.",
            "Sentiment is NOT an input to this model; sentiment enters through the "
            "documented rule-based fusion layer in the prediction service.",
        ],
    }
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


if __name__ == "__main__":
    result = train()
    print(json.dumps(result["evaluation"], indent=2))
    print(f"Model saved to {MODEL_PATH}")
