"""
SentinelOps :: collector.py
============================
Run this script separately in a terminal.
It collects system metrics every 5 seconds and inserts them into PostgreSQL.

Usage:
    python collector.py
"""

import time
import db
import metrics

INTERVAL_SECONDS = 5  # kitne second baad collect kare

print("✅ SentinelOps Collector started — inserting every 5 seconds...")
print("   Press Ctrl+C to stop.\n")

while True:
    try:
        data = metrics.collect()
        row_id = db.insert_metric(data)
        print(f"[{data['collected_at'].strftime('%H:%M:%S')}] ✅ Inserted row id={row_id} | "
              f"CPU={data['cpu_percent']}% | MEM={data['memory_percent']}% | DISK={data['disk_percent']}%")
    except Exception as e:
        print(f"❌ Error: {e}")

    time.sleep(INTERVAL_SECONDS)
