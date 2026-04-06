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
import json
import os
import logging
import smtplib
import hashlib
import csv
from io import StringIO, BytesIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    import db
    import metrics
    DB_AVAILABLE = True
    METRICS_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False
    METRICS_AVAILABLE = False

LOG_FILE = "sentinelops.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger("SentinelOps")

def log_event(level, component, message):
    entry = {"timestamp": datetime.datetime.now().isoformat(), "level": level, "component": component, "message": message}
    if "log_entries" not in st.session_state:
        st.session_state.log_entries = []
    st.session_state.log_entries.insert(0, entry)
    if len(st.session_state.log_entries) > 500:
        st.session_state.log_entries = st.session_state.log_entries[:500]
    if level == "ERROR": logger.error(f"[{component}] {message}")
    elif level == "WARNING": logger.warning(f"[{component}] {message}")
    else: logger.info(f"[{component}] {message}")

def record_login(username, role, success, ip="N/A"):
    entry = {"timestamp": datetime.datetime.now().isoformat(), "username": username, "role": role, "success": success, "ip": ip}
    if "login_history" not in st.session_state:
        st.session_state.login_history = []
    st.session_state.login_history.insert(0, entry)
    if len(st.session_state.login_history) > 200:
        st.session_state.login_history = st.session_state.login_history[:200]

def record_alert(severity, component, message):
    entry = {"timestamp": datetime.datetime.now().isoformat(), "severity": severity, "component": component, "message": message}
    if "alert_history" not in st.session_state:
        st.session_state.alert_history = []
    st.session_state.alert_history.insert(0, entry)
    if len(st.session_state.alert_history) > 200:
        st.session_state.alert_history = st.session_state.alert_history[:200]

DEFAULT_SYSTEMS = [
    {"id": "local", "name": "localhost", "host": "127.0.0.1", "port": 22, "status": "online", "tags": ["primary", "prod"]},
]

def get_systems():
    if "registered_systems" not in st.session_state:
        st.session_state.registered_systems = DEFAULT_SYSTEMS.copy()
    return st.session_state.registered_systems

ADMIN_CONFIG_FILE = "admin_config.json"

def load_admin_config():
    defaults = {
        "users": {
            "admin": {"password_hash": hashlib.sha256("sentinel123".encode()).hexdigest(), "role": "admin"},
            "viewer": {"password_hash": hashlib.sha256("view123".encode()).hexdigest(), "role": "viewer"},
        },
        "alert_thresholds": {"cpu": 80, "memory": 85, "disk": 90, "cpu_temp": 80},
        "email_config": {"enabled": False, "smtp_server": "", "smtp_port": 587, "sender": "", "password": "", "recipients": []},
        "auto_refresh_interval": 30,
        "retention_days": 7,
        "voice_alerts": True,
    }
    if os.path.exists(ADMIN_CONFIG_FILE):
        try:
            with open(ADMIN_CONFIG_FILE) as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception:
            pass
    return defaults

def save_admin_config(config):
    with open(ADMIN_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

admin_config = load_admin_config()

def get_cpu_temperature():
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for key in ["coretemp", "cpu_thermal", "k10temp", "acpitz", "cpu-thermal"]:
                if key in temps and temps[key]:
                    readings = [t.current for t in temps[key] if t.current > 0]
                    if readings:
                        return round(sum(readings) / len(readings), 1)
            for key, entries in temps.items():
                if entries:
                    readings = [t.current for t in entries if t.current > 0]
                    if readings:
                        return round(sum(readings) / len(readings), 1)
    except Exception:
        pass
    cpu_pct = psutil.cpu_percent(interval=0.1)
    base_temp = 45.0
    load_contrib = cpu_pct * 0.42
    noise = random.uniform(-2.5, 2.5)
    simulated = base_temp + load_contrib + noise
    return round(min(max(simulated, 30.0), 105.0), 1)

def run_collector():
    while True:
        try:
            if DB_AVAILABLE and METRICS_AVAILABLE:
                data = metrics.collect()
                db.insert_metric(data)
        except Exception:
            pass
        time.sleep(5)

def analyze_root_cause(cpu, memory, disk, history_df=None):
    causes = []
    recommendations = []
    severity = "NORMAL"
    if cpu > 90:
        severity = "CRITICAL"
        causes.append(("🔥 CPU Saturation", f"CPU at {cpu}% — system overloaded"))
        recommendations.append("Kill high-CPU processes: `ps aux --sort=-%cpu | head -10`")
        recommendations.append("Check for runaway threads or infinite loops")
    elif cpu > 80:
        severity = "WARNING"
        causes.append(("⚡ High CPU Load", f"CPU at {cpu}% — approaching saturation"))
        recommendations.append("Monitor with `top` or `htop` for spike patterns")
    if memory > 90:
        severity = "CRITICAL"
        causes.append(("💥 Memory Pressure", f"RAM at {memory}% — possible OOM risk"))
        recommendations.append("Check swap usage: `free -h`")
        recommendations.append("Identify memory hogs: `ps aux --sort=-%mem | head -10`")
    elif memory > 85:
        if severity != "CRITICAL": severity = "WARNING"
        causes.append(("🧠 Memory Stress", f"RAM at {memory}% — investigate leaks"))
        recommendations.append("Restart memory-hungry services if safe")
    if disk > 95:
        severity = "CRITICAL"
        causes.append(("💾 Disk Full", f"Disk at {disk}% — I/O may fail soon"))
        recommendations.append("Clean logs: `journalctl --vacuum-size=500M`")
        recommendations.append("Find large files: `du -sh /* | sort -h | tail -20`")
    elif disk > 90:
        causes.append(("📀 Disk Warning", f"Disk at {disk}% — plan cleanup"))
    if history_df is not None and len(history_df) > 5:
        cpu_trend = history_df["cpu_percent"].tail(5).diff().mean()
        if cpu_trend > 5:
            causes.append(("📈 CPU Spike Trend", f"CPU rising +{cpu_trend:.1f}%/interval — investigate"))
            recommendations.append("Check cron jobs or scheduled tasks firing")
    if not causes:
        causes.append(("✅ All Systems Normal", "No anomalies detected"))
        recommendations.append("System is healthy — continue monitoring")
    return {"severity": severity, "causes": causes, "recommendations": recommendations}

def send_email_alert(subject, body, config):
    if not config.get("enabled"):
        return False, "Email alerts disabled"
    try:
        msg = MIMEMultipart()
        msg["From"] = config["sender"]
        msg["To"] = ", ".join(config["recipients"])
        msg["Subject"] = f"[SentinelOps] {subject}"
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
            server.starttls()
            server.login(config["sender"], config["password"])
            server.send_message(msg)
        log_event("INFO", "EmailAlert", f"Alert sent: {subject}")
        return True, "Sent"
    except Exception as e:
        log_event("ERROR", "EmailAlert", str(e))
        return False, str(e)

def get_ai_response(question, metrics_context):
    q = question.lower()
    cpu = metrics_context.get("cpu_percent", 0)
    mem = metrics_context.get("memory_percent", 0)
    disk = metrics_context.get("disk_percent", 0)
    health = metrics_context.get("health_score", 100)
    temp = metrics_context.get("cpu_temp", 0)
    responses = []
    if any(w in q for w in ["cpu", "processor", "compute"]):
        if cpu > 90:
            responses.append(f"🔥 **CPU CRITICAL at {cpu}%!**\n\n**Severity:** CRITICAL\n\n**Root Cause:** System is overloaded.\n\n**Solutions:**\n- Run `ps aux --sort=-%cpu | head -15`\n- Kill non-essential processes\n- Consider horizontal scaling")
        elif cpu > 80:
            responses.append(f"⚠️ **CPU HIGH at {cpu}%**\n\n**Severity:** WARNING\n\n**Solutions:**\n- Monitor with `htop`\n- Check scheduled jobs (`crontab -l`)")
        else:
            responses.append(f"✅ **CPU Normal at {cpu}%**\n\nNo action needed.")
    if any(w in q for w in ["temp", "temperature", "thermal", "heat", "hot"]):
        temp_thresh = admin_config.get("alert_thresholds", {}).get("cpu_temp", 80)
        if temp > temp_thresh:
            responses.append(f"🌡️ **CPU TEMPERATURE CRITICAL at {temp}°C!**\n\n**Solutions:**\n- Check CPU cooler\n- Clean dust from heatsink\n- Improve case airflow")
        else:
            responses.append(f"✅ **CPU Temperature Normal at {temp}°C**")
    if any(w in q for w in ["memory", "ram", "mem"]):
        if mem > 90:
            responses.append(f"🔥 **MEMORY CRITICAL at {mem}%!**\n\n**Solutions:**\n- Check swap: `free -h`\n- Find hogs: `ps aux --sort=-%mem | head -10`")
        elif mem > 85:
            responses.append(f"⚠️ **Memory HIGH at {mem}%**\n\n**Solutions:**\n- Investigate memory leaks\n- Restart heavy services")
        else:
            responses.append(f"✅ **Memory Normal at {mem}%**")
    if any(w in q for w in ["disk", "storage", "space"]):
        if disk > 95:
            responses.append(f"🚨 **DISK CRITICAL at {disk}%!**\n\n**Solutions:**\n- Find large files: `du -sh /* | sort -rh | head -20`\n- Clear logs: `journalctl --vacuum-time=2d`")
        else:
            responses.append(f"✅ **Disk Normal at {disk}%**")
    if any(w in q for w in ["health", "status", "overall", "summary"]):
        responses.append(f"{'💚' if health >= 70 else '🟡' if health >= 50 else '🔴'} **System Health: {health}/100**\n\n- CPU: {cpu}%\n- Memory: {mem}%\n- Disk: {disk}%\n- CPU Temp: {temp}°C")
    if any(w in q for w in ["why", "reason", "cause", "issue", "problem"]):
        rca = analyze_root_cause(cpu, mem, disk)
        cause_list = "\n".join([f"- **{c[0]}**: {c[1]}" for c in rca["causes"]])
        rec_list = "\n".join([f"- {r}" for r in rca["recommendations"]])
        responses.append(f"🔍 **Root Cause Analysis:**\n\n**Severity:** {rca['severity']}\n\n**Issues:**\n{cause_list}\n\n**Recommendations:**\n{rec_list}")
    if any(w in q for w in ["process", "top", "pid"]):
        try:
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try: procs.append(p.info)
                except: pass
            procs = sorted(procs, key=lambda x: x.get('cpu_percent', 0), reverse=True)[:5]
            proc_lines = "\n".join([f"- PID {p['pid']}: **{p['name']}** — CPU: {p['cpu_percent']:.1f}%, MEM: {p['memory_percent']:.1f}%" for p in procs])
            responses.append(f"🔍 **Top Processes by CPU:**\n\n{proc_lines}")
        except: responses.append("⚠️ Unable to retrieve process list.")
    if not responses:
        temp_thresh = admin_config.get("alert_thresholds", {}).get("cpu_temp", 80)
        responses.append(f"🤖 **Live Snapshot:**\n\n| Metric | Value | Status |\n|--------|-------|--------|\n| CPU | {cpu}% | {'🔴' if cpu > 80 else '✅'} |\n| Memory | {mem}% | {'🔴' if mem > 85 else '✅'} |\n| Disk | {disk}% | {'🔴' if disk > 90 else '✅'} |\n| CPU Temp | {temp}°C | {'🔴' if temp > temp_thresh else '✅'} |\n| Health | {health}/100 | {'🔴' if health < 50 else '🟡' if health < 70 else '💚'} |\n\nAsk about: **cpu**, **memory**, **disk**, **temperature**, **health**, **processes**")
    return "\n\n".join(responses)

def generate_pdf_report(cpu, memory, disk, health_score, health_color_name, alerts_list, log_entries, cpu_temp=0):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []
    title_style = ParagraphStyle('CustomTitle', parent=styles['Title'], fontSize=24, textColor=colors.HexColor('#1a1a2e'), spaceAfter=6, fontName='Helvetica-Bold', alignment=TA_CENTER)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#555555'), spaceAfter=20, alignment=TA_CENTER)
    section_style = ParagraphStyle('Section', parent=styles['Heading2'], fontSize=13, textColor=colors.HexColor('#0a3d62'), spaceBefore=16, spaceAfter=8, fontName='Helvetica-Bold')
    normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#333333'), spaceAfter=4, leading=14)
    now = datetime.datetime.now()
    story.append(Paragraph("SentinelOps", title_style))
    story.append(Paragraph("Enterprise System Health Report", subtitle_style))
    story.append(Paragraph(f"Generated: {now.strftime('%B %d, %Y at %H:%M:%S')}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#0a3d62')))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph("Executive Summary", section_style))
    health_label = "HEALTHY" if health_score >= 70 else ("WARNING" if health_score >= 50 else "CRITICAL")
    temp_thresh = admin_config.get("alert_thresholds", {}).get("cpu_temp", 80)
    summary_data = [
        ["Metric", "Value", "Status", "Threshold"],
        ["CPU Usage", f"{cpu}%", "NORMAL" if cpu < 80 else ("WARNING" if cpu < 90 else "CRITICAL"), f"{admin_config['alert_thresholds']['cpu']}%"],
        ["Memory Usage", f"{memory}%", "NORMAL" if memory < 85 else ("WARNING" if memory < 90 else "CRITICAL"), f"{admin_config['alert_thresholds']['memory']}%"],
        ["Disk Usage", f"{disk}%", "NORMAL" if disk < 90 else ("WARNING" if disk < 95 else "CRITICAL"), f"{admin_config['alert_thresholds']['disk']}%"],
        ["CPU Temperature", f"{cpu_temp}°C", "NORMAL" if cpu_temp < temp_thresh else "CRITICAL", f"{temp_thresh}°C"],
        ["Health Score", f"{health_score}/100", health_label, ">=70"],
    ]
    table = Table(summary_data, colWidths=[4*cm, 3*cm, 3.5*cm, 3.5*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,0), colors.HexColor('#0a3d62')),
        ('TEXTCOLOR', (0,0),(-1,0), colors.white),
        ('FONTNAME', (0,0),(-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0),(-1,-1), 'CENTER'),
        ('GRID', (0,0),(-1,-1), 0.5, colors.HexColor('#dee2e6')),
        ('FONTSIZE', (0,0),(-1,-1), 9),
        ('TOPPADDING', (0,0),(-1,-1), 8),
        ('BOTTOMPADDING', (0,0),(-1,-1), 8),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("Recent System Logs (Last 10 Entries)", section_style))
    if log_entries:
        log_data = [["Timestamp", "Level", "Component", "Message"]]
        for e in log_entries[:10]:
            log_data.append([e.get("timestamp","")[:16].replace("T"," "), e.get("level",""), e.get("component",""), e.get("message","")[:55]])
        log_table = Table(log_data, colWidths=[3.5*cm, 2.2*cm, 2.5*cm, 5.8*cm])
        log_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0),(-1,0), colors.HexColor('#1a3a5c')),
            ('TEXTCOLOR', (0,0),(-1,0), colors.white),
            ('FONTNAME', (0,0),(-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0),(-1,-1), 8),
            ('GRID', (0,0),(-1,-1), 0.5, colors.HexColor('#dee2e6')),
            ('TOPPADDING', (0,0),(-1,-1), 5),
            ('BOTTOMPADDING', (0,0),(-1,-1), 5),
        ]))
        story.append(log_table)
    else:
        story.append(Paragraph("No log entries available.", normal_style))
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cccccc')))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(f"SentinelOps Enterprise Health Engine v2.0  ·  {now.strftime('%Y-%m-%d %H:%M:%S')}  ·  CONFIDENTIAL", ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#aaaaaa'), alignment=TA_CENTER)))
    doc.build(story)
    buffer.seek(0)
    return buffer.read()

def inject_voice_alert(message, severity="WARNING"):
    if not admin_config.get("voice_alerts", True):
        return
    voice_js = f"""
    <script>
    (function() {{
        if ('speechSynthesis' in window) {{
            window.speechSynthesis.cancel();
            const msg = new SpeechSynthesisUtterance("{message}");
            msg.rate = 0.9;
            msg.pitch = {'0.8' if severity == 'CRITICAL' else '1.0'};
            msg.volume = 1;
            function speak() {{
                const voices = window.speechSynthesis.getVoices();
                const eng = voices.find(v => v.lang.startsWith('en'));
                if (eng) msg.voice = eng;
                window.speechSynthesis.speak(msg);
            }}
            if (window.speechSynthesis.getVoices().length > 0) {{ speak(); }}
            else {{ window.speechSynthesis.addEventListener('voiceschanged', speak, {{ once: true }}); }}
        }}
    }})();
    </script>
    """
    st.components.v1.html(voice_js, height=0)

def generate_simulated_rows(n=30):
    now = datetime.datetime.now()
    rows = []
    base_cpu = random.uniform(20, 50)
    base_mem = random.uniform(40, 65)
    base_disk = random.uniform(30, 55)
    for i in range(n):
        t = now - datetime.timedelta(minutes=(n - i))
        cpu  = max(0, min(100, base_cpu  + 10 * math.sin(i/5) + random.gauss(0,3)))
        mem  = max(0, min(100, base_mem  +  5 * math.sin(i/8) + random.gauss(0,2)))
        disk = max(0, min(100, base_disk +  2 * math.sin(i/12) + random.gauss(0,1)))
        rows.append({"collected_at": t, "cpu_percent": round(cpu,2), "memory_percent": round(mem,2), "disk_percent": round(disk,2)})
    return rows

def collect_live_metrics():
    if METRICS_AVAILABLE:
        try: return metrics.collect()
        except: pass
    return {"cpu_percent": psutil.cpu_percent(interval=0.5), "memory_percent": psutil.virtual_memory().percent, "disk_percent": psutil.disk_usage("/").percent}

def get_color(value, thresholds=(60, 80)):
    if value < thresholds[0]: return "#3fb950"
    elif value < thresholds[1]: return "#e3b341"
    else: return "#f85149"

def get_health_color(score):
    if score >= 70: return "#3fb950"
    elif score >= 50: return "#e3b341"
    else: return "#f85149"

def get_temp_color(temp, threshold=80):
    if temp < threshold - 20: return "#3fb950"
    elif temp < threshold: return "#e3b341"
    else: return "#f85149"

# ══════════════════════════════════════════════════════════
#  SESSION STATE INITIALIZATION
# ══════════════════════════════════════════════════════════
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None

# ══════════════════════════════════════════════════════════
#  LOGIN PAGE  ——  ONLY USER LOGIN ON FRONT PAGE
#  Admin can click "Admin Login" link to get their own page
# ══════════════════════════════════════════════════════════
if not st.session_state.logged_in:

    # ── Shared background styles ──
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
    .stApp { background:#020818 !important; font-family:'Poppins',sans-serif; }
    .orb1{position:fixed;width:500px;height:500px;border-radius:50%;background:rgba(6,182,212,0.12);filter:blur(100px);top:-150px;left:-150px;animation:o1 8s ease-in-out infinite alternate;z-index:0;}
    .orb2{position:fixed;width:400px;height:400px;border-radius:50%;background:rgba(59,130,246,0.1);filter:blur(90px);bottom:-100px;right:-100px;animation:o2 6s ease-in-out infinite alternate;z-index:0;}
    .orb3{position:fixed;width:250px;height:250px;border-radius:50%;background:rgba(14,165,233,0.08);filter:blur(80px);top:40%;right:20%;animation:o3 7s ease-in-out infinite alternate;z-index:0;}
    @keyframes o1{to{transform:translate(50px,40px) scale(1.1);}}
    @keyframes o2{to{transform:translate(-40px,30px) scale(1.1);}}
    @keyframes o3{to{transform:translateY(-50px) scale(1.2);}}
    .bg-grid{position:fixed;inset:0;background-image:linear-gradient(rgba(6,182,212,0.04) 1px,transparent 1px),linear-gradient(90deg,rgba(59,130,246,0.03) 1px,transparent 1px);background-size:50px 50px;z-index:0;}
    .scan-line{position:fixed;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(6,182,212,0.5),transparent);animation:scanAnim 6s ease-in-out infinite;z-index:1;}
    @keyframes scanAnim{0%{top:0;opacity:0;}5%{opacity:1;}95%{opacity:0.8;}100%{top:100%;opacity:0;}}
    .login-card{position:relative;z-index:10;width:100%;max-width:420px;margin:0 auto;background:rgba(2,15,35,0.85);border:1px solid rgba(6,182,212,0.2);border-radius:24px;padding:2.8rem 2.4rem;backdrop-filter:blur(20px);animation:cardIn 0.8s cubic-bezier(0.16,1,0.3,1) both,borderPulse 4s ease-in-out 1s infinite alternate;}
    @keyframes cardIn{from{opacity:0;transform:translateY(30px) scale(0.97);}to{opacity:1;transform:translateY(0) scale(1);}}
    @keyframes borderPulse{from{border-color:rgba(6,182,212,0.15);}to{border-color:rgba(6,182,212,0.5);box-shadow:0 0 40px rgba(6,182,212,0.08);}}
    .logo-ring{width:68px;height:68px;border-radius:50%;border:1px solid rgba(6,182,212,0.35);background:linear-gradient(135deg,rgba(6,182,212,0.15),rgba(59,130,246,0.1));display:flex;align-items:center;justify-content:center;font-size:28px;margin:0 auto 1rem;position:relative;animation:logoSpin 0.9s cubic-bezier(0.16,1,0.3,1) 0.3s both;}
    @keyframes logoSpin{from{opacity:0;transform:scale(0.4) rotate(-180deg);}to{opacity:1;transform:scale(1) rotate(0);}}
    .logo-ring::before{content:'';position:absolute;inset:-5px;border-radius:50%;border:1.5px solid transparent;border-top-color:#06b6d4;border-right-color:#3b82f6;animation:ringRot 3s linear infinite;}
    .logo-ring::after{content:'';position:absolute;inset:-10px;border-radius:50%;border:1px solid transparent;border-bottom-color:rgba(6,182,212,0.3);animation:ringRot 5s linear infinite reverse;}
    @keyframes ringRot{to{transform:rotate(360deg);}}
    .app-title{font-size:26px;font-weight:700;background:linear-gradient(90deg,#38bdf8,#06b6d4,#60a5fa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:-0.02em;text-align:center;margin-bottom:4px;}
    .app-sub{font-size:11px;color:#0e7490;font-family:'JetBrains Mono',monospace;letter-spacing:0.12em;text-align:center;margin-bottom:1.5rem;}
    .welcome-txt h3{font-size:18px;font-weight:600;color:#e0f2fe;text-align:center;margin-bottom:4px;}
    .welcome-txt p{font-size:12px;color:#0e7490;text-align:center;margin-bottom:1.5rem;}
    .creds-hint{background:rgba(6,182,212,0.06);border:1px solid rgba(6,182,212,0.15);border-radius:10px;padding:10px 14px;margin-top:10px;font-family:'JetBrains Mono',monospace;font-size:10px;color:#0e7490;text-align:center;}
    .status-bar{display:flex;align-items:center;justify-content:center;gap:8px;margin-top:1.2rem;}
    .status-dot{width:6px;height:6px;border-radius:50%;background:#06b6d4;display:inline-block;animation:blink2 1.5s ease-in-out infinite;}
    @keyframes blink2{0%,100%{opacity:1;}50%{opacity:0.2;}}
    .status-bar span{font-size:11px;color:#164e63;font-family:'JetBrains Mono',monospace;letter-spacing:0.08em;}
    .admin-link-bar{text-align:center;margin-top:1.2rem;font-family:'JetBrains Mono',monospace;font-size:11px;color:#164e63;}
    .admin-card{position:relative;z-index:10;width:100%;max-width:420px;margin:0 auto;background:rgba(2,15,35,0.90);border:1px solid rgba(250,204,21,0.25);border-radius:24px;padding:2.8rem 2.4rem;backdrop-filter:blur(20px);animation:cardIn 0.8s cubic-bezier(0.16,1,0.3,1) both,adminPulse 4s ease-in-out 1s infinite alternate;}
    @keyframes adminPulse{from{border-color:rgba(250,204,21,0.15);}to{border-color:rgba(250,204,21,0.5);box-shadow:0 0 40px rgba(250,204,21,0.06);}}
    </style>
    <div class="orb1"></div><div class="orb2"></div><div class="orb3"></div>
    <div class="bg-grid"></div>
    <div class="scan-line"></div>
    """, unsafe_allow_html=True)

    # Use session state to switch between user login and admin login views
    if "show_admin_login" not in st.session_state:
        st.session_state.show_admin_login = False

    # ── USER LOGIN (default front page) ──
    if not st.session_state.show_admin_login:
        st.markdown("""
        <div class="login-card">
            <div class="logo-ring">🛡️</div>
            <div class="app-title">SentinelOps</div>
            <div class="app-sub">ENTERPRISE HEALTH ENGINE v2.0</div>
            <div class="welcome-txt">
                <h3>Welcome Back</h3>
                <p>Sign in to access your dashboard</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3 = st.columns([1.2, 1, 1.2])
        with c2:
            username = st.text_input("👤  Username", placeholder="viewer", key="user_uname")
            password = st.text_input("🔒  Password", type="password", placeholder="••••••••", key="user_pass")

            if st.button("Sign In →", use_container_width=True, key="user_login_btn"):
                if not username:
                    st.error("⚠ Please enter your username")
                elif not password:
                    st.error("⚠ Please enter your password")
                else:
                    users = admin_config.get("users", {})
                    ph = hashlib.sha256(password.encode()).hexdigest()
                    if username in users and users[username]["password_hash"] == ph:
                        role = users[username]["role"]
                        st.session_state.logged_in = True
                        st.session_state.current_user = username
                        st.session_state.user_role = role
                        record_login(username, role, True)
                        log_event("INFO", "Auth", f"User '{username}' logged in (role: {role})")
                        st.rerun()
                    else:
                        record_login(username, "unknown", False)
                        log_event("WARNING", "Auth", f"Failed login attempt for '{username}'")
                        st.error("❌ Invalid username or password")

            st.markdown("""
            <div class="creds-hint">viewer / view123 &nbsp;·&nbsp; admin / sentinel123</div>
            <div class="status-bar">
                <div class="status-dot"></div>
                <span>ALL SYSTEMS OPERATIONAL</span>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

            # Admin login link button
            if st.button("👑  Admin Login", use_container_width=True, key="goto_admin"):
                st.session_state.show_admin_login = True
                st.rerun()

    # ── ADMIN LOGIN PAGE ──
    else:
        st.markdown("""
        <div class="admin-card">
            <div class="logo-ring" style="border-color:rgba(250,204,21,0.4);background:linear-gradient(135deg,rgba(250,204,21,0.12),rgba(245,158,11,0.08));">👑</div>
            <div class="app-title" style="background:linear-gradient(90deg,#fbbf24,#f59e0b,#fcd34d);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">Admin Portal</div>
            <div class="app-sub" style="color:#92400e;">RESTRICTED ACCESS · ADMIN ONLY</div>
            <div class="welcome-txt">
                <h3 style="color:#fef3c7;">Administrator Sign In</h3>
                <p style="color:#92400e;">Full system control · Logs · Configuration</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3 = st.columns([1.2, 1, 1.2])
        with c2:
            admin_uname = st.text_input("👑  Admin Username", placeholder="admin", key="admin_uname")
            admin_pass  = st.text_input("🔐  Admin Password", type="password", placeholder="••••••••", key="admin_pass")

            if st.button("Admin Login →", use_container_width=True, key="admin_login_btn"):
                if not admin_uname:
                    st.error("⚠ Please enter admin username")
                elif not admin_pass:
                    st.error("⚠ Please enter admin password")
                else:
                    users = admin_config.get("users", {})
                    ph = hashlib.sha256(admin_pass.encode()).hexdigest()
                    if admin_uname in users and users[admin_uname]["password_hash"] == ph:
                        role = users[admin_uname]["role"]
                        if role != "admin":
                            st.error("❌ This portal is for administrators only.")
                            record_login(admin_uname, role, False)
                        else:
                            st.session_state.logged_in = True
                            st.session_state.current_user = admin_uname
                            st.session_state.user_role = role
                            st.session_state.show_admin_login = False
                            record_login(admin_uname, role, True)
                            log_event("INFO", "Auth", f"Admin '{admin_uname}' logged in")
                            st.rerun()
                    else:
                        record_login(admin_uname, "unknown", False)
                        log_event("WARNING", "Auth", f"Failed admin login for '{admin_uname}'")
                        st.error("❌ Invalid administrator credentials")

            st.markdown("""
            <div class="creds-hint" style="border-color:rgba(250,204,21,0.2);color:#92400e;">admin / sentinel123</div>
            <div class="status-bar"><div class="status-dot" style="background:#fbbf24;"></div>
            <span style="color:#78350f;">ADMIN PORTAL · HIGH SECURITY</span></div>
            """, unsafe_allow_html=True)

            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
            if st.button("← Back to User Login", use_container_width=True, key="back_to_user"):
                st.session_state.show_admin_login = False
                st.rerun()

    st.stop()

# ─────────────────────────────
# BACKGROUND COLLECTOR
# ─────────────────────────────
if "collector_started" not in st.session_state:
    t = threading.Thread(target=run_collector, daemon=True)
    t.start()
    st.session_state.collector_started = True

# ─────────────────────────────
# PAGE CONFIG
# ─────────────────────────────
st.set_page_config(page_title="SentinelOps Dashboard", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@300;400;500;600;700&display=swap');
    .stApp { background-color: #0d1117; color: #e6edf3; font-family: 'Inter', sans-serif; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; padding-left: 2.5rem; padding-right: 2.5rem; max-width: 100%; }
    hr { border: none; border-top: 1px solid #21262d; margin: 1.2rem 0; }
    h2, h3 { color: #e6edf3 !important; font-family: 'Inter', sans-serif !important; font-weight: 600 !important; }
    .stButton > button { background: #21262d; color: #58a6ff; border: 1px solid #30363d; border-radius: 8px; padding: 0.45rem 1.2rem; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; font-weight: 600; transition: all 0.2s ease; letter-spacing: 0.04em; }
    .stButton > button:hover { background: #30363d; border-color: #58a6ff; color: #79c0ff; }
    .stTabs [data-baseweb="tab-list"] { background: #161b22; border-radius: 10px; padding: 4px; gap: 4px; border: 1px solid #21262d; }
    .stTabs [data-baseweb="tab"] { color: #8b949e; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; letter-spacing: 0.06em; padding: 6px 14px; border-radius: 7px; }
    .stTabs [aria-selected="true"] { background: #21262d !important; color: #58a6ff !important; }
    .stTextInput input, .stTextArea textarea { background: #161b22 !important; border: 1px solid #30363d !important; color: #e6edf3 !important; border-radius: 8px !important; font-family: 'JetBrains Mono', monospace !important; }
    .stAlert { border-radius: 10px !important; font-family: 'JetBrains Mono', monospace !important; }
    .chat-bubble-user { background: #1c2a3d; border: 1px solid #1f4068; border-radius: 12px 12px 4px 12px; padding: 10px 14px; margin: 6px 0; font-size: 0.85rem; color: #79c0ff; }
    .chat-bubble-ai { background: #161b22; border: 1px solid #21262d; border-left: 3px solid #3fb950; border-radius: 12px 12px 12px 4px; padding: 10px 14px; margin: 6px 0; font-size: 0.85rem; color: #e6edf3; }
    @keyframes alertPulse{0%,100%{opacity:1;}50%{opacity:0.7;}}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────
# COLLECT LIVE METRICS
# ─────────────────────────────
data = collect_live_metrics()
cpu_temp = get_cpu_temperature()
temp_threshold = admin_config.get("alert_thresholds", {}).get("cpu_temp", 80)
health_score = round(100 - (data['cpu_percent']*0.4 + data['memory_percent']*0.35 + data['disk_percent']*0.25), 1)
cpu_color    = get_color(data['cpu_percent'])
mem_color    = get_color(data['memory_percent'])
disk_color   = get_color(data['disk_percent'])
health_color = get_health_color(health_score)
temp_color   = get_temp_color(cpu_temp, temp_threshold)

# ─────────────────────────────
# AUTO ALERT CHECK
# ─────────────────────────────
thresholds = admin_config.get("alert_thresholds", {"cpu": 80, "memory": 85, "disk": 90, "cpu_temp": 80})
if "last_alert_time" not in st.session_state:
    st.session_state.last_alert_time = {}
now_ts = time.time()
alerts_triggered = []
for metric, key, threshold in [("CPU","cpu_percent",thresholds["cpu"]),("Memory","memory_percent",thresholds["memory"]),("Disk","disk_percent",thresholds["disk"])]:
    if data[key] > threshold:
        last_t = st.session_state.last_alert_time.get(metric, 0)
        if now_ts - last_t > 60:
            sev = "CRITICAL" if data[key] > threshold + 10 else "WARNING"
            msg = f"{metric} at {data[key]}% — threshold {threshold}%"
            alerts_triggered.append((sev, metric, msg))
            st.session_state.last_alert_time[metric] = now_ts
            log_event(sev, metric, msg)
            record_alert(sev, metric, msg)
if cpu_temp > temp_threshold:
    last_temp_t = st.session_state.last_alert_time.get("CPUTemp", 0)
    if now_ts - last_temp_t > 60:
        sev = "CRITICAL" if cpu_temp > temp_threshold + 10 else "WARNING"
        temp_msg = f"CPU Temperature at {cpu_temp}°C — threshold {temp_threshold}°C"
        alerts_triggered.append((sev, "CPU Temperature", temp_msg))
        st.session_state.last_alert_time["CPUTemp"] = now_ts
        log_event(sev, "CPUTemp", temp_msg)
        record_alert(sev, "CPUTemp", temp_msg)

# ─────────────────────────────
# HEADER
# ─────────────────────────────
col_logo, col_status = st.columns([3, 1])
with col_logo:
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">
        <span style="font-size:1.8rem;">🛡️</span>
        <div>
            <h1 style="margin:0;font-family:'Inter',sans-serif;font-weight:700;font-size:1.7rem;color:#e6edf3;letter-spacing:-0.02em;">SentinelOps</h1>
            <p style="margin:0;color:#8b949e;font-size:0.75rem;font-family:'JetBrains Mono',monospace;letter-spacing:0.05em;">ENTERPRISE HEALTH ENGINE · Logged in as <span style="color:#58a6ff;">{st.session_state.current_user}</span> <span style="color:#3fb950;">[{st.session_state.user_role.upper()}]</span></p>
        </div>
    </div>
    """, unsafe_allow_html=True)
with col_status:
    db_badge = '<span style="display:inline-block;padding:2px 10px;border-radius:20px;font-size:0.7rem;font-family:\'JetBrains Mono\',monospace;font-weight:600;letter-spacing:0.05em;background:#1a2d1e;color:#3fb950;border:1px solid #3fb950;">● LIVE DB</span>' if DB_AVAILABLE else '<span style="display:inline-block;padding:2px 10px;border-radius:20px;font-size:0.7rem;font-family:\'JetBrains Mono\',monospace;font-weight:600;letter-spacing:0.05em;background:#2d1a1a;color:#e3b341;border:1px solid #e3b341;">⚡ SIMULATED</span>'
    st.markdown(f'<div style="text-align:right;padding-top:8px;margin-bottom:6px;">{db_badge}</div>', unsafe_allow_html=True)
    if st.button("🚪 Logout", use_container_width=True):
        log_event("INFO", "Auth", f"User '{st.session_state.current_user}' logged out")
        for key in ["logged_in","current_user","user_role","show_admin_login"]:
            if key in st.session_state: del st.session_state[key]
        st.rerun()

st.markdown("---")

# ─────────────────────────────
# ALERT BANNER
# ─────────────────────────────
if alerts_triggered:
    for sev, comp, msg in alerts_triggered:
        color = "#f85149" if sev == "CRITICAL" else "#e3b341"
        icon = "🚨" if sev == "CRITICAL" else "⚠️"
        st.markdown(f'<div style="background:rgba(248,81,73,0.08);border:1px solid {color};border-left:4px solid {color};border-radius:10px;padding:0.7rem 1.2rem;margin-bottom:8px;font-family:\'JetBrains Mono\',monospace;font-size:0.82rem;color:{color};animation:alertPulse 2s ease-in-out infinite;">{icon} <strong>[{sev}]</strong> {comp}: {msg}</div>', unsafe_allow_html=True)
    if admin_config.get("voice_alerts") and alerts_triggered:
        temp_alert = next((a for a in alerts_triggered if "Temperature" in a[1]), None)
        if temp_alert: inject_voice_alert("Warning! Your CPU temperature is high.", temp_alert[0])
        else:
            top = alerts_triggered[0]
            inject_voice_alert(f"Alert: {top[1]}. {top[2]}", top[0])

if cpu_temp > temp_threshold:
    st.markdown(f'<div style="background:rgba(248,81,73,0.12);border:1px solid #f85149;border-left:4px solid #f85149;border-radius:10px;padding:0.7rem 1.2rem;margin-bottom:8px;font-family:\'JetBrains Mono\',monospace;font-size:0.82rem;color:#f85149;animation:alertPulse 1.5s ease-in-out infinite;">🌡️ <strong>[THERMAL ALERT]</strong> CPU Temperature: <strong>{cpu_temp}°C</strong> — Exceeds threshold of {temp_threshold}°C!</div>', unsafe_allow_html=True)

# ─────────────────────────────
# SYSTEM INFO BAR
# ─────────────────────────────
col1, col2, col3, col4 = st.columns(4)
info_style = "background:#161b22;border:1px solid #21262d;border-radius:10px;padding:0.55rem 1rem;font-family:'JetBrains Mono',monospace;font-size:0.78rem;color:#8b949e;"
col1.markdown(f'<div style="{info_style}">💻 &nbsp;<span style="color:#e6edf3;">{platform.node()}</span></div>', unsafe_allow_html=True)
col2.markdown(f'<div style="{info_style}">🧠 &nbsp;<span style="color:#e6edf3;">{round(psutil.virtual_memory().total/(1024**3),1)} GB RAM</span></div>', unsafe_allow_html=True)
col3.markdown(f'<div style="{info_style}">⚙️ &nbsp;<span style="color:#e6edf3;">{psutil.cpu_count(logical=False)} CPU Cores</span></div>', unsafe_allow_html=True)
col4.markdown(f'<div style="{info_style}">🌡️ &nbsp;<span style="color:{temp_color};">{cpu_temp}°C CPU Temp</span></div>', unsafe_allow_html=True)
st.markdown("<div style='margin:1.2rem 0;'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
#  ROLE-BASED TABS
#  Admin gets all tabs including Admin Panel — NO re-auth gate
# ══════════════════════════════════════════════════════════
is_admin = st.session_state.user_role == "admin"

if is_admin:
    tab_dashboard, tab_rca, tab_ai, tab_report, tab_logs, tab_multisys, tab_admin = st.tabs([
        "📊  Dashboard", "🔍  Root Cause", "🤖  AI Assistant", "📄  PDF Report",
        "🗒️  Logs", "🌐  Multi-System", "👑  Admin Panel",
    ])
else:
    tab_dashboard, tab_rca, tab_ai, tab_report = st.tabs([
        "📊  Dashboard", "🔍  Root Cause", "🤖  AI Assistant", "📄  PDF Report",
    ])

# ══════════════════════════════════════════════════════════
#  TAB 1: DASHBOARD
# ══════════════════════════════════════════════════════════
with tab_dashboard:
    st.markdown("### 📊 Live Metrics")
    m1, m2, m3, m4, m5 = st.columns(5)

    def metric_card(col, label, value, unit, color, icon):
        col.markdown(f"""
        <div style="background:#161b22;border:1px solid #21262d;border-radius:14px;padding:1.2rem 1.4rem;border-left:4px solid {color};">
            <div style="font-family:'JetBrains Mono',monospace;font-size:0.68rem;color:#8b949e;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">{icon} &nbsp;{label}</div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:2rem;font-weight:700;color:{color};">{value}<span style="font-size:1rem;color:#8b949e;">{unit}</span></div>
        </div>
        """, unsafe_allow_html=True)

    metric_card(m1, "CPU Usage",    data['cpu_percent'],    "%",  cpu_color,    "🔲")
    metric_card(m2, "Memory",       data['memory_percent'], "%",  mem_color,    "🧠")
    metric_card(m3, "Disk",         data['disk_percent'],   "%",  disk_color,   "💾")
    metric_card(m4, "CPU Temp",     cpu_temp,               "°C", temp_color,   "🌡️")
    metric_card(m5, "Health Score", health_score,           "",   health_color, "❤️")

    st.markdown("<div style='margin:1.5rem 0;'></div>", unsafe_allow_html=True)

    rows = []
    using_simulated = False
    if DB_AVAILABLE:
        try: rows = db.fetch_recent_metrics(30)
        except: rows = []
    if not rows:
        rows = generate_simulated_rows(30)
        using_simulated = True

    df = pd.DataFrame(rows)
    if "collected_at" in df.columns:
        df["collected_at"] = pd.to_datetime(df["collected_at"], errors="coerce")
        df = df.dropna(subset=["collected_at"]).sort_values("collected_at")
    else:
        df["collected_at"] = pd.Series(dtype="datetime64[ns]")
    for c in ["cpu_percent","memory_percent","disk_percent"]:
        if c not in df.columns: df[c] = 0
        else: df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    sim_label = " *(simulated)*" if using_simulated else ""
    st.markdown(f"### 📈 System Usage — Last 30 Minutes{sim_label}")

    plt.rcParams.update({"figure.facecolor":"#161b22","axes.facecolor":"#0d1117","axes.edgecolor":"#30363d","axes.labelcolor":"#8b949e","xtick.color":"#8b949e","ytick.color":"#8b949e","grid.color":"#21262d","text.color":"#e6edf3","font.family":"monospace","font.size":8})

    g1, g2, g3 = st.columns(3)
    for gcol, (col_key, label, color) in zip([g1,g2,g3],[("cpu_percent","CPU %","#58a6ff"),("memory_percent","Memory %","#3fb950"),("disk_percent","Disk %","#e3b341")]):
        with gcol:
            st.markdown(f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.72rem;color:#8b949e;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">{label}</div>', unsafe_allow_html=True)
            fig, ax = plt.subplots(figsize=(4, 2.2))
            if not df.empty and len(df) > 1:
                ax.fill_between(df["collected_at"], df[col_key], alpha=0.15, color=color)
                ax.plot(df["collected_at"], df[col_key], color=color, linewidth=1.5, zorder=3)
                ax.scatter(df["collected_at"].iloc[-1], df[col_key].iloc[-1], color=color, s=40, zorder=4)
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
                ax.xaxis.set_major_locator(mdates.AutoDateLocator())
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
            else:
                ax.text(0.5, 0.5, "Not enough data", transform=ax.transAxes, ha='center', va='center', color="#8b949e")
            ax.set_ylim(0, 100)
            ax.grid(True, alpha=0.4, linestyle='--')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)

    st.markdown("<div style='margin:1.5rem 0;'></div>", unsafe_allow_html=True)
    st.markdown("### 🔍 Top Processes")
    try:
        proc_list = []
        for p in psutil.process_iter(['pid','name','cpu_percent','memory_percent','status']):
            try: proc_list.append(p.info)
            except: pass
        proc_df = pd.DataFrame(proc_list).sort_values("cpu_percent", ascending=False).head(10)
        proc_df = proc_df[['pid','name','cpu_percent','memory_percent','status']].round(2)
        proc_df.columns = ['PID','Process','CPU %','MEM %','Status']
        st.dataframe(proc_df, use_container_width=True, height=280, hide_index=True)
    except: st.info("Process list unavailable in this environment.")

    st.markdown("<div style='margin:1.5rem 0;'></div>", unsafe_allow_html=True)
    st.markdown("### 🔔 System Status")
    critical = len([a for a in st.session_state.get("alert_history",[]) if a.get("severity")=="CRITICAL"])
    warning  = len([a for a in st.session_state.get("alert_history",[]) if a.get("severity")=="WARNING"])
    hs_label, hs_color = ("NORMAL","#3fb950") if health_score >= 70 else (("WARNING","#e3b341") if health_score >= 50 else ("CRITICAL","#f85149"))
    c1, c2, c3 = st.columns(3)
    def status_card(col, icon, label, value, color, sub=""):
        sub_html = f'<div style="font-size:0.75rem;color:#8b949e;">{sub}</div>' if sub else ""
        col.markdown(f'<div style="background:#161b22;border:1px solid #21262d;border-radius:14px;padding:1.2rem 1.4rem;text-align:center;border-top:3px solid {color};"><div style="font-size:1.8rem;margin-bottom:4px;">{icon}</div><div style="font-family:\'JetBrains Mono\',monospace;font-size:0.68rem;color:#8b949e;text-transform:uppercase;letter-spacing:0.1em;">{label}</div><div style="font-family:\'JetBrains Mono\',monospace;font-size:1.8rem;font-weight:700;color:{color};margin:4px 0;">{value}</div>{sub_html}</div>', unsafe_allow_html=True)
    status_card(c1, "🚨", "Critical Alerts", critical, "#f85149", "session alerts")
    status_card(c2, "⚠️", "Warnings",        warning,  "#e3b341", "session alerts")
    status_card(c3, "❤️", "Health Status",   hs_label, hs_color,  f"score: {health_score}")

    st.markdown("<div style='margin:1.5rem 0;'></div>", unsafe_allow_html=True)
    st.markdown("### 🗃️ Raw Data — Last 30 Minutes")
    table_df = df.copy()
    numeric_cols = table_df.select_dtypes(include="number").columns
    if len(numeric_cols) > 0: table_df[numeric_cols] = table_df[numeric_cols].round(2)
    st.dataframe(table_df, use_container_width=True, height=350, hide_index=True)

    st.markdown("<div style='margin:1.5rem 0;'></div>", unsafe_allow_html=True)
    fcol1, fcol2 = st.columns([1, 5])
    with fcol1:
        if st.button("🔄 Refresh"): st.rerun()
    with fcol2:
        st.markdown('<div style="padding-top:10px;font-family:\'JetBrains Mono\',monospace;font-size:0.72rem;color:#30363d;">SentinelOps v2.0 · Python · Streamlit</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
#  TAB 2: ROOT CAUSE ANALYSIS
# ══════════════════════════════════════════════════════════
with tab_rca:
    st.markdown("### 🔍 Root Cause Analysis Engine")
    rca_col1, rca_col2 = st.columns([1, 1])
    with rca_col1:
        st.markdown("#### 🎛️ Manual Override")
        rca_cpu  = st.slider("CPU %",    0, 100, int(data['cpu_percent']))
        rca_mem  = st.slider("Memory %", 0, 100, int(data['memory_percent']))
        rca_disk = st.slider("Disk %",   0, 100, int(data['disk_percent']))
        run_rca = st.button("🔍 Run Analysis", use_container_width=True)
    with rca_col2:
        st.markdown("#### 📡 Live Snapshot")
        for label, val, color in [("CPU",data['cpu_percent'],cpu_color),("Memory",data['memory_percent'],mem_color),("Disk",data['disk_percent'],disk_color),(f"CPU Temp",f"{cpu_temp}°C",temp_color),("Health",health_score,health_color)]:
            suffix = "%" if label not in ["CPU Temp","Health"] else ""
            st.markdown(f'<div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:8px 14px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;"><span style="font-family:\'JetBrains Mono\',monospace;font-size:0.8rem;color:#8b949e;">{label}</span><span style="font-family:\'JetBrains Mono\',monospace;font-size:1rem;font-weight:700;color:{color};">{val}{suffix}</span></div>', unsafe_allow_html=True)

    use_cpu  = rca_cpu  if run_rca else data['cpu_percent']
    use_mem  = rca_mem  if run_rca else data['memory_percent']
    use_disk = rca_disk if run_rca else data['disk_percent']

    st.markdown("---")
    rca_result = analyze_root_cause(use_cpu, use_mem, use_disk, df if 'df' in dir() else None)
    sev = rca_result["severity"]
    sev_color = {"NORMAL":"#3fb950","WARNING":"#e3b341","CRITICAL":"#f85149"}.get(sev,"#8b949e")
    st.markdown(f'<div style="background:rgba(22,27,34,0.8);border:1px solid {sev_color};border-radius:14px;padding:1.4rem 1.8rem;margin-bottom:1rem;"><div style="font-family:\'JetBrains Mono\',monospace;font-size:0.72rem;color:#8b949e;text-transform:uppercase;letter-spacing:0.12em;margin-bottom:8px;">OVERALL SEVERITY</div><div style="font-family:\'JetBrains Mono\',monospace;font-size:2rem;font-weight:700;color:{sev_color};">{sev}</div></div>', unsafe_allow_html=True)
    if cpu_temp > temp_threshold:
        st.markdown(f'<div style="background:#161b22;border:1px solid #21262d;border-left:4px solid #f85149;border-radius:8px;padding:10px 14px;margin-bottom:6px;font-family:\'JetBrains Mono\',monospace;font-size:0.82rem;color:#e6edf3;"><strong>🌡️ CPU Thermal Issue</strong> &nbsp;·&nbsp; <span style="color:#8b949e;">CPU at {cpu_temp}°C — exceeds {temp_threshold}°C threshold.</span></div>', unsafe_allow_html=True)
    st.markdown("#### 🧩 Detected Issues")
    for title, desc in rca_result["causes"]:
        st.markdown(f'<div style="background:#161b22;border:1px solid #21262d;border-left:4px solid {sev_color};border-radius:8px;padding:10px 14px;margin-bottom:6px;font-family:\'JetBrains Mono\',monospace;font-size:0.82rem;color:#e6edf3;"><strong>{title}</strong> &nbsp;·&nbsp; <span style="color:#8b949e;">{desc}</span></div>', unsafe_allow_html=True)
    st.markdown("#### 💡 Recommendations")
    for i, rec in enumerate(rca_result["recommendations"], 1):
        st.markdown(f'<div style="background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:8px 14px;margin-bottom:6px;font-family:\'JetBrains Mono\',monospace;font-size:0.8rem;color:#79c0ff;"><span style="color:#3fb950;">{i}.</span> {rec}</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
#  TAB 3: AI ASSISTANT
# ══════════════════════════════════════════════════════════
with tab_ai:
    st.markdown("### 🤖 SentinelOps AI Assistant")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
        st.session_state.chat_history.append({"role":"ai","message":f"👋 **SentinelOps AI online.**\n\nCurrent snapshot:\n- CPU: **{data['cpu_percent']}%** | Memory: **{data['memory_percent']}%** | Disk: **{data['disk_percent']}%**\n- CPU Temp: **{cpu_temp}°C** | Health: **{health_score}/100**\n\nAsk me anything about your system!"})
    for msg in st.session_state.chat_history:
        if msg["role"] == "user": st.markdown(f'<div class="chat-bubble-user">👤 {msg["message"]}</div>', unsafe_allow_html=True)
        else: st.markdown(f'<div class="chat-bubble-ai">🤖 {msg["message"]}</div>', unsafe_allow_html=True)
    st.markdown("<div style='margin:1rem 0;'></div>", unsafe_allow_html=True)
    qp1, qp2, qp3, qp4, qp5, qp6 = st.columns(6)
    for col, (label, prompt) in zip([qp1,qp2,qp3,qp4,qp5,qp6],[("🔥 CPU","Analyze CPU"),("🧠 Memory","Analyze Memory"),("🌡️ Temp","CPU Temperature"),("❤️ Health","System Health"),("🔍 Root Cause","Why are there issues?"),("⚙️ Processes","Show top processes")]):
        if col.button(label, use_container_width=True):
            st.session_state.chat_history.append({"role":"user","message":prompt})
            ctx = {**data,"health_score":health_score,"cpu_temp":cpu_temp}
            st.session_state.chat_history.append({"role":"ai","message":get_ai_response(prompt,ctx)})
            st.rerun()
    ai_input = st.text_input("💬 Ask the AI...", placeholder="e.g. Analyze CPU · CPU Temperature · System Health", key="ai_input_box")
    send_col, clear_col = st.columns([4, 1])
    with send_col:
        if st.button("Send →", use_container_width=True) and ai_input:
            st.session_state.chat_history.append({"role":"user","message":ai_input})
            ctx = {**data,"health_score":health_score,"cpu_temp":cpu_temp}
            st.session_state.chat_history.append({"role":"ai","message":get_ai_response(ai_input,ctx)})
            st.rerun()
    with clear_col:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()

# ══════════════════════════════════════════════════════════
#  TAB 4: PDF REPORT
# ══════════════════════════════════════════════════════════
with tab_report:
    st.markdown("### 📄 PDF System Health Report")
    hs_label_r = "HEALTHY" if health_score >= 70 else ("WARNING" if health_score >= 50 else "CRITICAL")
    hs_col_r = "#3fb950" if health_score >= 70 else ("#e3b341" if health_score >= 50 else "#f85149")
    r1, r2 = st.columns([1, 1])
    with r1:
        st.markdown(f'<div style="background:#161b22;border:1px solid #21262d;border-radius:14px;padding:1.4rem 1.6rem;border-left:4px solid #58a6ff;"><div style="font-family:\'JetBrains Mono\',monospace;font-size:0.7rem;color:#8b949e;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">📋 REPORT CONTENTS</div><div style="font-family:\'JetBrains Mono\',monospace;font-size:0.82rem;color:#e6edf3;line-height:1.8;">✅ &nbsp;CPU, Memory, Disk metrics<br>✅ &nbsp;CPU Temperature status<br>✅ &nbsp;Health score & status<br>✅ &nbsp;System information<br>✅ &nbsp;Recent system logs</div></div>', unsafe_allow_html=True)
    with r2:
        cpu_val = data['cpu_percent']
        mem_val = data['memory_percent']
        disk_val = data['disk_percent']
        st.markdown(f'''<div style="background:#161b22;border:1px solid #21262d;border-radius:14px;padding:1.4rem 1.6rem;border-left:4px solid {hs_col_r};">
<div style="font-family:'JetBrains Mono',monospace;font-size:0.7rem;color:#8b949e;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">📊 CURRENT SNAPSHOT</div>
<div style="font-family:'JetBrains Mono',monospace;font-size:0.85rem;color:#e6edf3;line-height:2;">
🔲 &nbsp;CPU: <span style="color:{cpu_color};font-weight:700;">{cpu_val}%</span><br>
🧠 &nbsp;Memory: <span style="color:{mem_color};font-weight:700;">{mem_val}%</span><br>
💾 &nbsp;Disk: <span style="color:{disk_color};font-weight:700;">{disk_val}%</span><br>
🌡️ &nbsp;CPU Temp: <span style="color:{temp_color};font-weight:700;">{cpu_temp}°C</span><br>
❤️ &nbsp;Health: <span style="color:{hs_col_r};font-weight:700;">{health_score}/100 — {hs_label_r}</span>
</div></div>''', unsafe_allow_html=True)
    st.markdown("<div style='margin:1rem 0;'></div>", unsafe_allow_html=True)
    if not REPORTLAB_AVAILABLE:
        st.warning("⚠️ `reportlab` not installed. Run: `pip install reportlab`")
    else:
        if st.button("📥 Generate & Download PDF Report", use_container_width=True):
            with st.spinner("Generating PDF report..."):
                try:
                    pdf_bytes = generate_pdf_report(cpu=data['cpu_percent'],memory=data['memory_percent'],disk=data['disk_percent'],health_score=health_score,health_color_name=hs_label_r,alerts_list=st.session_state.get("alert_history",[]),log_entries=st.session_state.get("log_entries",[]),cpu_temp=cpu_temp)
                    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    st.success("✅ Report generated!")
                    st.download_button(label="📄 Download PDF Report", data=pdf_bytes, file_name=f"sentinelops_report_{now_str}.pdf", mime="application/pdf", use_container_width=True)
                except Exception as e:
                    st.error(f"❌ Failed: {e}")

# ══════════════════════════════════════════════════════════
#  TAB 5: LOGS (ADMIN ONLY)
# ══════════════════════════════════════════════════════════
if is_admin:
    with tab_logs:
        st.markdown("### 🗒️ System Logs")
        log_col1, log_col2, log_col3 = st.columns([2, 1, 1])
        with log_col1: log_filter = st.selectbox("Filter by Level", ["ALL","INFO","WARNING","ERROR","CRITICAL"])
        with log_col2: log_component = st.selectbox("Component", ["ALL","Auth","CPU","Memory","Disk","CPUTemp","EmailAlert","RCA","AI","Report","MultiSys","Admin","System","Metrics"])
        with log_col3:
            st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
            if st.button("🔄 Refresh Logs", use_container_width=True): st.rerun()

        entries = st.session_state.get("log_entries", [])
        if not entries:
            log_event("INFO","System","SentinelOps v2.0 started")
            log_event("INFO","Auth",f"Session: {st.session_state.current_user}")
            log_event("INFO","Metrics",f"CPU={data['cpu_percent']}%, MEM={data['memory_percent']}%, DISK={data['disk_percent']}%, TEMP={cpu_temp}°C")
            entries = st.session_state.get("log_entries", [])

        filtered = entries
        if log_filter != "ALL": filtered = [e for e in filtered if e.get("level")==log_filter]
        if log_component != "ALL": filtered = [e for e in filtered if e.get("component")==log_component]

        total = len(entries)
        errors = sum(1 for e in entries if e.get("level")=="ERROR")
        warns  = sum(1 for e in entries if e.get("level")=="WARNING")
        infos  = sum(1 for e in entries if e.get("level")=="INFO")
        ls1,ls2,ls3,ls4 = st.columns(4)
        for col,val,label,color in [(ls1,total,"Total","#8b949e"),(ls2,infos,"Info","#58a6ff"),(ls3,warns,"Warnings","#e3b341"),(ls4,errors,"Errors","#f85149")]:
            col.markdown(f'<div style="background:#161b22;border:1px solid #21262d;border-top:2px solid {color};border-radius:8px;padding:8px 12px;text-align:center;"><div style="font-family:\'JetBrains Mono\',monospace;font-size:1.3rem;font-weight:700;color:{color};">{val}</div><div style="font-family:\'JetBrains Mono\',monospace;font-size:0.68rem;color:#8b949e;text-transform:uppercase;letter-spacing:0.08em;">{label}</div></div>', unsafe_allow_html=True)

        st.markdown("<div style='margin:1rem 0;'></div>", unsafe_allow_html=True)
        if filtered:
            log_html = '<div style="background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:1rem;max-height:450px;overflow-y:auto;font-family:\'JetBrains Mono\',monospace;font-size:0.78rem;">'
            for e in filtered[:100]:
                lvl = e.get("level","INFO")
                color = {"ERROR":"#f85149","WARNING":"#e3b341","CRITICAL":"#f85149"}.get(lvl,"#3fb950" if lvl=="INFO" else "#58a6ff")
                ts = e.get("timestamp","")[:19].replace("T"," ")
                log_html += f'<div style="padding:4px 0;border-bottom:1px solid #161b22;color:#8b949e;"><span style="color:#30363d;">{ts}</span> <span style="color:{color};">[{lvl}]</span> <span style="color:#58a6ff;">{e.get("component","")}</span> → <span style="color:#e6edf3;">{e.get("message","")}</span></div>'
            log_html += '</div>'
            st.markdown(log_html, unsafe_allow_html=True)
        else:
            st.markdown('<div style="background:#161b22;border:1px solid #21262d;border-radius:10px;padding:1.2rem;text-align:center;color:#8b949e;font-family:\'JetBrains Mono\',monospace;">No log entries match the current filter.</div>', unsafe_allow_html=True)

        st.markdown("<div style='margin:1rem 0;'></div>", unsafe_allow_html=True)
        dl1, dl2, dl3 = st.columns(3)
        with dl1:
            if entries:
                txt_data = "\n".join([f"{e.get('timestamp','')} [{e.get('level','')}] {e.get('component','')} → {e.get('message','')}" for e in entries])
                st.download_button("⬇️ Download .txt", txt_data, "sentinelops_logs.txt", "text/plain", use_container_width=True)
        with dl2:
            if entries:
                csv_data = pd.DataFrame(entries).to_csv(index=False)
                st.download_button("⬇️ Download .csv", csv_data, "sentinelops_logs.csv", "text/csv", use_container_width=True)
        with dl3:
            if st.button("🗑️ Clear Logs", use_container_width=True):
                st.session_state.log_entries = []
                st.rerun()

        st.markdown("---")
        st.markdown("#### 🔐 Login History")
        login_hist = st.session_state.get("login_history", [])
        if login_hist:
            lh_df = pd.DataFrame(login_hist)
            lh_df["timestamp"] = lh_df["timestamp"].str[:19].str.replace("T"," ")
            lh_df["success"] = lh_df["success"].map({True:"✅ Success", False:"❌ Failed"})
            st.dataframe(lh_df, use_container_width=True, height=200, hide_index=True)
        else: st.info("No login history this session.")

        st.markdown("---")
        st.markdown("#### 🚨 Alert History")
        alert_hist = st.session_state.get("alert_history", [])
        if alert_hist:
            ah_df = pd.DataFrame(alert_hist)
            ah_df["timestamp"] = ah_df["timestamp"].str[:19].str.replace("T"," ")
            st.dataframe(ah_df, use_container_width=True, height=200, hide_index=True)
        else: st.info("No alerts triggered this session.")

        if os.path.exists(LOG_FILE):
            st.markdown("---")
            st.markdown("#### 📁 File Log")
            with open(LOG_FILE) as f:
                file_lines = f.readlines()[-50:]
            st.text_area("Last 50 lines", "".join(file_lines), height=200)

# ══════════════════════════════════════════════════════════
#  TAB 6: MULTI-SYSTEM (ADMIN ONLY)
# ══════════════════════════════════════════════════════════
if is_admin:
    with tab_multisys:
        st.markdown("### 🌐 Multi-System Monitor")
        systems = get_systems()
        st.markdown("#### 🖥️ Registered Systems")
        cols_per_row = 3
        for i in range(0, len(systems), cols_per_row):
            row_systems = systems[i:i+cols_per_row]
            cols = st.columns(cols_per_row)
            for col, sys in zip(cols, row_systems):
                is_local = sys["id"] == "local"
                if is_local:
                    s_cpu=data['cpu_percent']; s_mem=data['memory_percent']; s_disk=data['disk_percent']; s_health=health_score; s_color=health_color
                else:
                    s_cpu=random.uniform(10,95); s_mem=random.uniform(20,90); s_disk=random.uniform(15,80)
                    s_health=round(100-(s_cpu*0.4+s_mem*0.35+s_disk*0.25),1); s_color=get_health_color(s_health)
                status_dot = "🟢" if sys["status"]=="online" else "🔴"
                tags_html = "".join([f'<span style="background:#21262d;padding:1px 6px;border-radius:4px;font-size:0.65rem;color:#58a6ff;margin-right:3px;">{t}</span>' for t in sys.get("tags",[])])
                col.markdown(f'<div style="background:#161b22;border:1px solid #21262d;border-top:3px solid {s_color};border-radius:12px;padding:1rem 1.2rem;margin-bottom:0.5rem;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;"><span style="font-family:\'JetBrains Mono\',monospace;font-weight:700;color:#e6edf3;font-size:0.9rem;">{status_dot} {sys["name"]}</span><span style="font-family:\'JetBrains Mono\',monospace;font-size:0.7rem;color:#8b949e;">{sys["host"]}</span></div><div style="margin-bottom:8px;">{tags_html}</div><div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;"><div style="text-align:center;"><div style="font-family:\'JetBrains Mono\',monospace;font-size:0.68rem;color:#8b949e;">CPU</div><div style="font-family:\'JetBrains Mono\',monospace;font-size:0.9rem;font-weight:700;color:{get_color(s_cpu)};">{s_cpu:.0f}%</div></div><div style="text-align:center;"><div style="font-family:\'JetBrains Mono\',monospace;font-size:0.68rem;color:#8b949e;">MEM</div><div style="font-family:\'JetBrains Mono\',monospace;font-size:0.9rem;font-weight:700;color:{get_color(s_mem)};">{s_mem:.0f}%</div></div><div style="text-align:center;"><div style="font-family:\'JetBrains Mono\',monospace;font-size:0.68rem;color:#8b949e;">DISK</div><div style="font-family:\'JetBrains Mono\',monospace;font-size:0.9rem;font-weight:700;color:{get_color(s_disk)};">{s_disk:.0f}%</div></div></div><div style="margin-top:8px;text-align:center;"><span style="font-family:\'JetBrains Mono\',monospace;font-size:0.7rem;color:{s_color};">❤️ Health: {s_health}</span></div></div>', unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### ➕ Register New System")
        na,nb,nc,nd = st.columns([2,2,1,1])
        new_name = na.text_input("Hostname / Label", placeholder="web-server-01")
        new_host = nb.text_input("IP / Host", placeholder="192.168.1.10")
        new_port = nc.number_input("SSH Port", value=22, min_value=1, max_value=65535)
        new_tags = nd.text_input("Tags (comma-sep)", placeholder="prod, web")
        if st.button("➕ Add System"):
            if new_name and new_host:
                new_sys = {"id":f"sys_{len(systems)+1}","name":new_name,"host":new_host,"port":new_port,"status":"online","tags":[t.strip() for t in new_tags.split(",") if t.strip()]}
                st.session_state.registered_systems = systems + [new_sys]
                st.success(f"✅ '{new_name}' registered!")
                st.rerun()
            else: st.error("⚠️ Name and Host required.")
        if len(systems) > 1:
            st.markdown("#### 🗑️ Remove System")
            removable = [s["name"] for s in systems if s["id"]!="local"]
            if removable:
                to_remove = st.selectbox("Select system to remove", removable)
                if st.button("🗑️ Remove"):
                    st.session_state.registered_systems = [s for s in systems if s["name"]!=to_remove]
                    st.success(f"Removed '{to_remove}'")
                    st.rerun()

# ══════════════════════════════════════════════════════════
#  TAB 7: ADMIN PANEL — NO RE-AUTH GATE, OPENS DIRECTLY
# ══════════════════════════════════════════════════════════
if is_admin:
    with tab_admin:
        st.markdown("### 👑 Admin Panel")

        admin_tabs = st.tabs([
            "⚙️ Thresholds", "📧 Email Alerts", "🔊 Voice Alerts",
            "👤 User Management", "🔧 System Config",
            "📊 System Overview", "🚨 Alert Monitor", "🛠️ Control Panel",
        ])

        # ── Thresholds ──
        with admin_tabs[0]:
            st.markdown("#### ⚙️ Alert Thresholds")
            t_cpu  = st.slider("🔲 CPU Alert Threshold %",         0, 100, admin_config["alert_thresholds"].get("cpu",80))
            t_mem  = st.slider("🧠 Memory Alert Threshold %",      0, 100, admin_config["alert_thresholds"].get("memory",85))
            t_disk = st.slider("💾 Disk Alert Threshold %",        0, 100, admin_config["alert_thresholds"].get("disk",90))
            t_temp = st.slider("🌡️ CPU Temperature Threshold °C", 40, 110, admin_config["alert_thresholds"].get("cpu_temp",80))
            if st.button("💾 Save Thresholds", use_container_width=True):
                admin_config["alert_thresholds"] = {"cpu":t_cpu,"memory":t_mem,"disk":t_disk,"cpu_temp":t_temp}
                save_admin_config(admin_config)
                log_event("INFO","Admin",f"Thresholds updated: CPU={t_cpu}%, MEM={t_mem}%, DISK={t_disk}%, TEMP={t_temp}°C")
                st.success("✅ Thresholds saved!")

        # ── Email ──
        with admin_tabs[1]:
            st.markdown("#### 📧 Email Alert Configuration")
            ec = admin_config.get("email_config", {})
            email_enabled = st.checkbox("Enable Email Alerts", value=ec.get("enabled",False))
            smtp_server  = st.text_input("SMTP Server", value=ec.get("smtp_server",""), placeholder="smtp.gmail.com")
            smtp_port    = st.number_input("SMTP Port", value=ec.get("smtp_port",587), min_value=1, max_value=65535)
            sender_email = st.text_input("Sender Email", value=ec.get("sender",""))
            sender_pass  = st.text_input("Sender Password", type="password", value=ec.get("password",""))
            recipients_raw = st.text_area("Recipients (one per line)", value="\n".join(ec.get("recipients",[])))
            col_save, col_test = st.columns(2)
            with col_save:
                if st.button("💾 Save Email Config", use_container_width=True):
                    admin_config["email_config"] = {"enabled":email_enabled,"smtp_server":smtp_server,"smtp_port":smtp_port,"sender":sender_email,"password":sender_pass,"recipients":[r.strip() for r in recipients_raw.split("\n") if r.strip()]}
                    save_admin_config(admin_config)
                    st.success("✅ Email config saved!")
            with col_test:
                if st.button("📤 Send Test Email", use_container_width=True):
                    ok, msg = send_email_alert("Test Alert","<h2>SentinelOps Test</h2><p>Email alerts working.</p>",admin_config.get("email_config",{}))
                    if ok: st.success("✅ Test email sent!")
                    else: st.error(f"❌ Failed: {msg}")

        # ── Voice ──
        with admin_tabs[2]:
            st.markdown("#### 🔊 Voice Alert Settings")
            voice_enabled = st.checkbox("Enable Voice Alerts", value=admin_config.get("voice_alerts",True))
            if st.button("💾 Save Voice Settings"):
                admin_config["voice_alerts"] = voice_enabled
                save_admin_config(admin_config)
                st.success("✅ Saved!")
            vc1, vc2 = st.columns(2)
            with vc1:
                if st.button("🔊 Test General Alert"):
                    inject_voice_alert("SentinelOps voice alert test. System is healthy.","INFO")
                    st.info("▶️ Playing test voice alert...")
            with vc2:
                if st.button("🌡️ Test Temp Alert"):
                    inject_voice_alert("Warning! Your CPU temperature is high.","CRITICAL")
                    st.info("▶️ Playing CPU temperature alert...")

        # ── User Management ──
        with admin_tabs[3]:
            st.markdown("#### 👤 User Management")
            users = admin_config.get("users", {})
            st.dataframe(pd.DataFrame([{"username":u,"role":v["role"]} for u,v in users.items()]), use_container_width=True, hide_index=True)
            st.markdown("---")
            st.markdown("##### ➕ Add / Update User")
            new_uname = st.text_input("Username", placeholder="operator1")
            new_upass = st.text_input("Password", type="password", placeholder="strong-password")
            new_urole = st.selectbox("Role", ["viewer","admin"])
            if st.button("💾 Save User", use_container_width=True):
                if new_uname and new_upass:
                    admin_config["users"][new_uname] = {"password_hash":hashlib.sha256(new_upass.encode()).hexdigest(),"role":new_urole}
                    save_admin_config(admin_config)
                    st.success(f"✅ User '{new_uname}' saved!")
                else: st.error("⚠️ Username and password required.")

        # ── System Config ──
        with admin_tabs[4]:
            st.markdown("#### 🔧 System Configuration")
            refresh_int = st.number_input("Auto Refresh Interval (seconds)", value=admin_config.get("auto_refresh_interval",30), min_value=5, max_value=300)
            retention   = st.number_input("Data Retention (days)", value=admin_config.get("retention_days",7), min_value=1, max_value=90)
            if st.button("💾 Save Config", use_container_width=True):
                admin_config["auto_refresh_interval"] = refresh_int
                admin_config["retention_days"] = retention
                save_admin_config(admin_config)
                st.success("✅ Config saved!")
            st.markdown("---")
            st.markdown("##### 🗑️ Danger Zone")
            st.warning("⚠️ These actions are irreversible.")
            dz1, dz2 = st.columns(2)
            with dz1:
                if st.button("🗑️ Clear All Logs"):
                    st.session_state.log_entries = []
                    st.success("✅ Logs cleared.")
            with dz2:
                if st.button("🗑️ Reset Chat History"):
                    st.session_state.chat_history = []
                    st.success("✅ Chat history cleared.")

        # ── System Overview ──
        with admin_tabs[5]:
            st.markdown("#### 📊 System Overview")
            ov1,ov2,ov3,ov4 = st.columns(4)
            hs_label_ov = "HEALTHY" if health_score >= 70 else ("WARNING" if health_score >= 50 else "CRITICAL")
            for col,title,value,sub,color,icon in [(ov1,"CPU Status",f"{data['cpu_percent']}%",f"Threshold: {admin_config['alert_thresholds'].get('cpu',80)}%",cpu_color,"🔲"),(ov2,"Memory Status",f"{data['memory_percent']}%",f"Threshold: {admin_config['alert_thresholds'].get('memory',85)}%",mem_color,"🧠"),(ov3,"CPU Temp",f"{cpu_temp}°C",f"Threshold: {admin_config['alert_thresholds'].get('cpu_temp',80)}°C",temp_color,"🌡️"),(ov4,"Health Score",f"{health_score}/100",hs_label_ov,health_color,"❤️")]:
                col.markdown(f'<div style="background:#161b22;border:1px solid #21262d;border-top:3px solid {color};border-radius:12px;padding:1.2rem 1.4rem;text-align:center;"><div style="font-size:1.6rem;">{icon}</div><div style="font-family:\'JetBrains Mono\',monospace;font-size:0.68rem;color:#8b949e;text-transform:uppercase;letter-spacing:0.1em;margin:4px 0;">{title}</div><div style="font-family:\'JetBrains Mono\',monospace;font-size:1.6rem;font-weight:700;color:{color};">{value}</div><div style="font-family:\'JetBrains Mono\',monospace;font-size:0.72rem;color:#8b949e;margin-top:4px;">{sub}</div></div>', unsafe_allow_html=True)
            st.markdown("<div style='margin:1rem 0;'></div>", unsafe_allow_html=True)
            st_col1,st_col2,st_col3,st_col4 = st.columns(4)
            st_col1.metric("Log Entries",       len(st.session_state.get("log_entries",[])))
            st_col2.metric("Login Events",      len(st.session_state.get("login_history",[])))
            st_col3.metric("Alerts Fired",      len(st.session_state.get("alert_history",[])))
            st_col4.metric("Registered Systems",len(get_systems()))
            st.markdown("<div style='margin:1rem 0;'></div>", unsafe_allow_html=True)
            cfg_display = {"CPU Threshold":f"{admin_config['alert_thresholds'].get('cpu',80)}%","Memory Threshold":f"{admin_config['alert_thresholds'].get('memory',85)}%","Disk Threshold":f"{admin_config['alert_thresholds'].get('disk',90)}%","CPU Temp Threshold":f"{admin_config['alert_thresholds'].get('cpu_temp',80)}°C","Voice Alerts":"Enabled" if admin_config.get("voice_alerts") else "Disabled","Email Alerts":"Enabled" if admin_config.get("email_config",{}).get("enabled") else "Disabled","Auto Refresh":f"{admin_config.get('auto_refresh_interval',30)}s","Data Retention":f"{admin_config.get('retention_days',7)} days","Total Users":len(admin_config.get("users",{}))}
            st.dataframe(pd.DataFrame(list(cfg_display.items()),columns=["Setting","Value"]), use_container_width=True, hide_index=True)

        # ── Alert Monitor ──
        with admin_tabs[6]:
            st.markdown("#### 🚨 Alert Monitor")
            alert_hist = st.session_state.get("alert_history", [])
            if not alert_hist:
                st.markdown('<div style="background:#161b22;border:1px solid #21262d;border-radius:10px;padding:1.5rem;text-align:center;color:#3fb950;font-family:\'JetBrains Mono\',monospace;">✅ No alerts fired this session — system is healthy!</div>', unsafe_allow_html=True)
            else:
                am1,am2,am3 = st.columns(3)
                am1.metric("Total Alerts",  len(alert_hist))
                am2.metric("Critical",      sum(1 for a in alert_hist if a.get("severity")=="CRITICAL"))
                am3.metric("Warnings",      sum(1 for a in alert_hist if a.get("severity")=="WARNING"))
                st.markdown("<div style='margin:0.8rem 0;'></div>", unsafe_allow_html=True)
                for a in alert_hist[:20]:
                    sev = a.get("severity","INFO")
                    a_color = "#f85149" if sev=="CRITICAL" else "#e3b341"
                    a_icon = "🚨" if sev=="CRITICAL" else "⚠️"
                    ts = a.get("timestamp","")[:19].replace("T"," ")
                    st.markdown(f'<div style="background:#161b22;border:1px solid #21262d;border-left:4px solid {a_color};border-radius:8px;padding:10px 14px;margin-bottom:6px;font-family:\'JetBrains Mono\',monospace;font-size:0.8rem;display:flex;justify-content:space-between;align-items:center;"><span>{a_icon} <span style="color:{a_color};font-weight:700;">[{sev}]</span> <span style="color:#58a6ff;">{a.get("component","")}</span> → <span style="color:#e6edf3;">{a.get("message","")}</span></span><span style="color:#30363d;font-size:0.72rem;">{ts}</span></div>', unsafe_allow_html=True)
            if st.button("🗑️ Clear Alert History"):
                st.session_state.alert_history = []
                st.rerun()

        # ── Control Panel ──
        with admin_tabs[7]:
            st.markdown("#### 🛠️ System Control Panel")
            st.markdown("##### 🔔 Trigger Test Alerts")
            cp1,cp2,cp3 = st.columns(3)
            with cp1:
                if st.button("⚡ CPU Warning", use_container_width=True):
                    record_alert("WARNING","CPU",f"TEST: CPU at 82%")
                    log_event("WARNING","CPU","TEST ALERT: CPU warning")
                    st.warning("⚡ CPU Warning injected.")
                    if admin_config.get("voice_alerts"): inject_voice_alert("Test alert: CPU usage is high.","WARNING")
            with cp2:
                if st.button("🔥 CPU Critical", use_container_width=True):
                    record_alert("CRITICAL","CPU","TEST: CPU at 95%")
                    log_event("CRITICAL","CPU","TEST ALERT: CPU critical")
                    st.error("🔥 CPU Critical injected.")
                    if admin_config.get("voice_alerts"): inject_voice_alert("Critical alert! CPU is critically high!","CRITICAL")
            with cp3:
                if st.button("🌡️ Temp Alert", use_container_width=True):
                    record_alert("CRITICAL","CPUTemp",f"TEST: CPU Temp at 92°C")
                    log_event("CRITICAL","CPUTemp","TEST ALERT: Temp critical")
                    st.error("🌡️ Temp Alert injected.")
                    if admin_config.get("voice_alerts"): inject_voice_alert("Warning! CPU temperature is high.","CRITICAL")
            cp4,cp5,cp6 = st.columns(3)
            with cp4:
                if st.button("🧠 Memory Warning", use_container_width=True):
                    record_alert("WARNING","Memory","TEST: Memory at 88%")
                    st.warning("🧠 Memory Warning injected.")
            with cp5:
                if st.button("💾 Disk Warning", use_container_width=True):
                    record_alert("WARNING","Disk","TEST: Disk at 93%")
                    st.warning("💾 Disk Warning injected.")
            with cp6:
                if st.button("📢 Test All Alerts", use_container_width=True):
                    for sev,comp,msg in [("WARNING","CPU","TEST: CPU at 82%"),("WARNING","Memory","TEST: Memory at 88%"),("CRITICAL","CPUTemp","TEST: CPU Temp at 92°C")]:
                        record_alert(sev,comp,msg)
                    st.error("📢 All test alerts injected!")

            st.markdown("---")
            st.markdown("##### 🗑️ Reset Operations")
            rc1,rc2 = st.columns(2)
            with rc1:
                if st.button("🗑️ Reset Logs", use_container_width=True):
                    st.session_state.log_entries = []
                    st.success("✅ Logs reset.")
            with rc2:
                if st.button("🗑️ Reset Alerts", use_container_width=True):
                    st.session_state.alert_history = []
                    st.success("✅ Alert history reset.")

            st.markdown("---")
            st.markdown("##### ℹ️ System Info")
            st.markdown(f'<div style="background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:1rem 1.4rem;font-family:\'JetBrains Mono\',monospace;font-size:0.8rem;color:#8b949e;line-height:2;">🖥️ &nbsp;Hostname: <span style="color:#e6edf3;">{platform.node()}</span><br>🐍 &nbsp;Python: <span style="color:#e6edf3;">{platform.python_version()}</span><br>🖥️ &nbsp;OS: <span style="color:#e6edf3;">{platform.system()} {platform.release()}</span><br>⚙️ &nbsp;CPU Cores: <span style="color:#e6edf3;">{psutil.cpu_count(logical=False)} physical / {psutil.cpu_count(logical=True)} logical</span><br>🧠 &nbsp;Total RAM: <span style="color:#e6edf3;">{round(psutil.virtual_memory().total/(1024**3),2)} GB</span><br>💾 &nbsp;Total Disk: <span style="color:#e6edf3;">{round(psutil.disk_usage("/").total/(1024**3),2)} GB</span><br>👤 &nbsp;Admin: <span style="color:#fbbf24;">{st.session_state.current_user}</span></div>', unsafe_allow_html=True)

# ─────────────────────────────
# FOOTER
# ─────────────────────────────
refresh_interval = admin_config.get("auto_refresh_interval", 30)
st.markdown(f'<div style="position:fixed;bottom:12px;right:16px;font-family:\'JetBrains Mono\',monospace;font-size:0.68rem;color:#21262d;z-index:999;">SentinelOps v2.0 · {st.session_state.current_user} [{st.session_state.user_role}] · Auto-refresh: {refresh_interval}s</div>', unsafe_allow_html=True)