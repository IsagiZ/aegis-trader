"""
Broker module — MetaTrader 5 execution.
Drop-in replacement pour broker.py (Alpaca).

Prérequis Windows :
  pip install MetaTrader5
  MT5 terminal doit être ouvert et connecté au compte démo.
"""
import time
from datetime import datetime, timezone, timedelta

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

# ── Mapping symboles Aegis → MT5 ───────────────────────────────
# Ajuste selon ton broker (XM, IC Markets, Pepperstone…)
SYMBOL_MAP = {
    "BTC/USD": "BTCUSD",
    "GLD":     "XAUUSD",   # or
    "SLV":     "XAGUSD",   # argent
    "SPY":     "US500",    # S&P 500 CFD — certains brokers: "SP500", "SPX500"
}
REVERSE_MAP     = {v: k for k, v in SYMBOL_MAP.items()}
CRYPTO_SYMBOLS  = {"BTCUSD", "BTC/USD"}
MAGIC_NUMBER    = 234000   # identifiant unique des ordres Aegis dans MT5


def _mt5(symbol: str) -> str:
    """Convertit symbole Aegis → symbole MT5."""
    return SYMBOL_MAP.get(symbol, symbol)


def _aegis(symbol: str) -> str:
    """Convertit symbole MT5 → symbole Aegis."""
    return REVERSE_MAP.get(symbol, symbol)


def _ensure_connected():
    if not MT5_AVAILABLE:
        raise RuntimeError("MetaTrader5 non installé — pip install MetaTrader5")
    if not mt5.terminal_info():
        if not mt5.initialize():
            raise RuntimeError(f"MT5 non connecté : {mt5.last_error()}\n"
                               "Ouvre MetaTrader 5 et connecte-toi à ton compte démo.")


def _lots_from_risk(symbol_mt5: str, entry: float, sl: float, risk_usd: float) -> float:
    """
    Calcule le nombre de lots pour risquer exactement risk_usd$.
    Formula : lots = risk_usd / (sl_distance × contract_size × tick_value/tick_size)
    """
    _ensure_connected()
    info = mt5.symbol_info(symbol_mt5)
    if not info:
        return 0.01   # lot minimum par défaut

    sl_distance  = abs(entry - sl)
    if sl_distance == 0:
        return info.volume_min

    # Valeur monétaire d'un mouvement de 1 point pour 1 lot
    tick_value   = info.trade_tick_value  # $ par tick pour 1 lot
    tick_size    = info.trade_tick_size   # taille du tick en prix
    point_value  = (tick_value / tick_size) if tick_size else 1.0

    risk_per_lot = sl_distance * point_value
    if risk_per_lot <= 0:
        return info.volume_min

    lots = risk_usd / risk_per_lot
    step = info.volume_step or 0.01
    lots = round(lots / step) * step
    lots = max(info.volume_min, min(info.volume_max, lots))
    return round(lots, 2)


# ── Public API ─────────────────────────────────────────────────

def get_live_price(symbol: str) -> float:
    """Prix live depuis MT5."""
    _ensure_connected()
    sym  = _mt5(symbol)
    tick = mt5.symbol_info_tick(sym)
    if tick:
        return float((tick.bid + tick.ask) / 2)
    return None


def get_account() -> dict:
    _ensure_connected()
    info = mt5.account_info()
    if not info:
        raise RuntimeError(f"MT5 account_info() failed: {mt5.last_error()}")
    return {
        "equity":       float(info.equity),
        "cash":         float(info.balance),
        "buying_power": float(info.margin_free),
    }


def get_positions() -> list:
    _ensure_connected()
    positions = mt5.positions_get() or []
    result = []
    for p in positions:
        symbol_aegis = _aegis(p.symbol)
        side         = "long" if p.type == mt5.POSITION_TYPE_BUY else "short"
        result.append({
            "symbol":          symbol_aegis,
            "qty":             float(p.volume),
            "side":            side,
            "avg_entry":       float(p.price_open),
            "current_price":   float(p.price_current),
            "market_value":    float(p.volume * p.price_current),
            "unrealized_pl":   float(p.profit),
            "unrealized_plpc": float(p.profit / (p.price_open * p.volume)) if p.price_open else 0,
            "_mt5_ticket":     p.ticket,
        })
    return result


def get_open_symbols() -> set:
    return {p["symbol"] for p in get_positions()}


def submit_bracket_order(
    symbol: str,
    qty: float,         # nombre de lots ou "risk shares" depuis risk_manager
    direction: str,     # "long" | "short"
    take_profit: float,
    stop_loss: float,
) -> dict:
    """
    Envoie un ordre marché avec SL et TP intégrés.
    qty est interprété comme le nombre de lots.
    """
    _ensure_connected()
    sym  = _mt5(symbol)
    info = mt5.symbol_info(sym)
    if not info:
        raise ValueError(f"Symbole MT5 inconnu : {sym}. Vérifie SYMBOL_MAP dans broker_mt5.py")
    if not info.visible:
        mt5.symbol_select(sym, True)

    tick = mt5.symbol_info_tick(sym)
    if not tick:
        raise RuntimeError(f"Impossible d'obtenir le prix pour {sym}")

    order_type = mt5.ORDER_TYPE_BUY  if direction == "long" else mt5.ORDER_TYPE_SELL
    price      = tick.ask            if direction == "long" else tick.bid

    # S'assurer que le volume respecte les contraintes du broker
    step = info.volume_step or 0.01
    volume = max(info.volume_min, round(float(qty) / step) * step)
    volume = min(volume, info.volume_max)

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       sym,
        "volume":       volume,
        "type":         order_type,
        "price":        price,
        "sl":           round(float(stop_loss),   info.digits),
        "tp":           round(float(take_profit), info.digits),
        "deviation":    30,
        "magic":        MAGIC_NUMBER,
        "comment":      "Aegis",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code = result.retcode if result else "?"
        msg  = result.comment if result else mt5.last_error()
        raise RuntimeError(f"MT5 order_send() échoué (code {code}): {msg}")

    return {
        "id":     str(result.order),
        "symbol": symbol,
        "qty":    volume,
        "side":   direction,
        "status": "filled",
        "type":   "market",
    }


def get_filled_entry_price(order_id: str) -> float:
    """Récupère le prix de fill depuis l'historique MT5."""
    _ensure_connected()
    try:
        deals = mt5.history_deals_get(
            datetime.now(timezone.utc) - timedelta(hours=1),
            datetime.now(timezone.utc),
        ) or []
        for d in deals:
            if str(d.order) == str(order_id) and d.price > 0:
                return float(d.price)
    except Exception:
        pass
    return 0.0


def close_position(symbol: str):
    """Ferme toute la position sur un symbole."""
    _ensure_connected()
    sym       = _mt5(symbol)
    positions = mt5.positions_get(symbol=sym) or []
    for pos in positions:
        direction  = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick       = mt5.symbol_info_tick(sym)
        close_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       sym,
            "volume":       pos.volume,
            "type":         direction,
            "position":     pos.ticket,
            "price":        close_price,
            "deviation":    30,
            "magic":        MAGIC_NUMBER,
            "comment":      "Aegis close",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        mt5.order_send(request)


def close_partial_position(symbol: str, qty: float):
    """Ferme une partie de la position (partial TP)."""
    _ensure_connected()
    sym       = _mt5(symbol)
    positions = mt5.positions_get(symbol=sym) or []
    if not positions:
        raise ValueError(f"Aucune position MT5 ouverte pour {symbol}")
    pos        = positions[0]
    info       = mt5.symbol_info(sym)
    step       = info.volume_step if info else 0.01
    volume     = max(info.volume_min if info else 0.01, round(qty / step) * step)
    direction  = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    tick       = mt5.symbol_info_tick(sym)
    close_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       sym,
        "volume":       volume,
        "type":         direction,
        "position":     pos.ticket,
        "price":        close_price,
        "deviation":    30,
        "magic":        MAGIC_NUMBER,
        "comment":      "Aegis partial TP",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    mt5.order_send(request)


def detect_close_reason(symbol: str, planned_sl: float, planned_tp: float):
    """Détecte si la position a été fermée par TP ou SL."""
    _ensure_connected()
    try:
        sym   = _mt5(symbol)
        deals = mt5.history_deals_get(
            datetime.now(timezone.utc) - timedelta(hours=48),
            datetime.now(timezone.utc),
        ) or []
        for d in sorted(deals, key=lambda x: x.time, reverse=True):
            if d.symbol == sym and d.entry == mt5.DEAL_ENTRY_OUT and d.price > 0:
                exit_price = float(d.price)
                dist_tp    = abs(exit_price - planned_tp)
                dist_sl    = abs(exit_price - planned_sl)
                reason     = "tp" if dist_tp < dist_sl else "sl"
                return reason, exit_price
    except Exception:
        pass
    return "manual", 0.0
