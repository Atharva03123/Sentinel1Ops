"""
SentinelOps :: processing.py
============================
Feature engineering pipeline.
Takes raw metric rows from the DB and produces enriched DataFrames
with moving averages, rolling statistics, and trend signals.
"""

import numpy as np
import pandas as pd
from typing import Optional


# ──────────────────────────────────────────────────────────────
#  DataFrame builder
# ──────────────────────────────────────────────────────────────

def build_dataframe(rows: list) -> Optional[pd.DataFrame]:
    """
    Convert a list of metric dicts (from db.fetch_recent_metrics)
    into a time-indexed DataFrame.

    Returns None if the list is empty.
    """
    if not rows:
        return None

    df = pd.DataFrame(rows)

    # Ensure collected_at is a proper datetime index
    df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)
    df = df.sort_values("collected_at").set_index("collected_at")

    # Keep only the numeric metric columns we care about
    cols = ["cpu_percent", "memory_percent", "disk_percent",
            "load_avg_1m", "load_avg_5m", "load_avg_15m"]
    df = df[[c for c in cols if c in df.columns]].copy()

    return df


# ──────────────────────────────────────────────────────────────
#  Feature engineering
# ──────────────────────────────────────────────────────────────

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived columns to the metrics DataFrame:

    Moving averages   → smoothed signal (noise reduction)
    Rolling std dev   → volatility indicator
    Delta columns     → rate of change per sample
    Trend scores      → direction signal per metric
    """
    df = df.copy()

    for col in ["cpu_percent", "memory_percent", "disk_percent"]:
        if col not in df.columns:
            continue

        # ── Moving averages ──────────────────────────────────
        df[f"{col}_ma3"]  = df[col].rolling(window=3,  min_periods=1).mean()
        df[f"{col}_ma5"]  = df[col].rolling(window=5,  min_periods=1).mean()
        df[f"{col}_ma10"] = df[col].rolling(window=10, min_periods=1).mean()

        # ── Rolling volatility ───────────────────────────────
        df[f"{col}_std5"] = df[col].rolling(window=5, min_periods=2).std().fillna(0)

        # ── Rate of change (delta per step) ─────────────────
        df[f"{col}_delta"] = df[col].diff().fillna(0)

        # ── Exponential weighted mean (reacts faster to spikes)
        df[f"{col}_ewm"]   = df[col].ewm(span=5, adjust=False).mean()

    # ── Composite load pressure (combines all load avgs) ────
    if all(c in df.columns for c in ["load_avg_1m", "load_avg_5m", "load_avg_15m"]):
        df["load_pressure"] = (
            0.5 * df["load_avg_1m"] +
            0.3 * df["load_avg_5m"] +
            0.2 * df["load_avg_15m"]
        )

    return df


# ──────────────────────────────────────────────────────────────
#  Trend detection
# ──────────────────────────────────────────────────────────────

def detect_trend(series: pd.Series) -> str:
    """
    Fit a linear regression to the series and classify the slope:
      - IMPROVING  : slope < -0.2  (values are falling)
      - DEGRADING  : slope >  0.2  (values are rising)
      - STABLE     : otherwise

    Returns one of 'IMPROVING' | 'STABLE' | 'DEGRADING'
    """
    if len(series) < 4:
        return "STABLE"

    x = np.arange(len(series))
    y = series.values.astype(float)

    # Remove NaNs
    mask = ~np.isnan(y)
    if mask.sum() < 4:
        return "STABLE"

    # Least-squares fit
    coeffs = np.polyfit(x[mask], y[mask], 1)
    slope  = coeffs[0]   # change per sample

    if slope > 0.2:
        return "DEGRADING"
    elif slope < -0.2:
        return "IMPROVING"
    return "STABLE"


def get_trend_summary(df: pd.DataFrame) -> dict:
    """
    Compute trend for each major metric over the full window.

    Returns:
        {
            "cpu"    : "DEGRADING" | "STABLE" | "IMPROVING",
            "memory" : ...,
            "disk"   : ...,
            "overall": ...
        }
    """
    trends = {}
    for key, col in [("cpu", "cpu_percent"),
                     ("memory", "memory_percent"),
                     ("disk", "disk_percent")]:
        if col in df.columns:
            trends[key] = detect_trend(df[col])
        else:
            trends[key] = "STABLE"

    # Overall = worst of the three
    order = {"IMPROVING": 0, "STABLE": 1, "DEGRADING": 2}
    trends["overall"] = max(trends.values(), key=lambda t: order.get(t, 1))
    return trends


# ──────────────────────────────────────────────────────────────
#  Summary statistics (for dashboard display)
# ──────────────────────────────────────────────────────────────

def compute_statistics(df: pd.DataFrame) -> dict:
    """
    Return mean / max / min / latest for the three core metrics.
    """
    stats = {}
    for col in ["cpu_percent", "memory_percent", "disk_percent"]:
        if col not in df.columns:
            continue
        key = col.replace("_percent", "")
        stats[key] = {
            "mean"  : round(df[col].mean(), 1),
            "max"   : round(df[col].max(),  1),
            "min"   : round(df[col].min(),  1),
            "latest": round(df[col].iloc[-1], 1),
            "std"   : round(df[col].std(),  1),
        }
    return stats
