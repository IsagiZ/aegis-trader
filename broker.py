"""
Broker module — Alpaca Paper Trading execution.
Submits bracket orders (entry + OCO TP/SL in a single call).
"""
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest,
    TakeProfitRequest, StopLossRequest,
    GetOrdersRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY


_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)


def get_live_price(symbol: str):
    """Retourne le prix live depuis Alpaca (dernier trade). Fallback None si indispo."""
    try:
        from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
        from alpaca.data.requests import StockLatestTradeRequest, CryptoLatestTradeRequest

        clean = symbol.replace("/", "")
        if clean in CRYPTO_SYMBOLS or "/" in symbol:
            dc   = CryptoHistoricalDataClient()
            resp = dc.get_crypto_latest_trade(CryptoLatestTradeRequest(symbol_or_symbols=clean))
            return float(resp[clean].price)
        else:
            dc   = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
            resp = dc.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbol))
            return float(resp[symbol].price)
    except Exception:
        return None


def get_account() -> dict:
    acc = _client.get_account()
    return {
        "equity":      float(acc.equity),
        "cash":        float(acc.cash),
        "buying_power": float(acc.buying_power),
    }


def get_positions() -> list:
    positions = _client.get_all_positions()
    return [
        {
            "symbol":        p.symbol,
            "qty":           float(p.qty),
            "side":          str(p.side),
            "avg_entry":     float(p.avg_entry_price),
            "current_price": float(p.current_price) if p.current_price else 0.0,
            "market_value":  float(p.market_value),
            "unrealized_pl": float(p.unrealized_pl),
            "unrealized_plpc": float(p.unrealized_plpc) if p.unrealized_plpc else 0.0,
        }
        for p in positions
    ]


CRYPTO_SYMBOLS = {"BTCUSD", "ETHUSD", "SOLUSD", "BTC/USD", "ETH/USD", "SOL/USD"}

def submit_bracket_order(
    symbol: str,
    qty: float,
    direction: str,     # "long" | "short"
    take_profit: float,
    stop_loss: float,
) -> dict:
    """
    Equities  : bracket order (entry + OCO TP/SL in one call).
    Crypto    : market order only — Alpaca forbids bracket orders for crypto.
                SL/TP are monitored and closed manually by the scanner.
    """
    side = OrderSide.BUY if direction == "long" else OrderSide.SELL
    tif  = TimeInForce.GTC if symbol in CRYPTO_SYMBOLS else TimeInForce.DAY

    if symbol in CRYPTO_SYMBOLS:
        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=tif,
        )
    else:
        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=int(qty),
            side=side,
            time_in_force=tif,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(take_profit, 2)),
            stop_loss=StopLossRequest(stop_price=round(stop_loss, 2)),
        )

    order = _client.submit_order(order_data)
    return {
        "id":       str(order.id),
        "symbol":   order.symbol,
        "qty":      float(order.qty),
        "side":     str(order.side),
        "status":   str(order.status),
        "type":     str(order.type),
    }


def cancel_all_orders():
    _client.cancel_orders()


def close_position(symbol: str):
    _client.close_position(symbol)


def close_partial_position(symbol: str, qty: float):
    """Close a fraction of an open position via market order in the opposite direction."""
    clean = symbol.replace("/", "")
    positions = _client.get_all_positions()
    pos = next((p for p in positions if p.symbol == clean or p.symbol == symbol), None)
    if not pos:
        raise ValueError(f"No open position for {symbol}")
    side = OrderSide.SELL if str(pos.side).lower() in ("long", "buy") else OrderSide.BUY
    tif  = TimeInForce.GTC if clean in CRYPTO_SYMBOLS else TimeInForce.DAY
    order_data = MarketOrderRequest(symbol=clean, qty=qty, side=side, time_in_force=tif)
    return _client.submit_order(order_data)


def get_open_symbols() -> set:
    """Returns set of symbols with an open position on Alpaca."""
    return {p["symbol"] for p in get_positions()}


def detect_close_reason(symbol: str, planned_sl: float, planned_tp: float) -> tuple[str, float]:
    """
    Looks at the last filled order for this symbol to determine
    if it was a TP or SL hit.
    Returns ("tp"|"sl"|"manual", exit_price).
    """
    try:
        req = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            symbols=[symbol],
            limit=10,
        )
        orders = _client.get_orders(req)
        # Find the most recently filled order for this symbol
        for order in sorted(orders, key=lambda o: str(o.filled_at or ""), reverse=True):
            if str(order.status) == "filled" and order.filled_avg_price:
                exit_price = float(order.filled_avg_price)
                # Determine TP vs SL by which price it's closer to
                dist_tp = abs(exit_price - planned_tp)
                dist_sl = abs(exit_price - planned_sl)
                reason = "tp" if dist_tp < dist_sl else "sl"
                return reason, exit_price
    except Exception:
        pass
    return "manual", 0.0


def get_filled_entry_price(order_id: str) -> float:
    """Returns the fill price of a submitted order."""
    try:
        order = _client.get_order_by_id(order_id)
        if order.filled_avg_price:
            return float(order.filled_avg_price)
    except Exception:
        pass
    return 0.0
