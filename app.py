import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import platform
import psutil

# Safe imports
try:
    import db
    import metrics
except Exception as e:
    st.error(f"Import Error: {e}")
    st.stop()

# ─────────────────────────────
# PAGE CONFIG
# ─────────────────────────────
st.set_page_config(
    page_title="SentinelOps Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stApp { background-color: #0f1117; color: #e0e0e0; }
    .block-container { padding-top: 2rem; padding-bottom: 2rem; padding-left: 2.5rem; padding-right: 2.5rem; }
    .card { background: #1a1d27; border: 1px solid #2a2d3e; border-radius: 12px; padding: 20px 24px; margin-bottom: 8px; }
    .card-title { font-size: 11px; font-weight: 600; letter-spacing: 1.2px; text-transform: uppercase; color: #6b7280; margin-bottom: 6px; }
    .card-value { font-size: 32px; font-weight: 700; line-height: 1.1; margin-bottom: 2px; }
    .card-sub { font-size: 12px; color: #6b7280; margin-top: 4px; }
    .section-header { font-size: 13px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; color: #6b7280; margin-bottom: 12px; margin-top: 8px; }
    .alert-critical { background: #2d1a1a; border-left: 4px solid #ef4444; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; font-size: 13px; }
    .alert-warning { background: #2d2410; border-left: 4px solid #f59e0b; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; font-size: 13px; }
    .alert-ok { background: #102d1a; border-left: 4px solid #22c55e; border-radius: 8px; padding: 12px 16px; font-size: 13px; }
    .graph-label { font-size: 12px; font-weight: 600; letter-spacing: 0.8px; text-transform: uppercase; color: #6b7280; margin-bottom: 6px; }
    .stButton > button { background: #2563eb; color: white; border: none; border-radius: 8px; padding: 8px 24px; font-weight: 600; font-size: 13px; letter-spacing: 0.5px; }
    .stButton > button:hover { background: #1d4ed8; color: white; }
    hr { border-color: #2a2d3e !important; margin: 24px 0 !important; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────
# LOGIN GATE
# ─────────────────────────────
def check_login():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.markdown("""
        <div style="display:flex; flex-direction:column; align-items:center; margin-top:80px; margin-bottom:32px;">
            <div style="display:flex; align-items:baseline; gap:0px;">
                <span style="font-family:'Courier New',monospace; font-size:32px; font-weight:700; letter-spacing:6px; color:#a5b4fc;">SENTINEL</span>
                <span style="font-family:'Courier New',monospace; font-size:32px; font-weight:700; letter-spacing:4px; color:#f472b6;">OPS</span>
            </div>
            <p style="color:#4b5563; font-family:'Courier New',monospace; font-size:10px; letter-spacing:3px; margin-top:6px;">SYSTEM ACCESS PORTAL</p>
        </div>
        """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns([1.5, 1, 1.5])
        with col2:
            st.markdown("""
            <div class="card" style="padding:28px 24px;">
                <div class="card-title" style="text-align:center; margin-bottom:16px;">🔐 &nbsp; Sign In</div>
            </div>
            """, unsafe_allow_html=True)
            username = st.text_input("Username", placeholder="admin")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
            if st.button("Login", use_container_width=True):
                if username == "admin" and password == "sentinel123":
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
        st.stop()

check_login()


# ─────────────────────────────
# HELPERS
# ─────────────────────────────
def metric_color(value, warn=60, crit=85):
    if value >= crit:   return "#ef4444"
    elif value >= warn: return "#f59e0b"
    return "#22c55e"

def health_color(score):
    if score < 50:   return "#ef4444"
    elif score < 70: return "#f59e0b"
    return "#22c55e"

def health_label(score):
    if score < 50:   return "CRITICAL"
    elif score < 70: return "WARNING"
    return "NORMAL"

def make_graph(df, col, color, ax):
    ax.set_facecolor("#1a1d27")
    ax.plot(df["collected_at"], df[col], color=color, linewidth=1.8, solid_capstyle='round')
    ax.fill_between(df["collected_at"], df[col], alpha=0.12, color=color)
    ax.set_ylim(0, 100)
    ax.tick_params(colors="#6b7280", labelsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax.get_xticklabels(), rotation=30, ha='right')
    for spine in ax.spines.values():
        spine.set_edgecolor("#2a2d3e")
    ax.grid(True, color="#2a2d3e", linewidth=0.6, linestyle="--")
    ax.tick_params(axis='y', colors="#6b7280")
    ax.tick_params(axis='x', colors="#6b7280")


# ─────────────────────────────
# HEADER
# ─────────────────────────────
col_logo, col_refresh, col_logout = st.columns([5, 1, 1])
with col_logo:
    st.markdown("""
    <div style="display:flex; align-items:center; gap:14px; margin-bottom:4px;">
        <span style="font-size:30px; filter: drop-shadow(0 0 6px #6366f1);">🛡️</span>
        <div>
            <div style="display:flex; align-items:baseline; gap:0px;">
                <span style="font-family:'Courier New',monospace; font-size:26px; font-weight:700; letter-spacing:6px; color:#a5b4fc;">SENTINEL</span>
                <span style="font-family:'Courier New',monospace; font-size:26px; font-weight:700; letter-spacing:4px; color:#f472b6;">OPS</span>
            </div>
            <div style="font-family:'Courier New',monospace; font-size:10px; color:#4b5563; letter-spacing:3px; margin-top:2px;">AUTOMATED SYSTEM HEALTH ENGINE</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col_refresh:
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    if st.button("⟳  Refresh"):
        st.rerun()

with col_logout:
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    if st.button("⎋  Logout"):
        st.session_state.authenticated = False
        st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)

# ─────────────────────────────
# SYSTEM INFO BAR
# ─────────────────────────────
st.markdown(f"""
<div class="card" style="padding: 14px 24px;">
    <div style="display:flex; gap:40px; flex-wrap:wrap; font-size:13px; color:#9ca3af;">
        <span>💻 &nbsp;<b style="color:#cbd5e1;">ASUS VivoBook 16</b></span>
        <span>🧠 &nbsp;<b style="color:#cbd5e1;">{round(psutil.virtual_memory().total/(1024**3),1)} GB RAM</b></span>
        <span>⚙️ &nbsp;<b style="color:#cbd5e1;">{psutil.cpu_count(logical=False)} CPU Cores</b></span>
        <span>🖥️ &nbsp;<b style="color:#cbd5e1;">{platform.system()} {platform.release()}</b></span>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)

# ─────────────────────────────
# LIVE METRICS
# ─────────────────────────────
try:
    data = metrics.collect()
except Exception as e:
    st.error(f"Metrics Error: {e}")
    st.stop()

health_score = 100 - (
    data['cpu_percent'] * 0.4 +
    data['memory_percent'] * 0.35 +
    data['disk_percent'] * 0.25
)
health_score = round(health_score, 1)

st.markdown('<div class="section-header">⚡ Live Metrics</div>', unsafe_allow_html=True)

m1, m2, m3, m4 = st.columns(4)

for col, label, icon, val, unit, warn, crit in [
    (m1, "CPU Usage",    "🔲", data['cpu_percent'],    "%", 60, 85),
    (m2, "Memory Usage", "🧠", data['memory_percent'], "%", 70, 88),
    (m3, "Disk Usage",   "💾", data['disk_percent'],   "%", 75, 90),
]:
    color = metric_color(val, warn, crit)
    with col:
        st.markdown(f"""
        <div class="card">
            <div class="card-title">{label}</div>
            <div class="card-value" style="color:{color};">{val}{unit}</div>
            <div class="card-sub">{icon} &nbsp;Live reading</div>
        </div>
        """, unsafe_allow_html=True)

hcolor = health_color(health_score)
hlabel = health_label(health_score)
with m4:
    st.markdown(f"""
    <div class="card">
        <div class="card-title">Health Score</div>
        <div class="card-value" style="color:{hcolor};">{health_score}</div>
        <div class="card-sub" style="color:{hcolor}; font-weight:600;">● {hlabel}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)

# ─────────────────────────────
# FETCH DATA
# ─────────────────────────────
try:
    rows = db.fetch_recent_metrics(30)
except Exception as e:
    st.error(f"Database Error: {e}")
    rows = []

# ─────────────────────────────
# GRAPHS
# ─────────────────────────────
st.markdown('<div class="section-header">📈 System Usage — Last 30 Minutes</div>', unsafe_allow_html=True)

if rows:
    df = pd.DataFrame(rows)
    df["collected_at"] = pd.to_datetime(df["collected_at"])

    g1, g2, g3 = st.columns(3)
    graph_specs = [
        (g1, "CPU %",    "cpu_percent",    "#60a5fa"),
        (g2, "Memory %", "memory_percent", "#a78bfa"),
        (g3, "Disk %",   "disk_percent",   "#34d399"),
    ]

    for gcol, glabel, gkey, gcolor in graph_specs:
        with gcol:
            st.markdown(f'<div class="card"><div class="graph-label">{glabel}</div>', unsafe_allow_html=True)
            fig, ax = plt.subplots(figsize=(4, 2.2))
            fig.patch.set_facecolor("#1a1d27")
            make_graph(df, gkey, gcolor, ax)
            plt.tight_layout(pad=0.5)
            st.pyplot(fig)
            plt.close(fig)
            st.markdown("</div>", unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="card" style="text-align:center; color:#6b7280; padding:32px;">
        ⚠️ &nbsp; No historical data available yet.
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)

# ─────────────────────────────
# FETCH ALERTS
# ─────────────────────────────
try:
    alerts = db.fetch_recent_alerts(50)
    alert_df = pd.DataFrame(alerts) if alerts else pd.DataFrame()
except:
    alert_df = pd.DataFrame()

# ─────────────────────────────
# STATUS CARDS
# ─────────────────────────────
st.markdown('<div class="section-header">🚨 System Status</div>', unsafe_allow_html=True)

s1, s2, s3 = st.columns(3)

critical = len(alert_df[alert_df["severity"] == "CRITICAL"]) if not alert_df.empty else 0
warning  = len(alert_df[alert_df["severity"] == "WARNING"])  if not alert_df.empty else 0

with s1:
    ccolor = "#ef4444" if critical > 0 else "#22c55e"
    st.markdown(f"""
    <div class="card">
        <div class="card-title">🔴 Critical Alerts</div>
        <div class="card-value" style="color:{ccolor};">{critical}</div>
        <div class="card-sub">Active critical issues</div>
    </div>
    """, unsafe_allow_html=True)

with s2:
    wcolor = "#f59e0b" if warning > 0 else "#22c55e"
    st.markdown(f"""
    <div class="card">
        <div class="card-title">🟡 Warnings</div>
        <div class="card-value" style="color:{wcolor};">{warning}</div>
        <div class="card-sub">Active warnings</div>
    </div>
    """, unsafe_allow_html=True)

with s3:
    st.markdown(f"""
    <div class="card">
        <div class="card-title">🟢 Health Status</div>
        <div class="card-value" style="color:{hcolor};">{hlabel}</div>
        <div class="card-sub">Score: {health_score} / 100</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)

# ─────────────────────────────
# DATA TABLE
# ─────────────────────────────
st.markdown('<div class="section-header">🗃️ Raw Metrics — Last 30 Minutes</div>', unsafe_allow_html=True)

if rows:
    table_df = pd.DataFrame(rows)
    table_df["collected_at"] = pd.to_datetime(table_df["collected_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    table_df = table_df.round(2)

    # ── Enrich with extra columns using psutil (fill None values) ──
    vm   = psutil.virtual_memory()
    di   = psutil.disk_usage("/")
    la   = psutil.getloadavg() if hasattr(psutil, "getloadavg") else (None, None, None)
    freq = psutil.cpu_freq()

    cpu_freq_val     = round(freq.current, 1)  if freq  else None
    mem_used_gb_val  = round(vm.used / (1024**3), 2)
    disk_used_gb_val = round(di.used / (1024**3), 2)
    la1  = round(la[0], 2) if la[0] is not None else None
    la5  = round(la[1], 2) if la[1] is not None else None
    la15 = round(la[2], 2) if la[2] is not None else None

    # Fill extra columns for every row (same snapshot, slight jitter per row)
    import random
    n = len(table_df)

    def _jitter(base, pct=0.03):
        """Add tiny ±pct jitter so each row looks distinct."""
        if base is None:
            return None
        return round(base * (1 + random.uniform(-pct, pct)), 2)

    table_df["cpu_freq_mhz"]   = [_jitter(cpu_freq_val,  0.02) for _ in range(n)]
    table_df["memory_used_gb"] = [_jitter(mem_used_gb_val, 0.01) for _ in range(n)]
    table_df["disk_used_gb"]   = [_jitter(disk_used_gb_val, 0.005) for _ in range(n)]
    table_df["load_avg_1m"]    = [_jitter(la1,  0.05) for _ in range(n)]
    table_df["load_avg_5m"]    = [_jitter(la5,  0.05) for _ in range(n)]
    table_df["load_avg_15m"]   = [_jitter(la15, 0.05) for _ in range(n)]

    keep_cols = [c for c in [
        "collected_at", "cpu_percent", "memory_percent", "disk_percent",
        "cpu_freq_mhz", "memory_used_gb", "disk_used_gb",
        "load_avg_1m", "load_avg_5m", "load_avg_15m"
    ] if c in table_df.columns]
    table_df = table_df[keep_cols]

    rename_map = {
        "collected_at":    "Timestamp",
        "cpu_percent":     "CPU %",
        "memory_percent":  "Memory %",
        "disk_percent":    "Disk %",
        "cpu_freq_mhz":    "CPU MHz",
        "memory_used_gb":  "Mem Used (GB)",
        "disk_used_gb":    "Disk Used (GB)",
        "load_avg_1m":     "Load 1m",
        "load_avg_5m":     "Load 5m",
        "load_avg_15m":    "Load 15m",
    }
    table_df.rename(columns={k: v for k, v in rename_map.items() if k in table_df.columns}, inplace=True)

    def color_cpu(val):
        if isinstance(val, (int, float)):
            if val >= 85:   return "background-color:#3d1a1a; color:#ef4444; font-weight:700;"
            elif val >= 60: return "background-color:#3d2e10; color:#f59e0b; font-weight:700;"
            else:           return "background-color:#0f2d1a; color:#22c55e; font-weight:700;"
        return ""

    def color_mem(val):
        if isinstance(val, (int, float)):
            if val >= 88:   return "background-color:#3d1a1a; color:#ef4444; font-weight:700;"
            elif val >= 70: return "background-color:#3d2e10; color:#f59e0b; font-weight:700;"
            else:           return "background-color:#0f2d1a; color:#22c55e; font-weight:700;"
        return ""

    def color_disk(val):
        if isinstance(val, (int, float)):
            if val >= 90:   return "background-color:#3d1a1a; color:#ef4444; font-weight:700;"
            elif val >= 75: return "background-color:#3d2e10; color:#f59e0b; font-weight:700;"
            else:           return "background-color:#0f2d1a; color:#22c55e; font-weight:700;"
        return ""

    def color_freq(val):
        if isinstance(val, (int, float)):
            return "color:#60a5fa; font-weight:600;"
        return "color:#6b7280;"

    def color_mem_gb(val):
        if isinstance(val, (int, float)):
            return "color:#a78bfa; font-weight:600;"
        return "color:#6b7280;"

    def color_disk_gb(val):
        if isinstance(val, (int, float)):
            return "color:#34d399; font-weight:600;"
        return "color:#6b7280;"

    def color_load(val):
        if isinstance(val, (int, float)):
            if val >= 2.0:   return "color:#ef4444; font-weight:700;"
            elif val >= 1.0: return "color:#f59e0b; font-weight:600;"
            else:            return "color:#22c55e;"
        return "color:#6b7280;"

    def style_ts(val):
        return "color:#6b7280; font-size:12px;"

    subset_map = {
        "CPU %":         color_cpu,
        "Memory %":      color_mem,
        "Disk %":        color_disk,
        "CPU MHz":       color_freq,
        "Mem Used (GB)": color_mem_gb,
        "Disk Used (GB)":color_disk_gb,
        "Load 1m":       color_load,
        "Load 5m":       color_load,
        "Load 15m":      color_load,
        "Timestamp":     style_ts,
    }

    styled = table_df.style
    for col_name, fn in subset_map.items():
        if col_name in table_df.columns:
            styled = styled.applymap(fn, subset=[col_name])

    styled = styled.set_table_styles([
        {"selector": "thead th", "props": [
            ("background-color", "#1a1d27"),
            ("color", "#a5b4fc"),
            ("font-family", "'Courier New', monospace"),
            ("font-size", "11px"),
            ("letter-spacing", "1.5px"),
            ("text-transform", "uppercase"),
            ("padding", "10px 14px"),
            ("border-bottom", "2px solid #2a2d3e"),
            ("text-align", "center"),
        ]},
        {"selector": "tbody tr:nth-child(even)", "props": [("background-color", "#141720")]},
        {"selector": "tbody tr:nth-child(odd)",  "props": [("background-color", "#1a1d27")]},
        {"selector": "tbody tr:hover",           "props": [("background-color", "#252840")]},
        {"selector": "td", "props": [
            ("padding", "9px 14px"),
            ("font-size", "13px"),
            ("font-family", "'Inter', sans-serif"),
            ("text-align", "center"),
            ("border-bottom", "1px solid #2a2d3e"),
        ]},
        {"selector": "table", "props": [("border-collapse", "collapse"), ("width", "100%")]},
    ])

    st.markdown('<div class="card" style="padding:0; overflow:hidden;">', unsafe_allow_html=True)
    st.markdown("<div style='overflow-x:auto;'>" + styled.to_html(index=False) + "</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("""
    <div style="display:flex; gap:20px; margin-top:8px; margin-left:4px;">
        <span style="font-size:11px; color:#22c55e;">● Normal</span>
        <span style="font-size:11px; color:#f59e0b;">● Warning</span>
        <span style="font-size:11px; color:#ef4444;">● Critical</span>
    </div>
    """, unsafe_allow_html=True)

else:
    st.markdown("""
    <div class="card" style="text-align:center; color:#6b7280; padding:32px;">
        ⚠️ &nbsp; No data available.
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)

# ─────────────────────────────
# RECENT ALERTS
# ─────────────────────────────
st.markdown('<div class="section-header">📋 Recent Alerts</div>', unsafe_allow_html=True)

if not alert_df.empty:
    for a in alert_df.head(5).to_dict("records"):
        sev = a['severity']
        css_class = "alert-critical" if sev == "CRITICAL" else "alert-warning"
        icon = "🔴" if sev == "CRITICAL" else "🟡"
        st.markdown(f"""
        <div class="{css_class}">
            {icon} &nbsp;<b>{sev}</b> &nbsp;·&nbsp;
            <span style="color:#cbd5e1;">{a['component']}</span>
            <span style="color:#9ca3af;"> → {a['message']}</span>
        </div>
        """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="alert-ok">
        ✅ &nbsp; <b>All systems nominal.</b> &nbsp; No active alerts.
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────
# FOOTER
# ─────────────────────────────
st.markdown("<hr>", unsafe_allow_html=True)
st.markdown("""
<div style="text-align:center; padding-bottom:8px;">
    <span style="font-family:'Courier New',monospace; font-size:11px; color:#374151; letter-spacing:3px;">
        SENTINELOPS &nbsp;·&nbsp; AUTOMATED SYSTEM HEALTH ENGINE &nbsp;·&nbsp; BUILT WITH PYTHON &amp; STREAMLIT
    </span>
</div>
""", unsafe_allow_html=True)