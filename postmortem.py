"""
Auto post-mortem engine.
Called after every closed trade. Analyzes signals, scores them,
and registers error patterns to block repeated mistakes.
"""
from datetime import datetime, timezone


def analyze(trade: dict, close_reason: str) -> tuple[str, "dict|None"]:
    """
    Returns (analysis_text, error_pattern_or_None).
    close_reason: "tp" | "sl" | "manual"
    """
    won      = close_reason == "tp"
    signals  = trade["planned"].get("signals", {})
    asset    = trade["asset"]
    direction = trade["direction"]
    rr       = trade["planned"].get("rr", 0)
    lines    = []
    error_pattern = None

    if won:
        lines.append(f"WIN via TP. R:R réalisé: {rr}.")
        if signals.get("rsi_signal") == "oversold" and direction == "long":
            lines.append("RSI oversold à l'entrée — signal confirmé valide.")
        if signals.get("rsi_signal") == "overbought" and direction == "short":
            lines.append("RSI overbought à l'entrée short — signal confirmé valide.")
        if signals.get("trend") == "bull" and direction == "long":
            lines.append("Entrée dans le sens du trend bull — edge confirmé.")
        if signals.get("trend") == "bear" and direction == "short":
            lines.append("Entrée dans le sens du trend bear — edge confirmé.")

    else:
        lines.append(f"LOSS via {'SL' if close_reason == 'sl' else 'sortie manuelle'}.")

        # RSI overbought sur un long
        if signals.get("rsi_signal") == "overbought" and direction == "long":
            lines.append("ERREUR: Long entré avec RSI overbought — prix déjà étendu, SL probable.")
            error_pattern = {
                "trigger_signals": {"rsi_signal": "overbought"},
                "bad_value": "overbought",
                "description": f"Long sur {asset} avec RSI overbought → SL systématique",
            }

        # RSI oversold sur un short
        elif signals.get("rsi_signal") == "oversold" and direction == "short":
            lines.append("ERREUR: Short entré avec RSI oversold — prix déjà étendu à la baisse.")
            error_pattern = {
                "trigger_signals": {"rsi_signal": "oversold"},
                "bad_value": "oversold",
                "description": f"Short sur {asset} avec RSI oversold → SL systématique",
            }

        # Entrée contre le trend
        elif signals.get("trend") == "bear" and direction == "long":
            lines.append("ERREUR: Long contre un trend bear — structure de marché défavorable.")
            error_pattern = {
                "trigger_signals": {"trend": "bear"},
                "bad_value": "bear",
                "description": f"Long sur {asset} contre trend bear → SL systématique",
            }

        elif signals.get("trend") == "bull" and direction == "short":
            lines.append("ERREUR: Short contre un trend bull — structure de marché défavorable.")
            error_pattern = {
                "trigger_signals": {"trend": "bull"},
                "bad_value": "bull",
                "description": f"Short sur {asset} contre trend bull → SL systématique",
            }

        else:
            lines.append("Conditions d'entrée correctes — setup valide mais marché adverse. Pas d'error pattern enregistré.")

    return " ".join(lines), error_pattern


def build_signal_key(asset: str, direction: str, signal_name: str, signal_val: str) -> str:
    return f"{asset}:{direction}:{signal_name}:{signal_val}"


def update_signal_scores(log_data: dict, trade: dict, close_reason: str) -> dict:
    """
    Updates signal win/loss scores in trading_log.json.
    Blacklists any signal with ≥3 losses and >65% loss rate.
    """
    won     = close_reason == "tp"
    asset   = trade["asset"]
    direction = trade["direction"]
    signals = trade["planned"].get("signals", {})

    scores = log_data.setdefault("signal_scores", {})

    for sig_name, sig_val in signals.items():
        key = build_signal_key(asset, direction, sig_name, str(sig_val))
        entry = scores.setdefault(key, {"wins": 0, "losses": 0, "blacklisted": False})

        if won:
            entry["wins"] += 1
        else:
            entry["losses"] += 1

        # Blacklist check
        total = entry["wins"] + entry["losses"]
        if total >= 3:
            loss_rate = entry["losses"] / total
            entry["blacklisted"] = loss_rate > 0.65
            if entry["blacklisted"]:
                entry["blacklisted_at"] = datetime.now(timezone.utc).isoformat()

    return log_data


def is_signal_blacklisted(log_data: dict, asset: str, direction: str, signals: dict) -> "str|None":
    """Returns reason string if any signal is blacklisted, else None."""
    scores = log_data.get("signal_scores", {})
    for sig_name, sig_val in signals.items():
        key = build_signal_key(asset, direction, sig_name, str(sig_val))
        entry = scores.get(key)
        if entry and entry.get("blacklisted"):
            total = entry["wins"] + entry["losses"]
            rate  = entry["losses"] / total * 100
            return f"Signal blacklisté [{key}] — {rate:.0f}% loss rate sur {total} trades"
    return None
