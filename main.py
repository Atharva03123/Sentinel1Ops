"""
SentinelOps :: main.py
=======================
Entry point for the SentinelOps CLI tool.

Usage:
    python main.py              # Run live dashboard (default)
    python main.py --once       # Collect one sample and exit
    python main.py --report     # Print historical stats and alerts
    python main.py --init-db    # Initialise the PostgreSQL schema
    python main.py --help       # Show help

Environment variables (override config.py defaults):
    SENTINEL_DB_HOST   SENTINEL_DB_PORT   SENTINEL_DB_NAME
    SENTINEL_DB_USER   SENTINEL_DB_PASS
    SENTINEL_INTERVAL  SENTINEL_WINDOW
"""

import argparse
import sys
import time

from rich.live    import Live
from rich.console import Console

import config
import db
import metrics
import processing
import prediction
import alert
import cli

console = Console()


# ──────────────────────────────────────────────────────────────
#  Core collection + analysis cycle
# ──────────────────────────────────────────────────────────────

def run_cycle(tick: int) -> tuple:
    """
    Execute one full monitoring cycle:
      1. Collect live metrics
      2. Store in PostgreSQL
      3. Fetch historical window
      4. Feature engineering
      5. Health scoring
      6. Prediction
      7. Alert evaluation

    Returns: (metric, health, prediction_result, stats, trends, alerts_list)
    """
    # 1 · Collect
    m = metrics.collect()

    # 2 · Store
    metric_id = db.insert_metric(m)

    # 3 · History
    rows = db.fetch_recent_metrics(config.HISTORY_WINDOW_MINUTES)

    # 4 · Feature engineering
    df = processing.build_dataframe(rows)

    # Default fallbacks when insufficient data
    stats  = {}
    trends = {"cpu": "STABLE", "memory": "STABLE", "disk": "STABLE", "overall": "STABLE"}
    pred   = {
        "horizon_minutes" : config.PREDICTION_HORIZON_MINUTES,
        "predicted_cpu"   : m["cpu_percent"],
        "predicted_memory": m["memory_percent"],
        "predicted_disk"  : m["disk_percent"],
        "predicted_health": 70.0,
        "confidence"      : 0.5,
        "trend"           : "STABLE",
    }

    if df is not None and len(df) >= config.MIN_SAMPLES_FOR_PREDICTION:
        df     = processing.engineer_features(df)
        stats  = processing.compute_statistics(df)
        trends = processing.get_trend_summary(df)
        pred   = prediction.predict(df)
        db.insert_prediction(pred)

    # 5 · Health score
    health = prediction.calculate_health_score(
        m["cpu_percent"],
        m["memory_percent"],
        m["disk_percent"],
    )
    db.insert_health_score(metric_id, health)

    # 6 · Alerts
    alerts_list = alert.evaluate_alerts(m, pred)
    for a in alerts_list:
        db.insert_alert(a)

    return m, health, pred, stats, trends, alerts_list


# ──────────────────────────────────────────────────────────────
#  Modes
# ──────────────────────────────────────────────────────────────

def mode_live_dashboard():
    """Continuously refresh the dashboard until Ctrl+C."""
    sysinfo = metrics.system_info()
    cli.print_banner(sysinfo)

    console.print(f"[grey50]Starting live monitoring "
                  f"(interval: {config.COLLECTION_INTERVAL_SEC}s, "
                  f"window: {config.HISTORY_WINDOW_MINUTES}m) ...[/grey50]\n")

    tick = 0
    with Live(console=console, refresh_per_second=1, screen=False) as live:
        while True:
            try:
                tick += 1
                m, health, pred, stats, trends, alerts_list = run_cycle(tick)
                panel = cli.build_dashboard(
                    metric=m,
                    health=health,
                    prediction=pred,
                    stats=stats,
                    trends=trends,
                    alerts=alerts_list,
                    tick=tick,
                )
                live.update(panel)
                time.sleep(config.COLLECTION_INTERVAL_SEC)

            except KeyboardInterrupt:
                break
            except Exception as e:
                console.print(f"[red]Cycle error: {e}[/red]")
                time.sleep(2)


def mode_once():
    """Collect a single sample, print results, and exit."""
    console.print("[cyan]Running single collection cycle ...[/cyan]")
    m, health, pred, stats, trends, alerts_list = run_cycle(tick=1)

    console.print(f"\n[bold]Metric snapshot:[/bold]")
    for k, v in m.items():
        if k != "collected_at":
            console.print(f"  {k:20s}: [white]{v}[/white]")

    console.print(f"\n[bold]Health:[/bold]")
    for k, v in health.items():
        color = {"NORMAL": "green", "WARNING": "yellow", "CRITICAL": "red"}.get(str(v), "white")
        console.print(f"  {k:20s}: [{color}]{v}[/{color}]")

    console.print(f"\n[bold]Prediction (+{pred['horizon_minutes']}m):[/bold]")
    for k, v in pred.items():
        console.print(f"  {k:20s}: [white]{v}[/white]")

    if alerts_list:
        console.print(f"\n[bold red]Alerts ({len(alerts_list)}):[/bold red]")
        for a in alerts_list:
            color, icon = alert.severity_style(a["severity"])
            console.print(f"  [{color}]{icon} [{a['severity']}] {a['component']}: {a['message']}[/{color}]")
    else:
        console.print("\n[green]✔  No alerts — system is healthy[/green]")


def mode_report():
    """Print historical statistics and recent alerts, then exit."""
    sysinfo = metrics.system_info()
    cli.print_banner(sysinfo)

    rows = db.fetch_recent_metrics(config.HISTORY_WINDOW_MINUTES)
    if not rows:
        console.print("[yellow]No data found. Run `python main.py --once` first to seed data.[/yellow]")
        return

    df = processing.build_dataframe(rows)
    if df is not None:
        df     = processing.engineer_features(df)
        stats  = processing.compute_statistics(df)
        trends = processing.get_trend_summary(df)

        # Stats table
        from rich.table import Table
        from rich       import box
        tbl = Table(
            title=f"Statistics — last {config.HISTORY_WINDOW_MINUTES} minutes ({len(rows)} samples)",
            box=box.ROUNDED, border_style="cyan",
        )
        tbl.add_column("Metric",  style="bright_black")
        tbl.add_column("Latest",  justify="right")
        tbl.add_column("Mean",    justify="right")
        tbl.add_column("Max",     justify="right")
        tbl.add_column("Min",     justify="right")
        tbl.add_column("Std",     justify="right")
        tbl.add_column("Trend",   justify="center")

        for key, label in [("cpu", "CPU"), ("memory", "MEMORY"), ("disk", "DISK")]:
            s  = stats.get(key, {})
            tr = trends.get(key, "STABLE")
            ti = {"IMPROVING": "↑", "STABLE": "→", "DEGRADING": "↓"}.get(tr, "→")
            tbl.add_row(
                label,
                f"{s.get('latest', 0):.1f}%",
                f"{s.get('mean',   0):.1f}%",
                f"{s.get('max',    0):.1f}%",
                f"{s.get('min',    0):.1f}%",
                f"{s.get('std',    0):.1f}",
                f"{ti} {tr}",
            )
        console.print(tbl)

    # Recent alerts
    recent_alerts = db.fetch_recent_alerts(limit=20)
    if recent_alerts:
        cli.print_alert_history(recent_alerts)
    else:
        console.print("\n[green]No alerts in history.[/green]")


def mode_init_db():
    """Initialise the PostgreSQL schema."""
    console.print("[cyan]Initialising PostgreSQL schema ...[/cyan]")
    try:
        db.initialize_schema()
        console.print("[green]✔  Schema created / verified successfully.[/green]")
    except Exception as e:
        cli.print_db_error(e)
        sys.exit(1)


# ──────────────────────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        prog="sentinelops",
        description="SentinelOps – Automated System Health Prediction & Early Warning Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py               Live dashboard
  python main.py --once        Single collection cycle
  python main.py --report      Historical stats report
  python main.py --init-db     Initialise database schema
        """
    )
    parser.add_argument("--once",    action="store_true", help="Collect one sample and exit")
    parser.add_argument("--report",  action="store_true", help="Show historical stats and alerts")
    parser.add_argument("--init-db", action="store_true", help="Initialise PostgreSQL schema",
                        dest="init_db")
    return parser.parse_args()


def main():
    args = parse_args()

    # Verify DB connectivity (except --help)
    try:
        conn = db.get_connection()
        conn.close()
    except Exception as e:
        cli.print_db_error(e)
        sys.exit(1)

    try:
        if args.init_db:
            mode_init_db()
        elif args.once:
            mode_once()
        elif args.report:
            mode_report()
        else:
            mode_live_dashboard()
    except KeyboardInterrupt:
        pass
    finally:
        cli.print_shutdown()


if __name__ == "__main__":
    main()
