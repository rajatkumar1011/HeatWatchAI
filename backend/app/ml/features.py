"""Shared feature engineering for the heatwave severity model.

The exact same transformation is used at training time and inference time
(prevent train/serve skew).
"""
from __future__ import annotations

from typing import Any

from app.utils.heat import compute_heat_index_c

FEATURE_NAMES = ["temperature_c", "humidity_pct", "heat_index_c", "wind_speed_kph"]

LABEL_LOW, LABEL_MODERATE, LABEL_HIGH = "low", "moderate", "high"


def build_features(temperature_c: float, humidity_pct: float,
                   heat_index_c: float | None, wind_speed_kph: float) -> dict[str, float]:
    """Build the model feature vector.

    When the NWS heat index is not applicable (conditions outside its
    documented envelope) the air temperature is used as the thermal-stress
    proxy and ``heat_index_applicable`` records that fact.
    """
    hi = heat_index_c if heat_index_c is not None else compute_heat_index_c(temperature_c, humidity_pct)
    if hi is None:
        hi = float(temperature_c)
        applicable = False
    else:
        applicable = True
    return {
        "temperature_c": float(temperature_c),
        "humidity_pct": float(humidity_pct),
        "heat_index_c": float(hi),
        "wind_speed_kph": float(wind_speed_kph),
        "heat_index_applicable": applicable,
    }


def features_from_observation(obs: dict[str, Any]) -> dict[str, float]:
    return build_features(
        obs["temperature_c"],
        obs["humidity_pct"],
        obs.get("heat_index_c"),
        obs.get("wind_speed_kph", 0.0),
    )


def label_from_heat_index(hi_c: float) -> str:
    """Documented label definition (NWS heat-index risk bands, merged):

    HI < 32 degC            -> low       (below 'extreme caution' envelope)
    32 <= HI < 41 degC      -> moderate  ('extreme caution')
    HI >= 41 degC           -> high      ('danger' and 'extreme danger')
    """
    if hi_c < 32.0:
        return LABEL_LOW
    if hi_c < 41.0:
        return LABEL_MODERATE
    return LABEL_HIGH
