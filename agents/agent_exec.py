"""
EXEC Agent — surveille les positions toutes les 5 minutes.
Détecte les fermetures TP/SL et déclenche les post-mortems.
"""
import os, sys, json, time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(Path(__file__).parent.parent)

from broker import get_open_symbols, detect_close_reason, get_account, get_positions
from trading_logger import get_open_trades, close_trade, write_post_mortem, update_portfolio_snapshot
from postmortem import analyze, update_signal_scores
from shared_state import update_agent, load_state, save_state
from config import CORE_ALLOCATION, SATELLITE_ALLOCATION
import subprocess

INTERVAL = 300  # 5 minutes

def _notify(title, msg):
    from notify import send
    send(title, msg)

def _load_tlog():
    with open("trading_log.json") as f: return json.load(f)

def _save_tlog(data):
    with open("trading_log.json", "w") as f: json.dump(data, f, indent=2)

def run():
    update_agent("EXEC", "ACTIVE", "Démarrage surveillance positions...")
    while True:
        try:
            open_in_log    = get_open_trades()
            open_on_alpaca = get_open_symbols()
            account        = get_account()
            positions      = get_positions()

            update_portfolio_snapshot(
                equity=account["equity"],
                core=account["equity"] * CORE_ALLOCATION,
                satellite=account["equity"] * SATELLITE_ALLOCATION,
                cash=account["cash"],
                open_positions=[p["symbol"] for p in positions],
            )

            closed_count = 0
            for trade in open_in_log:
                symbol = trade["asset"].replace("/", "")
                if trade["asset"] not in open_on_alpaca and symbol not in open_on_alpaca:
                    planned_sl = trade["planned"]["sl"]
                    planned_tp = trade["planned"]["tp"]
                    reason, exit_price = detect_close_reason(symbol, planned_sl, planned_tp)
                    if exit_price == 0.0:
                        exit_price = planned_tp if reason == "tp" else planned_sl

                    entry = trade["actual"].get("entry") or trade["planned"]["entry"]
                    qty   = trade["planned"].get("shares", 1)
                    pnl   = round(((exit_price - entry) if trade["direction"] == "long" else (entry - exit_price)) * qty, 2)

                    close_trade(trade["id"], exit_price, reason, pnl)

                    tlog = _load_tlog()
                    closed_trade = next((t for t in tlog["trades"] if t["id"] == trade["id"]), None)
                    if closed_trade:
                        analysis_text, error_pattern = analyze(closed_trade, reason)
                        write_post_mortem(trade["id"], analysis_text, error_pattern)
                        tlog = _load_tlog()
                        tlog = update_signal_scores(tlog, closed_trade, reason)
                        _save_tlog(tlog)

                    # Telegram résumé complet
                    try:
                        import telegram_notify as tg
                        tlog2 = _load_tlog()
                        all_closed = [t for t in tlog2["trades"] if t["status"] == "closed"]
                        wins = [t for t in all_closed if (t.get("pnl") or 0) > 0]
                        win_rate = round(len(wins) / len(all_closed) * 100) if all_closed else 0
                        entry_price = trade["actual"].get("entry") or trade["planned"]["entry"]
                        tg.trade_closed(
                            asset=trade["asset"],
                            direction=trade["direction"],
                            reason=reason,
                            entry=entry_price,
                            exit_price=exit_price,
                            pnl=pnl,
                            equity=account["equity"],
                            total_trades=len(all_closed),
                            win_rate=win_rate,
                        )
                    except Exception as te:
                        print(f"[TELEGRAM] erreur: {te}", flush=True)
                    closed_count += 1

            state = load_state()
            state["exec"] = {
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "equity": account["equity"],
                "cash": account["cash"],
                "open_positions": len(positions),
                "positions": positions,
            }
            save_state(state)

            msg = f"{len(open_in_log)} position(s) open | {closed_count} fermée(s) ce cycle"
            update_agent("EXEC", "IDLE", msg)

        except Exception as e:
            update_agent("EXEC", "ERROR", str(e))

        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
