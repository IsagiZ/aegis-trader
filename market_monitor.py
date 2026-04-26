"""
Market surveillance module.
Pulls live OHLCV data from Alpaca, computes indicators, evaluates Kill Switch,
and emits a structured MarketSnapshot for each asset.
"""
import os
import time
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY,
    EMA_FAST, EMA_MID, EMA_SLOW, RSI_PERIOD, RSI_OB, RSI_OS,
    VIX_SPIKE_THRESHOLD, VIX_EXPLOSION_THRESHOLD,
    CORE_ASSETS, SATELLITE_ASSETS, FIB_LEVELS,
)


# ── Data Classes ───────────────────────────────────────────────

@dataclass
class TechnicalSnapshot:
    asset: str
    price: float
    ema20: float
    ema50: float
    ema200: float
    rsi: float
    trend: str              # "bull" | "bear" | "neutral"
    rsi_signal: str         # "overbought" | "oversold" | "neutral"
    support: float
    resistance: float
    fib_levels: dict
    bias: str               # "long" | "short" | "flat"
    timestamp: str


@dataclass
class KillSwitchStatus:
    active: bool
    reason: Optional[str] = None
    vix: Optional[float] = None


@dataclass
class MarketSnapshot:
    timestamp: str
    kill_switch: KillSwitchStatus
    assets: "dict[str, TechnicalSnapshot]" = field(default_factory=dict)


# ── Clients ────────────────────────────────────────────────────

_stock_client  = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
_crypto_client = CryptoHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)


# ── Helpers ────────────────────────────────────────────────────

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)


def _fib_retracements(high: float, low: float) -> dict:
    diff = high - low
    return {str(lvl): round(high - diff * lvl, 4) for lvl in FIB_LEVELS}


def _key_levels(df: pd.DataFrame, window: int = 20) -> tuple[float, float]:
    recent = df.tail(window)
    return round(float(recent["low"].min()), 4), round(float(recent["high"].max()), 4)


def _fetch_bars(asset: str, days: int = 60) -> pd.DataFrame:
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    if asset in SATELLITE_ASSETS:
        req  = CryptoBarsRequest(symbol_or_symbols=asset, timeframe=TimeFrame.Day,
                                 start=start, end=end)
        bars = _crypto_client.get_crypto_bars(req)
    else:
        req  = StockBarsRequest(symbol_or_symbols=asset, timeframe=TimeFrame.Day,
                                start=start, end=end, feed=DataFeed.IEX)
        bars = _stock_client.get_stock_bars(req)

    df = bars.df
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(asset, level="symbol")
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def _analyze_asset(asset: str) -> TechnicalSnapshot:
    df = _fetch_bars(asset)
    close = df["close"]
    now   = datetime.now(timezone.utc).isoformat()

    e20  = float(_ema(close, EMA_FAST).iloc[-1])
    e50  = float(_ema(close, EMA_MID).iloc[-1])
    e200 = float(_ema(close, EMA_SLOW).iloc[-1])
    rsi  = _rsi(close, RSI_PERIOD)
    price = float(close.iloc[-1])

    # Trend classification
    if price > e20 > e50 > e200:
        trend = "bull"
    elif price < e20 < e50 < e200:
        trend = "bear"
    else:
        trend = "neutral"

    rsi_signal = "overbought" if rsi > RSI_OB else ("oversold" if rsi < RSI_OS else "neutral")

    support, resistance = _key_levels(df)
    high_swing = float(df["high"].tail(60).max())
    low_swing  = float(df["low"].tail(60).min())
    fibs = _fib_retracements(high_swing, low_swing)

    # Directional bias
    if trend == "bull" and rsi_signal != "overbought":
        bias = "long"
    elif trend == "bear" and rsi_signal != "oversold":
        bias = "short"
    else:
        bias = "flat"

    return TechnicalSnapshot(
        asset=asset, price=round(price, 4),
        ema20=round(e20, 4), ema50=round(e50, 4), ema200=round(e200, 4),
        rsi=rsi, trend=trend, rsi_signal=rsi_signal,
        support=support, resistance=resistance, fib_levels=fibs,
        bias=bias, timestamp=now,
    )


def _check_kill_switch(snapshots: "dict[str, TechnicalSnapshot]", vix_price: Optional[float]) -> KillSwitchStatus:
    # VIX check
    if vix_price and vix_price >= VIX_EXPLOSION_THRESHOLD:
        return KillSwitchStatus(active=True, reason=f"VIX explosion: {vix_price:.1f}", vix=vix_price)
    if vix_price and vix_price >= VIX_SPIKE_THRESHOLD:
        return KillSwitchStatus(active=True, reason=f"VIX spike: {vix_price:.1f}", vix=vix_price)

    # Irrational market: all assets dumping despite bull trend signals
    bears = [s for s in snapshots.values() if s.trend == "bear"]
    if len(bears) >= 3:
        return KillSwitchStatus(active=True, reason="3+ assets in bear trend simultaneously — market dislocation")

    return KillSwitchStatus(active=False)


def _fetch_vix() -> Optional[float]:
    try:
        req  = StockBarsRequest(symbol_or_symbols="VIXY", timeframe=TimeFrame.Day,
                                start=datetime.now(timezone.utc) - timedelta(days=5),
                                end=datetime.now(timezone.utc), feed=DataFeed.IEX)
        bars = _stock_client.get_stock_bars(req)
        df   = bars.df
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs("VIXY", level="symbol")
        return float(df["close"].iloc[-1])
    except Exception:
        return None


# ── Public Entry Point ─────────────────────────────────────────

def run_market_scan() -> MarketSnapshot:
    """Full market scan. Returns MarketSnapshot with all assets + kill switch status."""
    now = datetime.now(timezone.utc).isoformat()
    snapshots = {}  # type: dict

    all_assets = CORE_ASSETS + SATELLITE_ASSETS
    for asset in all_assets:
        try:
            snapshots[asset] = _analyze_asset(asset)
        except Exception as e:
            print(f"  [WARN] Could not analyze {asset}: {e}")

    vix = _fetch_vix()
    kill = _check_kill_switch(snapshots, vix)

    return MarketSnapshot(timestamp=now, kill_switch=kill, assets=snapshots)
