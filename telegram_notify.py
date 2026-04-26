"""
Notifications Telegram pour Aegis.
"""
import os
import requests
from datetime import datetime, timezone

TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "8476245241:AAFLK7T0C9A-vuHGbZfDmwPfVep9b0FidhI")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID",   "7863773047")
BASE    = f"https://api.telegram.org/bot{TOKEN}/sendMessage"


def _send(text: str):
    try:
        requests.post(BASE, json={
            "chat_id":    CHAT_ID,
            "text":       text,
            "parse_mode": "HTML",
        }, timeout=10)
    except Exception as e:
        print(f"[TELEGRAM] Erreur envoi: {e}", flush=True)


def trade_opened(asset: str, direction: str, qty: int,
                 entry: float, sl: float, tp: float, rr: float,
                 segment: str, equity: float):
    arrow = "📈" if direction == "long" else "📉"
    seg   = "🔵 CORE" if segment == "core" else "🟣 SATELLITE"
    _send(
        f"{arrow} <b>AEGIS — TRADE OUVERT</b>\n\n"
        f"Actif     : <b>{asset}</b> ({seg})\n"
        f"Direction : <b>{direction.upper()}</b> x{qty}\n"
        f"Entrée    : <b>${entry:,.4f}</b>\n"
        f"Stop Loss : ${sl:,.4f}\n"
        f"Take Profit: ${tp:,.4f}\n"
        f"R:R       : <b>1:{rr}</b>\n\n"
        f"💼 Capital total : <b>${equity:,.2f}</b>"
    )


def trade_closed(asset: str, direction: str, reason: str,
                 entry: float, exit_price: float, pnl: float,
                 equity: float, total_trades: int, win_rate: float):
    emoji  = "✅" if pnl >= 0 else "❌"
    result = "PROFIT" if pnl >= 0 else "PERTE"
    sign   = "+" if pnl >= 0 else ""
    _send(
        f"{emoji} <b>AEGIS — TRADE FERMÉ</b>\n\n"
        f"Actif     : <b>{asset}</b>\n"
        f"Direction : {direction.upper()} | {reason.upper()}\n"
        f"Entrée    : ${entry:,.4f}\n"
        f"Sortie    : ${exit_price:,.4f}\n\n"
        f"{'💰' if pnl >= 0 else '💸'} <b>{result} : {sign}{pnl:,.2f}$</b>\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"💼 Capital total : <b>${equity:,.2f}</b>\n"
        f"📊 Trades fermés : {total_trades}\n"
        f"🎯 Win rate      : {win_rate:.0f}%"
    )


def kill_switch(reason: str):
    _send(
        f"⚠️ <b>AEGIS — KILL SWITCH ACTIVÉ</b>\n\n"
        f"Raison : {reason}\n\n"
        f"🔴 Tous les trades suspendus. En attente de normalisation."
    )


def kill_switch_clear():
    _send("✅ <b>AEGIS — Kill Switch DÉSACTIVÉ</b>\n\nMarchés normalisés. Reprise du scan.")


def scan_summary(assets: dict, equity: float, open_positions: int):
    lines = ["🔍 <b>AEGIS — Scan Horaire</b>\n"]
    for name, d in assets.items():
        rsi   = d.get("rsi", 0)
        trend = d.get("trend", "")
        bias  = d.get("bias", "")
        price = d.get("price", 0)
        t_icon = "▲" if trend == "bull" else "▼" if trend == "bear" else "→"
        lines.append(f"{t_icon} <b>{name}</b> ${price:,.2f} | RSI {rsi} | {bias.upper()}")

    lines.append(f"\n💼 Capital : <b>${equity:,.2f}</b>")
    lines.append(f"📂 Positions ouvertes : {open_positions}")
    _send("\n".join(lines))


def setup_detected(asset: str, direction: str, price: float, rsi: float, label: str):
    arrow = "📈" if direction == "long" else "📉"
    _send(
        f"{arrow} <b>AEGIS — SETUP DÉTECTÉ</b>\n\n"
        f"Actif  : <b>{asset}</b>\n"
        f"Signal : {label}\n"
        f"Prix   : ${price:,.4f}\n"
        f"RSI    : {rsi}\n\n"
        f"⏳ Vérification du sizing et exécution..."
    )


def startup():
    _send(
        "⚡ <b>AEGIS DÉMARRÉ</b>\n\n"
        "Tous les agents sont actifs.\n"
        "Surveillance du marché en cours — scan toutes les heures.\n\n"
        "Actifs surveillés : SPY · GLD · SLV · BTC/USD"
    )
