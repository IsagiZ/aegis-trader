"""
Aegis REST API — Flask server running on $PORT on Render.
All agent threads share the same JSON files; this API reads/writes them
so the Mac desktop app can control the bot in real time.
"""
import os
import json
from pathlib import Path
from flask import Flask, jsonify, request, Response

BASE = Path(__file__).parent
app  = Flask(__name__)


@app.after_request
def _cors(resp: Response) -> Response:
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


# ── JSON helpers ───────────────────────────────────────────────

def _load(name: str) -> dict:
    p = BASE / name
    if not p.exists():
        return {}
    with open(p) as f:
        return json.load(f)


def _save(name: str, data: dict):
    with open(BASE / name, "w") as f:
        json.dump(data, f, indent=2)


# ── GET /api/state ─────────────────────────────────────────────

@app.route("/api/state")
def api_state():
    return jsonify(_load("agent_state.json"))


# ── GET /api/portfolio ─────────────────────────────────────────

@app.route("/api/portfolio")
def api_portfolio():
    tlog   = _load("trading_log.json")
    trades = tlog.get("trades", [])
    closed = [t for t in trades if t.get("status") == "closed"]
    open_t = [t for t in trades if t.get("status") == "open"]
    pnls   = [t.get("pnl", 0) or 0 for t in closed]
    wins   = [p for p in pnls if p > 0]
    return jsonify({
        "portfolio":    tlog.get("portfolio_snapshot", {}),
        "open_trades":  open_t,
        "closed_trades": closed[-10:],
        "total_pnl":    round(sum(pnls), 2),
        "win_rate":     round(len(wins) / len(pnls) * 100) if pnls else 0,
        "total_trades": len(closed),
    })


# ── GET /api/scan ──────────────────────────────────────────────

@app.route("/api/scan")
def api_scan():
    slog   = _load("scan_log.json")
    scans  = slog.get("scans", [])
    flag   = _load("trading_flag.json")
    return jsonify({
        "last_scan":      scans[-1] if scans else {},
        "trading_active": flag.get("trading_active", True),
        "total_scans":    len(scans),
        "kill_switch":    slog.get("last_kill_switch", False),
    })


# ── POST /api/command ──────────────────────────────────────────

@app.route("/api/command", methods=["POST", "OPTIONS"])
def api_command():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(force=True, silent=True) or {}
    cmd  = data.get("cmd", "")

    if cmd == "pause":
        _save("trading_flag.json", {"trading_active": False})
        return jsonify({"ok": True, "msg": "Trading SUSPENDU"})

    if cmd == "resume":
        _save("trading_flag.json", {"trading_active": True})
        return jsonify({"ok": True, "msg": "Trading REPRIS"})

    if cmd == "scan":
        try:
            from auto_scanner import run_single_scan, _load_scan_log, _save_scan_log
            log = _load_scan_log()
            log = run_single_scan(log)
            _save_scan_log(log)
            return jsonify({"ok": True, "msg": "Scan terminé"})
        except Exception as e:
            return jsonify({"ok": False, "msg": str(e)}), 500

    return jsonify({"ok": False, "msg": f"Commande inconnue: {cmd}"}), 400


# ── GET /health ────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "aegis-api"})


# ── GET / — status page ────────────────────────────────────────

@app.route("/")
def index():
    flag       = _load("trading_flag.json")
    active     = flag.get("trading_active", True)
    state_data = _load("agent_state.json")
    agents     = state_data.get("agents", {})

    rows = ""
    for name, info in agents.items():
        s = info.get("status", "OFFLINE")
        c = "#00ff88" if s == "ACTIVE" else "#ffd700" if s == "IDLE" else "#ff4444"
        m = (info.get("message") or "")[:50]
        rows += f"<tr><td>{name}</td><td style='color:{c}'>{s}</td><td>{m}</td></tr>"

    t_color = "#00ff88" if active else "#ff4444"
    t_label = "ACTIF" if active else "SUSPENDU"

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta http-equiv="refresh" content="15">
<title>Aegis API</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#060b14;color:#c0caf5;font-family:'Courier New',monospace;padding:40px}}
  h1{{color:#7dcfff;font-size:22px;margin-bottom:24px}}
  .badge{{display:inline-block;padding:4px 14px;border-radius:4px;font-weight:bold;margin-left:10px}}
  table{{border-collapse:collapse;width:500px;margin:20px 0}}
  td,th{{padding:8px 14px;border-bottom:1px solid #1e2030;text-align:left}}
  th{{color:#565f89;font-size:11px}}
  ul{{margin:16px 0 0 20px;color:#565f89;line-height:2}}
  li b{{color:#7aa2f7}}
  footer{{margin-top:40px;color:#30384a;font-size:11px}}
</style></head>
<body>
  <h1>⚡ AEGIS — API Server</h1>
  <p>Trading :
    <span class="badge" style="background:{t_color};color:#060b14">{t_label}</span>
  </p>
  <table>
    <tr><th>AGENT</th><th>STATUS</th><th>MESSAGE</th></tr>
    {rows}
  </table>
  <h3 style="color:#565f89;font-size:13px;margin-top:24px">ENDPOINTS</h3>
  <ul>
    <li><b>GET  /api/state</b> — statut des agents</li>
    <li><b>GET  /api/portfolio</b> — capital, trades, P&L</li>
    <li><b>GET  /api/scan</b> — dernier scan marché</li>
    <li><b>POST /api/command</b> — {{cmd: pause|resume|scan}}</li>
    <li><b>GET  /health</b> — healthcheck</li>
  </ul>
  <footer>Page auto-refresh 15s &nbsp;|&nbsp; Connect via Aegis Mac App for full dashboard</footer>
</body></html>"""


def run(port: int = 8501):
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
