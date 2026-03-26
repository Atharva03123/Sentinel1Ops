# SentinelOps
### Automated System Health Prediction & Early Warning Engine

```
███████╗███████╗███╗   ██╗████████╗██╗███╗   ██╗███████╗██╗      ██████╗ ██████╗ ███████╗
██╔════╝██╔════╝████╗  ██║╚══██╔══╝██║████╗  ██║██╔════╝██║     ██╔═══██╗██╔══██╗██╔════╝
███████╗█████╗  ██╔██╗ ██║   ██║   ██║██╔██╗ ██║█████╗  ██║     ██║   ██║██████╔╝███████╗
╚════██║██╔══╝  ██║╚██╗██║   ██║   ██║██║╚██╗██║██╔══╝  ██║     ██║   ██║██╔═══╝ ╚════██║
███████║███████╗██║ ╚████║   ██║   ██║██║ ╚████║███████╗███████╗╚██████╔╝██║     ███████║
╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚══════╝╚══════╝ ╚═════╝ ╚═╝     ╚══════╝
```

---

## What Is SentinelOps?

SentinelOps is a **CLI-based predictive monitoring system** that:

- Collects real-time CPU, Memory, and Disk metrics via `psutil`
- Persists all data in **PostgreSQL** (time-series storage)
- Engineers features (moving averages, trends, deltas) using **pandas/numpy**
- Predicts system health for the next 20 minutes using **linear regression + exponential smoothing**
- Calculates a **Health Score (0–100)** with weighted component scoring
- Fires **tiered alerts** (WARNING / CRITICAL) for threshold breaches and predicted failures
- Renders a **live terminal dashboard** using the `rich` library

---

## Project Structure

```
SentinelOps/
├── main.py          ← Entry point, CLI argument parsing, mode dispatcher
├── config.py        ← All configuration constants + env var overrides
├── db.py            ← PostgreSQL connection + all DB I/O helpers
├── metrics.py       ← Real-time system metrics collection (psutil)
├── processing.py    ← Feature engineering (pandas/numpy)
├── prediction.py    ← Health scoring + forecasting engine
├── alert.py         ← Alert evaluation and severity logic
├── cli.py           ← Rich terminal dashboard renderer
├── schema.sql       ← PostgreSQL table definitions + seed data
└── requirements.txt ← Python dependencies
```

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python      | 3.9+    |
| PostgreSQL  | 13+     |
| pip         | any     |

---

## Setup Guide (Step by Step)

### Step 1 – Clone / Download the project

```bash
git clone https://github.com/yourname/sentinelops
cd sentinelops
```

### Step 2 – Install Python dependencies

```bash
pip install -r requirements.txt
```

### Step 3 – Create the PostgreSQL database

Connect to your PostgreSQL instance and create the database:

```sql
CREATE DATABASE sentinelops;
```

### Step 4 – Configure credentials

Edit `config.py` **or** set environment variables:

```bash
export SENTINEL_DB_HOST=localhost
export SENTINEL_DB_PORT=5432
export SENTINEL_DB_NAME=sentinelops
export SENTINEL_DB_USER=postgres
export SENTINEL_DB_PASS=yourpassword
```

### Step 5 – Initialise the schema

```bash
python main.py --init-db
```

This runs `schema.sql` and seeds 30 minutes of sample data.

### Step 6 – Launch the live dashboard

```bash
python main.py
```

---

## Available Commands

| Command                   | Description                          |
|---------------------------|--------------------------------------|
| `python main.py`          | Live dashboard (default)             |
| `python main.py --once`   | Collect one sample and exit          |
| `python main.py --report` | Historical stats + alert history     |
| `python main.py --init-db`| Initialise PostgreSQL schema         |

---

## Configuration Reference

All settings live in `config.py` and can be overridden via environment variables:

| Config Key                    | Env Var              | Default | Description                        |
|-------------------------------|----------------------|---------|------------------------------------|
| `DB_HOST`                     | `SENTINEL_DB_HOST`   | localhost | PostgreSQL host                  |
| `COLLECTION_INTERVAL_SEC`     | `SENTINEL_INTERVAL`  | 5       | Seconds between samples            |
| `HISTORY_WINDOW_MINUTES`      | `SENTINEL_WINDOW`    | 30      | Analysis window                    |
| `CPU_WARNING_THRESHOLD`       | –                    | 70%     | CPU warning threshold              |
| `CPU_CRITICAL_THRESHOLD`      | –                    | 90%     | CPU critical threshold             |
| `PREDICTION_HORIZON_MINUTES`  | –                    | 20      | How far ahead to predict           |

---

## Dashboard Preview

```
╭─────────────────────────────────────────────────────────────────╮
│  SentinelOps System Dashboard     2024-12-01  14:32:17 UTC  #42  │
│ ─────────────────────────────────────────────────────────────── │
│  Real-Time Metrics                                               │
│  Metric    Current   Bar                     Trend   5m Avg  Peak│
│  CPU       65.2%     █████████████░░░░░░░░   → STABLE  62.1%  78%│
│  MEMORY    72.4%     ██████████████░░░░░░░   ↑ IMPROV  73.2%  79%│
│  DISK      38.1%     ███████░░░░░░░░░░░░░░   → STABLE  38.0%  39%│
│ ─────────────────────────────────────────────────────────────── │
│  Health & Prediction                                             │
│  Health Score    78.2 / 100  ████████████    Status   ● NORMAL   │
│  Prediction+20m  74.5 / 100  → STABLE        Confidence  82%    │
│ ─────────────────────────────────────────────────────────────── │
│  Alerts                                                          │
│  ✔  All systems nominal — no active alerts                       │
╰─────────────────────────────────────────────────────────────────╯
```

---

## Health Score Formula

```
score = (CPU_score × 0.40) + (Memory_score × 0.35) + (Disk_score × 0.25)

Where each component_score maps usage% to 0–100:
  0%        → 100 (perfect)
  warning   → 60
  critical  → 20
  100%      → 0  (failed)
```

---

## Database Schema

```sql
system_metrics   ← raw metric snapshots (time-series)
health_scores    ← computed health scores per cycle
predictions      ← model forecasts
alerts           ← triggered alert log
```

---

## Tech Stack

| Layer       | Technology              |
|-------------|-------------------------|
| Language    | Python 3.9+             |
| Database    | PostgreSQL 13+          |
| DB adapter  | psycopg2-binary         |
| Metrics     | psutil                  |
| Processing  | pandas, numpy           |
| Terminal UI | rich                    |

---

*Built as a production-grade DevOps monitoring tool.*
# Sentinel1Ops
