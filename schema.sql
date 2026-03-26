-- ============================================================
--  SentinelOps :: PostgreSQL Schema
--  Time-series metrics storage + alert history
-- ============================================================

-- Extension for UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─────────────────────────────────────────────
--  Table: system_metrics
--  Stores raw system metrics collected by psutil
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_metrics (
    id              SERIAL PRIMARY KEY,
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cpu_percent     FLOAT       NOT NULL CHECK (cpu_percent BETWEEN 0 AND 100),
    memory_percent  FLOAT       NOT NULL CHECK (memory_percent BETWEEN 0 AND 100),
    disk_percent    FLOAT       NOT NULL CHECK (disk_percent BETWEEN 0 AND 100),
    cpu_freq_mhz    FLOAT,
    memory_used_gb  FLOAT,
    disk_used_gb    FLOAT,
    load_avg_1m     FLOAT,
    load_avg_5m     FLOAT,
    load_avg_15m    FLOAT
);

-- Index for fast time-range queries
CREATE INDEX IF NOT EXISTS idx_metrics_collected_at
    ON system_metrics (collected_at DESC);

-- ─────────────────────────────────────────────
--  Table: health_scores
--  Computed health score per collection cycle
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS health_scores (
    id              SERIAL PRIMARY KEY,
    scored_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metric_id       INT REFERENCES system_metrics(id) ON DELETE CASCADE,
    health_score    FLOAT       NOT NULL CHECK (health_score BETWEEN 0 AND 100),
    status          VARCHAR(20) NOT NULL CHECK (status IN ('NORMAL', 'WARNING', 'CRITICAL')),
    cpu_score       FLOAT,
    memory_score    FLOAT,
    disk_score      FLOAT
);

CREATE INDEX IF NOT EXISTS idx_health_scored_at
    ON health_scores (scored_at DESC);

-- ─────────────────────────────────────────────
--  Table: predictions
--  Stores model prediction results
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS predictions (
    id                  SERIAL PRIMARY KEY,
    predicted_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    horizon_minutes     INT         NOT NULL,
    predicted_cpu       FLOAT,
    predicted_memory    FLOAT,
    predicted_disk      FLOAT,
    predicted_health    FLOAT,
    confidence          FLOAT,
    trend               VARCHAR(20) CHECK (trend IN ('IMPROVING', 'STABLE', 'DEGRADING'))
);

-- ─────────────────────────────────────────────
--  Table: alerts
--  Alert log with severity and message
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alerts (
    id              SERIAL PRIMARY KEY,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    severity        VARCHAR(20) NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    component       VARCHAR(50) NOT NULL,
    message         TEXT        NOT NULL,
    value           FLOAT,
    threshold       FLOAT,
    acknowledged    BOOLEAN     DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at
    ON alerts (triggered_at DESC);

-- ─────────────────────────────────────────────
--  Sample seed data (last 30 minutes simulation)
-- ─────────────────────────────────────────────
INSERT INTO system_metrics
    (collected_at, cpu_percent, memory_percent, disk_percent,
     cpu_freq_mhz, memory_used_gb, disk_used_gb, load_avg_1m, load_avg_5m, load_avg_15m)
SELECT
    NOW() - (i || ' minutes')::INTERVAL,
    -- Simulate gradual CPU ramp-up
    40 + random() * 20 + (i * 0.3),
    55 + random() * 10 + (i * 0.1),
    30 + random() * 5,
    2400 + random() * 400,
    ROUND((8 + random() * 4)::numeric, 2),
    ROUND((120 + random() * 20)::numeric, 2),
    1.2 + random() * 0.8,
    1.0 + random() * 0.6,
    0.9 + random() * 0.4
FROM generate_series(30, 1, -1) AS s(i);

-- Confirm seeded rows
SELECT COUNT(*) AS seeded_rows FROM system_metrics;
