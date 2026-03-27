"""
SentinelOps :: db.py
====================
PostgreSQL connection pool and all database I/O helpers.
Uses psycopg2 with a simple connection context manager.
"""

import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional
import config



# ──────────────────────────────────────────────────────────────
#  Connection factory
# ──────────────────────────────────────────────────────────────

def get_connection():
    import os
    import psycopg2

    db_url = os.getenv("DATABASE_URL")

    # Render
    if db_url:
        return psycopg2.connect(db_url)

    # Local
    return psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="sentinelops",
        user="postgres",
        password="atharva"
    )


@contextmanager
def db_cursor(commit: bool = False):
    """
    Context manager that yields a DictCursor.
    Automatically commits or rolls back on exit.

    Usage:
        with db_cursor(commit=True) as cur:
            cur.execute("INSERT ...")
    """
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
#  Schema bootstrap
# ──────────────────────────────────────────────────────────────

def initialize_schema():
    """
    Read schema.sql and execute it against the database.
    Safe to run multiple times (uses IF NOT EXISTS).
    """
    with open("schema.sql", "r") as f:
        sql = f.read()
    with db_cursor(commit=True) as cur:
        cur.execute(sql)


# ──────────────────────────────────────────────────────────────
#  Metrics I/O
# ──────────────────────────────────────────────────────────────

def insert_metric(metric: dict) -> int:
    """
    Insert a single metrics snapshot. Returns the new row id.

    Expected keys: cpu_percent, memory_percent, disk_percent,
                   cpu_freq_mhz, memory_used_gb, disk_used_gb,
                   load_avg_1m, load_avg_5m, load_avg_15m
    """
    sql = """
        INSERT INTO system_metrics
            (cpu_percent, memory_percent, disk_percent,
             cpu_freq_mhz, memory_used_gb, disk_used_gb,
             load_avg_1m, load_avg_5m, load_avg_15m)
        VALUES
            (%(cpu_percent)s, %(memory_percent)s, %(disk_percent)s,
             %(cpu_freq_mhz)s, %(memory_used_gb)s, %(disk_used_gb)s,
             %(load_avg_1m)s, %(load_avg_5m)s, %(load_avg_15m)s)
        RETURNING id
    """
    with db_cursor(commit=True) as cur:
        cur.execute(sql, metric)
        return cur.fetchone()["id"]


def fetch_recent_metrics(minutes: int = 30) -> list:
    """
    Fetch metrics collected in the last `minutes` minutes.
    Returns list of dicts ordered oldest → newest.
    """
    sql = """
        SELECT *
        FROM   system_metrics
        WHERE  collected_at >= NOW() - (%s || ' minutes')::INTERVAL
        ORDER  BY collected_at ASC
    """
    with db_cursor() as cur:
        cur.execute(sql, (minutes,))
        return [dict(row) for row in cur.fetchall()]


def fetch_latest_metric() -> Optional[dict]:
    """Return the single most recent metric row, or None."""
    sql = "SELECT * FROM system_metrics ORDER BY collected_at DESC LIMIT 1"
    with db_cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
        return dict(row) if row else None


# ──────────────────────────────────────────────────────────────
#  Health score I/O
# ──────────────────────────────────────────────────────────────

def insert_health_score(metric_id: int, scores: dict):
    """
    Persist a computed health score record.

    Expected keys: health_score, status, cpu_score, memory_score, disk_score
    """
    sql = """
        INSERT INTO health_scores
            (metric_id, health_score, status, cpu_score, memory_score, disk_score)
        VALUES
            (%(metric_id)s, %(health_score)s, %(status)s,
             %(cpu_score)s, %(memory_score)s, %(disk_score)s)
    """
    scores["metric_id"] = metric_id
    with db_cursor(commit=True) as cur:
        cur.execute(sql, scores)


def fetch_health_history(limit: int = 60) -> list:
    """Return the last `limit` health score records."""
    sql = """
        SELECT * FROM health_scores
        ORDER  BY scored_at DESC
        LIMIT  %s
    """
    with db_cursor() as cur:
        cur.execute(sql, (limit,))
        return [dict(row) for row in cur.fetchall()]


# ──────────────────────────────────────────────────────────────
#  Prediction I/O
# ──────────────────────────────────────────────────────────────

def insert_prediction(pred: dict):
    """
    Store a prediction result.

    Expected keys: horizon_minutes, predicted_cpu, predicted_memory,
                   predicted_disk, predicted_health, confidence, trend
    """
    sql = """
        INSERT INTO predictions
            (horizon_minutes, predicted_cpu, predicted_memory, predicted_disk,
             predicted_health, confidence, trend)
        VALUES
            (%(horizon_minutes)s, %(predicted_cpu)s, %(predicted_memory)s,
             %(predicted_disk)s, %(predicted_health)s, %(confidence)s, %(trend)s)
    """
    with db_cursor(commit=True) as cur:
        cur.execute(sql, pred)


def fetch_latest_prediction() -> Optional[dict]:
    """Return the most recent prediction row."""
    sql = "SELECT * FROM predictions ORDER BY predicted_at DESC LIMIT 1"
    with db_cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
        return dict(row) if row else None


# ──────────────────────────────────────────────────────────────
#  Alert I/O
# ──────────────────────────────────────────────────────────────

def insert_alert(alert: dict):
    """
    Log a triggered alert.

    Expected keys: severity, component, message, value, threshold
    """
    sql = """
        INSERT INTO alerts
            (severity, component, message, value, threshold)
        VALUES
            (%(severity)s, %(component)s, %(message)s, %(value)s, %(threshold)s)
    """
    with db_cursor(commit=True) as cur:
        cur.execute(sql, alert)


def fetch_recent_alerts(limit: int = 10) -> list:
    """Return the `limit` most recent alerts."""
    sql = """
        SELECT * FROM alerts
        ORDER  BY triggered_at DESC
        LIMIT  %s
    """
    with db_cursor() as cur:
        cur.execute(sql, (limit,))
        return [dict(row) for row in cur.fetchall()]
