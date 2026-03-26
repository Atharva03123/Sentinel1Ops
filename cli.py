"""
SentinelOps :: cli.py
======================
All terminal UI rendering using the `rich` library.

Responsibilities:
  - Startup / shutdown banners
  - Live dashboard layout
  - Alert panels
  - Historical stats table
"""

from datetime import datetime, timezone
from rich                 import box
from rich.align           import Align
from rich.columns         import Columns
from rich.console         import Console
from rich.layout          import Layout
from rich.panel           import Panel
from rich.progress        import BarColumn, Progress, TextColumn
from rich.table           import Table
from rich.text            import Text
from rich.live            import Live
from rich.rule            import Rule
from rich.style           import Style

import config
from alert import severity_style

console = Console()


# ──────────────────────────────────────────────────────────────
#  Brand colours
# ──────────────────────────────────────────────────────────────

BRAND_COLOR   = "bright_cyan"
HEADER_COLOR  = "bold bright_white on grey15"
LABEL_COLOR   = "bright_black"
VALUE_COLOR   = "bold white"
GOOD_COLOR    = "bright_green"
WARN_COLOR    = "bright_yellow"
CRIT_COLOR    = "bright_red"
DIM_COLOR     = "grey50"


# ──────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────

def _color_for_pct(pct: float, warn: float, crit: float) -> str:
    if pct >= crit:
        return CRIT_COLOR
    elif pct >= warn:
        return WARN_COLOR
    return GOOD_COLOR


def _health_color(score: float) -> str:
    if score >= 70:
        return GOOD_COLOR
    elif score >= 40:
        return WARN_COLOR
    return CRIT_COLOR


def _bar(pct: float, width: int = 20) -> str:
    """ASCII progress bar."""
    filled = int(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _trend_icon(trend: str) -> str:
    return {"IMPROVING": "↑", "STABLE": "→", "DEGRADING": "↓"}.get(trend, "→")


# ──────────────────────────────────────────────────────────────
#  Startup banner
# ──────────────────────────────────────────────────────────────

def print_banner(sysinfo: dict):
    console.print()
    console.print(Rule(style="grey30"))

    banner = Text(justify="center")
    banner.append("  ███████╗███████╗███╗   ██╗████████╗██╗███╗   ██╗███████╗██╗      \n", style="bold bright_cyan")
    banner.append("  ██╔════╝██╔════╝████╗  ██║╚══██╔══╝██║████╗  ██║██╔════╝██║      \n", style="bold cyan")
    banner.append("  ███████╗█████╗  ██╔██╗ ██║   ██║   ██║██╔██╗ ██║█████╗  ██║      \n", style="bold cyan")
    banner.append("  ╚════██║██╔══╝  ██║╚██╗██║   ██║   ██║██║╚██╗██║██╔══╝  ██║      \n", style="cyan")
    banner.append("  ███████║███████╗██║ ╚████║   ██║   ██║██║ ╚████║███████╗███████╗  \n", style="cyan")
    banner.append("  ╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚══════╝╚══════╝  \n", style="bright_black")
    banner.append("            O P S   ·   Automated System Health Engine\n", style=f"bold {BRAND_COLOR}")
    banner.append(f"                          v{config.APP_VERSION}\n", style="grey50")

    console.print(Panel(banner, border_style="grey30", padding=(0, 2)))

    # System info row
    info_table = Table.grid(padding=(0, 4))
    info_table.add_column(style=LABEL_COLOR)
    info_table.add_column(style=VALUE_COLOR)
    info_table.add_column(style=LABEL_COLOR)
    info_table.add_column(style=VALUE_COLOR)

    info_table.add_row(
        "Hostname",  sysinfo.get("hostname", "N/A"),
        "OS",        sysinfo.get("os", "N/A"),
    )
    info_table.add_row(
        "CPU Cores", f"{sysinfo.get('cpu_cores','?')}c / {sysinfo.get('cpu_threads','?')}t",
        "Total RAM", f"{sysinfo.get('total_ram_gb','?')} GB",
    )
    info_table.add_row(
        "Total Disk", f"{sysinfo.get('total_disk_gb','?')} GB",
        "Python",    sysinfo.get("python_ver", "N/A"),
    )
    console.print(Align.center(info_table))
    console.print(Rule(style="grey30"))
    console.print()


# ──────────────────────────────────────────────────────────────
#  Live dashboard panel
# ──────────────────────────────────────────────────────────────

def build_dashboard(metric: dict,
                    health: dict,
                    prediction: dict,
                    stats: dict,
                    trends: dict,
                    alerts: list,
                    tick: int) -> Panel:
    """
    Assemble the entire dashboard into a single rich Panel.
    Called on every refresh cycle.
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M:%S UTC")

    # ── Header ───────────────────────────────────────────────
    header_text = Text(justify="right")
    header_text.append("SentinelOps ", style=f"bold {BRAND_COLOR}")
    header_text.append("System Dashboard", style="bold white")
    header_text.append(f"  │  {now_str}", style=DIM_COLOR)
    header_text.append(f"  │  Tick #{tick}", style=DIM_COLOR)

    # ── Metric gauges ────────────────────────────────────────
    gauge_table = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style=HEADER_COLOR,
        border_style="grey23",
        padding=(0, 1),
        expand=True,
    )
    gauge_table.add_column("Metric",    style=LABEL_COLOR,  min_width=12)
    gauge_table.add_column("Current",   justify="right",     min_width=8)
    gauge_table.add_column("Bar",       min_width=22)
    gauge_table.add_column("Trend",     justify="center",    min_width=10)
    gauge_table.add_column("5-min Avg", justify="right",     min_width=10)
    gauge_table.add_column("Peak",      justify="right",     min_width=8)

    rows_data = [
        ("CPU",    "cpu_percent",    config.CPU_WARNING_THRESHOLD,  config.CPU_CRITICAL_THRESHOLD,  "cpu"),
        ("MEMORY", "memory_percent", config.MEM_WARNING_THRESHOLD,  config.MEM_CRITICAL_THRESHOLD,  "memory"),
        ("DISK",   "disk_percent",   config.DISK_WARNING_THRESHOLD, config.DISK_CRITICAL_THRESHOLD, "disk"),
    ]

    for label, key, warn, crit, skey in rows_data:
        val  = metric.get(key, 0)
        col  = _color_for_pct(val, warn, crit)
        bar  = _bar(val)
        tr   = trends.get(skey, "STABLE")
        ti   = _trend_icon(tr)
        tr_c = GOOD_COLOR if tr == "IMPROVING" else (WARN_COLOR if tr == "STABLE" else CRIT_COLOR)
        avg  = stats.get(skey, {}).get("mean", val)
        peak = stats.get(skey, {}).get("max", val)

        gauge_table.add_row(
            label,
            Text(f"{val:5.1f}%", style=f"bold {col}"),
            Text(bar, style=col),
            Text(f"{ti} {tr}", style=tr_c),
            Text(f"{avg:5.1f}%", style=DIM_COLOR),
            Text(f"{peak:5.1f}%", style=DIM_COLOR),
        )

    # ── Health score + prediction row ───────────────────────
    hs  = health["health_score"]
    hc  = _health_color(hs)
    status_map = {"NORMAL": GOOD_COLOR, "WARNING": WARN_COLOR, "CRITICAL": CRIT_COLOR}
    sc  = status_map.get(health["status"], "white")

    pred_health = prediction.get("predicted_health", hs)
    pred_trend  = prediction.get("trend", "STABLE")
    pred_conf   = prediction.get("confidence", 0) * 100
    pred_cpu    = prediction.get("predicted_cpu", 0)
    pred_mem    = prediction.get("predicted_memory", 0)
    pred_disk   = prediction.get("predicted_disk", 0)
    horizon     = prediction.get("horizon_minutes", config.PREDICTION_HORIZON_MINUTES)
    ph_col      = _health_color(pred_health)
    pt_icon     = _trend_icon(pred_trend)

    summary_table = Table(
        box=box.SIMPLE_HEAD,
        show_header=False,
        border_style="grey23",
        padding=(0, 2),
        expand=True,
    )
    summary_table.add_column(style=LABEL_COLOR, min_width=20)
    summary_table.add_column(style=VALUE_COLOR)
    summary_table.add_column(style=LABEL_COLOR, min_width=20)
    summary_table.add_column(style=VALUE_COLOR)

    summary_table.add_row(
        "Health Score",
        Text(f"  {hs:5.1f} / 100  {_bar(hs, 12)}", style=f"bold {hc}"),
        "Status",
        Text(f"  ● {health['status']}", style=f"bold {sc}"),
    )
    summary_table.add_row(
        f"Prediction (+{horizon}m)",
        Text(f"  {pred_health:5.1f} / 100  {pt_icon} {pred_trend}", style=f"bold {ph_col}"),
        "Confidence",
        Text(f"  {pred_conf:.0f}%", style=VALUE_COLOR),
    )
    summary_table.add_row(
        "Predicted CPU",
        Text(f"  {pred_cpu:.1f}%", style=_color_for_pct(pred_cpu, config.CPU_WARNING_THRESHOLD, config.CPU_CRITICAL_THRESHOLD)),
        "Predicted Memory",
        Text(f"  {pred_mem:.1f}%", style=_color_for_pct(pred_mem, config.MEM_WARNING_THRESHOLD, config.MEM_CRITICAL_THRESHOLD)),
    )
    summary_table.add_row(
        "Predicted Disk",
        Text(f"  {pred_disk:.1f}%", style=_color_for_pct(pred_disk, config.DISK_WARNING_THRESHOLD, config.DISK_CRITICAL_THRESHOLD)),
        "Load Avg (1m)",
        Text(f"  {metric.get('load_avg_1m', 0):.2f}", style=VALUE_COLOR),
    )

    # ── Alerts panel ────────────────────────────────────────
    if alerts:
        alert_table = Table(
            box=box.MINIMAL,
            show_header=True,
            header_style="bold grey50",
            border_style="grey19",
            expand=True,
        )
        alert_table.add_column("SEV",       min_width=10)
        alert_table.add_column("Component", min_width=18)
        alert_table.add_column("Message",   ratio=1)
        alert_table.add_column("Value",     justify="right", min_width=8)

        for a in alerts[-5:]:    # show last 5
            color, icon = severity_style(a["severity"])
            alert_table.add_row(
                Text(f"{icon} {a['severity']}", style=f"bold {color}"),
                Text(a["component"], style=color),
                Text(a["message"][:80], style="white"),
                Text(f"{a['value']:.1f}%", style=f"bold {color}"),
            )
        alert_section = Panel(
            alert_table,
            title="[bold red]⚠  Active Alerts[/bold red]",
            border_style="red",
            padding=(0, 1),
        )
    else:
        ok_text = Text("  ✔  All systems nominal — no active alerts", style=f"bold {GOOD_COLOR}")
        alert_section = Panel(
            Align.center(ok_text, vertical="middle"),
            title="[bold green]Alerts[/bold green]",
            border_style="green",
            height=4,
        )

    # ── Assemble full panel ──────────────────────────────────
    from rich.console import Group
    body = Group(
        header_text,
        Rule(style="grey23"),
        Panel(gauge_table,   title="[bold]Real-Time Metrics[/bold]", border_style="grey30", padding=(0,0)),
        Panel(summary_table, title="[bold]Health & Prediction[/bold]", border_style="grey30", padding=(0,0)),
        alert_section,
        Text(
            f"\n  ⏱  Refreshing every {config.DASHBOARD_REFRESH_SEC}s  │  "
            f"Press Ctrl+C to exit  │  "
            f"DB: {config.DB_NAME}@{config.DB_HOST}:{config.DB_PORT}",
            style=DIM_COLOR,
        ),
    )

    return Panel(body, border_style=BRAND_COLOR, padding=(0, 1))


# ──────────────────────────────────────────────────────────────
#  Standalone tables (used in --report mode)
# ──────────────────────────────────────────────────────────────

def print_alert_history(alerts: list):
    """Print a formatted table of recent alerts."""
    table = Table(
        title="Recent Alerts",
        box=box.ROUNDED,
        show_header=True,
        header_style=HEADER_COLOR,
        border_style=BRAND_COLOR,
    )
    table.add_column("Time (UTC)",  style=DIM_COLOR,   min_width=22)
    table.add_column("Severity",    min_width=10)
    table.add_column("Component",   min_width=18)
    table.add_column("Message",     ratio=1)
    table.add_column("Value",       justify="right", min_width=8)

    for a in alerts:
        ts    = a.get("triggered_at", "")
        if hasattr(ts, "strftime"):
            ts = ts.strftime("%Y-%m-%d %H:%M:%S")
        color, icon = severity_style(a.get("severity", "INFO"))
        table.add_row(
            str(ts),
            Text(f"{icon} {a.get('severity','')}", style=f"bold {color}"),
            a.get("component", ""),
            a.get("message", "")[:80],
            f"{a.get('value', 0):.1f}%",
        )

    console.print(table)


def print_db_error(error: Exception):
    console.print(Panel(
        f"[bold red]Database connection failed[/bold red]\n\n"
        f"[white]{error}[/white]\n\n"
        f"[grey50]Check config.py or set SENTINEL_DB_* environment variables[/grey50]",
        title="[red]Connection Error[/red]",
        border_style="red",
    ))


def print_shutdown():
    console.print()
    console.print(Rule(style="grey30"))
    console.print(Align.center(
        Text("SentinelOps stopped. Goodbye.", style=f"bold {BRAND_COLOR}")
    ))
    console.print(Rule(style="grey30"))
    console.print()
