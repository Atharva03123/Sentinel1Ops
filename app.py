"""
╔══════════════════════════════════════════════════════════════╗
║           SentinelOps AI  —  Enterprise Edition v2.0        ║
║         Automated System Health & Monitoring Engine         ║
╚══════════════════════════════════════════════════════════════╝
"""

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
import logging
import os
import uuid
import hashlib

# ── Safe imports ──────────────────────────────────────────────
try:
    import db
    import metrics
    DB_AVAILABLE = True
    METRICS_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False
    METRICS_AVAILABLE = False

# ═══════════════════════════════════════════════════════════════
# APP CONSTANTS
# ═══════════════════════════════════════════════════════════════
APP_VERSION  = "2.0.1"
COMPANY_NAME = "SentinelOps AI"
BUILD_YEAR   = "2026"
LOG_FILE     = "system.log"

ROLES = {
    "admin": {
        "label": "Administrator", "icon": "👑",
        "color": "#ff4d6d", "badge_bg": "#2a0a10",
        "permissions": ["dashboard","alerts","ai_assistant","admin_panel",
                        "logs","login_history","system_overview","user_management"],
    },
    "user": {
        "label": "Operator", "icon": "🧑‍💻",
        "color": "#2d7cf6", "badge_bg": "#0a1428",
        "permissions": ["dashboard","alerts","ai_assistant"],
    },
    "viewer": {
        "label": "Viewer", "icon": "👁️",
        "color": "#10d98a", "badge_bg": "#0a1e14",
        "permissions": ["dashboard"],
    },
}

def _h(p): return hashlib.sha256(p.encode()).hexdigest()

USERS_DB = {
    "superadmin": {"hash": _h("admin@999"),   "role": "admin",  "name": "Super Admin",   "email": "admin@sentinel.io",  "dept": "IT Operations"},
    "root":       {"hash": _h("r00tAccess"),  "role": "admin",  "name": "Root Admin",    "email": "root@sentinel.io",   "dept": "Infrastructure"},
    "admin":      {"hash": _h("sentinel123"), "role": "user",   "name": "John Mitchell", "email": "john@sentinel.io",   "dept": "DevOps"},
    "user1":      {"hash": _h("pass1234"),    "role": "user",   "name": "Priya Sharma",  "email": "priya@sentinel.io",  "dept": "SRE Team"},
    "monitor":    {"hash": _h("watch99"),     "role": "user",   "name": "Carlos Ruiz",   "email": "carlos@sentinel.io", "dept": "Monitoring"},
    "viewer1":    {"hash": _h("view2024"),    "role": "viewer", "name": "Alice Chen",    "email": "alice@sentinel.io",  "dept": "Management"},
    "guest":      {"hash": _h("guest123"),    "role": "viewer", "name": "Guest User",    "email": "guest@sentinel.io",  "dept": "External"},
}

# ═══════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════
def setup_logger():
    lg = logging.getLogger("SentinelOps")
    lg.setLevel(logging.DEBUG)
    if not lg.handlers:
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        lg.addHandler(fh)
    return lg

logger = setup_logger()

def log_event(level: str, message: str, category: str = "SYSTEM"):
    getattr(logger, level.lower(), logger.info)(f"[{category}] {message}")

def read_logs(filter_level=None, filter_category=None, limit=200):
    if not os.path.exists(LOG_FILE):
        return []
    lines = []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if filter_level and filter_level != "ALL":
                    if f"| {filter_level}" not in line:
                        continue
                if filter_category and filter_category != "ALL":
                    if f"[{filter_category}]" not in line:
                        continue
                lines.append(line)
    except Exception:
        pass
    return lines[-limit:]

def clear_logs():
    try:
        open(LOG_FILE, "w").close()
        log_event("info", "Log file cleared by admin", "ADMIN")
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════════
_defaults = {
    "logged_in":        False,
    "current_user":     None,
    "current_role":     None,
    "session_id":       None,
    "login_time":       None,
    "show_admin_panel": False,
    "collector_started":False,
    "chat_history":     [],
    "login_history":    [],
    "sel_role_login":   "user",
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

def has_perm(p):
    return p in ROLES.get(st.session_state.current_role or "viewer", {}).get("permissions", [])

def record_login(username, role, success):
    st.session_state.login_history.append({
        "time":     datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "username": username,
        "role":     role,
        "status":   "SUCCESS" if success else "FAILED",
        "session":  str(uuid.uuid4())[:8].upper(),
    })
    log_event("info" if success else "warning",
              f"Login {'SUCCESS' if success else 'FAILED'} | user={username} | role={role}", "AUTH")

# ═══════════════════════════════════════════════════════════════
# BACKGROUND COLLECTOR
# ═══════════════════════════════════════════════════════════════
def run_collector():
    while True:
        try:
            if DB_AVAILABLE and METRICS_AVAILABLE:
                db.insert_metric(metrics.collect())
        except Exception:
            pass
        time.sleep(5)

# ═══════════════════════════════════════════════════════════════
# VOICE ALERT
# ═══════════════════════════════════════════════════════════════
def voice_alert(msg, key, cooldown=45):
    now = time.time()
    ck  = f"vc_{key}"
    if now - st.session_state.get(ck, 0) < cooldown:
        return
    st.session_state[ck] = now
    safe = msg.replace("'", "\\'")
    st.components.v1.html(
        f"<script>(function(){{if(!window.speechSynthesis)return;"
        f"var u=new SpeechSynthesisUtterance('{safe}');u.lang='en-US';"
        f"u.rate=0.95;window.speechSynthesis.cancel();window.speechSynthesis.speak(u);}})();</script>",
        height=0
    )

# ═══════════════════════════════════════════════════════════════
# METRICS HELPERS
# ═══════════════════════════════════════════════════════════════
def collect_live():
    if METRICS_AVAILABLE:
        try: return metrics.collect()
        except Exception: pass
    return {
        "cpu_percent":    psutil.cpu_percent(interval=0.5),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent":   psutil.disk_usage("/").percent,
    }

def get_cpu_temp():
    try:
        t = psutil.sensors_temperatures()
        if t:
            for k in ("coretemp","k10temp","cpu_thermal","acpitz"):
                if k in t and t[k]:
                    return round(t[k][0].current, 1)
    except Exception:
        pass
    cpu = psutil.cpu_percent(interval=0.1)
    return round(max(28, min(98, 38 + (cpu/100)*52 + random.gauss(0,1.5))), 1)

def get_net():
    try:
        n = psutil.net_io_counters()
        return round(n.bytes_sent/(1024**2),1), round(n.bytes_recv/(1024**2),1)
    except Exception:
        return 0.0, 0.0

def get_uptime():
    try:
        delta = datetime.datetime.now() - datetime.datetime.fromtimestamp(psutil.boot_time())
        h, rem = divmod(int(delta.total_seconds()), 3600)
        d, h = divmod(h, 24)
        m = rem // 60
        return f"{d}d {h}h {m}m" if d else f"{h}h {m}m"
    except Exception:
        return "N/A"

def get_procs(n=8):
    procs = []
    try:
        for p in psutil.process_iter(['pid','name','cpu_percent','memory_percent']):
            try:
                i = p.info
                procs.append({"PID": i['pid'], "Process": (i['name'] or "")[:22],
                               "CPU %": round(i['cpu_percent'] or 0,1),
                               "MEM %": round(i['memory_percent'] or 0,1)})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass
    return sorted(procs, key=lambda x: x["CPU %"], reverse=True)[:n]

def gen_sim(n=30):
    now = datetime.datetime.now()
    bc,bm,bd = random.uniform(20,50),random.uniform(40,65),random.uniform(30,55)
    rows = []
    for i in range(n):
        t = now - datetime.timedelta(minutes=(n-i))
        rows.append({
            "collected_at":   t,
            "cpu_percent":    round(max(0,min(100,bc+10*math.sin(i/5)+random.gauss(0,3))),2),
            "memory_percent": round(max(0,min(100,bm+5*math.sin(i/8)+random.gauss(0,2))),2),
            "disk_percent":   round(max(0,min(100,bd+2*math.sin(i/12)+random.gauss(0,1))),2),
        })
    return rows

def gcol(v, t=(60,80)):
    return "#10d98a" if v < t[0] else ("#f5c542" if v < t[1] else "#ff4d6d")

def hcol(s):
    return "#10d98a" if s>=70 else ("#f5c542" if s>=50 else "#ff4d6d")

# ═══════════════════════════════════════════════════════════════
# AI ASSISTANT
# ═══════════════════════════════════════════════════════════════
def ai_response(query, live):
    q    = query.lower().strip()
    cpu  = live.get("cpu_percent",0)
    mem  = live.get("memory_percent",0)
    disk = live.get("disk_percent",0)
    temp = get_cpu_temp()
    health = max(0, 100-(cpu*.4+mem*.35+disk*.25))

    def sev(v,w=70,c=90):
        return "🔴 CRITICAL" if v>=c else ("🟡 WARNING" if v>=w else "🟢 NORMAL")

    if any(k in q for k in ["cpu","processor","core"]):
        sol = ("Terminate high-CPU processes immediately. Use Task Manager or `top`."
               if cpu>90 else "Review background services. Disable startup programs."
               if cpu>70 else "CPU operating optimally. No action needed.")
        return (f"**🔲 CPU Diagnostic**\n\n"
                f"| Metric | Value |\n|--------|-------|\n"
                f"| Usage | **{cpu}%** |\n| Temperature | **{temp}°C** |\n"
                f"| Severity | {sev(cpu)} |\n| Logical Cores | {psutil.cpu_count(logical=True)} |\n\n"
                f"**Recommendation:** {sol}")

    if any(k in q for k in ["memory","ram","mem"]):
        vm  = psutil.virtual_memory()
        sol = ("Close apps immediately. Expand RAM or swap." if mem>85
               else "Monitor memory-heavy processes. Check for leaks." if mem>65
               else "Memory usage nominal.")
        return (f"**🧠 Memory Diagnostic**\n\n"
                f"| Metric | Value |\n|--------|-------|\n"
                f"| Usage | **{mem}%** |\n| Available | **{round(vm.available/(1024**3),2)} GB** |\n"
                f"| Total | **{round(vm.total/(1024**3),2)} GB** |\n| Severity | {sev(mem,65,85)} |\n\n"
                f"**Recommendation:** {sol}")

    if any(k in q for k in ["disk","storage","drive","space","ssd","hdd"]):
        du  = psutil.disk_usage("/")
        sol = ("URGENT: Delete temp files, empty trash, move data." if disk>90
               else "Schedule cleanup. Archive cold data." if disk>70
               else "Disk usage acceptable.")
        return (f"**💾 Disk Diagnostic**\n\n"
                f"| Metric | Value |\n|--------|-------|\n"
                f"| Usage | **{disk}%** |\n| Free | **{round(du.free/(1024**3),1)} GB** |\n"
                f"| Total | **{round(du.total/(1024**3),1)} GB** |\n| Severity | {sev(disk)} |\n\n"
                f"**Recommendation:** {sol}")

    if any(k in q for k in ["temp","temperature","heat","thermal","overheat"]):
        sol = ("CRITICAL: Verify fan operation. Clean heatsink. Reapply thermal paste." if temp>80
               else "Improve case airflow. Check fan curves." if temp>65
               else "Temperature in safe range.")
        return (f"**🌡️ Thermal Diagnostic**\n\n"
                f"| Threshold | Value |\n|-----------|-------|\n"
                f"| Current | **{temp}°C** |\n| Safe | < 65°C |\n"
                f"| Warning | 65–80°C |\n| Critical | > 80°C |\n| Status | {sev(temp,65,80)} |\n\n"
                f"**Recommendation:** {sol}")

    if any(k in q for k in ["slow","lag","freeze","hang","performance"]):
        causes = []
        if cpu>70:  causes.append(f"High CPU ({cpu}%)")
        if mem>70:  causes.append(f"High Memory ({mem}%)")
        if disk>80: causes.append(f"Low Disk ({disk}%)")
        if temp>75: causes.append(f"Thermal Throttle ({temp}°C)")
        if not causes: causes = ["No obvious bottleneck — check I/O wait or network"]
        return (f"**🐢 Performance Diagnosis**\n\n**Identified Causes:**\n" +
                "\n".join(f"- ⚠️ {c}" for c in causes) +
                "\n\n**Action Plan:**\n"
                "1. Restart heaviest processes\n2. Free RAM by closing idle apps\n"
                "3. Check disk I/O\n4. Verify network latency\n5. Run malware scan")

    if any(k in q for k in ["health","score","status","overview","report","system"]):
        ns,nr = get_net()
        hs = "🟢 NORMAL" if health>=70 else ("🟡 WARNING" if health>=50 else "🔴 CRITICAL")
        return (f"**❤️ Full System Health Report**\n\n"
                f"| Component | Value | Status |\n|-----------|-------|--------|\n"
                f"| Health Score | **{round(health,1)}** | {hs} |\n"
                f"| CPU | {cpu}% | {sev(cpu)} |\n| Memory | {mem}% | {sev(mem,65,85)} |\n"
                f"| Disk | {disk}% | {sev(disk)} |\n| Temp | {temp}°C | {sev(temp,65,80)} |\n"
                f"| Uptime | {get_uptime()} | 🟢 |\n| Net Sent | {ns} MB | — |\n| Net Recv | {nr} MB | — |")

    if any(k in q for k in ["alert","warn","critical","error"]):
        items = []
        if cpu>90:   items.append("🔴 CPU CRITICAL")
        elif cpu>70: items.append("🟡 CPU WARNING")
        if mem>85:   items.append("🔴 MEMORY CRITICAL")
        elif mem>65: items.append("🟡 MEMORY WARNING")
        if disk>90:  items.append("🔴 DISK CRITICAL")
        if temp>80:  items.append("🔴 TEMP CRITICAL")
        if not items: items = ["✅ No active alerts — all systems nominal"]
        return "**🔔 Active Alerts**\n\n" + "\n".join(f"- {i}" for i in items)

    if any(k in q for k in ["network","net","bandwidth"]):
        ns,nr = get_net()
        return (f"**🌐 Network Summary**\n\n"
                f"- **Sent:** {ns} MB (since boot)\n- **Received:** {nr} MB (since boot)\n"
                f"- **Active Processes:** {len(psutil.pids())}")

    if any(k in q for k in ["process","processes","top","task"]):
        procs = get_procs(5)
        lines = ["**⚙️ Top Processes**\n\n| PID | Process | CPU % | MEM % |","|-----|---------|-------|-------|"]
        for p in procs:
            lines.append(f"| {p['PID']} | {p['Process']} | {p['CPU %']} | {p['MEM %']} |")
        return "\n".join(lines)

    return (f"**🤖 SentinelOps AI Assistant**\n\n"
            f"Try: `cpu` · `memory` · `disk` · `temperature` · `network` · `processes` · `health` · `alerts` · `slow`\n\n"
            f"**Snapshot:** CPU {cpu}% | RAM {mem}% | Disk {disk}% | Temp {temp}°C")

# ═══════════════════════════════════════════════════════════════
# DASHBOARD CSS
# ═══════════════════════════════════════════════════════════════
DASH_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');
:root{
    --bg:#070b14; --s1:#0e1421; --s2:#141d2e;
    --b1:#1c2640; --b2:#243050;
    --t1:#d4dff0; --muted:#3a4a6a;
    --acc:#2d7cf6; --acc2:#00c4ff;
    --green:#10d98a; --yellow:#f5c542; --red:#ff4d6d;
    --purple:#a78bfa;
    --fh:'Syne',sans-serif; --fm:'DM Mono',monospace; --fb:'DM Sans',sans-serif;
}
.stApp{background:var(--bg) !important;color:var(--t1);font-family:var(--fb);}
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding:1.6rem 2.5rem;max-width:100%;}
hr{border:none;border-top:1px solid var(--b1);margin:1.2rem 0;}
h1,h2,h3,h4{font-family:var(--fh) !important;color:var(--t1) !important;}
.stButton>button{
    background:var(--s2);color:var(--acc2);border:1px solid var(--b2);
    border-radius:8px;padding:0.44rem 1.1rem;
    font-family:var(--fm);font-size:0.78rem;font-weight:500;
    letter-spacing:0.04em;transition:all 0.18s;
}
.stButton>button:hover{background:var(--acc);border-color:var(--acc2);color:#fff;box-shadow:0 0 14px rgba(45,124,246,.3);}
.stTextInput>div>div>input,.stTextArea textarea{
    background:var(--s1) !important;border:1px solid var(--b2) !important;
    color:var(--t1) !important;border-radius:8px !important;
    font-family:var(--fm) !important;font-size:0.83rem !important;
}
.stSelectbox>div>div,[data-baseweb="select"]{
    background:var(--s1) !important;border:1px solid var(--b2) !important;border-radius:8px !important;
}
[data-testid="stDataFrame"]{border:1px solid var(--b1);border-radius:10px;overflow:hidden;}
.stTabs [data-baseweb="tab-list"]{background:var(--s1);border-bottom:1px solid var(--b1);}
.stTabs [data-baseweb="tab"]{font-family:var(--fm);font-size:0.78rem;color:var(--muted);padding:0.55rem 1.1rem;}
.stTabs [aria-selected="true"]{color:var(--acc2) !important;border-bottom:2px solid var(--acc2) !important;background:transparent !important;}
</style>
"""

LOGIN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Mono:wght@400;500&display=swap');
:root{--bg:#070b14;--s1:rgba(14,20,33,0.94);--b1:rgba(45,124,246,0.16);
      --acc:#2d7cf6;--acc2:#00c4ff;--red:#ff4d6d;--green:#10d98a;--t1:#d4dff0;--muted:#3a4a6a;}
.stApp{background:var(--bg) !important;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding:0 !important;max-width:100%;}
.bg-grid{position:fixed;inset:0;
    background-image:linear-gradient(rgba(45,124,246,.04) 1px,transparent 1px),
                     linear-gradient(90deg,rgba(0,196,255,.025) 1px,transparent 1px);
    background-size:48px 48px;animation:gd 30s linear infinite;z-index:0;}
@keyframes gd{to{background-position:48px 48px;}}
.orb1{position:fixed;width:580px;height:580px;border-radius:50%;
    background:radial-gradient(circle,rgba(45,124,246,.13),transparent 68%);
    top:-200px;left:-200px;animation:o1 9s ease-in-out infinite alternate;z-index:0;}
.orb2{position:fixed;width:460px;height:460px;border-radius:50%;
    background:radial-gradient(circle,rgba(0,196,255,.08),transparent 68%);
    bottom:-130px;right:-130px;animation:o2 7s ease-in-out infinite alternate;z-index:0;}
.orb3{position:fixed;width:240px;height:240px;border-radius:50%;
    background:radial-gradient(circle,rgba(255,77,109,.06),transparent 70%);
    top:38%;right:16%;animation:o3 11s ease-in-out infinite alternate;z-index:0;}
@keyframes o1{to{transform:translate(45px,35px) scale(1.1);}}
@keyframes o2{to{transform:translate(-30px,22px) scale(1.08);}}
@keyframes o3{to{transform:translateY(-35px) scale(1.14);}}
.scan{position:fixed;left:0;right:0;height:1.5px;
    background:linear-gradient(90deg,transparent,rgba(0,196,255,.55),transparent);
    animation:sc 7s ease-in-out infinite;z-index:2;opacity:0;}
@keyframes sc{0%{top:0;opacity:0;}5%{opacity:1;}90%{opacity:.6;}100%{top:100%;opacity:0;}}
.lcard{position:relative;z-index:10;width:100%;max-width:420px;margin:0 auto;
    background:var(--s1);border:1px solid var(--b1);border-radius:20px;
    padding:2.4rem 2.2rem 2rem;backdrop-filter:blur(24px);
    box-shadow:0 0 70px rgba(45,124,246,.08),0 36px 70px rgba(0,0,0,.45);
    animation:ci .75s cubic-bezier(.16,1,.3,1) both;}
@keyframes ci{from{opacity:0;transform:translateY(22px) scale(.975);}to{opacity:1;transform:none;}}
.brand-ring{width:62px;height:62px;border-radius:50%;
    background:linear-gradient(135deg,rgba(45,124,246,.17),rgba(0,196,255,.09));
    border:1px solid rgba(45,124,246,.28);display:flex;align-items:center;
    justify-content:center;font-size:24px;margin:0 auto .9rem;position:relative;
    animation:ri .9s cubic-bezier(.16,1,.3,1) .2s both;}
.brand-ring::before{content:'';position:absolute;inset:-5px;border-radius:50%;
    border:1.5px solid transparent;border-top-color:var(--acc2);border-right-color:var(--acc);
    animation:spin 3s linear infinite;}
.brand-ring::after{content:'';position:absolute;inset:-11px;border-radius:50%;
    border:1px solid transparent;border-bottom-color:rgba(0,196,255,.22);
    animation:spin 6s linear infinite reverse;}
@keyframes ri{from{opacity:0;transform:scale(.3) rotate(-180deg);}to{opacity:1;transform:none;}}
@keyframes spin{to{transform:rotate(360deg);}}
.btitle{font-family:'Syne',sans-serif;font-size:22px;font-weight:800;
    background:linear-gradient(90deg,var(--acc2),var(--acc),#a78bfa);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;
    text-align:center;letter-spacing:-.02em;margin-bottom:2px;}
.bsub{font-family:'DM Mono',monospace;font-size:9px;color:#1e3a5f;
    letter-spacing:.18em;text-align:center;margin-bottom:1.6rem;text-transform:uppercase;}
.slabel{font-family:'DM Mono',monospace;font-size:9px;color:var(--muted);
    letter-spacing:.14em;text-transform:uppercase;margin-bottom:.45rem;margin-top:.9rem;}
.div-row{display:flex;align-items:center;gap:9px;margin:.9rem 0;}
.div-line{flex:1;height:1px;background:var(--b1);}
.div-txt{font-family:'DM Mono',monospace;font-size:8.5px;color:var(--muted);letter-spacing:.1em;}
.pulsebar{display:flex;align-items:center;justify-content:center;gap:7px;margin-top:1.2rem;}
.pdot{width:5px;height:5px;border-radius:50%;background:var(--green);animation:bl 1.6s ease-in-out infinite;}
@keyframes bl{0%,100%{opacity:1;}50%{opacity:.12;}}
.ptxt{font-family:'DM Mono',monospace;font-size:9.5px;color:#1e4a30;letter-spacing:.1em;}
.stTextInput>div>div>input{
    background:rgba(7,11,20,.85) !important;border:1px solid rgba(45,124,246,.2) !important;
    color:#d4dff0 !important;border-radius:9px !important;
    font-family:'DM Mono',monospace !important;font-size:.82rem !important;}
.stTextInput>div>div>input:focus{border-color:rgba(0,196,255,.5) !important;box-shadow:0 0 0 2px rgba(0,196,255,.08) !important;}
.stButton>button{
    background:linear-gradient(135deg,var(--acc),#1a5fd4) !important;
    color:#fff !important;border:none !important;border-radius:9px !important;
    font-family:'DM Mono',monospace !important;font-size:.8rem !important;
    font-weight:500 !important;padding:.52rem 1rem !important;
    letter-spacing:.06em !important;box-shadow:0 4px 16px rgba(45,124,246,.25) !important;
    transition:all .2s !important;}
.stButton>button:hover{background:linear-gradient(135deg,var(--acc2),var(--acc)) !important;box-shadow:0 6px 24px rgba(0,196,255,.3) !important;}
.stCheckbox>label{font-family:'DM Mono',monospace;font-size:.76rem;color:var(--muted);}
</style>
"""

# ═══════════════════════════════════════════════════════════════
#  LOGIN PAGE
# ═══════════════════════════════════════════════════════════════
if not st.session_state.logged_in:
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    st.markdown("""
    <div class="bg-grid"></div>
    <div class="orb1"></div><div class="orb2"></div><div class="orb3"></div>
    <div class="scan"></div>
    <div style="display:flex;align-items:center;justify-content:center;min-height:90vh;padding:2rem;">
        <div class="lcard">
            <div class="brand-ring">🛡️</div>
            <div class="btitle">SentinelOps AI</div>
            <div class="bsub">Enterprise System Health Platform</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    lc1, lc2, lc3 = st.columns([1.3, 1, 1.3])
    with lc2:
        # Role selector
        st.markdown('<div class="slabel">Select Access Level</div>', unsafe_allow_html=True)
        rb1, rb2, rb3 = st.columns(3)
        with rb1:
            if st.button("👁️\nViewer",   use_container_width=True, key="rl_v"):
                st.session_state.sel_role_login = "viewer"
        with rb2:
            if st.button("🧑‍💻\nOperator", use_container_width=True, key="rl_u"):
                st.session_state.sel_role_login = "user"
        with rb3:
            if st.button("👑\nAdmin",    use_container_width=True, key="rl_a"):
                st.session_state.sel_role_login = "admin"

        sel = st.session_state.sel_role_login
        rm  = ROLES[sel]
        st.markdown(
            f'<div style="text-align:center;margin:.35rem 0 .8rem;font-family:\'DM Mono\',monospace;'
            f'font-size:.7rem;color:{rm["color"]};background:{rm["badge_bg"]};'
            f'border:1px solid {rm["color"]}40;border-radius:6px;padding:3px 0;">'
            f'{rm["icon"]} &nbsp;{rm["label"].upper()} SELECTED</div>', unsafe_allow_html=True)

        st.markdown('<div class="div-row"><div class="div-line"></div><div class="div-txt">AUTHENTICATE</div><div class="div-line"></div></div>', unsafe_allow_html=True)

        uname = st.text_input("Username", placeholder="Enter username",   label_visibility="collapsed", key="li_user")
        pword = st.text_input("Password", type="password", placeholder="Enter password ••••••••", label_visibility="collapsed", key="li_pass")
        st.checkbox("Keep me signed in")

        if st.button("Sign In  →", use_container_width=True, key="li_btn"):
            if not uname:
                st.error("⚠️ Username required")
            elif not pword:
                st.error("⚠️ Password required")
            else:
                udata = USERS_DB.get(uname)
                if udata and udata["hash"] == _h(pword):
                    actual = udata["role"]
                    if actual != sel:
                        record_login(uname, sel, False)
                        st.error(f"❌ This account does not have `{rm['label']}` access.")
                    else:
                        st.session_state.logged_in    = True
                        st.session_state.current_user = uname
                        st.session_state.current_role = actual
                        st.session_state.session_id   = str(uuid.uuid4())[:8].upper()
                        st.session_state.login_time   = datetime.datetime.now()
                        record_login(uname, actual, True)
                        log_event("info", f"Session start | user={uname} | role={actual} | sid={st.session_state.session_id}", "AUTH")
                        st.rerun()
                else:
                    record_login(uname, sel, False)
                    st.error("❌ Invalid credentials. Access denied.")

        st.markdown('<div class="pulsebar"><div class="pdot"></div><span class="ptxt">ALL SYSTEMS OPERATIONAL</span></div>', unsafe_allow_html=True)

        st.markdown("""
        <div style="margin-top:.9rem;padding:.65rem .9rem;background:rgba(45,124,246,.05);
                    border:1px solid rgba(45,124,246,.14);border-radius:8px;
                    font-family:'DM Mono',monospace;font-size:.67rem;color:#3a4a6a;line-height:1.75;">
            <span style="color:#2d7cf6;">Demo credentials:</span><br>
            👑 <span style="color:#d4dff0;">superadmin</span> / <span style="color:#d4dff0;">admin@999</span><br>
            🧑‍💻 <span style="color:#d4dff0;">admin</span> / <span style="color:#d4dff0;">sentinel123</span><br>
            👁️ <span style="color:#d4dff0;">viewer1</span> / <span style="color:#d4dff0;">view2024</span>
        </div>""", unsafe_allow_html=True)
    st.stop()

# ─── Collector ────────────────────────────────────────────────
if not st.session_state.collector_started:
    threading.Thread(target=run_collector, daemon=True).start()
    st.session_state.collector_started = True

# ─── Page config ──────────────────────────────────────────────
st.set_page_config(
    page_title="SentinelOps AI — Enterprise",
    page_icon="🛡️", layout="wide",
    initial_sidebar_state="collapsed"
)
st.markdown(DASH_CSS, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
#  LIVE DATA
# ═══════════════════════════════════════════════════════════════
live       = collect_live()
cpu_temp   = get_cpu_temp()
net_s, net_r = get_net()
proc_count = len(psutil.pids())

health_score = round(max(0, 100-(live['cpu_percent']*.4+live['memory_percent']*.35+live['disk_percent']*.25)), 1)
cpu_c  = gcol(live['cpu_percent'])
mem_c  = gcol(live['memory_percent'])
disk_c = gcol(live['disk_percent'])
temp_c = gcol(cpu_temp,(65,80))
h_c    = hcol(health_score)

# Voice alerts
if live['cpu_percent']>90:     voice_alert("Warning! CPU usage is critical. Immediate action required.","cpu_crit",60);log_event("error",f"CPU CRITICAL {live['cpu_percent']}%","ALERT")
elif live['cpu_percent']>70:   voice_alert("CPU usage is elevated. Please review your system.","cpu_warn",45);log_event("warning",f"CPU WARNING {live['cpu_percent']}%","ALERT")
if live['memory_percent']>85:  voice_alert("Memory usage is critical. Close unused applications.","mem_crit",60);log_event("error",f"MEMORY CRITICAL {live['memory_percent']}%","ALERT")
elif live['memory_percent']>70:voice_alert("Memory usage is high.","mem_warn",45);log_event("warning",f"MEMORY WARNING {live['memory_percent']}%","ALERT")
if cpu_temp>80:                voice_alert("Warning! CPU temperature is dangerously high. Check your cooling system.","temp_crit",60);log_event("error",f"CPU TEMP CRITICAL {cpu_temp}°C","ALERT")

# ═══════════════════════════════════════════════════════════════
#  NAVIGATION BAR
# ═══════════════════════════════════════════════════════════════
cur_user   = st.session_state.current_user or "unknown"
cur_role   = st.session_state.current_role or "viewer"
rm         = ROLES.get(cur_role, ROLES["viewer"])
uinfo      = USERS_DB.get(cur_user, {})
full_name  = uinfo.get("name", cur_user)
dept       = uinfo.get("dept", "—")
sid        = st.session_state.session_id or "——"
ltime      = st.session_state.login_time
sdur       = f"{int((datetime.datetime.now()-ltime).total_seconds()//60)}m" if ltime else "—"

n1, n2, n3 = st.columns([2,3,2])
with n1:
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:10px;">
        <span style="font-size:1.5rem;">🛡️</span>
        <div>
            <div style="font-family:'Syne',sans-serif;font-size:1.25rem;font-weight:800;
                        background:linear-gradient(90deg,#00c4ff,#2d7cf6);
                        -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                        letter-spacing:-.02em;line-height:1.1;">SentinelOps AI</div>
            <div style="font-family:'DM Mono',monospace;font-size:.6rem;color:#1e3a5f;
                        letter-spacing:.14em;">ENTERPRISE v{APP_VERSION}</div>
        </div>
    </div>""", unsafe_allow_html=True)

with n2:
    pills_html = '<div style="display:flex;gap:5px;align-items:center;justify-content:center;flex-wrap:wrap;">'
    for ic, txt, col, bg in [
        ("⏱","UPTIME "+get_uptime(),"#10d98a","#0a1e14"),
        ("🔗","SID "+sid,"#2d7cf6","#0a1428"),
        ("⏰","SESSION "+sdur,"#f5c542","#1e1500"),
        ("🔒",rm["label"].upper(),rm["color"],rm["badge_bg"]),
    ]:
        pills_html += (f'<span style="background:{bg};border:1px solid {col}40;border-radius:20px;'
                       f'padding:2.5px 9px;font-family:\'DM Mono\',monospace;font-size:.62rem;'
                       f'color:{col};letter-spacing:.07em;">{ic} {txt}</span>')
    pills_html += "</div>"
    st.markdown(pills_html, unsafe_allow_html=True)

with n3:
    st.markdown(
        f'<div style="text-align:right;margin-bottom:3px;">'
        f'<span style="font-family:\'DM Mono\',monospace;font-size:.7rem;color:{rm["color"]};">'
        f'{rm["icon"]} {full_name}</span>'
        f'<span style="font-family:\'DM Mono\',monospace;font-size:.62rem;color:#3a4a6a;margin-left:6px;">'
        f'[{dept}]</span></div>', unsafe_allow_html=True)
    nb1, nb2 = st.columns(2)
    with nb1:
        if has_perm("admin_panel"):
            if st.button("👑 Admin Panel", use_container_width=True, key="toggle_admin"):
                st.session_state.show_admin_panel = not st.session_state.show_admin_panel
                st.rerun()
    with nb2:
        if st.button("🚪 Sign Out", use_container_width=True, key="signout"):
            log_event("info", f"Sign out | user={cur_user} | sid={sid}", "AUTH")
            for k,v in _defaults.items():
                st.session_state[k] = v
            st.rerun()

st.markdown('<div style="height:1px;background:linear-gradient(90deg,transparent,#1c2640,#243050,#1c2640,transparent);margin:.4rem 0 1.1rem;"></div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ═══════════════════════════════════════════════════════════════
if st.session_state.show_admin_panel and has_perm("admin_panel"):
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#100e1e,#180e20);border:1px solid #ff4d6d40;
                border-radius:14px;padding:.9rem 1.5rem;margin-bottom:1.2rem;display:flex;align-items:center;gap:12px;">
        <span style="font-size:1.2rem;">👑</span>
        <div>
            <div style="font-family:'Syne',sans-serif;font-size:.95rem;font-weight:700;color:#ff4d6d;">
                ADMINISTRATOR PANEL</div>
            <div style="font-family:'DM Mono',monospace;font-size:.62rem;color:#4a2a35;letter-spacing:.09em;">
                RESTRICTED · {full_name.upper()} · SESSION {sid}</div>
        </div>
    </div>""", unsafe_allow_html=True)

    at1, at2, at3, at4 = st.tabs(["📋 System Logs", "🔐 Auth History", "🖥️ Infrastructure", "👥 Users"])

    with at1:
        st.markdown("#### 📋 Log Viewer")
        fc1,fc2,fc3,fc4,fc5 = st.columns([2,1.6,1,1,1])
        with fc1: flvl = st.selectbox("Level",    ["ALL","INFO","WARNING","ERROR"],        key="lf_l")
        with fc2: fcat = st.selectbox("Category", ["ALL","AUTH","ALERT","SYSTEM","ADMIN"], key="lf_c")
        with fc3:
            st.markdown("<div style='margin-top:27px;'></div>", unsafe_allow_html=True)
            if st.button("↺ Refresh", use_container_width=True): st.rerun()
        with fc4:
            st.markdown("<div style='margin-top:27px;'></div>", unsafe_allow_html=True)
            if st.button("🗑 Clear",   use_container_width=True): clear_logs(); st.success("Cleared.")
        with fc5:
            raw = read_logs()
            st.markdown("<div style='margin-top:27px;'></div>", unsafe_allow_html=True)
            st.download_button("⬇ Export", data="\n".join(raw),
                               file_name=f"sentinel_{datetime.date.today()}.txt", mime="text/plain")

        filtered = read_logs(flvl if flvl!="ALL" else None, fcat if fcat!="ALL" else None)
        st.markdown(f'<div style="font-family:\'DM Mono\',monospace;font-size:.66rem;color:#3a4a6a;margin-bottom:5px;">{len(filtered)} entries found</div>', unsafe_allow_html=True)
        lhtml = ""
        for line in reversed(filtered[-80:]):
            if "| ERROR" in line:    c="#ff4d6d"
            elif "| WARNING" in line:c="#f5c542"
            else:                    c="#3a4a6a"
            safe = line.replace("<","&lt;").replace(">","&gt;")
            lhtml += (f'<div style="background:#0e1421;border-left:2px solid {c};border-radius:4px;'
                      f'padding:3px 8px;margin-bottom:2px;font-family:\'DM Mono\',monospace;'
                      f'font-size:.7rem;color:{c};white-space:pre-wrap;">{safe}</div>')
        st.markdown(
            f'<div style="max-height:380px;overflow-y:auto;padding:3px;">'
            f'{lhtml or "<div style=\'color:#3a4a6a;padding:1rem;font-family:DM Mono,monospace;font-size:.76rem;\'>No entries.</div>"}'
            f'</div>', unsafe_allow_html=True)

    with at2:
        st.markdown("#### 🔐 Authentication Log")
        if st.session_state.login_history:
            ldf = pd.DataFrame(st.session_state.login_history)
            total   = len(ldf)
            success = ldf["status"].str.contains("SUCCESS").sum()
            failed  = total - success
            sc1,sc2,sc3 = st.columns(3)
            for col, lbl, val, col_hex in [
                (sc1,"Total Attempts",total,"#2d7cf6"),
                (sc2,"Successful",success,"#10d98a"),
                (sc3,"Failed",failed,"#ff4d6d"),
            ]:
                col.markdown(f"""
                <div style="background:#0e1421;border:1px solid #1c2640;border-radius:10px;
                            padding:.85rem;text-align:center;border-top:2px solid {col_hex};">
                    <div style="font-family:'DM Mono',monospace;font-size:.62rem;color:#3a4a6a;text-transform:uppercase;">{lbl}</div>
                    <div style="font-family:'Syne',sans-serif;font-size:1.5rem;font-weight:700;color:{col_hex};">{val}</div>
                </div>""", unsafe_allow_html=True)
            st.markdown("<div style='margin-top:.9rem;'></div>", unsafe_allow_html=True)
            st.dataframe(ldf.iloc[::-1], use_container_width=True, hide_index=True, height=280)
        else:
            st.info("No authentication events yet.")

    with at3:
        st.markdown("#### 🖥️ Infrastructure Details")
        vm = psutil.virtual_memory()
        du = psutil.disk_usage("/")
        freq = psutil.cpu_freq()
        ov = [
            ("OS",           f"{platform.system()} {platform.release()}"),
            ("Architecture", platform.machine()),
            ("Hostname",     platform.node()),
            ("Python",       platform.python_version()),
            ("CPU Physical", str(psutil.cpu_count(logical=False))),
            ("CPU Logical",  str(psutil.cpu_count(logical=True))),
            ("CPU Freq",     f"{round(freq.current/1000,2)} GHz (max {round(freq.max/1000,2)} GHz)" if freq else "N/A"),
            ("RAM Total",    f"{round(vm.total/(1024**3),2)} GB"),
            ("RAM Available",f"{round(vm.available/(1024**3),2)} GB"),
            ("RAM Used %",   f"{vm.percent}%"),
            ("Disk Total",   f"{round(du.total/(1024**3),1)} GB"),
            ("Disk Free",    f"{round(du.free/(1024**3),1)} GB"),
            ("Disk Used %",  f"{du.percent}%"),
            ("System Uptime",get_uptime()),
            ("Processes",    str(proc_count)),
            ("Net Sent",     f"{net_s} MB"),
            ("Net Recv",     f"{net_r} MB"),
        ]
        rows_html = ""
        for k,v in ov:
            rows_html += (f'<tr><td style="color:#3a4a6a;padding:5px 12px;font-size:.74rem;border-bottom:1px solid #141d2e;">{k}</td>'
                          f'<td style="color:#d4dff0;padding:5px 12px;font-size:.74rem;font-weight:500;border-bottom:1px solid #141d2e;">{v}</td></tr>')
        st.markdown(f'<table style="width:100%;border-collapse:collapse;font-family:\'DM Mono\',monospace;background:#0e1421;border:1px solid #1c2640;border-radius:10px;overflow:hidden;">{rows_html}</table>', unsafe_allow_html=True)

        st.markdown("#### ⚙️ Top Processes")
        procs = get_procs(8)
        if procs:
            st.dataframe(pd.DataFrame(procs), use_container_width=True, hide_index=True, height=260)

    with at4:
        st.markdown("#### 👥 Registered Users")
        user_rows = []
        for un, ud in USERS_DB.items():
            r = ud["role"]
            user_rows.append({
                "Username":   un,
                "Full Name":  ud.get("name","—"),
                "Role":       f"{ROLES[r]['icon']} {ROLES[r]['label']}",
                "Department": ud.get("dept","—"),
                "Email":      ud.get("email","—"),
                "Status":     "🟢 Active",
            })
        st.dataframe(pd.DataFrame(user_rows), use_container_width=True, hide_index=True)
        st.markdown("""
        <div style="background:#0e1421;border:1px solid #1c2640;border-radius:8px;
                    padding:.75rem 1.1rem;margin-top:.8rem;font-family:'DM Mono',monospace;
                    font-size:.7rem;color:#3a4a6a;">
            ℹ️ &nbsp;Modify <code style="color:#2d7cf6;">USERS_DB</code> in source to manage users.
            API-based management planned for v3.0.
        </div>""", unsafe_allow_html=True)

    if st.button("✕  Close Admin Panel", key="close_admin"):
        st.session_state.show_admin_panel = False
        st.rerun()

    st.markdown('<div style="height:1px;background:linear-gradient(90deg,transparent,#1c2640,transparent);margin:1.1rem 0;"></div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
#  SYSTEM INFO BAR
# ═══════════════════════════════════════════════════════════════
sib = st.columns(5)
for col, (ic, lbl, val) in zip(sib, [
    ("💻","HOST",    platform.node()),
    ("🧠","RAM",     f"{round(psutil.virtual_memory().total/(1024**3),1)} GB"),
    ("⚙️","CORES",  f"{psutil.cpu_count(logical=False)}P / {psutil.cpu_count(logical=True)}L"),
    ("🖥️","OS",     f"{platform.system()} {platform.release()}"),
    ("⏱️","UPTIME", get_uptime()),
]):
    col.markdown(
        f'<div style="background:#0e1421;border:1px solid #1c2640;border-radius:8px;padding:.48rem .85rem;">'
        f'<div style="font-family:\'DM Mono\',monospace;font-size:.58rem;color:#3a4a6a;letter-spacing:.12em;">{ic} {lbl}</div>'
        f'<div style="font-family:\'DM Mono\',monospace;font-size:.78rem;color:#d4dff0;font-weight:500;">{val}</div></div>',
        unsafe_allow_html=True)

st.markdown("<div style='margin:1.2rem 0;'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
#  LIVE METRICS
# ═══════════════════════════════════════════════════════════════
st.markdown('<div style="font-family:\'Syne\',sans-serif;font-size:1rem;font-weight:700;color:#d4dff0;margin-bottom:.7rem;">📊 Live Metrics</div>', unsafe_allow_html=True)

def mcard(col, lbl, val, unit, color, icon, sub=""):
    col.markdown(f"""
    <div style="background:#0e1421;border:1px solid #1c2640;border-radius:12px;
                padding:.95rem 1.1rem;border-left:3px solid {color};position:relative;overflow:hidden;">
        <div style="position:absolute;top:0;right:0;width:55px;height:55px;
                    background:radial-gradient(circle,{color}16,transparent 70%);
                    border-radius:0 12px 0 55px;"></div>
        <div style="font-family:'DM Mono',monospace;font-size:.6rem;color:#3a4a6a;
                    text-transform:uppercase;letter-spacing:.12em;margin-bottom:3px;">{icon} {lbl}</div>
        <div style="font-family:'Syne',sans-serif;font-size:1.65rem;font-weight:700;
                    color:{color};line-height:1;">{val}<span style="font-size:.8rem;color:#3a4a6a;
                    font-family:'DM Mono',monospace;"> {unit}</span></div>
        {f'<div style="font-family:\'DM Mono\',monospace;font-size:.6rem;color:#3a4a6a;margin-top:1px;">{sub}</div>' if sub else ''}
    </div>""", unsafe_allow_html=True)

mc = st.columns(5)
mcard(mc[0],"CPU Usage",   live['cpu_percent'],   "%",  cpu_c,  "🔲", f"{psutil.cpu_count(logical=True)} threads")
mcard(mc[1],"Memory",      live['memory_percent'],"%",  mem_c,  "🧠", f"{round(psutil.virtual_memory().available/(1024**3),1)} GB free")
mcard(mc[2],"Disk",        live['disk_percent'],  "%",  disk_c, "💾", f"{round(psutil.disk_usage('/').free/(1024**3),1)} GB free")
mcard(mc[3],"CPU Temp",    cpu_temp,              "°C", temp_c, "🌡️", "sensor/simulated")
mcard(mc[4],"Health Score",health_score,          "",   h_c,    "❤️",
      "NORMAL" if health_score>=70 else ("WARNING" if health_score>=50 else "CRITICAL"))

# Alert banners
def abanner(msg, col, bg):
    st.markdown(f'<div style="background:{bg};border:1px solid {col};border-radius:8px;padding:.55rem .95rem;margin-top:5px;font-family:\'DM Mono\',monospace;font-size:.76rem;color:{col};">{msg}</div>', unsafe_allow_html=True)

if cpu_temp>80:             abanner(f"🔴  CPU TEMPERATURE CRITICAL: {cpu_temp}°C — Check cooling immediately!","#ff4d6d","#200a10")
elif cpu_temp>65:           abanner(f"🟡  CPU TEMPERATURE WARNING: {cpu_temp}°C — Improve airflow.","#f5c542","#1e1400")
if live['cpu_percent']>90:   abanner(f"🔴  CPU CRITICAL: {live['cpu_percent']}% — Terminate high-load processes.","#ff4d6d","#200a10")
elif live['cpu_percent']>70: abanner(f"🟡  CPU WARNING: {live['cpu_percent']}% — Review background processes.","#f5c542","#1e1400")
if live['memory_percent']>85: abanner(f"🔴  MEMORY CRITICAL: {live['memory_percent']}% — Free RAM immediately.","#ff4d6d","#200a10")
elif live['memory_percent']>70:abanner(f"🟡  MEMORY WARNING: {live['memory_percent']}% — Monitor memory usage.","#f5c542","#1e1400")
if live['disk_percent']>90:  abanner(f"🔴  DISK CRITICAL: {live['disk_percent']}% — Free disk space now.","#ff4d6d","#200a10")

st.markdown("<div style='margin:1.2rem 0;'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
#  EXTENDED METRICS
# ═══════════════════════════════════════════════════════════════
st.markdown('<div style="font-family:\'Syne\',sans-serif;font-size:1rem;font-weight:700;color:#d4dff0;margin-bottom:.7rem;">🌐 Extended Metrics</div>', unsafe_allow_html=True)
em = st.columns(4)
freq_val = round(psutil.cpu_freq().current/1000, 2) if psutil.cpu_freq() else "N/A"
mcard(em[0],"Net Sent",   net_s,      "MB",  "#a78bfa","📤","since boot")
mcard(em[1],"Net Recv",   net_r,      "MB",  "#34d399","📥","since boot")
mcard(em[2],"Processes",  proc_count, "",    "#f59e0b","⚙️","running now")
mcard(em[3],"CPU Freq",   freq_val,   "GHz", "#60a5fa","⚡","current clock")

st.markdown("<div style='margin:1.2rem 0;'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
#  30-MINUTE GRAPHS
# ═══════════════════════════════════════════════════════════════
rows, using_sim = [], False
if DB_AVAILABLE:
    try: rows = db.fetch_recent_metrics(30)
    except Exception: rows = []
if not rows: rows = gen_sim(30); using_sim = True

df = pd.DataFrame(rows)
if "collected_at" in df.columns:
    df["collected_at"] = pd.to_datetime(df["collected_at"], errors="coerce")
    df = df.dropna(subset=["collected_at"]).sort_values("collected_at")
else:
    df["collected_at"] = pd.Series(dtype="datetime64[ns]")
for cn in ["cpu_percent","memory_percent","disk_percent"]:
    if cn not in df.columns: df[cn]=0
    else: df[cn]=pd.to_numeric(df[cn],errors="coerce").fillna(0)

sim_note = " *(simulated)*" if using_sim else ""
st.markdown(f'<div style="font-family:\'Syne\',sans-serif;font-size:1rem;font-weight:700;color:#d4dff0;margin-bottom:.7rem;">📈 30-Minute Trend{sim_note}</div>', unsafe_allow_html=True)

plt.rcParams.update({
    "figure.facecolor":"#0e1421","axes.facecolor":"#070b14",
    "axes.edgecolor":"#1c2640","axes.labelcolor":"#3a4a6a",
    "xtick.color":"#3a4a6a","ytick.color":"#3a4a6a",
    "grid.color":"#141d2e","text.color":"#d4dff0",
    "font.family":"monospace","font.size":7.5,
})

gc1,gc2,gc3 = st.columns(3)
for gcol_w, (ck, lbl, col) in zip([gc1,gc2,gc3],[
    ("cpu_percent","CPU %","#2d7cf6"),
    ("memory_percent","Memory %","#10d98a"),
    ("disk_percent","Disk %","#f5c542"),
]):
    with gcol_w:
        st.markdown(f'<div style="font-family:\'DM Mono\',monospace;font-size:.62rem;color:#3a4a6a;text-transform:uppercase;letter-spacing:.12em;margin-bottom:3px;">{lbl}</div>', unsafe_allow_html=True)
        fig, ax = plt.subplots(figsize=(4,2.1))
        if not df.empty and len(df)>1:
            ax.fill_between(df["collected_at"],df[ck],alpha=0.11,color=col)
            ax.plot(df["collected_at"],df[ck],color=col,linewidth=1.4,zorder=3)
            ax.scatter(df["collected_at"].iloc[-1],df[ck].iloc[-1],color=col,s=32,zorder=5)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.setp(ax.xaxis.get_majorticklabels(),rotation=28,ha='right')
        else:
            ax.text(.5,.5,"Insufficient data",transform=ax.transAxes,ha='center',va='center',color="#3a4a6a",fontsize=8)
        ax.set_ylim(0,100)
        ax.grid(True,alpha=0.3,linestyle='--',linewidth=.6)
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
        fig.tight_layout(); st.pyplot(fig); plt.close(fig)

st.markdown("<div style='margin:1.2rem 0;'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
#  STATUS CARDS
# ═══════════════════════════════════════════════════════════════
alert_df = pd.DataFrame()
if DB_AVAILABLE:
    try:
        al = db.fetch_recent_alerts(50)
        alert_df = pd.DataFrame(al) if al else pd.DataFrame()
    except Exception: pass

if not alert_df.empty and "severity" in alert_df.columns:
    n_crit = int((alert_df["severity"]=="CRITICAL").sum())
    n_warn = int((alert_df["severity"]=="WARNING").sum())
else:
    n_crit = sum([live['cpu_percent']>90, live['memory_percent']>85, cpu_temp>80, live['disk_percent']>90])
    n_warn = sum([70<live['cpu_percent']<=90, 70<live['memory_percent']<=85, 65<cpu_temp<=80])

hs_lbl = "NORMAL" if health_score>=70 else ("WARNING" if health_score>=50 else "CRITICAL")

st.markdown('<div style="font-family:\'Syne\',sans-serif;font-size:1rem;font-weight:700;color:#d4dff0;margin-bottom:.7rem;">🔔 System Status</div>', unsafe_allow_html=True)
sc1,sc2,sc3 = st.columns(3)

def scard(col, icon, lbl, val, color, sub=""):
    col.markdown(f"""
    <div style="background:#0e1421;border:1px solid #1c2640;border-radius:12px;
                padding:1rem 1.2rem;text-align:center;border-top:2px solid {color};">
        <div style="font-size:1.5rem;margin-bottom:2px;">{icon}</div>
        <div style="font-family:'DM Mono',monospace;font-size:.6rem;color:#3a4a6a;
                    text-transform:uppercase;letter-spacing:.1em;">{lbl}</div>
        <div style="font-family:'Syne',sans-serif;font-size:1.6rem;font-weight:700;
                    color:{color};margin:3px 0;">{val}</div>
        {f'<div style="font-size:.65rem;color:#3a4a6a;font-family:\'DM Mono\',monospace;">{sub}</div>' if sub else ''}
    </div>""", unsafe_allow_html=True)

scard(sc1,"🚨","Critical Alerts",n_crit,"#ff4d6d","active incidents")
scard(sc2,"⚠️","Warnings",       n_warn,"#f5c542","requires attention")
scard(sc3,"❤️","Health Status",  hs_lbl,h_c,      f"score: {health_score}/100")

st.markdown("<div style='margin:1.2rem 0;'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
#  TABLE + TOP PROCESSES
# ═══════════════════════════════════════════════════════════════
tc1, tc2 = st.columns([3,2])
with tc1:
    st.markdown('<div style="font-family:\'Syne\',sans-serif;font-size:1rem;font-weight:700;color:#d4dff0;margin-bottom:.7rem;">🗃️ Raw Data — Last 30 Min</div>', unsafe_allow_html=True)
    tdf = df.copy()
    if "collected_at" in tdf.columns:
        tdf["collected_at"] = pd.to_datetime(tdf["collected_at"],errors="coerce")
    nc = tdf.select_dtypes(include="number").columns
    if len(nc): tdf[nc] = tdf[nc].round(2)
    st.dataframe(tdf, use_container_width=True, height=300, hide_index=True)

with tc2:
    st.markdown('<div style="font-family:\'Syne\',sans-serif;font-size:1rem;font-weight:700;color:#d4dff0;margin-bottom:.7rem;">⚙️ Top Processes by CPU</div>', unsafe_allow_html=True)
    procs = get_procs(8)
    if procs:
        st.dataframe(pd.DataFrame(procs), use_container_width=True, height=300, hide_index=True)
    else:
        st.info("Cannot fetch process list.")

st.markdown("<div style='margin:1.2rem 0;'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
#  RECENT ALERTS
# ═══════════════════════════════════════════════════════════════
st.markdown('<div style="font-family:\'Syne\',sans-serif;font-size:1rem;font-weight:700;color:#d4dff0;margin-bottom:.7rem;">📋 Recent Alerts</div>', unsafe_allow_html=True)

if not alert_df.empty and {"severity","component","message"}.issubset(alert_df.columns):
    for a in alert_df.head(5).to_dict("records"):
        sv = str(a.get("severity","INFO"))
        co = str(a.get("component","unknown"))
        ms = str(a.get("message",""))
        ic, c = ("🔴","#ff4d6d") if sv=="CRITICAL" else (("🟡","#f5c542") if sv=="WARNING" else ("🔵","#2d7cf6"))
        st.markdown(f"""
        <div style="background:#0e1421;border:1px solid #1c2640;border-left:3px solid {c};
                    border-radius:8px;padding:.6rem .95rem;margin-bottom:3px;
                    font-family:'DM Mono',monospace;font-size:.76rem;color:#d4dff0;">
            {ic} &nbsp;<span style="color:{c};font-weight:600;">[{sv}]</span>
            &nbsp;<span style="color:#3a4a6a;">{co}</span>&nbsp;→&nbsp;{ms}
        </div>""", unsafe_allow_html=True)
else:
    st.markdown("""
    <div style="background:#0a1e14;border:1px solid #10d98a40;border-radius:8px;
                padding:.65rem .95rem;font-family:'DM Mono',monospace;font-size:.76rem;color:#10d98a;">
        ✅ &nbsp;No active alerts — all systems nominal.
    </div>""", unsafe_allow_html=True)

st.markdown("<div style='margin:1.2rem 0;'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
#  AI ASSISTANT
# ═══════════════════════════════════════════════════════════════
st.markdown('<div style="font-family:\'Syne\',sans-serif;font-size:1rem;font-weight:700;color:#d4dff0;margin-bottom:.5rem;">🤖 AI Diagnostic Assistant</div>', unsafe_allow_html=True)
st.markdown("""
<div style="background:linear-gradient(135deg,#0e1421,#0c1828);border:1px solid #1c2640;
            border-radius:10px;padding:.65rem 1rem;margin-bottom:.8rem;">
    <span style="font-family:'DM Mono',monospace;font-size:.7rem;color:#3a4a6a;">
        💡 Try: <span style="color:#2d7cf6;">cpu</span> · <span style="color:#10d98a;">memory</span> ·
        <span style="color:#f5c542;">disk</span> · <span style="color:#ff4d6d;">temperature</span> ·
        <span style="color:#a78bfa;">network</span> · <span style="color:#34d399;">processes</span> ·
        <span style="color:#60a5fa;">health</span> · <span style="color:#f59e0b;">alerts</span> ·
        <span style="color:#d4dff0;">slow</span>
    </span>
</div>""", unsafe_allow_html=True)

qb = st.columns(5)
for col, (btn_lbl, q_text) in zip(qb, [
    ("🔲 CPU",       "cpu analysis"),
    ("🧠 Memory",    "memory analysis"),
    ("❤️ Health",    "system health overview"),
    ("🌡️ Temp",     "cpu temperature"),
    ("⚙️ Processes", "top processes"),
]):
    with col:
        if st.button(btn_lbl, use_container_width=True, key=f"qb_{btn_lbl}"):
            r = ai_response(q_text, live)
            st.session_state.chat_history.append((btn_lbl, r))
            log_event("info", f"AI quick: {q_text}", "AI")

ai_c1, ai_c2 = st.columns([5,1])
with ai_c1:
    uq = st.text_input("Query…", placeholder="e.g. Why is my system slow? / Analyse memory / Show network stats",
                        key="ai_q", label_visibility="collapsed")
with ai_c2:
    send = st.button("Send →", use_container_width=True, key="ai_send")

if send and uq.strip():
    r = ai_response(uq, live)
    st.session_state.chat_history.append((uq, r))
    log_event("info", f"AI query: {uq}", "AI")

if st.session_state.chat_history:
    st.markdown("<div style='margin-top:.5rem;'></div>", unsafe_allow_html=True)
    for q, r in reversed(st.session_state.chat_history[-6:]):
        st.markdown(f'<div style="background:#070b14;border:1px solid #1c2640;border-radius:7px;padding:.42rem .85rem;margin-bottom:3px;font-family:\'DM Mono\',monospace;font-size:.72rem;color:#2d7cf6;">👤 {q}</div>', unsafe_allow_html=True)
        st.markdown(r)
        st.markdown('<div style="height:1px;background:#1c2640;margin:5px 0;"></div>', unsafe_allow_html=True)
    if st.button("🗑 Clear Chat", key="clr_chat"):
        st.session_state.chat_history = []
        st.rerun()

st.markdown("<div style='margin:2rem 0 .5rem;'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
#  FOOTER
# ═══════════════════════════════════════════════════════════════
ff1, ff2, ff3 = st.columns([1,3,2])
with ff1:
    if st.button("↺ Refresh", use_container_width=True): st.rerun()
with ff2:
    st.markdown(f'<div style="padding-top:9px;font-family:\'DM Mono\',monospace;font-size:.63rem;color:#1c2640;">{COMPANY_NAME} · Enterprise v{APP_VERSION} · © {BUILD_YEAR} · Python · psutil · Streamlit</div>', unsafe_allow_html=True)
with ff3:
    st.markdown(f'<div style="padding-top:9px;text-align:right;font-family:\'DM Mono\',monospace;font-size:.63rem;color:#1c2640;">🕐 {datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")} &nbsp;·&nbsp; {rm["icon"]} {full_name}</div>', unsafe_allow_html=True)