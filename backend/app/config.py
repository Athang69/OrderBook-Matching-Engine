"""Settings. Money is always an integer number of paise."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NSE_DATA_DIR = ROOT / "data" / "nse"
LOG_DIR = ROOT / "logs"
ENGINE_BIN = ROOT / "engine" / "build" / "ob_engine"
FRONTEND_DIST = ROOT / "frontend" / "dist"

# Live prices from Yahoo Finance. Set ORDERBOOK_LIVE=0 to run without the internet (the tests do):
# every stock is then listed, but no prices arrive and orders wait.
LIVE = os.environ.get("ORDERBOOK_LIVE", "1") != "0"

# Every NSE stock in these series can be searched and traded. EQ is the normal market. BE is
# "trade for trade": every trade must be settled by delivery, so intraday is not allowed.
SERIES = ("EQ", "BE")
DELIVERY_ONLY_SERIES = ("BE",)

# Shown first, until the user builds their own watchlist in the browser.
DEFAULT_WATCHLIST = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "ITC", "LT"]
INDICES = {"NIFTY 50": "^NSEI", "SENSEX": "^BSESN", "NIFTY BANK": "^NSEBANK"}

QUOTE_POLL_SECONDS = 5  # best bid and offer, day range, 52-week range, valuation (Yahoo limits how often)
MAX_LIVE_SYMBOLS = 100  # stocks streamed at once: the watchlist, the one on screen, open orders and positions
CHART_CACHE_SECONDS = {"1d": 60, "5d": 300, "1mo": 900, "6mo": 3600, "1y": 3600, "5y": 3600}

# Stocks that trade in derivatives have no fixed band at NSE ("No Band"); they start the day with
# a 10% operating range, which is what is applied to them here.
DEFAULT_BAND_PCT = 10

# NSE's normal session, Monday to Friday, in Indian time (hour, minute).
PRE_OPEN = (9, 0)
MARKET_OPEN = (9, 15)
MARKET_CLOSE = (15, 30)
# Brokers close intraday positions themselves shortly before the close; most do it at 3:20 pm.
INTRADAY_SQUARE_OFF = (15, 20)

# The one account. There is no login: this runs on your own computer for one person.
DEMO_USER = "demo"
DEMO_CASH = 10_00_000 * 100  # Rs 10,00,000 of virtual money

# Intraday (MIS) orders need 20% of the order value as margin, i.e. 5x leverage.
MIS_MARGIN_DIVISOR = 5
MAX_ORDER_QTY = 100_000

# Names and words for the news search where the NSE name alone finds the wrong stories or misses
# the usual ones. Every other stock uses its company name from Yahoo Finance or NSE.
COMPANIES = {
    "RELIANCE": ("Reliance Industries", ["Reliance", "RIL"]),
    "TCS": ("Tata Consultancy Services", ["TCS", "Tata Consultancy"]),
    "HDFCBANK": ("HDFC Bank", ["HDFC Bank"]),
    "INFY": ("Infosys", ["Infosys", "Infy"]),
    "ICICIBANK": ("ICICI Bank", ["ICICI Bank"]),
    "SBIN": ("State Bank of India", ["SBI", "State Bank of India"]),
    "ITC": ("ITC", ["ITC"]),
    "LT": ("Larsen & Toubro", ["Larsen", "L&T"]),
    "BHARTIARTL": ("Bharti Airtel", ["Airtel"]),
    "HINDUNILVR": ("Hindustan Unilever", ["Hindustan Unilever", "HUL"]),
    "M&M": ("Mahindra & Mahindra", ["Mahindra", "M&M"]),
    "MARUTI": ("Maruti Suzuki", ["Maruti"]),
    "ETERNAL": ("Zomato", ["Eternal", "Zomato"]),
    "BAJFINANCE": ("Bajaj Finance", ["Bajaj Finance"]),
    "KOTAKBANK": ("Kotak Mahindra Bank", ["Kotak"]),
    "AXISBANK": ("Axis Bank", ["Axis Bank"]),
    "SUNPHARMA": ("Sun Pharma", ["Sun Pharma"]),
    "TATASTEEL": ("Tata Steel", ["Tata Steel"]),
    "ADANIENT": ("Adani Enterprises", ["Adani Enterprises", "Adani Ent"]),
    "ONGC": ("ONGC", ["ONGC"]),
    "NTPC": ("NTPC", ["NTPC"]),
    "WIPRO": ("Wipro", ["Wipro"]),
    "HCLTECH": ("HCLTech", ["HCLTech", "HCL Tech", "HCL Technologies"]),
}
NEWS_PER_STOCK = 3
NEWS_CACHE_SECONDS = 300  # ask Google News about a stock at most once every five minutes
MAX_NEWS_SYMBOLS = 10
