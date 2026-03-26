"""
SentinelOps :: config.py
========================
Central configuration.  Override any value via environment variables.
"""

import os

# ── PostgreSQL ──────────────────────────────────────────────
DB_HOST     = os.getenv("SENTINEL_DB_HOST",     "localhost")
DB_PORT     = int(os.getenv("SENTINEL_DB_PORT", "5432"))
DB_NAME     = os.getenv("SENTINEL_DB_NAME",     "sentinelops")
DB_USER     = os.getenv("SENTINEL_DB_USER",     "postgres")
DB_PASSWORD = os.getenv("SENTINEL_DB_PASS",     "atharva")

# ── Collection ───────────────────────────────────────────────
COLLECTION_INTERVAL_SEC = int(os.getenv("SENTINEL_INTERVAL", "5"))  # seconds between samples
HISTORY_WINDOW_MINUTES  = int(os.getenv("SENTINEL_WINDOW",   "30")) # analysis window

# ── Health Scoring weights ────────────────────────────────────
# Must sum to 1.0
CPU_WEIGHT    = 0.40
MEMORY_WEIGHT = 0.35
DISK_WEIGHT   = 0.25

# ── Alert thresholds ─────────────────────────────────────────
CPU_WARNING_THRESHOLD    = 70.0
CPU_CRITICAL_THRESHOLD   = 90.0
MEM_WARNING_THRESHOLD    = 75.0
MEM_CRITICAL_THRESHOLD   = 90.0
DISK_WARNING_THRESHOLD   = 80.0
DISK_CRITICAL_THRESHOLD  = 90.0

# ── Prediction ───────────────────────────────────────────────
PREDICTION_HORIZON_MINUTES = 20   # how far ahead to predict
MIN_SAMPLES_FOR_PREDICTION = 10   # need at least this many rows

# ── Display ──────────────────────────────────────────────────
DASHBOARD_REFRESH_SEC = 5         # how often CLI refreshes
APP_VERSION           = "1.0.0"
