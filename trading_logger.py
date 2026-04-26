"""
Persistent trade journal — reads/writes trading_log.json.
Every position goes through pre_trade() → open_trade() → close_trade().
Error patterns are indexed to block repeated mistakes.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from config import TRADING_LOG_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict:
    p = Path(TRADING_LOG_PATH)
    if not p.exists():
        return {"meta": {}, "portfolio_snapshot": {}, "error_patterns": [], "kill_switch_events": [], "trades": []}
    with open(p) as f:
        return json.load(f)


def _save(data: dict):
    with open(TRADING_LOG_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ── Public API ─────────────────────────────────────────────────

def pre_trade_check(asset: str, direction: str, thesis: str, score: dict) -> "Optional[str]":
    """
    Check error_patterns before entry. Returns blocking reason or None if clear.
    thesis  : why we're entering (string)
    score   : dict of signals used (e.g. {"rsi_div": True, "ema_trend": "bull"})
    """
    data = _load()
    for ep in data.get("error_patterns", []):
        if ep["asset"] == asset and ep["direction"] == direction and ep["active"]:
            for trigger in ep["trigger_signals"]:
                if trigger in score and score[trigger] == ep["bad_value"]:
                    return f"BLOCKED by error pattern #{ep['id']}: {ep['description']}"
    return None


def log_pre_trade(asset: str, direction: str, entry: float, sl: float, tp: float,
                  thesis: str, score: dict, segment: str) -> str:
    """Register intent before order submission. Returns trade_id."""
    data = _load()
    trade_id = str(uuid.uuid4())[:8]
    record = {
        "id": trade_id,
        "segment": segment,          # "core" | "satellite"
        "asset": asset,
        "direction": direction,      # "long" | "short"
        "status": "pending",
        "planned": {
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "rr": round((tp - entry) / (entry - sl), 2) if direction == "long" else round((entry - tp) / (sl - entry), 2),
            "thesis": thesis,
            "signals": score,
        },
        "actual": {},
        "post_mortem": None,
        "opened_at": None,
        "closed_at": None,
        "pnl": None,
        "alpaca_order_id": None,
    }
    data["trades"].append(record)
    _save(data)
    return trade_id


def open_trade(trade_id: str, alpaca_order_id: str, fill_price: float):
    data = _load()
    for t in data["trades"]:
        if t["id"] == trade_id:
            t["status"] = "open"
            t["opened_at"] = _now()
            t["alpaca_order_id"] = alpaca_order_id
            t["actual"]["entry"] = fill_price
            break
    _save(data)


def close_trade(trade_id: str, exit_price: float, exit_reason: str, pnl: float):
    data = _load()
    for t in data["trades"]:
        if t["id"] == trade_id:
            t["status"] = "closed"
            t["closed_at"] = _now()
            t["actual"]["exit"] = exit_price
            t["actual"]["exit_reason"] = exit_reason  # "tp" | "sl" | "manual"
            t["pnl"] = pnl
            break
    _save(data)


def write_post_mortem(trade_id: str, analysis: str, error_pattern: "Optional[dict]" = None):
    """
    analysis      : free-text retrospective
    error_pattern : if loss was due to a repeatable mistake, provide:
        {"trigger_signals": {"rsi_div": True}, "bad_value": True, "description": "..."}
    """
    data = _load()
    for t in data["trades"]:
        if t["id"] == trade_id:
            t["post_mortem"] = {"written_at": _now(), "analysis": analysis}
            if error_pattern:
                ep_id = len(data["error_patterns"]) + 1
                data["error_patterns"].append({
                    "id": ep_id,
                    "asset": t["asset"],
                    "direction": t["direction"],
                    "trigger_signals": error_pattern["trigger_signals"],
                    "bad_value": error_pattern.get("bad_value"),
                    "description": error_pattern["description"],
                    "first_seen": _now(),
                    "active": True,
                })
            break
    _save(data)


def log_kill_switch(reason: str, vix: Optional[float] = None):
    data = _load()
    data.setdefault("kill_switch_events", []).append({
        "timestamp": _now(),
        "reason": reason,
        "vix": vix,
    })
    _save(data)


def update_portfolio_snapshot(equity: float, core: float, satellite: float,
                               cash: float, open_positions: list):
    data = _load()
    data["portfolio_snapshot"] = {
        "last_updated": _now(),
        "total_equity": equity,
        "core_equity": core,
        "satellite_equity": satellite,
        "cash": cash,
        "open_positions": open_positions,
    }
    _save(data)


def get_open_trades() -> list:
    return [t for t in _load()["trades"] if t["status"] == "open"]


def get_error_patterns() -> list:
    return [ep for ep in _load().get("error_patterns", []) if ep["active"]]
