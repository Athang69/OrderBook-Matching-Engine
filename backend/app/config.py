"""Settings for the simulator. Money is always an integer number of paise."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NSE_DATA_DIR = ROOT / "data" / "nse"
LOG_DIR = ROOT / "logs"
ENGINE_BIN = ROOT / "engine" / "build" / "ob_engine"
FRONTEND_DIST = ROOT / "frontend" / "dist"

# Stocks loaded into the simulator. Each gets its own order book in the engine.
SYMBOLS = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "ITC", "LT"]

DEPTH_LEVELS = 5

# Stocks that trade in derivatives have no fixed band at NSE ("No Band"); they start
# the day with a 10% operating range, which is what the simulator applies to them.
DEFAULT_BAND_PCT = 10

# The one human account. There is no login: this is a single-user simulator.
DEMO_USER = "demo"
DEMO_CASH = 10_00_000 * 100  # Rs 10,00,000 of virtual money

# Intraday (MIS) orders need 20% of the order value as margin, i.e. 5x leverage.
MIS_MARGIN_DIVISOR = 5
MAX_ORDER_QTY = 100_000

# Robot traders replay the previous day's open -> high/low -> close path over this many seconds.
SESSION_SECONDS = 900
BOT_USERS = ["mm1", "mm2", "retail", "taker"]
BOT_CASH = 500_00_00_000 * 100  # Rs 500 crore each
BOT_SHARES = 5_000_000

# News: company names for the search, and the words a headline must contain to count as
# news about that stock (matched as whole words, ignoring case).
COMPANIES = {
    "RELIANCE": ("Reliance Industries", ["Reliance", "RIL"]),
    "TCS": ("Tata Consultancy Services", ["TCS", "Tata Consultancy"]),
    "HDFCBANK": ("HDFC Bank", ["HDFC Bank"]),
    "INFY": ("Infosys", ["Infosys", "Infy"]),
    "ICICIBANK": ("ICICI Bank", ["ICICI Bank"]),
    "SBIN": ("State Bank of India", ["SBI", "State Bank of India"]),
    "ITC": ("ITC", ["ITC"]),
    "LT": ("Larsen & Toubro", ["Larsen", "L&T"]),
}
NEWS_PER_STOCK = 3
NEWS_CACHE_SECONDS = 600  # ask Google News for a stock at most once every 10 minutes
