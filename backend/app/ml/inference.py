"""Severity model inference (FR-05).

Loads the serialized scikit-learn artifact once and exposes validated
prediction with class probabilities. The prediction service uses:

1. the weather-based ML model when the artifact is available,
2. a documented rule-based heat-index banding fallback when it is not,
3. a transparent rule-based fusion layer on top (sentiment can only raise,
   never lower, the weather-based assessment).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib

from app.ml.features import FEATURE_NAMES, build_features
from app.utils.heat import compute_heat_index_c

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "severity_model.joblib"
META_PATH = ARTIFACT_DIR / "severity_model_meta.json"

# Expected-severity values per class used to express the weather model's
# output on a 0-100 scale (documented in the model card).
CLASS_SEVERITY_VALUES = {"low": 20.0, "moderate": 55.0, "high": 90.0}


class SeverityPredictor:
    """Wraps the weather-based severity model artifact."""

    def __init__(self) -> None:
        self.model = None
        self.meta: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if MODEL_PATH.exists():
            self.model = joblib.load(MODEL_PATH)
            if META_PATH.exists():
                self.meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        else:
            self.model = None

    @property
    def available(self) -> bool:
        return self.model is not None

    @property
    def version(self) -> str:
        return self.meta.get("model_version", "unavailable")

    def weather_risk_score(self, temperature_c: float, humidity_pct: float,
                           heat_index_c: float | None, wind_speed_kph: float) -> dict[str, Any]:
        """Predict the weather-only risk on a 0-100 scale with probabilities."""
        feats = build_features(temperature_c, humidity_pct, heat_index_c, wind_speed_kph)
        vector = [[feats[name] for name in FEATURE_NAMES]]

        if self.model is not None:
            probas = self.model.predict_proba(vector)[0]
            classes = [str(c) for c in self.model.classes_]
            proba_map = {c: float(p) for c, p in zip(classes, probas)}
            predicted = classes[int(probas.argmax())]
            score = sum(CLASS_SEVERITY_VALUES.get(c, 50.0) * p for c, p in proba_map.items())
            return {
                "methodology": f"ml_severity_model:{self.version}",
                "model_version": self.version,
                "predicted_class": predicted,
                "probabilities": {c: round(p, 4) for c, p in proba_map.items()},
                "weather_score": round(min(100.0, max(0.0, score)), 1),
                "confidence": round(float(probas.max()) * 100.0, 1),
                "confidence_basis": "weather model class probability",
                "features": feats,
            }

        # Documented rule-based fallback (no artifact): NWS heat-index bands.
        hi = heat_index_c if heat_index_c is not None else compute_heat_index_c(temperature_c, humidity_pct)
        effective_hi = hi if hi is not None else float(temperature_c)
        if effective_hi >= 41.0:
            predicted, score = "high", 90.0
        elif effective_hi >= 32.0:
            predicted, score = "moderate", 55.0
        else:
            predicted, score = "low", 20.0
        return {
            "methodology": "rule_based_heat_index_bands (model artifact not available)",
            "model_version": "rule-v1",
            "predicted_class": predicted,
            "probabilities": {predicted: 1.0},
            "weather_score": score,
            "confidence": None,
            "confidence_basis": "rule-based method exposes no statistical confidence",
            "features": feats,
        }
