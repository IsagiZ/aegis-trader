from dotenv import load_dotenv
import os

load_dotenv()

# ── Alpaca ─────────────────────────────────────────────────────
ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_BASE_URL   = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# ── Portfolio Architecture (90/10) ─────────────────────────────
CORE_ALLOCATION      = 0.90   # SPY, GLD, SLV
SATELLITE_ALLOCATION = 0.10   # BTC/USD

CORE_ASSETS      = ["SPY", "GLD", "SLV"]
SATELLITE_ASSETS = ["BTC/USD"]
ALL_ASSETS       = CORE_ASSETS + SATELLITE_ASSETS

# ── Risk Protocol ──────────────────────────────────────────────
MAX_RISK_PER_TRADE   = 0.03   # 3% of allocated segment capital
MIN_RISK_REWARD      = 2.0    # Minimum R:R ratio
CRYPTO_SL_PCT        = 0.04   # 4% SL for crypto (tighter than 20-bar low)
EQUITY_SL_PCT        = 0.03   # 3% SL for equities

# ── Trailing Stop ──────────────────────────────────────────────
TRAIL_BREAKEVEN_PCT  = 0.03   # +3% profit → SL remonte au breakeven
TRAIL_ACTIVE_PCT     = 0.05   # +5% profit → trailing stop activé
TRAIL_DISTANCE_PCT   = 0.02   # SL trail à 2% sous le prix actuel

# ── Kill Switch Thresholds ─────────────────────────────────────
VIX_SPIKE_THRESHOLD     = 30.0   # Suspend if VIX > 30
VIX_EXPLOSION_THRESHOLD = 40.0   # Full halt if VIX > 40
CORRELATION_CHAOS_WINDOW = 20    # bars to compute rolling correlation

# ── Technical Parameters ───────────────────────────────────────
EMA_FAST   = 20
EMA_MID    = 50
EMA_SLOW   = 200
RSI_PERIOD = 14
RSI_OB     = 70
RSI_OS     = 30
FIB_LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786]

# ── Paths ──────────────────────────────────────────────────────
TRADING_LOG_PATH = "trading_log.json"
