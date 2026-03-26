"""
SentinelOps :: metrics.py
=========================
Real-time system metrics collection via psutil.
All values are normalised into a flat dict ready for DB insertion.
"""

import psutil
import platform
from datetime import datetime, timezone
from typing import Optional


# ──────────────────────────────────────────────────────────────
#  Core collector
# ──────────────────────────────────────────────────────────────

def collect() -> dict:
    """
    Sample all relevant system metrics and return a flat dict.

    Returns:
        {
            cpu_percent      : float   – CPU utilisation %
            memory_percent   : float   – RAM utilisation %
            disk_percent     : float   – Root-disk utilisation %
            cpu_freq_mhz     : float   – Current CPU frequency (MHz)
            memory_used_gb   : float   – RAM used in GB
            disk_used_gb     : float   – Disk used in GB
            load_avg_1m      : float   – 1-min load average
            load_avg_5m      : float   – 5-min load average
            load_avg_15m     : float   – 15-min load average
            collected_at     : datetime
        }
    """

    # ── CPU ─────────────────────────────────────────────────
    # interval=1 gives a meaningful non-zero reading
    cpu_pct = psutil.cpu_percent(interval=1)

    # CPU frequency (may be None on some VMs)
    freq = psutil.cpu_freq()
    cpu_freq_mhz = round(freq.current, 1) if freq else 0.0

    # ── Memory ──────────────────────────────────────────────
    mem = psutil.virtual_memory()
    mem_pct     = mem.percent
    mem_used_gb = round(mem.used / (1024 ** 3), 2)

    # ── Disk ────────────────────────────────────────────────
    disk = psutil.disk_usage("/")
    disk_pct     = disk.percent
    disk_used_gb = round(disk.used / (1024 ** 3), 2)

    # ── Load average (Unix) / fallback for Windows ──────────
    try:
        load1, load5, load15 = psutil.getloadavg()
    except AttributeError:
        # Windows doesn't support getloadavg
        load1 = load5 = load15 = cpu_pct / 100.0

    return {
        "cpu_percent"    : round(cpu_pct, 2),
        "memory_percent" : round(mem_pct, 2),
        "disk_percent"   : round(disk_pct, 2),
        "cpu_freq_mhz"   : cpu_freq_mhz,
        "memory_used_gb" : mem_used_gb,
        "disk_used_gb"   : disk_used_gb,
        "load_avg_1m"    : round(load1, 3),
        "load_avg_5m"    : round(load5, 3),
        "load_avg_15m"   : round(load15, 3),
        "collected_at"   : datetime.now(timezone.utc),
    }


# ──────────────────────────────────────────────────────────────
#  System info (displayed once at startup)
# ──────────────────────────────────────────────────────────────

def system_info() -> dict:
    """
    Return static system information shown in the startup banner.
    """
    uname = platform.uname()
    mem   = psutil.virtual_memory()
    disk  = psutil.disk_usage("/")

    return {
        "os"           : f"{uname.system} {uname.release}",
        "hostname"     : uname.node,
        "cpu_cores"    : psutil.cpu_count(logical=False),
        "cpu_threads"  : psutil.cpu_count(logical=True),
        "total_ram_gb" : round(mem.total / (1024 ** 3), 1),
        "total_disk_gb": round(disk.total / (1024 ** 3), 1),
        "python_ver"   : platform.python_version(),
    }


# ──────────────────────────────────────────────────────────────
#  Inline test
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    data = collect()
    # Convert datetime to string for JSON serialisation
    data["collected_at"] = data["collected_at"].isoformat()
    print(json.dumps(data, indent=2))
