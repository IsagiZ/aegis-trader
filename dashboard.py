"""
Aegis Command Center — Dashboard Streamlit.
Lancer : streamlit run dashboard.py
"""
import os, sys, json, subprocess
from pathlib import Path
from datetime import datetime, timezone

os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import plotly.graph_objects as go

# ── Config page ────────────────────────────────────────────────
st.set_page_config(
    page_title="AEGIS Command Center",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS thème dark mission-control ────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700;900&display=swap');

/* Background */
.stApp { background-color: #060b14; color: #c8d8e8; }
section[data-testid="stSidebar"] { background-color: #060b14; }

/* Fonts */
html, body, [class*="css"] { font-family: 'Share Tech Mono', monospace; }

/* Hide streamlit defaults */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1rem; padding-bottom: 0; max-width: 100%; }

/* Metric cards */
.metric-card {
    background: linear-gradient(135deg, #0a1628 0%, #0d1f3c 100%);
    border: 1px solid #1a3a5c;
    border-top: 2px solid #00d4ff;
    border-radius: 4px;
    padding: 16px 20px;
    position: relative;
    overflow: hidden;
}
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, #00d4ff, transparent);
}
.metric-label { font-size: 10px; color: #4a7fa8; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 4px; }
.metric-value { font-family: 'Orbitron', monospace; font-size: 22px; font-weight: 700; color: #00ff9d; }
.metric-value.red { color: #ff4444; }
.metric-value.yellow { color: #ffd700; }
.metric-sub { font-size: 10px; color: #4a7fa8; margin-top: 4px; }

/* Agent cards */
.agent-card {
    background: #0a1628;
    border: 1px solid #1a3a5c;
    border-radius: 6px;
    padding: 14px;
    text-align: center;
    position: relative;
}
.agent-name { font-family: 'Orbitron', monospace; font-size: 13px; font-weight: 700; color: #00d4ff; letter-spacing: 2px; }
.agent-status-active { color: #00ff9d; font-size: 10px; letter-spacing: 1px; }
.agent-status-idle   { color: #ffd700; font-size: 10px; letter-spacing: 1px; }
.agent-status-offline{ color: #ff4444; font-size: 10px; letter-spacing: 1px; }
.agent-status-error  { color: #ff6600; font-size: 10px; letter-spacing: 1px; }
.agent-msg { font-size: 9px; color: #4a7fa8; margin-top: 4px; max-height: 28px; overflow: hidden; }
.agent-avatar {
    width: 48px; height: 48px;
    border-radius: 50%;
    margin: 0 auto 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
    border: 2px solid #1a3a5c;
}
.agent-avatar.active { border-color: #00ff9d; box-shadow: 0 0 10px #00ff9d44; }
.agent-avatar.idle   { border-color: #ffd700; }
.agent-avatar.offline{ border-color: #ff4444; }

/* Header */
.main-header {
    font-family: 'Orbitron', monospace;
    font-size: 11px;
    letter-spacing: 4px;
    color: #4a7fa8;
    text-transform: uppercase;
    border-bottom: 1px solid #1a3a5c;
    padding-bottom: 8px;
    margin-bottom: 16px;
}
.system-status {
    font-family: 'Orbitron', monospace;
    font-size: 14px;
    letter-spacing: 3px;
    text-align: center;
}
.system-ok   { color: #00ff9d; }
.system-warn { color: #ffd700; }
.system-halt { color: #ff4444; }

/* Section titles */
.section-title {
    font-family: 'Orbitron', monospace;
    font-size: 10px;
    letter-spacing: 3px;
    color: #4a7fa8;
    border-left: 2px solid #00d4ff;
    padding-left: 8px;
    margin: 16px 0 10px;
    text-transform: uppercase;
}

/* Table */
.mkt-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.mkt-table th {
    background: #0a1628;
    color: #4a7fa8;
    font-size: 9px;
    letter-spacing: 2px;
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid #1a3a5c;
    text-transform: uppercase;
}
.mkt-table td { padding: 8px 12px; border-bottom: 1px solid #0d1f3c; }
.mkt-table tr:hover { background: #0d1f3c; }
.bull { color: #00ff9d; }
.bear { color: #ff4444; }
.neutral { color: #ffd700; }
.flat { color: #4a7fa8; }

/* Buttons */
.stButton > button {
    font-family: 'Orbitron', monospace;
    font-size: 11px;
    letter-spacing: 2px;
    border-radius: 3px;
    border: 1px solid;
    padding: 8px 24px;
    text-transform: uppercase;
    transition: all 0.2s;
    width: 100%;
}
div[data-testid="column"]:nth-child(1) .stButton > button {
    background: linear-gradient(135deg, #003a1a, #00612a);
    border-color: #00ff9d;
    color: #00ff9d;
}
div[data-testid="column"]:nth-child(1) .stButton > button:hover {
    box-shadow: 0 0 15px #00ff9d66;
}
div[data-testid="column"]:nth-child(2) .stButton > button {
    background: linear-gradient(135deg, #3a0000, #610000);
    border-color: #ff4444;
    color: #ff4444;
}

/* Kill switch badge */
.ks-clear { background: #003a1a; border: 1px solid #00ff9d; color: #00ff9d; padding: 6px 16px; border-radius: 3px; font-size: 10px; letter-spacing: 2px; display: inline-block; }
.ks-active { background: #3a0000; border: 1px solid #ff4444; color: #ff4444; padding: 6px 16px; border-radius: 3px; font-size: 10px; letter-spacing: 2px; display: inline-block; animation: blink 1s infinite; }
@keyframes blink { 50% { opacity: 0.5; } }

/* Trade row */
.trade-win  { color: #00ff9d; }
.trade-loss { color: #ff4444; }
.trade-open { color: #ffd700; }

/* Scanline effect */
.stApp::after {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px);
    pointer-events: none;
    z-index: 9999;
}
</style>
""", unsafe_allow_html=True)

# ── Auto-refresh toutes les 30s ────────────────────────────────
st.markdown("""
<script>
setTimeout(function(){ window.location.reload(); }, 30000);
</script>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────

def _load_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _is_running() -> bool:
    try:
        flag = _load_json("trading_flag.json")
        return flag.get("trading_active", True)
    except Exception:
        return True


def _start_bot():
    with open("trading_flag.json", "w") as f:
        json.dump({"trading_active": True}, f)
    try:
        import telegram_notify as tg
        tg.send("⚡ AEGIS ACTIVÉ", "Trading activé depuis le dashboard.")
    except Exception:
        pass


def _stop_bot():
    with open("trading_flag.json", "w") as f:
        json.dump({"trading_active": False}, f)
    try:
        import telegram_notify as tg
        tg.send("⏸ AEGIS SUSPENDU", "Trading suspendu depuis le dashboard.")
    except Exception:
        pass


def _trend_html(trend: str) -> str:
    icons = {"bull": "▲ BULL", "bear": "▼ BEAR", "neutral": "→ NEUT"}
    cls   = {"bull": "bull",   "bear": "bear",    "neutral": "neutral"}
    return f'<span class="{cls.get(trend, "flat")}">{icons.get(trend, trend)}</span>'


def _bias_html(bias: str) -> str:
    cls = {"long": "bull", "short": "bear", "flat": "flat"}
    return f'<span class="{cls.get(bias, "flat")}">{bias.upper()}</span>'


def _agent_html(name: str, icon: str, info: dict) -> str:
    status  = info.get("status", "OFFLINE").upper()
    message = info.get("message", "")
    last    = info.get("last_seen", "")
    if last:
        try:
            dt  = datetime.fromisoformat(last)
            ago = int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
            last = f"{ago}min ago"
        except Exception:
            last = ""

    cls_map = {"ACTIVE": "active", "IDLE": "idle", "OFFLINE": "offline", "ERROR": "error"}
    dot_map = {"ACTIVE": "●", "IDLE": "◉", "OFFLINE": "○", "ERROR": "⚠"}
    cls = cls_map.get(status, "offline")

    return f"""
<div class="agent-card">
  <div class="agent-avatar {cls}">{icon}</div>
  <div class="agent-name">{name}</div>
  <div class="agent-status-{cls}">{dot_map.get(status, '○')} {status}</div>
  <div class="agent-msg">{message or last}</div>
</div>
"""


# ── Load data ──────────────────────────────────────────────────
tlog   = _load_json("trading_log.json")
slog   = _load_json("scan_log.json")
state  = _load_json("agent_state.json")

snap_portfolio = tlog.get("portfolio_snapshot", {})
equity    = snap_portfolio.get("total_equity") or 100000
cash      = snap_portfolio.get("cash") or equity
core_eq   = snap_portfolio.get("core_equity") or equity * 0.9
sat_eq    = snap_portfolio.get("satellite_equity") or equity * 0.1
open_pos  = len(snap_portfolio.get("open_positions", []))

trades     = tlog.get("trades", [])
closed     = [t for t in trades if t["status"] == "closed"]
wins       = [t for t in closed if (t.get("pnl") or 0) > 0]
total_pnl  = sum(t.get("pnl", 0) or 0 for t in closed)
win_rate   = round(len(wins) / len(closed) * 100) if closed else 0

last_scans = slog.get("scans", [])
last_assets = last_scans[-1]["assets"] if last_scans else {}

kill_switch = False
macro_info  = state.get("macro", {})
if macro_info.get("danger_zone"):
    kill_switch = True

agents_info = state.get("agents", {})
running = _is_running()

# ── HEADER ─────────────────────────────────────────────────────
ts_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
st.markdown(f"""
<div style="display:flex; justify-content:space-between; align-items:center; border-bottom: 1px solid #1a3a5c; padding-bottom:12px; margin-bottom:16px;">
  <div>
    <div style="font-family:Orbitron,monospace; font-size:20px; font-weight:900; color:#00d4ff; letter-spacing:4px;">⚡ AEGIS</div>
    <div style="font-size:9px; color:#4a7fa8; letter-spacing:3px;">COMMAND CENTER // v1.0</div>
  </div>
  <div class="system-status {'system-ok' if running and not kill_switch else 'system-warn' if not running else 'system-halt'}">
    {'● SYSTEMS OPERATIONAL' if running and not kill_switch else '◉ STANDBY' if not running else '⚠ KILL SWITCH ACTIVE'}
  </div>
  <div style="font-size:10px; color:#4a7fa8;">{ts_now}<br><span style="color:{'#00ff9d' if running else '#ff4444'}">{'● BOT ACTIVE' if running else '○ BOT OFFLINE'}</span></div>
</div>
""", unsafe_allow_html=True)

# ── CONTROLS ───────────────────────────────────────────────────
ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([1, 1, 4, 1])
with ctrl1:
    if st.button("▶  START ALL AGENTS"):
        _start_bot()
        st.rerun()
with ctrl2:
    if st.button("⏹  STOP ALL AGENTS"):
        _stop_bot()
        st.rerun()
with ctrl3:
    ks_html = f'<span class="ks-active">⚠ KILL SWITCH — {macro_info.get("recommendation","")}</span>' if kill_switch else '<span class="ks-clear">✓ KILL SWITCH CLEAR</span>'
    st.markdown(ks_html, unsafe_allow_html=True)
with ctrl4:
    if st.button("↺  REFRESH"):
        st.rerun()

st.markdown("---")

# ── METRICS ROW ────────────────────────────────────────────────
st.markdown('<div class="section-title">Portfolio Overview</div>', unsafe_allow_html=True)
m1, m2, m3, m4, m5, m6 = st.columns(6)

pnl_class = "metric-value" if total_pnl >= 0 else "metric-value red"
wr_class  = "metric-value" if win_rate >= 50 else "metric-value yellow"

metrics = [
    (m1, "TOTAL EQUITY",       f"${equity:,.2f}",     "metric-value",  "Paper Trading"),
    (m2, "CASH DISPONIBLE",    f"${cash:,.2f}",        "metric-value",  f"{cash/equity*100:.1f}% du capital"),
    (m3, "CORE (90%)",         f"${core_eq:,.2f}",     "metric-value",  "SPY · GLD · SLV"),
    (m4, "SATELLITE (10%)",    f"${sat_eq:,.2f}",      "metric-value",  "BTC/USD"),
    (m5, "P&L TOTAL",          f"{'+'if total_pnl>=0 else ''}{total_pnl:,.2f}$", pnl_class, f"{len(closed)} trades fermés"),
    (m6, "WIN RATE",           f"{win_rate}%",          wr_class,        f"{len(wins)}W / {len(closed)-len(wins)}L"),
]
for col, label, value, cls, sub in metrics:
    with col:
        st.markdown(f"""
<div class="metric-card">
  <div class="metric-label">{label}</div>
  <div class="{cls}">{value}</div>
  <div class="metric-sub">{sub}</div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── AGENTS ROW ─────────────────────────────────────────────────
st.markdown('<div class="section-title">Agent Status</div>', unsafe_allow_html=True)

agent_defs = [
    ("MACRO",  "🌐", agents_info.get("MACRO",  {})),
    ("SIGNAL", "📡", agents_info.get("SIGNAL", {})),
    ("RISK",   "🛡", agents_info.get("RISK",   {})),
    ("EXEC",   "⚡", agents_info.get("EXEC",   {})),
    ("MEMORY", "🧠", agents_info.get("MEMORY", {})),
]
a_cols = st.columns(5)
for col, (name, icon, info) in zip(a_cols, agent_defs):
    with col:
        st.markdown(_agent_html(name, icon, info), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── MARKET DATA ────────────────────────────────────────────────
st.markdown('<div class="section-title">Live Market Signals</div>', unsafe_allow_html=True)

if last_assets:
    rows = ""
    for asset, data in last_assets.items():
        price = data.get("price", 0)
        rsi   = data.get("rsi", 0)
        trend = data.get("trend", "")
        bias  = data.get("bias", "")
        seg   = "CORE" if asset in ["SPY","GLD","SLV"] else "SAT"
        seg_color = "#00d4ff" if seg == "CORE" else "#a855f7"
        rsi_color = "#ff4444" if rsi > 70 else "#00ff9d" if rsi < 30 else "#c8d8e8"
        rows += f"""
<tr>
  <td><span style="color:{seg_color};font-size:9px">[{seg}]</span> <strong style="color:#c8d8e8">{asset}</strong></td>
  <td style="color:#00d4ff;font-family:Orbitron,monospace">${price:,.4f}</td>
  <td>{_trend_html(trend)}</td>
  <td style="color:{rsi_color}">{rsi}</td>
  <td>{_bias_html(bias)}</td>
  <td style="color:#4a7fa8;font-size:10px">{last_scans[-1]['timestamp'] if last_scans else '—'}</td>
</tr>"""

    st.markdown(f"""
<table class="mkt-table">
<thead><tr>
  <th>Asset</th><th>Prix</th><th>Trend</th><th>RSI</th><th>Bias</th><th>Dernier scan</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>
""", unsafe_allow_html=True)
else:
    st.markdown('<span style="color:#4a7fa8;font-size:12px">Aucune donnée — lancer le bot pour scanner le marché.</span>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── TRADES + MACRO ─────────────────────────────────────────────
left, right = st.columns([3, 2])

with left:
    st.markdown('<div class="section-title">Trade History</div>', unsafe_allow_html=True)
    if trades:
        rows = ""
        for t in reversed(trades[-15:]):
            status = t["status"]
            pnl    = t.get("pnl")
            if status == "open":
                pnl_str   = "OPEN"
                pnl_class = "trade-open"
            elif pnl is not None:
                pnl_str   = f"{'+'if pnl>=0 else ''}{pnl:.2f}$"
                pnl_class = "trade-win" if pnl >= 0 else "trade-loss"
            else:
                pnl_str, pnl_class = "—", "flat"

            direction = t.get("direction","").upper()
            asset     = t.get("asset","")
            opened    = (t.get("opened_at") or "")[:10]
            rr        = t["planned"].get("rr","—")
            pm        = "✓" if t.get("post_mortem") else "—"

            rows += f"""
<tr>
  <td style="color:#4a7fa8;font-size:10px">{opened}</td>
  <td style="color:#00d4ff">{asset}</td>
  <td class="{'bull' if direction=='LONG' else 'bear'}">{direction}</td>
  <td style="color:#c8d8e8">{rr}:1</td>
  <td class="{pnl_class}">{pnl_str}</td>
  <td style="color:#4a7fa8">{pm}</td>
</tr>"""
        st.markdown(f"""
<table class="mkt-table">
<thead><tr><th>Date</th><th>Asset</th><th>Dir</th><th>R:R</th><th>P&L</th><th>PM</th></tr></thead>
<tbody>{rows}</tbody>
</table>
""", unsafe_allow_html=True)
    else:
        st.markdown('<span style="color:#4a7fa8;font-size:12px">Aucun trade enregistré.</span>', unsafe_allow_html=True)

with right:
    st.markdown('<div class="section-title">Macro & Calendrier</div>', unsafe_allow_html=True)
    macro = state.get("macro", {})
    events = macro.get("upcoming_events", [
        {"date": "2026-04-30", "event": "GDP Q1", "impact": "HIGH"},
        {"date": "2026-04-30", "event": "PCE Deflator", "impact": "HIGH"},
        {"date": "2026-05-01", "event": "NFP", "impact": "HIGH"},
    ])
    for ev in events:
        color = "#ff4444" if ev["impact"] == "HIGH" else "#ffd700"
        st.markdown(f"""
<div style="background:#0a1628;border-left:2px solid {color};padding:8px 12px;margin-bottom:6px;border-radius:0 4px 4px 0;">
  <span style="font-size:9px;color:#4a7fa8;">{ev['date']}</span><br>
  <span style="color:{color};font-size:11px;">⚠ {ev['event']}</span>
  <span style="float:right;font-size:9px;color:{color};">{ev['impact']}</span>
</div>
""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Error patterns
    patterns = tlog.get("error_patterns", [])
    active_p = [p for p in patterns if p.get("active")]
    st.markdown('<div class="section-title">Error Patterns Actifs</div>', unsafe_allow_html=True)
    if active_p:
        for p in active_p:
            st.markdown(f"""
<div style="background:#1a0a0a;border-left:2px solid #ff4444;padding:8px 12px;margin-bottom:6px;border-radius:0 4px 4px 0;font-size:10px;">
  <span style="color:#ff4444;">#{p['id']} [{p['asset']} {p['direction'].upper()}]</span><br>
  <span style="color:#c8d8e8;">{p['description']}</span>
</div>
""", unsafe_allow_html=True)
    else:
        st.markdown('<span style="color:#4a7fa8;font-size:11px;">✓ Aucun pattern d\'erreur enregistré</span>', unsafe_allow_html=True)

# ── Footer ─────────────────────────────────────────────────────
st.markdown("""
<div style="margin-top:24px;border-top:1px solid #1a3a5c;padding-top:8px;display:flex;justify-content:space-between;">
  <span style="font-size:9px;color:#1a3a5c;">AEGIS QUANT TRADER // PAPER MODE // AUTO-REFRESH 30s</span>
  <span style="font-size:9px;color:#1a3a5c;">⚡ Powered by Alpaca Markets</span>
</div>
""", unsafe_allow_html=True)
