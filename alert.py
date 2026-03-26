"""
SentinelOps :: alert.py
========================
Alert evaluation engine.

Checks current metric values against configurable thresholds
and emits structured alert dicts that are:
  1. Stored in PostgreSQL via db.insert_alert()
  2. Rendered in the CLI dashboard
  3. Optionally extended with email/webhook hooks
"""

from typing import Optional
import config


# ──────────────────────────────────────────────────────────────
#  Threshold checks
# ──────────────────────────────────────────────────────────────

def _check_metric(component: str,
                  value: float,
                  warning_threshold: float,
                  critical_threshold: float) -> Optional[dict]:
    """
    Evaluate a single metric against warning / critical thresholds.

    Returns an alert dict if a threshold is breached, else None.
    """
    if value >= critical_threshold:
        return {
            "severity"  : "CRITICAL",
            "component" : component,
            "message"   : (
                f"{component} usage is critically high at {value:.1f}% "
                f"(threshold: {critical_threshold}%)"
            ),
            "value"     : value,
            "threshold" : critical_threshold,
        }
    elif value >= warning_threshold:
        return {
            "severity"  : "WARNING",
            "component" : component,
            "message"   : (
                f"{component} usage is elevated at {value:.1f}% "
                f"(threshold: {warning_threshold}%)"
            ),
            "value"     : value,
            "threshold" : warning_threshold,
        }
    return None


# ──────────────────────────────────────────────────────────────
#  Predictive alert (pre-failure early warning)
# ──────────────────────────────────────────────────────────────

def _check_prediction_alert(prediction: dict) -> Optional[dict]:
    """
    Fire an early-warning alert if the predicted health score
    will drop below a critical level within the horizon window.
    """
    ph = prediction.get("predicted_health", 100)
    horizon = prediction.get("horizon_minutes", 20)
    trend   = prediction.get("trend", "STABLE")

    if ph < 30:
        return {
            "severity"  : "CRITICAL",
            "component" : "PREDICTION_ENGINE",
            "message"   : (
                f"System health predicted to reach {ph:.0f}/100 "
                f"within {horizon} minutes. Trend: {trend}. Immediate action required."
            ),
            "value"     : ph,
            "threshold" : 30.0,
        }
    elif ph < 50 and trend == "DEGRADING":
        return {
            "severity"  : "WARNING",
            "component" : "PREDICTION_ENGINE",
            "message"   : (
                f"Predictive warning: health score may fall to {ph:.0f}/100 "
                f"in {horizon} minutes. Trend is {trend}."
            ),
            "value"     : ph,
            "threshold" : 50.0,
        }
    return None


# ──────────────────────────────────────────────────────────────
#  Main evaluation function
# ──────────────────────────────────────────────────────────────

def evaluate_alerts(metric: dict,
                    prediction: Optional[dict] = None) -> list:
    """
    Run all alert checks against a fresh metric snapshot.

    Args:
        metric     : dict from metrics.collect()
        prediction : dict from prediction.predict() (optional)

    Returns:
        List of alert dicts (may be empty if everything is healthy).
        Each dict has keys: severity, component, message, value, threshold
    """
    alerts = []

    # ── CPU ─────────────────────────────────────────────────
    cpu_alert = _check_metric(
        "CPU",
        metric["cpu_percent"],
        config.CPU_WARNING_THRESHOLD,
        config.CPU_CRITICAL_THRESHOLD,
    )
    if cpu_alert:
        alerts.append(cpu_alert)

    # ── Memory ──────────────────────────────────────────────
    mem_alert = _check_metric(
        "MEMORY",
        metric["memory_percent"],
        config.MEM_WARNING_THRESHOLD,
        config.MEM_CRITICAL_THRESHOLD,
    )
    if mem_alert:
        alerts.append(mem_alert)

    # ── Disk ────────────────────────────────────────────────
    disk_alert = _check_metric(
        "DISK",
        metric["disk_percent"],
        config.DISK_WARNING_THRESHOLD,
        config.DISK_CRITICAL_THRESHOLD,
    )
    if disk_alert:
        alerts.append(disk_alert)

    # ── Predictive early warning ─────────────────────────────
    if prediction:
        pred_alert = _check_prediction_alert(prediction)
        if pred_alert:
            alerts.append(pred_alert)

    return alerts


# ──────────────────────────────────────────────────────────────
#  Severity colour helper (used by cli.py)
# ──────────────────────────────────────────────────────────────

SEVERITY_STYLES = {
    "INFO"    : ("cyan",    "ℹ"),
    "WARNING" : ("yellow",  "⚠"),
    "CRITICAL": ("red",     "✖"),
    "NORMAL"  : ("green",   "✔"),
}

def severity_style(severity: str) -> tuple:
    """Return (colour_name, icon_char) for rich markup."""
    return SEVERITY_STYLES.get(severity.upper(), ("white", "•"))
