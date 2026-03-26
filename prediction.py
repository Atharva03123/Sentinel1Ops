"""
SentinelOps :: prediction.py
=============================
Health score calculation + time-series prediction engine.

Health Score (0–100):
  100 = perfect health
    0 = complete failure

Prediction:
  Uses linear regression (numpy polyfit) as the primary model,
  with exponential smoothing as a secondary estimator.
  Both are blended for a final prediction.
"""

import numpy as np
import pandas as pd
from typing import Optional
import config


# ──────────────────────────────────────────────────────────────
#  Health scoring
# ──────────────────────────────────────────────────────────────

def _metric_score(value: float,
                  warning_threshold: float,
                  critical_threshold: float) -> float:
    """
    Convert a raw % value into a 0–100 score.
    Higher usage → lower score.

    Score map:
      0%  usage → 100 (perfect)
      warning   → 60
      critical  → 20
      100% usage→ 0  (dead)
    """
    if value <= 0:
        return 100.0
    if value >= 100:
        return 0.0

    # Piece-wise linear degradation
    if value < warning_threshold:
        # Green zone: linear from 100 → 60
        score = 100 - (value / warning_threshold) * 40
    elif value < critical_threshold:
        # Yellow zone: linear from 60 → 20
        ratio = (value - warning_threshold) / (critical_threshold - warning_threshold)
        score = 60 - ratio * 40
    else:
        # Red zone: linear from 20 → 0
        ratio = (value - critical_threshold) / (100 - critical_threshold)
        score = 20 - ratio * 20

    return max(0.0, min(100.0, round(score, 2)))


def calculate_health_score(cpu: float,
                            memory: float,
                            disk: float) -> dict:
    """
    Compute individual and composite health scores.

    Returns:
        {
            health_score  : float (0–100),
            status        : "NORMAL" | "WARNING" | "CRITICAL",
            cpu_score     : float,
            memory_score  : float,
            disk_score    : float,
        }
    """
    cpu_score    = _metric_score(cpu,    config.CPU_WARNING_THRESHOLD,  config.CPU_CRITICAL_THRESHOLD)
    memory_score = _metric_score(memory, config.MEM_WARNING_THRESHOLD,  config.MEM_CRITICAL_THRESHOLD)
    disk_score   = _metric_score(disk,   config.DISK_WARNING_THRESHOLD, config.DISK_CRITICAL_THRESHOLD)

    # Weighted composite
    composite = (
        config.CPU_WEIGHT    * cpu_score +
        config.MEMORY_WEIGHT * memory_score +
        config.DISK_WEIGHT   * disk_score
    )
    composite = round(composite, 1)

    # Classify status
    if composite >= 70:
        status = "NORMAL"
    elif composite >= 40:
        status = "WARNING"
    else:
        status = "CRITICAL"

    return {
        "health_score" : composite,
        "status"       : status,
        "cpu_score"    : cpu_score,
        "memory_score" : memory_score,
        "disk_score"   : disk_score,
    }


# ──────────────────────────────────────────────────────────────
#  Prediction engine
# ──────────────────────────────────────────────────────────────

def _linear_forecast(series: pd.Series, steps_ahead: int) -> Optional[float]:
    """
    Fit a linear trend to `series` and extrapolate `steps_ahead` steps.
    Returns None if insufficient data.
    """
    values = series.dropna().values.astype(float)
    if len(values) < config.MIN_SAMPLES_FOR_PREDICTION:
        return None

    x = np.arange(len(values))
    coeffs = np.polyfit(x, values, 1)   # [slope, intercept]
    future_x = len(values) + steps_ahead - 1
    predicted = np.polyval(coeffs, future_x)
    return float(np.clip(predicted, 0, 100))


def _exponential_forecast(series: pd.Series, steps_ahead: int) -> Optional[float]:
    """
    Simple exponential smoothing forecast.
    alpha ∈ (0,1): higher → more weight on recent observations.
    """
    values = series.dropna().values.astype(float)
    if len(values) < 3:
        return None

    alpha = 0.3
    smoothed = values[0]
    for v in values[1:]:
        smoothed = alpha * v + (1 - alpha) * smoothed

    # Extrapolate using the last delta
    last_delta = (values[-1] - values[-3]) / 2 if len(values) >= 3 else 0
    predicted  = smoothed + last_delta * steps_ahead
    return float(np.clip(predicted, 0, 100))


def predict(df: pd.DataFrame,
            horizon_minutes: int = config.PREDICTION_HORIZON_MINUTES) -> dict:
    """
    Blend linear regression and exponential smoothing to predict
    CPU, Memory, Disk usage `horizon_minutes` ahead.

    Steps ahead is approximated assuming 5-second sampling intervals
    (horizon_minutes * 12 samples per minute).

    Returns:
        {
            horizon_minutes  : int,
            predicted_cpu    : float,
            predicted_memory : float,
            predicted_disk   : float,
            predicted_health : float,
            confidence       : float  (0–1),
            trend            : str,
        }
    """
    # Samples per minute (assuming COLLECTION_INTERVAL_SEC)
    spm          = 60 / config.COLLECTION_INTERVAL_SEC
    steps_ahead  = int(horizon_minutes * spm)

    results = {}
    for col in ["cpu_percent", "memory_percent", "disk_percent"]:
        if col not in df.columns:
            results[col] = df[col].iloc[-1] if col in df.columns else 50.0
            continue

        series = df[col]
        lin  = _linear_forecast(series, steps_ahead)
        exp  = _exponential_forecast(series, steps_ahead)

        if lin is None and exp is None:
            # Not enough data – use latest value
            results[col] = float(series.iloc[-1])
        elif lin is None:
            results[col] = exp
        elif exp is None:
            results[col] = lin
        else:
            # Blend: 60% linear, 40% exponential
            results[col] = round(0.6 * lin + 0.4 * exp, 2)

    predicted_cpu    = results.get("cpu_percent",    50.0)
    predicted_memory = results.get("memory_percent", 50.0)
    predicted_disk   = results.get("disk_percent",   50.0)

    # Compute predicted health score
    health = calculate_health_score(predicted_cpu, predicted_memory, predicted_disk)
    predicted_health = health["health_score"]

    # Confidence: inverse of variance in recent window
    recent_std = df[["cpu_percent", "memory_percent", "disk_percent"]].tail(10).std().mean()
    confidence = float(np.clip(1 - (recent_std / 50), 0.2, 0.98))

    # Overall trend (comparing predicted vs current)
    current_health = calculate_health_score(
        float(df["cpu_percent"].iloc[-1]),
        float(df["memory_percent"].iloc[-1]),
        float(df["disk_percent"].iloc[-1]),
    )["health_score"]

    delta = predicted_health - current_health
    if delta > 3:
        trend = "IMPROVING"
    elif delta < -3:
        trend = "DEGRADING"
    else:
        trend = "STABLE"

    return {
        "horizon_minutes" : horizon_minutes,
        "predicted_cpu"   : round(predicted_cpu, 2),
        "predicted_memory": round(predicted_memory, 2),
        "predicted_disk"  : round(predicted_disk, 2),
        "predicted_health": round(predicted_health, 1),
        "confidence"      : round(confidence, 2),
        "trend"           : trend,
    }
