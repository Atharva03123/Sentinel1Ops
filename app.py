import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import platform
import psutil
import datetime
import random
import math
import threading
import time

# Safe imports
try:
    import db
    import metrics
    DB_AVAILABLE = True
    METRICS_AVAILABLE = True
except Exception as e:
    DB_AVAILABLE = False
    METRICS_AVAILABLE = False

# ─────────────────────────────
# BACKGROUND COLLECTOR THREAD
# ─────────────────────────────
def run_collector():
    """Har 5 second mein metrics collect karke DB mein insert karta hai."""
    while True:
        try:
            if DB_AVAILABLE and METRICS_AVAILABLE:
                data = metrics.collect()
                db.insert_metric(data)
        except Exception:
            pass
        time.sleep(5)

# Sirf ek baar thread start ho
if "collector_started" not in st.session_state:
    t = threading.Thread(target=run_collector, daemon=True)
    t.start()
    st.session_state.collector_started = True

# ─────────────────────────────
# PAGE CONFIG
# ─────────────────────────────
st.set_page_config(
    page_title="SentinelOps Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ─────────────────────────────
# GLOBAL STYLES
# ─────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@300;400;500;600;700&display=swap');

    .stApp {
        background-color: #0d1117;
        color: #e6edf3;
        font-family: 'Inter', sans-serif;
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        padding-left: 3rem;
        padding-right: 3rem;
        max-width: 100%;
    }
    hr {
        border: none;
        border-top: 1px solid #21262d;
        margin: 1.5rem 0;
    }
    h2, h3 {
        color: #e6edf3 !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
    }
    [data-testid="stDataFrame"] {
        border: 1px solid #30363d;
        border-radius: 10px;
        overflow: hidden;
    }
    .stButton > button {
        background: #21262d;
        color: #58a6ff;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.85rem;
        font-weight: 600;
        transition: all 0.2s ease;
        letter-spacing: 0.05em;
    }
    .stButton > button:hover {
        background: #30363d;
        border-color: #58a6ff;
        color: #79c0ff;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────
# HELPER: GENERATE SIMULATED DATA
# ─────────────────────────────
def generate_simulated_rows(n=30):
    now = datetime.datetime.now()
    rows = []
    base_cpu = random.uniform(20, 50)
    base_mem = random.uniform(40, 65)
    base_disk = random.uniform(30, 55)
    for i in range(n):
        t = now - datetime.timedelta(minutes=(n - i))
        cpu  = max(0, min(100, base_cpu  + 10 * math.sin(i / 5) + random.gauss(0, 3)))
        mem  = max(0, min(100, base_mem  +  5 * math.sin(i / 8) + random.gauss(0, 2)))
        disk = max(0, min(100, base_disk +  2 * math.sin(i / 12) + random.gauss(0, 1)))
        rows.append({
            "collected_at":   t,
            "cpu_percent":    round(cpu, 2),
            "memory_percent": round(mem, 2),
            "disk_percent":   round(disk, 2),
        })
    return rows

# ─────────────────────────────
# COLLECT LIVE METRICS
# ─────────────────────────────
def collect_live_metrics():
    if METRICS_AVAILABLE:
        try:
            return metrics.collect()
        except Exception:
            pass
    return {
        "cpu_percent":    psutil.cpu_percent(interval=0.5),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent":   psutil.disk_usage("/").percent,
    }

# ─────────────────────────────
# HEADER
# ─────────────────────────────
col_logo, col_status = st.columns([3, 1])

with col_logo:
    st.markdown("""
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:4px;">
        <span style="font-size:1.8rem;">🛡️</span>
        <div>
            <h1 style="margin:0; font-family:'Inter',sans-serif; font-weight:700;
                       font-size:1.8rem; color:#e6edf3; letter-spacing:-0.02em;">
                SentinelOps
            </h1>
            <p style="margin:0; color:#8b949e; font-size:0.8rem;
                      font-family:'JetBrains Mono',monospace; letter-spacing:0.05em;">
                AUTOMATED SYSTEM HEALTH ENGINE
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col_status:
    db_badge = (
        '<span style="display:inline-block; padding:2px 10px; border-radius:20px; '
        'font-size:0.7rem; font-family:\'JetBrains Mono\',monospace; font-weight:600; '
        'letter-spacing:0.05em; background:#1a2d1e; color:#3fb950; border:1px solid #3fb950;">● LIVE</span>'
        if DB_AVAILABLE else
        '<span style="display:inline-block; padding:2px 10px; border-radius:20px; '
        'font-size:0.7rem; font-family:\'JetBrains Mono\',monospace; font-weight:600; '
        'letter-spacing:0.05em; background:#2d1a1a; color:#e3b341; border:1px solid #e3b341;">⚡ SIMULATED</span>'
    )
    st.markdown(f'<div style="text-align:right; padding-top:8px;">{db_badge}</div>', unsafe_allow_html=True)

st.markdown("---")

# ─────────────────────────────
# SYSTEM INFO BAR
# ─────────────────────────────
col1, col2, col3, col4 = st.columns(4)
info_style = (
    "background:#161b22; border:1px solid #21262d; border-radius:10px;"
    "padding:0.6rem 1rem; font-family:'JetBrains Mono',monospace;"
    "font-size:0.8rem; color:#8b949e;"
)
col1.markdown(f'<div style="{info_style}">💻 &nbsp;<span style="color:#e6edf3;">{platform.node()}</span></div>', unsafe_allow_html=True)
col2.markdown(f'<div style="{info_style}">🧠 &nbsp;<span style="color:#e6edf3;">{round(psutil.virtual_memory().total/(1024**3),1)} GB RAM</span></div>', unsafe_allow_html=True)
col3.markdown(f'<div style="{info_style}">⚙️ &nbsp;<span style="color:#e6edf3;">{psutil.cpu_count(logical=False)} CPU Cores</span></div>', unsafe_allow_html=True)
col4.markdown(f'<div style="{info_style}">🖥️ &nbsp;<span style="color:#e6edf3;">{platform.system()} {platform.release()}</span></div>', unsafe_allow_html=True)

st.markdown("<div style='margin:1.5rem 0;'></div>", unsafe_allow_html=True)

# ─────────────────────────────
# LIVE METRICS
# ─────────────────────────────
data = collect_live_metrics()

health_score = 100 - (
    data['cpu_percent'] * 0.4 +
    data['memory_percent'] * 0.35 +
    data['disk_percent'] * 0.25
)
health_score = round(health_score, 1)

def get_color(value, thresholds=(60, 80)):
    if value < thresholds[0]: return "#3fb950"
    elif value < thresholds[1]: return "#e3b341"
    else: return "#f85149"

def get_health_color(score):
    if score >= 70: return "#3fb950"
    elif score >= 50: return "#e3b341"
    else: return "#f85149"

cpu_color    = get_color(data['cpu_percent'])
mem_color    = get_color(data['memory_percent'])
disk_color   = get_color(data['disk_percent'])
health_color = get_health_color(health_score)

st.markdown("### 📊 Live Metrics")

m1, m2, m3, m4 = st.columns(4)

def metric_card(col, label, value, unit, color, icon):
    col.markdown(f"""
    <div style="background:#161b22; border:1px solid #21262d; border-radius:14px;
                padding:1.2rem 1.4rem; border-left:4px solid {color};">
        <div style="font-family:'JetBrains Mono',monospace; font-size:0.7rem;
                    color:#8b949e; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:6px;">
            {icon} &nbsp;{label}
        </div>
        <div style="font-family:'JetBrains Mono',monospace; font-size:2rem;
                    font-weight:700; color:{color};">
            {value}<span style="font-size:1rem; color:#8b949e;">{unit}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

metric_card(m1, "CPU Usage",    data['cpu_percent'],    "%", cpu_color,    "🔲")
metric_card(m2, "Memory",       data['memory_percent'], "%", mem_color,    "🧠")
metric_card(m3, "Disk",         data['disk_percent'],   "%", disk_color,   "💾")
metric_card(m4, "Health Score", health_score,           "",  health_color, "❤️")

st.markdown("<div style='margin:1.5rem 0;'></div>", unsafe_allow_html=True)

# ─────────────────────────────
# FETCH DATA
# ─────────────────────────────
rows = []
using_simulated = False

if DB_AVAILABLE:
    try:
        rows = db.fetch_recent_metrics(30)
    except Exception:
        rows = []

if not rows:
    rows = generate_simulated_rows(30)
    using_simulated = True

# ─────────────────────────────
# GRAPHS
# ─────────────────────────────
df = pd.DataFrame(rows)

if "collected_at" in df.columns:
    df["collected_at"] = pd.to_datetime(df["collected_at"], errors="coerce")
    df = df.dropna(subset=["collected_at"])
    df = df.sort_values("collected_at")
else:
    df["collected_at"] = pd.Series(dtype="datetime64[ns]")

for col_name in ["cpu_percent", "memory_percent", "disk_percent"]:
    if col_name not in df.columns:
        df[col_name] = 0
    else:
        df[col_name] = pd.to_numeric(df[col_name], errors="coerce").fillna(0)

sim_label = " *(simulated — waiting for DB data)*" if using_simulated else ""
st.markdown(f"### 📈 System Usage — Last 30 Minutes{sim_label}")

graph_configs = [
    ("cpu_percent",    "CPU %",    "#58a6ff"),
    ("memory_percent", "Memory %", "#3fb950"),
    ("disk_percent",   "Disk %",   "#e3b341"),
]

g1, g2, g3 = st.columns(3)
graph_cols = [g1, g2, g3]

plt.rcParams.update({
    "figure.facecolor": "#161b22",
    "axes.facecolor":   "#0d1117",
    "axes.edgecolor":   "#30363d",
    "axes.labelcolor":  "#8b949e",
    "xtick.color":      "#8b949e",
    "ytick.color":      "#8b949e",
    "grid.color":       "#21262d",
    "text.color":       "#e6edf3",
    "font.family":      "monospace",
    "font.size":        8,
})

for gcol, (col_key, label, color) in zip(graph_cols, graph_configs):
    with gcol:
        st.markdown(f"""
        <div style="font-family:'JetBrains Mono',monospace; font-size:0.72rem;
                    color:#8b949e; text-transform:uppercase; letter-spacing:0.1em;
                    margin-bottom:6px;">{label}</div>
        """, unsafe_allow_html=True)

        fig, ax = plt.subplots(figsize=(4, 2.2))

        if not df.empty and len(df) > 1:
            ax.fill_between(df["collected_at"], df[col_key], alpha=0.15, color=color)
            ax.plot(df["collected_at"], df[col_key], color=color, linewidth=1.5, zorder=3)
            ax.scatter(df["collected_at"].iloc[-1], df[col_key].iloc[-1], color=color, s=40, zorder=4)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
        else:
            ax.text(0.5, 0.5, "Not enough data", transform=ax.transAxes,
                    ha='center', va='center', color="#8b949e", fontsize=9)

        ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.4, linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

st.markdown("<div style='margin:1.5rem 0;'></div>", unsafe_allow_html=True)

# ─────────────────────────────
# STATUS CARDS
# ─────────────────────────────
st.markdown("### 🔔 System Status")

alert_df = pd.DataFrame()
if DB_AVAILABLE:
    try:
        alerts = db.fetch_recent_alerts(50)
        alert_df = pd.DataFrame(alerts) if alerts else pd.DataFrame()
    except Exception:
        alert_df = pd.DataFrame()

if not alert_df.empty and "severity" in alert_df.columns:
    critical = int((alert_df["severity"] == "CRITICAL").sum())
    warning  = int((alert_df["severity"] == "WARNING").sum())
else:
    critical = 0
    warning  = 0

if health_score >= 70:
    hs_label, hs_color = "NORMAL", "#3fb950"
elif health_score >= 50:
    hs_label, hs_color = "WARNING", "#e3b341"
else:
    hs_label, hs_color = "CRITICAL", "#f85149"

c1, c2, c3 = st.columns(3)

def status_card(col, icon, label, value, color, sub=""):
    col.markdown(f"""
    <div style="background:#161b22; border:1px solid #21262d; border-radius:14px;
                padding:1.2rem 1.4rem; text-align:center; border-top:3px solid {color};">
        <div style="font-size:1.8rem; margin-bottom:4px;">{icon}</div>
        <div style="font-family:'JetBrains Mono',monospace; font-size:0.7rem;
                    color:#8b949e; text-transform:uppercase; letter-spacing:0.1em;">{label}</div>
        <div style="font-family:'JetBrains Mono',monospace; font-size:1.8rem;
                    font-weight:700; color:{color}; margin:4px 0;">{value}</div>
        {f'<div style="font-size:0.75rem; color:#8b949e;">{sub}</div>' if sub else ''}
    </div>
    """, unsafe_allow_html=True)

status_card(c1, "🚨", "Critical Alerts", critical, "#f85149", "last 50 alerts")
status_card(c2, "⚠️", "Warnings",        warning,  "#e3b341", "last 50 alerts")
status_card(c3, "❤️", "Health Status",   hs_label, hs_color,  f"score: {health_score}")

st.markdown("<div style='margin:1.5rem 0;'></div>", unsafe_allow_html=True)

# ─────────────────────────────
# DATA TABLE
# ─────────────────────────────
st.markdown("### 🗃️ Last 30 Minutes — Raw Data")

table_df = df.copy()
if "collected_at" in table_df.columns:
    table_df["collected_at"] = pd.to_datetime(table_df["collected_at"], errors="coerce")
numeric_cols = table_df.select_dtypes(include="number").columns
if len(numeric_cols) > 0:
    table_df[numeric_cols] = table_df[numeric_cols].round(2)

st.dataframe(table_df, use_container_width=True, height=400, hide_index=True)

st.markdown("<div style='margin:1.5rem 0;'></div>", unsafe_allow_html=True)

# ─────────────────────────────
# RECENT ALERTS
# ─────────────────────────────
st.markdown("### 📋 Recent Alerts")

if not alert_df.empty:
    required_cols = {"severity", "component", "message"}
    if required_cols.issubset(alert_df.columns):
        for a in alert_df.head(5).to_dict("records"):
            severity  = str(a.get("severity", "INFO"))
            component = str(a.get("component", "unknown"))
            message   = str(a.get("message", ""))
            if severity == "CRITICAL":
                icon, color = "🔴", "#f85149"
            elif severity == "WARNING":
                icon, color = "🟡", "#e3b341"
            else:
                icon, color = "🔵", "#58a6ff"
            st.markdown(f"""
            <div style="background:#161b22; border:1px solid #21262d; border-left:4px solid {color};
                        border-radius:10px; padding:0.8rem 1.2rem; margin-bottom:0.5rem;
                        font-family:'JetBrains Mono',monospace; font-size:0.82rem; color:#e6edf3;">
                {icon} &nbsp;<span style="color:{color}; font-weight:700;">[{severity}]</span>
                &nbsp;<span style="color:#8b949e;">{component}</span>
                &nbsp;→&nbsp; {message}
            </div>
            """, unsafe_allow_html=True)
    else:
        missing = required_cols - set(alert_df.columns)
        st.warning(f"⚠️ Alert table missing columns: {missing}")
        st.dataframe(alert_df.head(5), use_container_width=True, hide_index=True)
else:
    st.markdown("""
    <div style="background:#1a2d1e; border:1px solid #3fb950; border-radius:10px;
                padding:0.8rem 1.2rem; font-family:'JetBrains Mono',monospace;
                font-size:0.82rem; color:#3fb950;">
        ✅ &nbsp; No active alerts — system running normally.
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='margin:2rem 0 1rem;'></div>", unsafe_allow_html=True)

# ─────────────────────────────
# FOOTER + REFRESH
# ─────────────────────────────
fcol1, fcol2 = st.columns([1, 5])
with fcol1:
    if st.button("🔄  Refresh"):
        st.rerun()

with fcol2:
    st.markdown("""
    <div style="padding-top:10px; font-family:'JetBrains Mono',monospace;
                font-size:0.72rem; color:#30363d;">
        SentinelOps · Built with Python, PostgreSQL &amp; Streamlit
    </div>
    """, unsafe_allow_html=True)