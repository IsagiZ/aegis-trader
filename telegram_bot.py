"""
Aegis Telegram Bot — commandes de contrôle.
/status /scan /pause /resume /trades /capital /performance
"""
import os
import json
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "8476245241:AAFLK7T0C9A-vuHGbZfDmwPfVep9b0FidhI")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID",   "7863773047")
BASE    = f"https://api.telegram.org/bot{TOKEN}"


# ── Helpers ────────────────────────────────────────────────────

def _send(text: str):
    try:
        requests.post(f"{BASE}/sendMessage", json={
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"
        }, timeout=10)
    except Exception as e:
        print(f"[TELEGRAM BOT] send error: {e}", flush=True)


def _load_tlog() -> dict:
    try:
        with open("trading_log.json") as f:
            return json.load(f)
    except Exception:
        return {"trades": [], "portfolio_snapshot": {}}


def _load_scan_log() -> dict:
    try:
        with open("scan_log.json") as f:
            return json.load(f)
    except Exception:
        return {"scans": []}


def _load_flag() -> bool:
    try:
        with open("trading_flag.json") as f:
            return json.load(f).get("trading_active", True)
    except Exception:
        return True


def _set_flag(active: bool):
    with open("trading_flag.json", "w") as f:
        json.dump({"trading_active": active}, f)


# ── Commandes ──────────────────────────────────────────────────

def cmd_status():
    tlog  = _load_tlog()
    slog  = _load_scan_log()
    snap  = tlog.get("portfolio_snapshot", {})
    flag  = _load_flag()
    last  = slog.get("scans", [{}])[-1]

    equity = snap.get("total_equity", 0)
    cash   = snap.get("cash", 0)
    pos    = len(snap.get("open_positions", []))
    ts     = last.get("timestamp", "jamais")
    state  = "✅ ACTIF" if flag else "⏸ EN PAUSE"

    trades  = tlog.get("trades", [])
    closed  = [t for t in trades if t["status"] == "closed"]
    open_t  = [t for t in trades if t["status"] == "open"]

    _send(
        f"⚡ <b>AEGIS — STATUT</b>\n\n"
        f"Trading     : <b>{state}</b>\n"
        f"Dernier scan: {ts}\n\n"
        f"💼 Capital  : <b>${equity:,.2f}</b>\n"
        f"💵 Cash     : ${cash:,.2f}\n"
        f"📂 Positions: {pos} ouvertes\n"
        f"📊 Trades   : {len(open_t)} open | {len(closed)} fermés"
    )


def cmd_scan():
    _send("🔍 <b>Scan en cours...</b>")
    try:
        from auto_scanner import run_single_scan, _load_scan_log, _save_scan_log
        log = _load_scan_log()
        log = run_single_scan(log)
        _save_scan_log(log)
        scans = log.get("scans", [])
        last  = scans[-1] if scans else {}
        assets = last.get("assets", {})
        lines = ["📡 <b>Scan terminé</b>\n"]
        for name, d in assets.items():
            t = "▲" if d["trend"] == "bull" else "▼" if d["trend"] == "bear" else "→"
            lines.append(f"{t} <b>{name}</b> ${d['price']:,.2f} | RSI {d['rsi']} | {d['bias'].upper()}")
        _send("\n".join(lines))
    except Exception as e:
        _send(f"❌ Erreur scan: {e}")


def cmd_pause():
    _set_flag(False)
    _send("⏸ <b>Trading SUSPENDU</b>\n\nAegis ne prendra aucun nouveau trade.\nUtilise /resume pour reprendre.")


def cmd_resume():
    _set_flag(True)
    _send("▶️ <b>Trading REPRIS</b>\n\nAegis surveille le marché et prendra les prochains setups valides.")


def cmd_trades():
    tlog   = _load_tlog()
    trades = tlog.get("trades", [])
    closed = [t for t in trades if t["status"] == "closed"]

    if not closed:
        _send("📊 <b>Aucun trade fermé pour l'instant.</b>")
        return

    lines = ["📊 <b>Derniers trades</b>\n"]
    for t in reversed(closed[-5:]):
        pnl   = t.get("pnl", 0) or 0
        sign  = "+" if pnl >= 0 else ""
        emoji = "✅" if pnl >= 0 else "❌"
        date  = (t.get("closed_at") or "")[:10]
        lines.append(
            f"{emoji} <b>{t['asset']}</b> {t['direction'].upper()} "
            f"| {sign}{pnl:.2f}$ | {date}"
        )
    _send("\n".join(lines))


def cmd_capital():
    tlog = _load_tlog()
    snap = tlog.get("portfolio_snapshot", {})

    equity  = snap.get("total_equity", 0)
    cash    = snap.get("cash", 0)
    core    = snap.get("core_equity", 0)
    sat     = snap.get("satellite_equity", 0)
    updated = (snap.get("last_updated") or "")[:16].replace("T", " ")

    _send(
        f"💼 <b>AEGIS — CAPITAL</b>\n\n"
        f"Total      : <b>${equity:,.2f}</b>\n"
        f"Cash       : ${cash:,.2f} ({cash/equity*100:.1f}%)\n"
        f"Core (90%) : ${core:,.2f}\n"
        f"Satellite  : ${sat:,.2f}\n\n"
        f"🕐 Mis à jour : {updated} UTC"
    )


def cmd_performance():
    tlog   = _load_tlog()
    trades = tlog.get("trades", [])
    closed = [t for t in trades if t["status"] == "closed"]

    if not closed:
        _send("📈 <b>Aucun trade fermé pour l'instant.</b>\n\nReviens après les premiers trades !")
        return

    pnls     = [t.get("pnl", 0) or 0 for t in closed]
    total    = sum(pnls)
    wins     = [p for p in pnls if p > 0]
    losses   = [p for p in pnls if p <= 0]
    win_rate = round(len(wins) / len(closed) * 100)
    best     = max(pnls) if pnls else 0
    worst    = min(pnls) if pnls else 0
    avg_win  = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0

    sign = "+" if total >= 0 else ""
    _send(
        f"📈 <b>AEGIS — PERFORMANCE</b>\n\n"
        f"P&L Total  : <b>{sign}{total:,.2f}$</b>\n"
        f"Win Rate   : <b>{win_rate}%</b> ({len(wins)}W / {len(losses)}L)\n\n"
        f"Meilleur   : +{best:.2f}$\n"
        f"Pire       : {worst:.2f}$\n"
        f"Moy. gain  : +{avg_win:.2f}$\n"
        f"Moy. perte : {avg_loss:.2f}$\n\n"
        f"Total trades: {len(closed)}"
    )


# ── Polling Loop ───────────────────────────────────────────────

COMMANDS = {
    "/status":      cmd_status,
    "/scan":        cmd_scan,
    "/pause":       cmd_pause,
    "/resume":      cmd_resume,
    "/trades":      cmd_trades,
    "/capital":     cmd_capital,
    "/performance": cmd_performance,
}

HELP_TEXT = (
    "⚡ <b>AEGIS — Commandes disponibles</b>\n\n"
    "/status      — État du bot\n"
    "/scan        — Scan immédiat\n"
    "/pause       — Suspendre le trading\n"
    "/resume      — Reprendre le trading\n"
    "/trades      — Derniers trades\n"
    "/capital     — État du capital\n"
    "/performance — Statistiques complètes"
)


def _get_offset() -> int:
    """Récupère le dernier update_id pour ignorer les vieux messages."""
    try:
        resp = requests.get(f"{BASE}/getUpdates", params={"offset": -1}, timeout=10)
        results = resp.json().get("result", [])
        if results:
            return results[-1]["update_id"] + 1
    except Exception:
        pass
    return 0


def run():
    print("[TELEGRAM BOT] Démarré — en écoute des commandes", flush=True)

    # Ignorer tous les messages déjà reçus avant ce démarrage
    offset = _get_offset()
    print(f"[TELEGRAM BOT] Offset initial: {offset}", flush=True)

    while True:
        try:
            resp = requests.get(
                f"{BASE}/getUpdates",
                params={"offset": offset, "timeout": 20},
                timeout=25,
            )
            if not resp.ok:
                time.sleep(5)
                continue

            data = resp.json()
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg    = update.get("message", {})
                if not msg:
                    continue
                text = msg.get("text", "").strip().split()[0].lower()
                cid  = str(msg.get("chat", {}).get("id", ""))

                if cid != CHAT_ID:
                    continue

                print(f"[TELEGRAM BOT] Commande reçue: {text}", flush=True)

                try:
                    if text in COMMANDS:
                        COMMANDS[text]()
                    elif text in ["/start", "/help"]:
                        _send(HELP_TEXT)
                    else:
                        _send("Commande inconnue. Tape /help pour voir les commandes disponibles.")
                except Exception as cmd_err:
                    print(f"[TELEGRAM BOT] Erreur commande {text}: {cmd_err}", flush=True)
                    _send(f"❌ Erreur: {cmd_err}")

        except Exception as e:
            print(f"[TELEGRAM BOT] polling error: {e}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    run()
