"""Heat index calculation (NWS Rothfusz regression with adjustments).

The heat index is calculated only when its applicability conditions hold
(roughly T >= 27 degC / 80 degF and sufficiently high humidity, per the US
National Weather Service documentation). Outside that envelope the function
returns None and callers must surface the limitation rather than substituting
an apparent-temperature value.
"""
from __future__ import annotations


def _c_to_f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


def _f_to_c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


def compute_heat_index_c(temperature_c: float, humidity_pct: float) -> float | None:
    """Return the NWS heat index in degC, or None when not applicable."""
    t_f = _c_to_f(temperature_c)
    rh = float(humidity_pct)

    # Simple Rothfusz applicability check: HI table used for T >= 80F and
    # RH >= 40%. Below that, the heat index is not meaningfully defined.
    if t_f < 80.0 or rh < 40.0:
        return None

    hi_f = (
        -42.379
        + 2.04901523 * t_f
        + 10.14333127 * rh
        - 0.22475541 * t_f * rh
        - 0.00683783 * t_f * t_f
        - 0.05481717 * rh * rh
        + 0.00122874 * t_f * t_f * rh
        + 0.00085282 * t_f * rh * rh
        - 0.00000199 * t_f * t_f * rh * rh
    )

    # NWS adjustments
    if rh < 13.0 and 80.0 <= t_f <= 112.0:
        hi_f -= ((13.0 - rh) / 4.0) * ((17.0 - abs(t_f - 95.0)) / 17.0) ** 0.5
    elif rh > 85.0 and 80.0 <= t_f <= 87.0:
        hi_f += ((rh - 85.0) / 10.0) * ((87.0 - t_f) / 5.0)

    hi_c = _f_to_c(hi_f)
    # The regression can dip below air temperature at RH edges; the heat
    # index is never lower than the air temperature by definition.
    return round(max(hi_c, temperature_c), 2)


def heat_index_band(hi_c: float) -> str:
    """NWS heat-index risk band (documented reference thresholds)."""
    if hi_c < 32.0:        # < ~90F: Caution
        return "caution"
    if hi_c < 41.0:        # 90-103F: Extreme caution
        return "extreme_caution"
    if hi_c < 54.0:        # 103-124F: Danger
        return "danger"
    return "extreme_danger"  # 125F+
