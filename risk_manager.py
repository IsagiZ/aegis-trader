"""
Risk Manager — position sizing, R:R validation, bracket order parameters.
All logic is pure (no side effects). Broker module handles execution.
"""
from typing import Optional
from config import MAX_RISK_PER_TRADE, MIN_RISK_REWARD, CORE_ALLOCATION, SATELLITE_ALLOCATION


def compute_position(
    total_equity: float,
    segment: str,           # "core" | "satellite"
    entry: float,
    stop_loss: float,
    take_profit: float,
    direction: str,         # "long" | "short"
) -> "Optional[dict]":
    """
    Returns position dict or None if trade fails risk filters.
    {
        shares: int,
        risk_usd: float,
        rr: float,
        entry: float,
        sl: float,
        tp: float,
        segment_equity: float,
    }
    """
    # Allocated capital for this segment
    alloc = CORE_ALLOCATION if segment == "core" else SATELLITE_ALLOCATION
    segment_equity = total_equity * alloc

    # Dollar risk per share
    if direction == "long":
        risk_per_share = entry - stop_loss
        reward_per_share = take_profit - entry
    else:
        risk_per_share = stop_loss - entry
        reward_per_share = entry - take_profit

    if risk_per_share <= 0 or reward_per_share <= 0:
        return None

    rr = reward_per_share / risk_per_share
    if rr < MIN_RISK_REWARD:
        return None

    max_risk_usd = segment_equity * MAX_RISK_PER_TRADE
    shares = int(max_risk_usd / risk_per_share)
    if shares < 1:
        return None

    return {
        "shares": shares,
        "risk_usd": round(shares * risk_per_share, 2),
        "rr": round(rr, 2),
        "entry": entry,
        "sl": stop_loss,
        "tp": take_profit,
        "segment_equity": round(segment_equity, 2),
    }


def validate_structure(entry: float, sl: float, tp: float, direction: str) -> tuple[bool, str]:
    """Quick structural validation before deeper sizing."""
    if direction == "long":
        if sl >= entry:
            return False, "SL must be below entry for long"
        if tp <= entry:
            return False, "TP must be above entry for long"
    else:
        if sl <= entry:
            return False, "SL must be above entry for short"
        if tp >= entry:
            return False, "TP must be below entry for short"
    return True, "ok"
