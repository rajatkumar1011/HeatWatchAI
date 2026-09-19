"""Automated heatwave alert engine (FR-06).

- Evaluates each new prediction against configurable thresholds stored in
  AppSetting (environment defaults on first use).
- Persists qualifying alerts with the triggering condition, linked to the
  prediction and location.
- Deduplication/cooldown: an unchanged condition does not re-alert within
  the cooldown window; a strictly higher severity escalates immediately.
- Every generated alert is a HeatWatch AI *system* alert — clearly distinct
  from official government advisories, which are managed separately.
"""
from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import AppSetting, Alert, Prediction
from app.utils.responses import log_event
from app.utils.timeutils import as_utc, utcnow

SETTING_HIGH_THRESHOLD = "alert_high_threshold"
SETTING_MODERATE_THRESHOLD = "alert_moderate_threshold"
SETTING_COOLDOWN_MINUTES = "alert_cooldown_minutes"
SETTING_ALERTS_ENABLED = "alerts_enabled"
SETTING_ALERT_ON_MODERATE = "alert_on_moderate"


def _get_float_setting(key: str, default: float) -> float:
    row = db.session.get(AppSetting, key)
    if row and row.value is not None:
        try:
            return float(json.loads(row.value))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return default


def _get_bool_setting(key: str, default: bool) -> bool:
    row = db.session.get(AppSetting, key)
    if row and row.value is not None:
        try:
            return bool(json.loads(row.value))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return default


_ALERT_RANK = {"low": 0, "moderate": 1, "high": 2}


class AlertService:
    def __init__(self, config):
        self.config = config

    # ------------------------------------------------------------- settings
    def thresholds(self) -> dict:
        return {
            "high_threshold": _get_float_setting(SETTING_HIGH_THRESHOLD, self.config["ALERT_HIGH_THRESHOLD"]),
            "moderate_threshold": _get_float_setting(SETTING_MODERATE_THRESHOLD, self.config["ALERT_MODERATE_THRESHOLD"]),
            "cooldown_minutes": int(_get_float_setting(SETTING_COOLDOWN_MINUTES, self.config["ALERT_COOLDOWN_MINUTES"])),
            "alerts_enabled": _get_bool_setting(SETTING_ALERTS_ENABLED, self.config["ALERTS_ENABLED"]),
            "alert_on_moderate": _get_bool_setting(SETTING_ALERT_ON_MODERATE, False),
        }

    # ------------------------------------------------------------ evaluation
    def evaluate_prediction(self, prediction: Prediction, now_override=None) -> Alert | None:
        """Evaluate a prediction against thresholds.

        ``now_override`` is used by the demonstration seeder to evaluate
        historical predictions at their own timestamp (cooldown and alert
        generation time then follow the prediction time). Live evaluation
        leaves it as None.
        """
        t = self.thresholds()
        if not t["alerts_enabled"]:
            return None
        evaluated_at = as_utc(now_override) if now_override else utcnow()

        qualifies = (
            prediction.severity_score >= t["high_threshold"]
            or (t["alert_on_moderate"] and prediction.severity_score >= t["moderate_threshold"])
        )

        if not qualifies:
            # Recovery: the condition no longer holds — resolve stale active
            # alerts for this location that predate this prediction.
            stale = db.session.execute(
                select(Alert).where(
                    Alert.location_id == prediction.location_id,
                    Alert.status == "active",
                    Alert.generated_at < evaluated_at,
                )
            ).scalars().all()
            for alert in stale:
                alert.status = "resolved"
                alert.resolved_at = evaluated_at
            if stale:
                db.session.commit()
                log_event("alert", f"{len(stale)} alert(s) auto-resolved for {prediction.location.display_name}",
                          details={"prediction_id": prediction.id})
            return None

        level = "high" if prediction.severity_score >= t["high_threshold"] else "moderate"
        triggered_by = (f"fused severity {prediction.severity_score:.0f}/100 >= "
                        f"{t['high_threshold']:.0f} (high)" if level == "high" else
                        f"fused severity {prediction.severity_score:.0f}/100 >= "
                        f"{t['moderate_threshold']:.0f} (moderate)")

        # Cooldown / escalation policy.
        cooldown = evaluated_at - timedelta(minutes=t["cooldown_minutes"])
        active = db.session.execute(
            select(Alert)
            .where(
                Alert.location_id == prediction.location_id,
                Alert.status.in_(("active", "acknowledged")),
                Alert.generated_at >= cooldown,
                Alert.generated_at < evaluated_at,
            )
            .order_by(Alert.generated_at.desc())
        ).scalars().all()
        for existing in active:
            if _ALERT_RANK[level] <= _ALERT_RANK.get(existing.risk_level, 0):
                return None  # unchanged or lower condition within cooldown
        # Reaching here means: escalation to a strictly higher level, or no
        # recent active alert for this location.

        location = prediction.location
        message = (
            f"HeatWatch AI system alert: {level.upper()} heatwave risk predicted for "
            f"{location.display_name}. Fused severity {prediction.severity_score:.0f}/100 "
            f"(model: {prediction.model_version}). Verify current observations and review "
            f"public safety guidance. This is an application-generated warning, not an "
            f"official government advisory."
        )
        alert = Alert(
            prediction_id=prediction.id,
            location_id=prediction.location_id,
            risk_level=level,
            severity_score=prediction.severity_score,
            message=message,
            triggered_by=triggered_by,
            status="active",
            generated_at=evaluated_at,
            data_mode=prediction.data_mode,
        )
        db.session.add(alert)
        db.session.commit()
        log_event("alert", f"{level.upper()} alert generated for {location.display_name}",
                  level="warning", details={"alert_id": alert.id, "prediction_id": prediction.id,
                                            "severity": prediction.severity_score})
        return alert

    def acknowledge(self, alert: Alert, user_id: int) -> Alert:
        if alert.status == "active":
            alert.status = "acknowledged"
            alert.acknowledged_by = user_id
            alert.acknowledged_at = utcnow()
            db.session.commit()
        return alert

    def resolve(self, alert: Alert) -> Alert:
        if alert.status != "resolved":
            alert.status = "resolved"
            alert.resolved_at = utcnow()
            db.session.commit()
        return alert

    def history(self, location_id: int | None = None, start=None, end=None, status: str | None = None):
        stmt = select(Alert).order_by(Alert.generated_at.desc())
        if location_id is not None:
            stmt = stmt.where(Alert.location_id == location_id)
        if status:
            stmt = stmt.where(Alert.status == status)
        if start is not None:
            stmt = stmt.where(Alert.generated_at >= as_utc(start))
        if end is not None:
            stmt = stmt.where(Alert.generated_at <= as_utc(end))
        return list(db.session.execute(stmt).scalars())
