"""
Auto post-mortem engine.
Called after every closed trade. Analyzes signals, scores them,
and registers error patterns to block repeated mistakes.
"""
from datetime import datetime, timezone


def analyze(trade: dict, close_reason: str) -> tuple[str, "dict|None"]:
    """
    Returns (analysis_text, error_pattern_or_None).
    close_reason: "tp" | "sl" | "trailing_stop" | "manual"
    """
    won       = close_reason == "tp"
    signals   = trade["planned"].get("signals", {})
    asset     = trade["asset"]
    direction = trade["direction"]
    rr        = trade["planned"].get("rr", 0)
    rsi_val   = float(signals.get("rsi", 50))
    trend     = signals.get("trend", "neutral")
    rsi_sig   = signals.get("rsi_signal", "neutral")
    ema_pos   = signals.get("price_vs_ema20", "above")

    lines = []
    error_pattern = None

    # ── Durée du trade ────────────────────────────────────────
    opened_at  = trade.get("opened_at")
    closed_at  = trade.get("closed_at")
    held_hours = None
    if opened_at and closed_at:
        try:
            t0 = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
            held_hours = (t1 - t0).total_seconds() / 3600
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════
    #  CAS 1 : WIN
    # ══════════════════════════════════════════════════════════
    if won:
        lines.append(f"WIN via TP. R:R réalisé: {rr}.")
        if rsi_sig == "oversold" and direction == "long":
            lines.append("RSI oversold à l'entrée — signal confirmé valide.")
        if rsi_sig == "overbought" and direction == "short":
            lines.append("RSI overbought à l'entrée short — signal confirmé valide.")
        if trend == "bull" and direction == "long":
            lines.append("Entrée dans le sens du trend bull — edge confirmé.")
        if trend == "bear" and direction == "short":
            lines.append("Entrée dans le sens du trend bear — edge confirmé.")
        if held_hours and held_hours < 6:
            lines.append(f"Trade rapide ({held_hours:.1f}h) — bon timing d'entrée.")
        return " ".join(lines), None

    # ══════════════════════════════════════════════════════════
    #  CAS 2 : LOSS — Détection élargie des patterns d'erreur
    # ══════════════════════════════════════════════════════════
    exit_reason_label = "SL" if close_reason == "sl" else \
                        "trailing stop" if close_reason == "trailing_stop" else "sortie manuelle"
    lines.append(f"LOSS via {exit_reason_label}.")

    # Durée très courte = mauvais timing d'entrée
    if held_hours is not None and held_hours < 2:
        lines.append(f"Trade fermé en {held_hours:.1f}h seulement — très mauvais timing d'entrée.")
        error_pattern = {
            "trigger_signals": {"trend": trend, "rsi_signal": rsi_sig},
            "bad_value": rsi_sig,
            "description": f"{asset} {direction} fermé en <2h — setup prématuré (RSI={rsi_val:.0f}, trend={trend})",
        }

    # RSI étendu sur un long (>65) même si label "neutral"
    elif direction == "long" and rsi_val >= 65:
        lines.append(f"ERREUR: Long entré avec RSI={rsi_val:.0f} (>65) — momentum étendu, rebond déjà en place.")
        error_pattern = {
            "trigger_signals": {"rsi_signal": rsi_sig, "trend": trend},
            "bad_value": rsi_sig,
            "description": f"Long {asset} avec RSI≥65 ({rsi_val:.0f}) → SL fréquent, attendre pullback",
        }

    # RSI bas sur un short (<35) même si label "neutral"
    elif direction == "short" and rsi_val <= 35:
        lines.append(f"ERREUR: Short entré avec RSI={rsi_val:.0f} (<35) — prix déjà survendu.")
        error_pattern = {
            "trigger_signals": {"rsi_signal": rsi_sig, "trend": trend},
            "bad_value": rsi_sig,
            "description": f"Short {asset} avec RSI≤35 ({rsi_val:.0f}) → SL fréquent, attendre rebond",
        }

    # RSI explicitement overbought sur un long
    elif rsi_sig == "overbought" and direction == "long":
        lines.append("ERREUR: Long entré avec RSI overbought — prix déjà étendu, SL probable.")
        error_pattern = {
            "trigger_signals": {"rsi_signal": "overbought"},
            "bad_value": "overbought",
            "description": f"Long sur {asset} avec RSI overbought → SL systématique",
        }

    # RSI explicitement oversold sur un short
    elif rsi_sig == "oversold" and direction == "short":
        lines.append("ERREUR: Short entré avec RSI oversold — prix déjà étendu à la baisse.")
        error_pattern = {
            "trigger_signals": {"rsi_signal": "oversold"},
            "bad_value": "oversold",
            "description": f"Short sur {asset} avec RSI oversold → SL systématique",
        }

    # Entrée contre le trend
    elif trend == "bear" and direction == "long":
        lines.append("ERREUR: Long contre un trend bear — structure de marché défavorable.")
        error_pattern = {
            "trigger_signals": {"trend": "bear"},
            "bad_value": "bear",
            "description": f"Long sur {asset} contre trend bear → SL systématique",
        }

    elif trend == "bull" and direction == "short":
        lines.append("ERREUR: Short contre un trend bull — structure de marché défavorable.")
        error_pattern = {
            "trigger_signals": {"trend": "bull"},
            "bad_value": "bull",
            "description": f"Short sur {asset} contre trend bull → SL systématique",
        }

    # Long alors que prix sous EMA20 (tendance baissière court terme)
    elif direction == "long" and ema_pos == "below":
        lines.append("AVERTISSEMENT: Long entré avec prix sous EMA20 — pas d'élan haussier immédiat.")
        error_pattern = {
            "trigger_signals": {"price_vs_ema20": "below", "trend": trend},
            "bad_value": "below",
            "description": f"Long {asset} avec prix sous EMA20 → structure défavorable",
        }

    # Short alors que prix au-dessus EMA20
    elif direction == "short" and ema_pos == "above":
        lines.append("AVERTISSEMENT: Short entré avec prix au-dessus EMA20 — élan encore haussier.")
        error_pattern = {
            "trigger_signals": {"price_vs_ema20": "above", "trend": trend},
            "bad_value": "above",
            "description": f"Short {asset} avec prix au-dessus EMA20 → structure défavorable",
        }

    # Trailing stop déclenché = bonne entrée mais gestion sortie à améliorer
    elif close_reason == "trailing_stop":
        lines.append("Trailing stop déclenché — entrée correcte mais prix est revenu après profit partiel.")
        lines.append("Considérer un trailing plus large ou TP partiel avant trailing.")

    else:
        lines.append(f"Setup valide (RSI={rsi_val:.0f}, trend={trend}) mais marché adverse. Volatilité imprévue.")

    if held_hours:
        lines.append(f"Durée: {held_hours:.1f}h.")

    return " ".join(lines), error_pattern


def build_signal_key(asset: str, direction: str, signal_name: str, signal_val: str) -> str:
    return f"{asset}:{direction}:{signal_name}:{signal_val}"


def update_signal_scores(log_data: dict, trade: dict, close_reason: str) -> dict:
    """
    Updates signal win/loss scores in trading_log.json.
    Blacklists any signal with ≥3 losses and >65% loss rate.
    """
    won       = close_reason == "tp"
    asset     = trade["asset"]
    direction = trade["direction"]
    signals   = trade["planned"].get("signals", {})

    scores = log_data.setdefault("signal_scores", {})

    for sig_name, sig_val in signals.items():
        key   = build_signal_key(asset, direction, sig_name, str(sig_val))
        entry = scores.setdefault(key, {"wins": 0, "losses": 0, "blacklisted": False})

        if won:
            entry["wins"] += 1
        else:
            entry["losses"] += 1

        total = entry["wins"] + entry["losses"]
        if total >= 3:
            loss_rate            = entry["losses"] / total
            entry["blacklisted"] = loss_rate > 0.65
            if entry["blacklisted"]:
                entry["blacklisted_at"] = datetime.now(timezone.utc).isoformat()

    return log_data


def is_signal_blacklisted(log_data: dict, asset: str, direction: str, signals: dict) -> "str|None":
    """Returns reason string if any signal is blacklisted, else None."""
    scores = log_data.get("signal_scores", {})
    for sig_name, sig_val in signals.items():
        key   = build_signal_key(asset, direction, sig_name, str(sig_val))
        entry = scores.get(key)
        if entry and entry.get("blacklisted"):
            total = entry["wins"] + entry["losses"]
            rate  = entry["losses"] / total * 100
            return f"Signal blacklisté [{key}] — {rate:.0f}% loss rate sur {total} trades"
    return None
