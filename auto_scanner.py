"""
Aegis Auto-Scanner — Full-Auto Mode.
Runs every hour:
  1. Scans market (Kill Switch, setups)
  2. Monitors open positions → closes + runs post-mortem when TP/SL hit
  3. Executes new bracket orders when a setup is validated
"""
import os
import sys
import time
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from notify import send as _notify

os.chdir(Path(__file__).parent)

from market_monitor import run_market_scan, TechnicalSnapshot
from broker import (
    get_account, get_positions, get_open_symbols,
    submit_bracket_order, detect_close_reason, get_filled_entry_price,
)
from risk_manager import compute_position, validate_structure
from trading_logger import (
    pre_trade_check, log_pre_trade, open_trade,
    close_trade, write_post_mortem, log_kill_switch,
    update_portfolio_snapshot, get_open_trades,
)
from postmortem import analyze, update_signal_scores, is_signal_blacklisted
from config import CORE_ASSETS, SATELLITE_ASSETS, CORE_ALLOCATION, SATELLITE_ALLOCATION

SCAN_LOG_PATH = "scan_log.json"
SCAN_INTERVAL = 3600  # 1 heure


# ── Setup Rules ────────────────────────────────────────────────
# Chaque règle définit les conditions d'entrée + les niveaux SL/TP

def _compute_levels(snap: TechnicalSnapshot, direction: str) -> tuple[float, float]:
    """
    Calcule SL et TP à partir de la structure de marché.
    Long  : SL = support,  TP = résistance
    Short : SL = résistance, TP = support
    """
    if direction == "long":
        sl = snap.support
        tp = snap.resistance
    else:
        sl = snap.resistance
        tp = snap.support
    return sl, tp


SETUP_RULES = {
    "BTC/USD": {
        "direction": "long",
        "segment": "satellite",
        "conditions": lambda s: (
            s.rsi < 65 and
            s.trend == "bull" and
            s.price >= s.ema20
        ),
        "label": "BTC Long — RSI normalisé + bull trend + au-dessus EMA20",
        "signals_fn": lambda s: {
            "rsi_signal": s.rsi_signal,
            "trend": s.trend,
            "price_vs_ema20": "above" if s.price >= s.ema20 else "below",
        },
    },
    "GLD": {
        "direction": "short",
        "segment": "core",
        "conditions": lambda s: (
            s.trend == "bear" and
            s.rsi >= 45 and
            abs(s.price - s.resistance) / s.resistance < 0.015
        ),
        "label": "GLD Short — rejet résistance + bear trend",
        "signals_fn": lambda s: {
            "rsi_signal": s.rsi_signal,
            "trend": s.trend,
            "price_vs_resistance": round((s.price - s.resistance) / s.resistance * 100, 2),
        },
    },
    "SLV": {
        "direction": "short",
        "segment": "core",
        "conditions": lambda s: (
            s.trend == "bear" and
            s.rsi >= 45 and
            abs(s.price - s.resistance) / s.resistance < 0.015
        ),
        "label": "SLV Short — rejet résistance + bear trend",
        "signals_fn": lambda s: {
            "rsi_signal": s.rsi_signal,
            "trend": s.trend,
            "price_vs_resistance": round((s.price - s.resistance) / s.resistance * 100, 2),
        },
    },
    "SPY": {
        "direction": "long",
        "segment": "core",
        "conditions": lambda s: (
            s.rsi < 65 and
            s.trend == "bull"
        ),
        "label": "SPY Long — RSI normalisé + bull trend",
        "signals_fn": lambda s: {
            "rsi_signal": s.rsi_signal,
            "trend": s.trend,
        },
    },
}


# ── Notification ───────────────────────────────────────────────

def _notify(title: str, message: str):
    from notify import send
    send(title, message)
    _log(f"[NOTIF] {title}: {message}")


def _log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── Scan Log ───────────────────────────────────────────────────

def _load_scan_log() -> dict:
    p = Path(SCAN_LOG_PATH)
    if not p.exists():
        return {"scans": [], "last_kill_switch": False, "last_setups": [], "traded_setups": []}
    with open(p) as f:
        return json.load(f)


def _save_scan_log(data: dict):
    with open(SCAN_LOG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _load_trading_log() -> dict:
    p = Path("trading_log.json")
    with open(p) as f:
        return json.load(f)


def _save_trading_log(data: dict):
    with open("trading_log.json", "w") as f:
        json.dump(data, f, indent=2)


# ── Position Monitor ───────────────────────────────────────────

def monitor_open_positions(log_data: dict):
    """
    Compare positions ouvertes dans le log vs Alpaca.
    Si une position a disparu d'Alpaca → TP ou SL touché → post-mortem auto.
    """
    open_in_log   = get_open_trades()
    open_on_alpaca = get_open_symbols()

    for trade in open_in_log:
        symbol = trade["asset"].replace("/", "")  # BTC/USD → BTCUSD pour Alpaca
        alpaca_sym = trade["asset"] if trade["asset"] in ["BTC/USD"] else trade["asset"]

        # Normaliser : Alpaca renvoie BTCUSD pas BTC/USD
        check_sym = symbol if trade["asset"] in SATELLITE_ASSETS else trade["asset"]

        if check_sym not in open_on_alpaca and trade["asset"] not in open_on_alpaca:
            # Position fermée sur Alpaca
            planned_sl = trade["planned"]["sl"]
            planned_tp = trade["planned"]["tp"]

            # Détecter TP vs SL
            reason, exit_price = detect_close_reason(
                symbol, planned_sl, planned_tp
            )
            if exit_price == 0.0:
                exit_price = planned_tp if reason == "tp" else planned_sl

            # Calculer P&L
            entry = trade["actual"].get("entry") or trade["planned"]["entry"]
            qty   = trade["planned"].get("shares", 1)
            if trade["direction"] == "long":
                pnl = (exit_price - entry) * qty
            else:
                pnl = (entry - exit_price) * qty

            pnl = round(pnl, 2)
            close_trade(trade["id"], exit_price, reason, pnl)

            # Post-mortem automatique
            tlog = _load_trading_log()
            closed_trade = next((t for t in tlog["trades"] if t["id"] == trade["id"]), None)
            if closed_trade:
                analysis_text, error_pattern = analyze(closed_trade, reason)
                write_post_mortem(trade["id"], analysis_text, error_pattern)
                tlog = _load_trading_log()
                tlog = update_signal_scores(tlog, closed_trade, reason)
                _save_trading_log(tlog)

            emoji = "✅" if reason == "tp" else "❌"
            _notify(
                f"AEGIS {emoji} {trade['asset']} fermé",
                f"{reason.upper()} | P&L: {'+'if pnl>=0 else ''}{pnl:.2f}$ | {trade['direction'].upper()}"
            )
            _log(f"Position fermée: {trade['asset']} | {reason.upper()} | P&L: {pnl:+.2f}$")


# ── Trade Executor ─────────────────────────────────────────────

def execute_setup(snap: TechnicalSnapshot, rule: dict, account: dict, traded_setups: list) -> bool:
    """
    Valide et exécute un bracket order pour un setup détecté.
    Retourne True si l'ordre a été soumis.
    """
    asset     = snap.asset
    direction = rule["direction"]
    segment   = rule["segment"]
    signals   = rule["signals_fn"](snap)

    # ── Vérifier qu'on ne trade pas déjà cet actif ────────────
    open_syms = get_open_symbols()
    check = asset.replace("/", "")
    if asset in open_syms or check in open_syms:
        _log(f"  Skip {asset} — position déjà ouverte.")
        return False

    # ── Vérifier qu'on n'a pas déjà traité ce setup ce scan ──
    setup_key = f"{asset}:{direction}"
    if setup_key in traded_setups:
        _log(f"  Skip {asset} — déjà tradé dans ce cycle.")
        return False

    # ── Error Pattern Check ────────────────────────────────────
    block = pre_trade_check(asset, direction, rule["label"], signals)
    if block:
        _log(f"  BLOQUÉ: {block}")
        _notify(f"AEGIS BLOQUÉ {asset}", block)
        return False

    # ── Signal Blacklist Check ─────────────────────────────────
    tlog = _load_trading_log()
    blacklist_reason = is_signal_blacklisted(tlog, asset, direction, signals)
    if blacklist_reason:
        _log(f"  BLACKLISTÉ: {blacklist_reason}")
        _notify(f"AEGIS BLACKLIST {asset}", blacklist_reason)
        return False

    # ── Calcul SL / TP ─────────────────────────────────────────
    sl, tp = _compute_levels(snap, direction)

    ok, err = validate_structure(snap.price, sl, tp, direction)
    if not ok:
        _log(f"  Structure invalide pour {asset}: {err}")
        return False

    # ── Position Sizing ────────────────────────────────────────
    pos = compute_position(
        total_equity=account["equity"],
        segment=segment,
        entry=snap.price,
        stop_loss=sl,
        take_profit=tp,
        direction=direction,
    )

    if not pos:
        _log(f"  Position sizing échoué pour {asset} — R:R insuffisant ou taille < 1")
        return False

    _log(f"  Setup validé: {asset} {direction.upper()} | Qty={pos['shares']} | Entry~{snap.price} SL={sl} TP={tp} R:R={pos['rr']}")

    # ── Log pré-trade ──────────────────────────────────────────
    trade_id = log_pre_trade(
        asset=asset,
        direction=direction,
        entry=snap.price,
        sl=sl,
        tp=tp,
        thesis=rule["label"],
        score=signals,
        segment=segment,
    )

    # ── Soumission ordre ───────────────────────────────────────
    try:
        import telegram_notify as tg
        tg.setup_detected(asset, direction, snap.price, signals.get("rsi_signal", ""), rule["label"])

        order = submit_bracket_order(
            symbol=asset,
            qty=pos["shares"],
            direction=direction,
            take_profit=tp,
            stop_loss=sl,
        )
        fill_price = get_filled_entry_price(order["id"]) or snap.price
        open_trade(trade_id, order["id"], fill_price)

        tg.trade_opened(
            asset=asset, direction=direction, qty=pos["shares"],
            entry=fill_price, sl=sl, tp=tp, rr=pos["rr"],
            segment=segment, equity=account["equity"],
        )
        _log(f"  Ordre soumis: {order}")
        return True

    except Exception as e:
        _log(f"  ERREUR soumission ordre {asset}: {e}")
        _notify(f"AEGIS ERREUR {asset}", str(e))
        return False


# ── Main Scan Cycle ────────────────────────────────────────────

def run_single_scan(log_data: dict) -> dict:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _log(f"=== Scan Aegis démarré ===")

    try:
        snapshot  = run_market_scan()
        account   = get_account()
        positions = get_positions()
    except Exception as e:
        _log(f"ERREUR scan marché: {e}")
        return log_data

    # Mise à jour snapshot portefeuille
    update_portfolio_snapshot(
        equity=account["equity"],
        core=account["equity"] * CORE_ALLOCATION,
        satellite=account["equity"] * SATELLITE_ALLOCATION,
        cash=account["cash"],
        open_positions=[p["symbol"] for p in positions],
    )

    # ── 1. Surveiller les positions ouvertes ───────────────────
    _log("Surveillance positions ouvertes...")
    monitor_open_positions(log_data)

    # ── 2. Kill Switch ─────────────────────────────────────────
    ks      = snapshot.kill_switch
    prev_ks = log_data.get("last_kill_switch", False)

    if ks.active and not prev_ks:
        log_kill_switch(ks.reason, ks.vix)
        import telegram_notify as tg
        tg.kill_switch(ks.reason or "Marché irrationnel")

    if not ks.active and prev_ks:
        import telegram_notify as tg
        tg.kill_switch_clear()

    log_data["last_kill_switch"] = ks.active

    # ── 3. Détection et exécution des setups ───────────────────
    traded_this_cycle = log_data.get("traded_setups", [])

    # Vérifier le flag pause
    try:
        import json as _json
        with open("trading_flag.json") as _f:
            _trading_active = _json.load(_f).get("trading_active", True)
    except Exception:
        _trading_active = True

    if not ks.active and _trading_active:
        _log("Détection des setups...")
        for asset, rule in SETUP_RULES.items():
            snap = snapshot.assets.get(asset)
            if not snap:
                continue

            conditions_met = rule["conditions"](snap)
            _log(f"  {asset}: RSI={snap.rsi} Trend={snap.trend} Bias={snap.bias} → Setup={'OUI' if conditions_met else 'non'}")

            if conditions_met:
                executed = execute_setup(snap, rule, account, traded_this_cycle)
                if executed:
                    traded_this_cycle.append(f"{asset}:{rule['direction']}")
    elif not _trading_active:
        _log("Trading SUSPENDU via /pause — aucun trade")
    else:
        _log(f"KILL SWITCH ACTIF: {ks.reason} — aucun trade")

    # Reset traded_setups à chaque nouveau jour
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if log_data.get("trade_date") != today:
        log_data["traded_setups"] = []
        log_data["trade_date"] = today
    else:
        log_data["traded_setups"] = traded_this_cycle

    # ── 4. Enregistrement scan log ─────────────────────────────
    log_data.setdefault("scans", []).append({
        "timestamp": now_str,
        "equity": account["equity"],
        "kill_switch": ks.active,
        "assets": {
            name: {"price": s.price, "rsi": s.rsi, "trend": s.trend, "bias": s.bias}
            for name, s in snapshot.assets.items()
        },
    })
    log_data["scans"] = log_data["scans"][-168:]

    _log(f"=== Scan terminé. Prochain dans {SCAN_INTERVAL // 60}min ===\n")
    return log_data


# ── Entry Point ────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  AEGIS FULL-AUTO SCANNER — Mode Exécution Active")
    print("  Surveillance toutes les heures.")
    print("  Press Ctrl+C to stop.")
    print("=" * 55)

    log_data = _load_scan_log()

    while True:
        log_data = run_single_scan(log_data)
        _save_scan_log(log_data)
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAegis arrêté.")
        sys.exit(0)
