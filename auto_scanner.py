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

from market_monitor import run_market_scan, TechnicalSnapshot, get_4h_bias
from broker import (
    get_account, get_positions, get_open_symbols,
    submit_bracket_order, detect_close_reason, get_filled_entry_price,
    close_position, close_partial_position, get_live_price, CRYPTO_SYMBOLS,
)
from risk_manager import compute_position, validate_structure
from trading_logger import (
    pre_trade_check, log_pre_trade, open_trade,
    close_trade, write_post_mortem, log_kill_switch,
    update_portfolio_snapshot, get_open_trades,
    get_consecutive_losses, add_cooldown, is_in_cooldown,
)
from postmortem import analyze, update_signal_scores, is_signal_blacklisted
from config import (
    CORE_ASSETS, SATELLITE_ASSETS, CORE_ALLOCATION, SATELLITE_ALLOCATION,
    CRYPTO_SL_PCT, EQUITY_SL_PCT,
    TRAIL_BREAKEVEN_PCT, TRAIL_ACTIVE_PCT, TRAIL_DISTANCE_PCT,
    RSI_OB, RSI_OS,
)

SCAN_LOG_PATH         = "scan_log.json"
ACTIVITY_LOG_PATH     = "activity.log"
SCAN_INTERVAL         = 600   # 10 minutes — surveillance positions
SETUP_INTERVAL        = 3600  # 1 heure   — détection nouveaux setups
SETUP_EVERY_N         = SETUP_INTERVAL // SCAN_INTERVAL  # = 6 cycles
REGIME_RANGING_ATR_PCT = 0.8   # ATR% 4H < 0.8% → marché en range → pas de nouveau trade

_log_write_count = 0


# ── Setup Rules ────────────────────────────────────────────────
# Chaque règle définit les conditions d'entrée + les niveaux SL/TP

def _compute_levels(snap: TechnicalSnapshot, direction: str) -> tuple[float, float]:
    """
    SL = % fixe selon l'actif (crypto plus serré que le range 20-bougies).
    TP = entry + 2× le risque (R:R ≥ 2.0 garanti).
    Crypto : SL à 4% → position 2-3× plus grande qu'avec le support 20-bougies.
    Equity : SL à 3% ou support structurel si plus proche.
    """
    is_crypto = snap.asset in SATELLITE_ASSETS or "/" in snap.asset
    sl_pct = CRYPTO_SL_PCT if is_crypto else EQUITY_SL_PCT

    if direction == "long":
        sl_pct_level = snap.price * (1 - sl_pct)
        # Pour les equities, prendre le plus conservateur (plus proche de l'entrée)
        sl = max(sl_pct_level, snap.support) if not is_crypto else sl_pct_level
        risk = snap.price - sl
        tp = snap.price + risk * 2.0
    else:
        sl_pct_level = snap.price * (1 + sl_pct)
        sl = min(sl_pct_level, snap.resistance) if not is_crypto else sl_pct_level
        risk = sl - snap.price
        tp = snap.price - risk * 2.0
    return sl, tp


# ── Règles autonomes — direction déterminée par snap.bias + GoldAI ──
# Le bot analyse lui-même chaque actif et décide long ou short.
# Condition unique : le marché doit avoir une direction claire (bias != flat).
SETUP_RULES = {
    "BTC/USD": {
        "asset"      : "BTC/USD",
        "segment"    : "satellite",
        "allow_short": True,    # crypto : long + short OK
    },
    "GLD": {
        "asset"      : "GLD",
        "segment"    : "core",
        "allow_short": False,   # ETF : Alpaca Paper ne supporte pas le short
    },
    "SLV": {
        "asset"      : "SLV",
        "segment"    : "core",
        "allow_short": False,
    },
    "SPY": {
        "asset"      : "SPY",
        "segment"    : "core",
        "allow_short": False,
    },
}


# ── Notification ───────────────────────────────────────────────

def _notify(title: str, message: str):
    from notify import send
    send(title, message)
    _log(f"[NOTIF] {title}: {message}")


def _log(msg: str):
    global _log_write_count
    ts   = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(ACTIVITY_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        _log_write_count += 1
        if _log_write_count % 60 == 0:          # trim toutes les 60 lignes
            with open(ACTIVITY_LOG_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > 400:
                with open(ACTIVITY_LOG_PATH, "w", encoding="utf-8") as f:
                    f.writelines(lines[-400:])
    except Exception:
        pass


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


# ── AI Helpers ─────────────────────────────────────────────────

def _get_adaptive_rsi_thresholds(tlog: dict, asset: str) -> tuple[float, float]:
    """
    Compute per-asset RSI thresholds from closed trade history.
    If losses cluster at high RSI → lower the OB threshold.
    Returns (ob_threshold, os_threshold).
    """
    closed = [
        t for t in tlog.get("trades", [])
        if t["asset"] == asset and t["status"] == "closed" and t.get("pnl") is not None
    ]
    if len(closed) < 5:
        return RSI_OB, RSI_OS

    loss_rsi = []
    for t in closed:
        rsi_val = t.get("planned", {}).get("signals", {}).get("rsi")
        if rsi_val is not None and t["pnl"] < 0:
            loss_rsi.append(float(rsi_val))

    if len(loss_rsi) < 3:
        return RSI_OB, RSI_OS

    avg = sum(loss_rsi) / len(loss_rsi)
    ob = max(60.0, avg - 5) if avg > 65 else RSI_OB
    os_ = min(40.0, avg + 5) if avg < 35 else RSI_OS
    return round(ob, 1), round(os_, 1)


def _claude_pretrade_check(asset: str, direction: str, snap: TechnicalSnapshot,
                            sl: float, tp: float, account: dict) -> tuple[bool, str]:
    """
    Calls Claude Haiku to validate the trade. Returns (approved, reason).
    Fails open if API is unavailable.
    """
    try:
        import anthropic
        rr = round(
            (tp - snap.price) / (snap.price - sl) if direction == "long"
            else (snap.price - tp) / (sl - snap.price),
            2
        )
        prompt = (
            f"Tu es un analyste quantitatif. Évalue ce setup et réponds "
            f"UNIQUEMENT par 'APPROUVÉ' ou 'REJETÉ' + une raison courte (≤ 2 lignes).\n\n"
            f"Asset: {asset} | Direction: {direction.upper()}\n"
            f"Prix: {snap.price} | SL: {sl} ({abs(snap.price-sl)/snap.price*100:.1f}%) | "
            f"TP: {tp} | R:R={rr}\n"
            f"RSI 1D: {snap.rsi:.1f} ({snap.rsi_signal}) | Trend 1D: {snap.trend}\n"
            f"EMA20={snap.ema20:.2f} EMA50={snap.ema50:.2f} EMA200={snap.ema200:.2f}\n"
            f"Equity: ${account['equity']:.0f}\n\n"
            f"Critères: R:R ≥ 2, direction cohérente avec trend, RSI hors zone extrême."
        )
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        response = msg.content[0].text.strip()
        approved = "APPROUVÉ" in response.upper() or "APPROUVE" in response.upper()
        return approved, response
    except Exception as e:
        return True, f"Claude API indisponible ({e}) — filtre désactivé"


# ── Position Monitor ───────────────────────────────────────────

def _update_trailing_sl(trade_id: str, new_sl: float):
    """Met à jour le trailing SL dans trading_log.json."""
    tlog = _load_trading_log()
    for t in tlog["trades"]:
        if t["id"] == trade_id:
            t.setdefault("actual", {})["trailing_sl"] = new_sl
            break
    _save_trading_log(tlog)


def _mark_partial_tp(trade_id: str, price: float):
    """Enregistre qu'un TP partiel (50%) a été exécuté."""
    tlog = _load_trading_log()
    for t in tlog["trades"]:
        if t["id"] == trade_id:
            t.setdefault("actual", {})["partial_tp_done"]  = True
            t["actual"]["partial_tp_price"] = price
            break
    _save_trading_log(tlog)


def _close_and_log(trade: dict, exit_price: float, reason: str):
    """Ferme une position dans le log, écrit le post-mortem et notifie."""
    entry = trade["actual"].get("entry") or trade["planned"]["entry"]
    qty   = trade["planned"].get("shares", 1)
    if trade["direction"] == "long":
        pnl = (exit_price - entry) * qty
    else:
        pnl = (entry - exit_price) * qty
    pnl = round(pnl, 2)
    close_trade(trade["id"], exit_price, reason, pnl)

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

    # ── Cooldown automatique après pertes consécutives ────────
    if pnl < 0:
        consecutive = get_consecutive_losses(trade["asset"])
        if consecutive >= 2:
            add_cooldown(trade["asset"], hours=24)
            _log(f"  ⏸ COOLDOWN 24h activé sur {trade['asset']} — {consecutive} pertes consécutives")
            import telegram_notify as tg_cool
            try:
                from telegram_notify import _send
                _send(
                    f"⏸ <b>AEGIS COOLDOWN</b> — {trade['asset']}\n"
                    f"{consecutive} pertes consécutives détectées.\n"
                    f"Pause de 24h avant de retenter sur cet actif."
                )
            except Exception:
                pass


def monitor_open_positions(log_data: dict):
    """
    Surveille les positions ouvertes.
    - Équités : détecte la fermeture via bracket order Alpaca.
    - Crypto  : vérifie proactivement SL/TP et ferme manuellement si atteint
                (Alpaca n'accepte pas les bracket orders pour le crypto).
    """
    open_in_log    = get_open_trades()
    open_on_alpaca = get_open_symbols()
    positions_map  = {p["symbol"]: p for p in get_positions()}

    for trade in open_in_log:
        symbol    = trade["asset"].replace("/", "")   # BTC/USD → BTCUSD
        check_sym = symbol if trade["asset"] in SATELLITE_ASSETS else trade["asset"]
        is_crypto = symbol in CRYPTO_SYMBOLS or trade["asset"] in CRYPTO_SYMBOLS

        still_open = check_sym in open_on_alpaca or trade["asset"] in open_on_alpaca

        if not still_open:
            # Position fermée par Alpaca (bracket ordre équité exécuté)
            planned_sl = trade["planned"]["sl"]
            planned_tp = trade["planned"]["tp"]
            reason, exit_price = detect_close_reason(symbol, planned_sl, planned_tp)
            if exit_price == 0.0:
                exit_price = planned_tp if reason == "tp" else planned_sl
            _close_and_log(trade, exit_price, reason)

        elif is_crypto and still_open:
            # Crypto sans bracket : vérifier SL/TP + trailing stop manuellement
            pos = positions_map.get(check_sym) or positions_map.get(trade["asset"])
            if not pos:
                continue
            current   = pos["current_price"]
            entry     = trade["actual"].get("entry") or trade["planned"]["entry"]
            direction = trade["direction"]
            pl_tp     = trade["planned"]["tp"]

            # ── Trailing Stop Logic ────────────────────────────
            # SL effectif = max(planned_sl, trailing_sl stocké dans actual)
            active_sl = trade["actual"].get("trailing_sl") or trade["planned"]["sl"]
            profit_pct = (current - entry) / entry if direction == "long" else (entry - current) / entry

            new_sl = active_sl  # par défaut, SL inchangé

            if profit_pct >= TRAIL_ACTIVE_PCT:
                # +5% → trailing à 2% sous le prix actuel
                trail_sl = current * (1 - TRAIL_DISTANCE_PCT) if direction == "long" \
                           else current * (1 + TRAIL_DISTANCE_PCT)
                if trail_sl > active_sl if direction == "long" else trail_sl < active_sl:
                    new_sl = round(trail_sl, 2)
                    _log(f"  {trade['asset']} trailing SL mis à jour : {active_sl:.2f} → {new_sl:.2f} (profit {profit_pct*100:.1f}%)")

            elif profit_pct >= TRAIL_BREAKEVEN_PCT and active_sl < entry:
                # +3% → SL remonte au breakeven (entrée)
                new_sl = round(entry, 2)
                _log(f"  {trade['asset']} SL breakeven activé : {active_sl:.2f} → {new_sl:.2f} (profit {profit_pct*100:.1f}%)")

            # Sauvegarder le nouveau SL si modifié
            if new_sl != active_sl:
                _update_trailing_sl(trade["id"], new_sl)
                import telegram_notify as tg_n
                try:
                    tg_n.trailing_stop_updated(trade["asset"], active_sl, new_sl, current, profit_pct * 100)
                except Exception:
                    pass

            # ── Partial TP à 1R (crypto uniquement) ──────────
            risk         = abs(entry - trade["planned"]["sl"])
            tp_1r        = (entry + risk) if direction == "long" else (entry - risk)
            partial_done = trade["actual"].get("partial_tp_done", False)

            if not partial_done:
                hit_1r = (direction == "long"  and current >= tp_1r) or \
                         (direction == "short" and current <= tp_1r)
                if hit_1r:
                    try:
                        half_qty = round(float(pos["qty"]) / 2, 6)
                        if half_qty > 0:
                            close_partial_position(check_sym, half_qty)
                            _mark_partial_tp(trade["id"], current)
                            _update_trailing_sl(trade["id"], entry)  # SL → breakeven
                            new_sl = entry  # Appliquer immédiatement pour ce cycle
                            _log(f"  {trade['asset']} PARTIAL TP 1R @ {current:.4f} — "
                                 f"{half_qty} unités fermées, SL → breakeven {entry:.4f}")
                            try:
                                from telegram_notify import _send
                                _send(
                                    f"📊 <b>AEGIS PARTIAL TP</b> — {trade['asset']}\n"
                                    f"50% fermé à 1R : {current:.4f}\n"
                                    f"SL déplacé au breakeven : {entry:.4f}\n"
                                    f"50% de la position reste ouverte vers TP={pl_tp:.4f}"
                                )
                            except Exception:
                                pass
                    except Exception as e:
                        _log(f"  Erreur partial TP {trade['asset']}: {e}")

            # ── Vérifier SL/TP ────────────────────────────────
            tp_hit = (direction == "long"  and current >= pl_tp) or \
                     (direction == "short" and current <= pl_tp)
            sl_hit = (direction == "long"  and current <= new_sl) or \
                     (direction == "short" and current >= new_sl)

            if tp_hit or sl_hit:
                reason = "tp" if tp_hit else ("trailing_stop" if new_sl != trade["planned"]["sl"] else "sl")
                _log(f"  {trade['asset']} {reason.upper()} @ {current:.2f} | SL actif={new_sl:.2f} — fermeture")
                try:
                    close_position(check_sym)
                except Exception as e:
                    _log(f"  Erreur fermeture {trade['asset']}: {e}")
                _close_and_log(trade, current, reason)


# ── GoldAI Confirmation Filter ─────────────────────────────────

GOLDAI_CSV = "/Users/arshadgoolamy/Desktop/GoldAI/signals_history.csv"
GOLDAI_ASSET_MAP = {
    "BTC/USD": ["Bitcoin", "BTC"],
    "GLD":     ["Or", "Gold", "XAU"],
    "SLV":     ["Argent", "Silver", "XAG"],
    "SPY":     ["S&P 500", "SP500", "SPY"],
}
GOLDAI_MIN_SCORE = 28   # Score minimum sur 50 pour valider
GOLDAI_MAX_AGE_H = 4    # Ignorer signaux de plus de 4h


def _check_goldai_confirmation(asset: str, direction: str) -> tuple[bool, str]:
    """
    Lit signals_history.csv de GoldAI.
    Retourne (True, raison) si GoldAI confirme la direction, (False, raison) sinon.
    Si GoldAI est indisponible, laisse passer (fail-open).
    """
    import csv
    from datetime import datetime, timezone, timedelta

    try:
        keywords = GOLDAI_ASSET_MAP.get(asset, [asset])
        cutoff   = datetime.now(timezone.utc) - timedelta(hours=GOLDAI_MAX_AGE_H)

        with open(GOLDAI_CSV, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        matching = []
        for row in reversed(rows):   # plus récents en premier
            name = row.get("asset_name", "") + row.get("symbol", "")
            if not any(k.lower() in name.lower() for k in keywords):
                continue
            try:
                ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                if ts < cutoff:
                    continue
            except Exception:
                continue
            matching.append(row)

        if not matching:
            return True, f"GoldAI : aucun signal récent pour {asset} — filtre ignoré"

        latest = matching[0]
        score   = float(latest.get("score", 0))
        decision = latest.get("decision", "").upper()

        is_buy  = "ACHAT" in decision or "BUY" in decision
        is_sell = "VENTE" in decision or "SELL" in decision

        if score < GOLDAI_MIN_SCORE:
            return False, f"GoldAI score trop faible : {score:.0f}/50 < {GOLDAI_MIN_SCORE} requis"

        if direction == "long" and not is_buy:
            return False, f"GoldAI dit {decision} ({score:.0f}/50) — pas de confirmation ACHAT"
        if direction == "short" and not is_sell:
            return False, f"GoldAI dit {decision} ({score:.0f}/50) — pas de confirmation VENTE"

        return True, f"GoldAI {decision} {score:.0f}/50 ✓"

    except FileNotFoundError:
        return True, "GoldAI CSV introuvable — filtre désactivé"
    except Exception as e:
        return True, f"GoldAI indisponible ({e}) — filtre désactivé"


# ── Trade Executor ─────────────────────────────────────────────

def execute_setup(snap: TechnicalSnapshot, rule: dict, account: dict,
                  traded_setups: list, direction: str = None) -> bool:
    """
    Valide et exécute un bracket order pour un setup détecté.
    La direction est déterminée autonomement via snap.bias + GoldAI.
    Retourne True si l'ordre a été soumis.
    """
    asset     = snap.asset
    direction = direction or snap.bias
    segment   = rule["segment"]
    signals   = {
        "rsi_signal" : snap.rsi_signal,
        "trend"      : snap.trend,
        "bias"       : snap.bias,
        "rsi"        : snap.rsi,
        "price_vs_ema20": "above" if snap.price >= snap.ema20 else "below",
    }
    label = (
        f"{asset} {'Long' if direction == 'long' else 'Short'} — "
        f"Analyse autonome : {snap.trend} trend | RSI {snap.rsi:.0f} | "
        f"GoldAI validation"
    )

    # ── Vérifier si le short est autorisé sur cet actif ──────
    if direction == "short" and not rule.get("allow_short", True):
        _log(f"  Skip {asset} short — short non supporté sur cet actif (ETF)")
        return False

    # ── Vérifier le cooldown (pertes consécutives) ────────────
    cooldown_reason = is_in_cooldown(asset)
    if cooldown_reason:
        _log(f"  {asset} EN COOLDOWN — {cooldown_reason}")
        return False

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

    # ── Filtre GoldAI — confirmation croisée ──────────────────
    goldai_ok, goldai_reason = _check_goldai_confirmation(asset, direction)
    if not goldai_ok:
        _log(f"  GOLDAI FILTER: {goldai_reason}")
        return False
    _log(f"  GoldAI confirme: {goldai_reason}")

    # ── Confirmation 4H + Régime de marché ────────────────────
    trend_4h, atr_pct = get_4h_bias(asset)
    if (direction == "long" and trend_4h == "bear") or \
       (direction == "short" and trend_4h == "bull"):
        _log(f"  4H FILTER: trend 4H={trend_4h} opposé à {direction} — bloqué")
        return False
    _log(f"  4H OK: trend={trend_4h} | ATR 4H={atr_pct:.2f}%")

    if atr_pct > 0 and atr_pct < REGIME_RANGING_ATR_PCT:
        _log(f"  RÉGIME RANGE: ATR 4H={atr_pct:.2f}% < {REGIME_RANGING_ATR_PCT}% — marché en range, trade ignoré")
        return False

    # ── RSI Adaptatif par actif ────────────────────────────────
    tlog_for_rsi = _load_trading_log()
    rsi_ob, rsi_os = _get_adaptive_rsi_thresholds(tlog_for_rsi, asset)
    if direction == "long" and snap.rsi > rsi_ob:
        _log(f"  RSI ADAPTATIF: RSI={snap.rsi:.1f} > seuil OB={rsi_ob:.0f} pour {asset} — bloqué")
        return False
    if direction == "short" and snap.rsi < rsi_os:
        _log(f"  RSI ADAPTATIF: RSI={snap.rsi:.1f} < seuil OS={rsi_os:.0f} pour {asset} — bloqué")
        return False
    if rsi_ob != RSI_OB or rsi_os != RSI_OS:
        _log(f"  RSI adaptatif actif pour {asset}: OB={rsi_ob} OS={rsi_os} (défaut: {RSI_OB}/{RSI_OS})")

    # ── Error Pattern Check ────────────────────────────────────
    block = pre_trade_check(asset, direction, label, signals)
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

    # ── Calcul SL / TP avec prix live ─────────────────────────
    live = get_live_price(asset)
    if live and abs(live - snap.price) / snap.price > 0.005:
        _log(f"  Prix rafraîchi {asset}: snapshot={snap.price:.4f} → live={live:.4f}")
        snap = snap.__class__(
            asset=snap.asset, price=live,
            ema20=snap.ema20, ema50=snap.ema50, ema200=snap.ema200,
            rsi=snap.rsi, trend=snap.trend, rsi_signal=snap.rsi_signal,
            support=snap.support, resistance=snap.resistance,
            fib_levels=snap.fib_levels, bias=snap.bias, timestamp=snap.timestamp,
        )
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

    # ── Validation Claude AI ───────────────────────────────────
    claude_ok, claude_reason = _claude_pretrade_check(asset, direction, snap, sl, tp, account)
    if not claude_ok:
        _log(f"  CLAUDE REJETÉ: {claude_reason}")
        _notify(f"AEGIS Claude {asset}", f"Setup rejeté par IA: {claude_reason[:80]}")
        return False
    _log(f"  Claude IA: {claude_reason[:100]}")

    _log(f"  Setup validé: {asset} {direction.upper()} | Qty={pos['shares']} | Entry~{snap.price} SL={sl} TP={tp} R:R={pos['rr']}")

    # ── Log pré-trade ──────────────────────────────────────────
    trade_id = log_pre_trade(
        asset=asset,
        direction=direction,
        entry=snap.price,
        sl=sl,
        tp=tp,
        thesis=label,
        score=signals,
        segment=segment,
    )

    # ── Soumission ordre ───────────────────────────────────────
    try:
        import telegram_notify as tg
        tg.setup_detected(asset, direction, snap.price, signals.get("rsi_signal", ""), label)

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
        # Marquer le trade comme échoué pour ne pas laisser un pending orphelin
        try:
            from datetime import datetime, timezone as _tz
            tlog_err = _load_trading_log()
            for _t in tlog_err["trades"]:
                if _t["id"] == trade_id and _t["status"] == "pending":
                    _t["status"]   = "failed"
                    _t["closed_at"] = datetime.now(_tz.utc).isoformat()
                    _t["pnl"]      = 0
                    _t.setdefault("actual", {})["exit_reason"] = f"order_error: {str(e)[:80]}"
                    break
            _save_trading_log(tlog_err)
        except Exception:
            pass
        return False


# ── Main Scan Cycle ────────────────────────────────────────────

def run_single_scan(log_data: dict, setup_scan: bool = True) -> dict:
    """
    setup_scan=True  → scan complet (positions + nouveaux setups) — toutes les 1h
    setup_scan=False → surveillance positions uniquement           — toutes les 10min
    """
    now_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    mode_tag = "COMPLET" if setup_scan else "POSITIONS"
    _log(f"=== Scan Aegis démarré [{mode_tag}] ===")

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

    if not ks.active and _trading_active and setup_scan:
        _log("Détection des setups...")
        for asset, rule in SETUP_RULES.items():
            snap = snapshot.assets.get(asset)
            if not snap:
                continue

            # ── Décision autonome de direction ────────────────
            # Le bot utilise snap.bias (calculé à partir de trend + RSI)
            # puis valide avec GoldAI avant d'agir.
            direction = snap.bias   # "long" | "short" | "flat"
            _log(f"  {asset}: RSI={snap.rsi:.1f} Trend={snap.trend} → Bias={direction}")

            if direction == "flat":
                _log(f"  {asset} ignoré — marché sans direction claire (RSI extrême ou trend neutre)")
                continue

            executed = execute_setup(snap, rule, account, traded_this_cycle, direction)
            if executed:
                traded_this_cycle.append(f"{asset}:{direction}")
    elif not setup_scan:
        _log("Cycle rapide (10min) — surveillance positions uniquement, pas de nouveaux setups")
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

    # ── 5. Heartbeat Telegram (seulement sur scan complet) ────────
    if setup_scan:
        try:
            import telegram_notify as tg
            open_count = len(get_open_trades())
            tg.heartbeat(account["equity"], open_count, SETUP_INTERVAL // 60)
        except Exception as e:
            _log(f"Heartbeat Telegram échoué: {e}")

    next_min = SCAN_INTERVAL // 60
    _log(f"=== Scan [{mode_tag}] terminé. Prochain dans {next_min}min ===\n")
    return log_data


# ── Entry Point ────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  AEGIS FULL-AUTO SCANNER — Mode Exécution Active")
    print(f"  Positions    : surveillées toutes les {SCAN_INTERVAL//60} min")
    print(f"  Nouveaux trades : détectés toutes les {SETUP_INTERVAL//60} min")
    print("  Press Ctrl+C to stop.")
    print("=" * 55)

    log_data  = _load_scan_log()
    cycle_num = 0

    while True:
        # Scan complet toutes les SETUP_EVERY_N cycles (1h)
        # Scan rapide (positions seulement) tous les autres cycles (10min)
        is_setup_cycle = (cycle_num % SETUP_EVERY_N == 0)

        log_data = run_single_scan(log_data, setup_scan=is_setup_cycle)
        _save_scan_log(log_data)

        cycle_num += 1
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAegis arrêté.")
        sys.exit(0)
