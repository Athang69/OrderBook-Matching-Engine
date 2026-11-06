"""HTTP and WebSocket API, and the wiring that starts every part.

REST (prices are integers in paise):
  GET    /v1/status                         market session, live feed health
  GET    /v1/market/symbols                 every NSE stock that can be traded: symbol, name, series, rules
  GET    /v1/market/instrument/{symbol}     one stock's rules for the day and its live quote
  GET    /v1/market/quotes?symbols=         live quotes for several stocks
  GET    /v1/market/chart/{symbol}?range=   price bars: 1d, 5d, 15m, 1h, 1mo, 6mo, 1y or 5y
  GET    /v1/market/sparklines?symbols=     today's price in about 75 points per stock, for small charts
  GET    /v1/market/trades/{symbol}         the latest real trades
  GET    /v1/market/orderbook/{symbol}      real best bid and offer, and your orders waiting in the engine
  GET    /v1/market/indices                 NIFTY 50, SENSEX, NIFTY BANK
  POST   /v1/orders                         place an order
  DELETE /v1/orders/{order_id}              cancel an open order
  GET    /v1/orders/{order_id}              one order with its fills
  GET    /v1/orders?user_id=&open_only=     a user's orders
  GET    /v1/portfolio/{user_id}            cash, holdings, intraday positions, profit and loss, charges
  POST   /v1/portfolio/{user_id}/squareoff  close all intraday positions
  POST   /v1/recommendations                which of the chosen stocks to buy, with your views (recomendation_system)
  POST   /v1/recommendations/intraday       buy, sell short or stay out, from live data and your views
  GET    /v1/news?symbols=                  latest news headlines for each stock
  GET    /v1/explain/{symbol}?date=         why the stock moved that day, from the market, similar companies and news
WebSocket:
  /v1/stream/marketdata                     send {"subscribe": [symbols]}; quotes and trades are pushed
"""
import asyncio
import contextlib
import datetime as dt
import json
import logging
import pathlib
import subprocess
import sys
import threading
import time
from typing import Literal

# Add project root to path so recomendation_system (at repo root) is importable
_PROJECT_ROOT = str(pathlib.Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, intraday, pivot as _pivot, indicators as _indicators
from .audit import AuditLog
from .engine_client import EngineClient
from .exchange import Exchange
from .analysis import AnalysisError, Analyst
from .explain import ExplainError, Explainer, to_date
from .instruments import load_instruments
from .market_data import MarketData
from .news import SOURCE as NEWS_SOURCE
from .news import NewsService, company_terms
from .session import IST, session_status
from .yahoo import YahooClient, YahooStream, from_yahoo, to_yahoo

log = logging.getLogger("orderbook")

BROADCAST_SECONDS = 0.25
MAX_SUBSCRIPTIONS = 60  # stocks one browser can follow at once
REQUEST_KEEP_SECONDS = 900  # a stock asked for over REST stays live this long
BARS_PER_POLL = 4  # first-time chart loads per quote poll, so a long watchlist does not hold up quotes
REFERENCE_REFRESH = ((8, 45), (19, 0))  # Indian times to download NSE's newest files for the next session
CHART_RANGES = ("1d", "5d", "1mo", "6mo", "1y", "5y")
INDEX_BY_TICKER = {ticker: name for name, ticker in config.INDICES.items()}
GLOBAL_CHART_CACHE: dict[tuple[str, str, str], tuple[float, dict]] = {}
GLOBAL_CHART_TTL = 300


class Simulator:
    """Everything that runs behind the API."""

    def __init__(self, live: bool = config.LIVE) -> None:
        self.live = live
        self.instruments = load_instruments(config.NSE_DATA_DIR, config.SERIES, config.DEFAULT_BAND_PCT)
        self.engine = EngineClient(config.ENGINE_BIN)
        self.market = MarketData(self.instruments)
        self.audit = AuditLog(config.LOG_DIR)
        self.yahoo = YahooClient()
        self.stream = YahooStream(self.on_tick)
        self.yahoo_state: tuple[str | None, float | None] = (None, None)  # NIFTY 50 state and when it was read
        self.exchange = Exchange(self.engine, self.instruments, self.market, self.audit, lambda: self.session(),
                                 config.MIS_MARGIN_DIVISOR, config.MAX_ORDER_QTY, 5, config.DELIVERY_ONLY_SERIES)
        self.exchange.create_account(config.DEMO_USER, config.DEMO_CASH)
        self.news = NewsService(self.news_terms, config.NEWS_PER_STOCK, config.NEWS_CACHE_SECONDS)
        self.explainer = Explainer(self.yahoo, lambda: set(self.instruments), self.news_terms)
        self.analyst = Analyst(self.explainer,
                               lambda s: (self.market.quote(s) or {}).get("name") or self.instruments[s].name,
                               get_indicators=self.get_indicators)
        self.requested: dict[str, float] = {}  # stock -> when it was last asked for
        self.bars_loaded: dict[str, str] = {}  # stock -> trading day its one-minute bars were loaded for
        self.charts: dict[tuple[str, str], tuple[float, dict]] = {}
        self.sockets: dict[WebSocket, set[str]] = {}
        self.feed = {"quotes_at": None, "quote_error": None}
        self.started_day: str | None = None
        self.refreshed: set[tuple[str, tuple[int, int]]] = set()
        self._symbol_list: dict | None = None
        # pivot cache: symbol -> (trading_day, levels_dict) — recomputed when the session changes
        self._pivot_cache: dict[str, tuple[str, dict]] = {}
        # indicator cache: symbol -> (trading_day, indicators_dict) — recomputed once per trading day
        self._indicator_cache: dict[str, tuple[str, dict]] = {}
        # NIFTY 50 daily close series for Beta, refreshed once per trading day
        self._nifty_cache: tuple[str, list[tuple[str, float]]] | None = None

    # ---- the session and reference data ----

    def session(self) -> dict:
        return session_status(time.time(), *self.yahoo_state)

    def status(self) -> dict:
        return {"session": self.session(), "data_date": next(iter(self.instruments.values())).data_date,
                "demo_user": config.DEMO_USER, "margin_divisor": config.MIS_MARGIN_DIVISOR, "live": self.live,
                "feed": {"stream_connected": self.stream.connected, "last_tick": self.stream.last_message,
                         "stream_error": self.stream.error, **self.feed}}

    def symbol_list(self) -> dict:
        if self._symbol_list is None:
            rows = sorted(([i.symbol, i.name, i.series, i.close, i.tick, i.band_pct, i.lower_band, i.upper_band]
                           for i in self.instruments.values()), key=lambda r: r[0])
            self._symbol_list = {"data_date": next(iter(self.instruments.values())).data_date, "count": len(rows),
                                 "watchlist": config.DEFAULT_WATCHLIST, "symbols": rows}
        return self._symbol_list

    def news_terms(self, symbol: str) -> tuple[str, list[str]]:
        quote = self.market.quote(symbol) or {}
        instrument = self.instruments.get(symbol)
        return company_terms(symbol, quote.get("name") or (instrument.name if instrument else symbol), config.COMPANIES)

    def get_pivot(self, symbol: str) -> dict:
        """Classic pivot levels for one stock, cached per trading day."""
        trading_day = self.session()["trading_day"]
        cached = self._pivot_cache.get(symbol)
        if cached and cached[0] == trading_day:
            return {"symbol": symbol, "trading_day": trading_day, **cached[1], "error": None}
        inst = self.instruments.get(symbol)
        if inst is None:
            return _pivot_error(symbol, trading_day, "Unknown symbol")
        if inst.prev_high <= 0 or inst.prev_low <= 0:
            return _pivot_error(symbol, trading_day, "Previous session high/low not in NSE data")
        levels = _pivot.compute_pivot(inst.prev_high, inst.prev_low, inst.close)
        if levels is None:
            return _pivot_error(symbol, trading_day, "Could not compute pivot levels from the available data")
        self._pivot_cache[symbol] = (trading_day, levels)
        return {"symbol": symbol, "trading_day": trading_day, **levels, "error": None}

    def _nifty_series(self, trading_day: str) -> list[tuple[str, float]]:
        """NIFTY 50 daily close series, fetched once per trading day and cached."""
        if self._nifty_cache and self._nifty_cache[0] == trading_day:
            return self._nifty_cache[1]
        try:
            data  = self.yahoo.global_chart("^NSEI", "1y", "1d")
            bars  = data.get("bars") or []
            from datetime import datetime, timezone
            series = [(datetime.fromtimestamp(b[0], timezone.utc).date().isoformat(), b[4])
                      for b in bars if b[4]]
            self._nifty_cache = (trading_day, series)
            return series
        except Exception:
            return []

    def get_indicators(self, symbol: str) -> dict:
        """RSI, MACD, Fibonacci and Beta for one stock, cached per trading day.

        Fetches 1-year daily OHLCV from Yahoo once per stock per session and runs all four
        pure-function calculations. Returns a dict with keys rsi, macd, fibonacci, beta;
        each value is either the indicator result dict or {"error": reason_string}.
        """
        trading_day = self.session()["trading_day"]
        cached = self._indicator_cache.get(symbol)
        if cached and cached[0] == trading_day:
            return cached[1]

        inst = self.instruments.get(symbol)
        if inst is None:
            return {"rsi": {"error": "unknown_symbol"}, "macd": {"error": "unknown_symbol"},
                    "fibonacci": {"error": "unknown_symbol"}, "beta": {"error": "unknown_symbol"}}

        try:
            from .yahoo import to_yahoo as _ty
            from datetime import datetime, timezone as _tz
            data = self.yahoo.global_chart(_ty(symbol), "1y", "1d")
            bars = data.get("bars") or []
        except Exception:
            err = {"error": "data_unavailable"}
            result = {"rsi": err, "macd": err, "fibonacci": err, "beta": err}
            return result

        closes = [b[4] for b in bars if b[4]]
        ohlc   = [(b[1], b[2], b[3], b[4]) for b in bars if b[4]]  # (open, high, low, close)

        from datetime import datetime, timezone
        stock_series = [(datetime.fromtimestamp(b[0], timezone.utc).date().isoformat(), b[4])
                        for b in bars if b[4]]

        rsi_result  = _indicators.compute_rsi(closes)
        macd_result = _indicators.compute_macd(closes)
        fib_result  = _indicators.compute_fibonacci(ohlc, closes[-1] if closes else 0.0)

        nifty = self._nifty_series(trading_day)
        beta_result = _indicators.compute_beta(stock_series, nifty) if nifty else {"error": "benchmark_unavailable"}

        result = {"rsi": rsi_result, "macd": macd_result, "fibonacci": fib_result, "beta": beta_result}
        self._indicator_cache[symbol] = (trading_day, result)
        return result

    def reload_reference_data(self) -> None:
        """Downloads NSE's newest daily files and applies the new closing prices and price bands."""
        script = config.ROOT / "scripts" / "fetch_nse_data.py"
        try:
            subprocess.run([sys.executable, str(script)], timeout=120, check=False, capture_output=True)
            instruments = load_instruments(config.NSE_DATA_DIR, config.SERIES, config.DEFAULT_BAND_PCT)
        except Exception:
            log.exception("could not refresh NSE reference data")
            return
        self.instruments = instruments
        self.market.set_instruments(instruments)
        self.exchange.set_instruments(instruments)
        self._symbol_list = None

    # ---- which stocks are live ----

    def touch(self, symbols) -> None:
        now = time.time()
        for symbol in symbols:
            if symbol in self.instruments:
                self.requested[symbol] = now

    def wanted(self) -> list[str]:
        """Stocks to keep live, most important first: the default watchlist, stocks with orders or
        positions, then whatever browsers have asked for most recently."""
        now = time.time()
        for subscribed in self.sockets.values():
            for symbol in subscribed:
                self.requested[symbol] = now
        for symbol, at in list(self.requested.items()):
            if now - at > REQUEST_KEEP_SECONDS:
                del self.requested[symbol]
        recent = sorted(self.requested, key=self.requested.get, reverse=True)
        ordered = dict.fromkeys([*config.DEFAULT_WATCHLIST, *sorted(self.exchange.symbols_in_use()), *recent])
        return [s for s in ordered if s in self.instruments][:config.MAX_LIVE_SYMBOLS]

    # ---- live feed ----

    def on_tick(self, tick: dict) -> None:
        """A price from the stream (runs on the event loop)."""
        ticker = tick["ticker"]
        if ticker in INDEX_BY_TICKER:
            self.market.on_index(INDEX_BY_TICKER[ticker], {"ltp": tick["price"], "time": tick["time"]})
            return
        symbol = from_yahoo(ticker)
        if symbol not in self.instruments:
            return
        traded = self.market.on_tick(symbol, tick["price"], tick["day_volume"], tick["time"])
        self.exchange.on_market_trade(symbol, tick["price"], traded)

    def apply_quotes(self, quotes: dict[str, dict], received: float) -> None:
        for ticker, quote in quotes.items():
            if ticker in INDEX_BY_TICKER:
                self.market.on_index(INDEX_BY_TICKER[ticker], quote)
                if ticker == config.INDICES["NIFTY 50"] and quote["market_state"]:
                    self.yahoo_state = (quote["market_state"], received)
            else:
                symbol = from_yahoo(ticker)
                if symbol in self.instruments:
                    self.market.on_quote(symbol, quote, received)

    def load_bars(self, symbol: str) -> None:
        """Today's one-minute bars (the last session's when the market is closed). Blocks."""
        chart = self.yahoo.chart(to_yahoo(symbol), "1d", "1m")
        self.market.set_bars(symbol, chart["bars"])
        self.bars_loaded[symbol] = self.session()["trading_day"]

    async def activate(self, symbols: list[str]) -> None:
        """Fetches a quote and today's bars now for stocks that have no live data yet."""
        new = [s for s in symbols if s in self.instruments and not (self.market.quote(s) or {}).get("polled_at")]
        if not new or not self.live:
            return
        self.touch(new)
        try:
            quotes = await asyncio.to_thread(self.yahoo.quotes, [to_yahoo(s) for s in new])
            self.apply_quotes(quotes, time.time())
            await asyncio.gather(*(asyncio.to_thread(self.load_bars, s) for s in new[:BARS_PER_POLL]),
                                 return_exceptions=True)
        except Exception as err:
            self.feed["quote_error"] = f"{type(err).__name__}: {err}"[:200]

    async def poll_quotes_forever(self) -> None:
        backoff = config.QUOTE_POLL_SECONDS
        while True:
            symbols = self.wanted()
            index_tickers = list(config.INDICES.values())
            tickers = [to_yahoo(s) for s in symbols] + index_tickers
            self.stream.set_tickers(tickers)
            try:
                quotes = await asyncio.to_thread(self.yahoo.quotes, tickers)
                self.apply_quotes(quotes, time.time())
                self.feed["quotes_at"], self.feed["quote_error"] = time.time(), None
                backoff = config.QUOTE_POLL_SECONDS
            except Exception as err:  # no internet, Yahoo refusing or rate limiting
                self.feed["quote_error"] = f"{type(err).__name__}: {err}"[:200]
                backoff = min(backoff * 2, 60)
            today = self.session()["trading_day"]
            for symbol in [s for s in symbols if self.bars_loaded.get(s) != today][:BARS_PER_POLL]:
                try:
                    await asyncio.to_thread(self.load_bars, symbol)
                except Exception:
                    self.bars_loaded[symbol] = today  # do not retry every few seconds; the stream builds bars
            await asyncio.sleep(backoff)

    async def clock_forever(self) -> None:
        """Every second: the exchange's session jobs, a new day's reset, and NSE file refreshes."""
        while True:
            await asyncio.sleep(1)
            session = self.session()
            self.exchange.on_clock()
            day = session["trading_day"]
            if session["state"] in ("PRE_OPEN", "OPEN") and self.started_day != day:
                if self.started_day is not None:
                    self.market.new_day()
                    self.bars_loaded.clear()
                self.started_day = day
            local = dt.datetime.now(IST)
            for hm in REFERENCE_REFRESH:
                key = (day, hm)
                if (local.hour, local.minute) == hm and key not in self.refreshed and self.live:
                    self.refreshed.add(key)
                    asyncio.get_running_loop().run_in_executor(None, self.reload_reference_data)

    async def broadcast_forever(self) -> None:
        ticks = 0
        while True:
            await asyncio.sleep(BROADCAST_SECONDS)
            ticks += 1
            changed, trades, indices = self.market.drain()
            send_status = ticks % round(1 / BROADCAST_SECONDS) == 0
            if not self.sockets:
                continue
            status = self.status() if send_status else None
            for socket, subscribed in list(self.sockets.items()):
                quotes = {s: q for s, q in changed.items() if s in subscribed}
                mine = [t for t in trades if t["symbol"] in subscribed]
                if not (quotes or mine or indices or status):
                    continue
                message = {"type": "update", "quotes": quotes, "trades": mine, "indices": indices}
                if status:
                    message["status"] = status
                try:
                    await socket.send_json(message)
                except Exception:  # the client went away
                    self.sockets.pop(socket, None)

    def shutdown(self) -> None:
        self.engine.close()
        self.audit.close()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Python lets one thread run at a time and switches every 5 ms by default; 0.5 ms keeps requests
    # quick while worker threads (quote downloads, recommendations) are busy.
    sys.setswitchinterval(0.0005)
    from .finbert import warm as _warm_finbert
    _warm_finbert()  # start loading FinBERT in the background
    sim = Simulator()
    app.state.sim = sim
    tasks = [asyncio.create_task(sim.broadcast_forever()), asyncio.create_task(sim.clock_forever())]
    if sim.live:
        tasks += [asyncio.create_task(sim.poll_quotes_forever()), asyncio.create_task(sim.stream.run())]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        sim.shutdown()


app = FastAPI(title="OrderBook: paper trading on live NSE prices", version="0.2.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=2000)
# The Vite dev server runs on another port during frontend development.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


def sim() -> Simulator:
    return app.state.sim


def require_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if symbol not in sim().instruments:
        raise HTTPException(404, f"{symbol} is not an NSE stock that can be traded here")
    return symbol


def require_symbols(symbols: list[str]) -> list[str]:
    cleaned = [s.strip().upper() for s in symbols]
    if len(set(cleaned)) != len(cleaned):
        raise HTTPException(422, "Each stock can be selected only once.")
    unknown = [s for s in cleaned if s not in sim().instruments]
    if unknown:
        raise HTTPException(422, f"Unknown stock: {', '.join(unknown)}.")
    return cleaned


def require_user(user_id: str) -> str:
    if not sim().exchange.has_account(user_id):
        raise HTTPException(404, f"unknown user {user_id}")
    return user_id


def _pivot_error(symbol: str, trading_day: str, msg: str) -> dict:
    return {"symbol": symbol, "trading_day": trading_day,
            "pp": None, "r1": None, "r2": None, "r3": None,
            "s1": None, "s2": None, "s3": None, "error": msg}


class OrderRequest(BaseModel):
    user_id: str = config.DEMO_USER
    symbol: str
    side: Literal["BUY", "SELL"]
    type: Literal["LIMIT", "MARKET"] = "LIMIT"
    product: Literal["CNC", "MIS"] = "CNC"
    qty: int = Field(gt=0)
    price: int | None = Field(default=None, gt=0, description="Limit price in paise; ignored for market orders")


Confidences = dict[str, float]


class RecommendationRequest(BaseModel):
    user_id: str = config.DEMO_USER
    symbols: list[str] = Field(min_length=2, max_length=10, description="Stocks to choose between; at least two")
    confidences: Confidences = Field(default_factory=dict,
                                     description="Your confidence in each stock, 0 to 100; 50 or missing means no view")
    budget: int = Field(gt=0, description="Amount to invest, in paise")


class IntradayRequest(BaseModel):
    user_id: str = config.DEMO_USER
    symbols: list[str] = Field(min_length=1, max_length=20)
    confidences: Confidences = Field(default_factory=dict,
                                     description="Your confidence that each stock rises today, 0 to 100")
    budget: int = Field(gt=0, description="Margin money to use, in paise; positions can be 5 times this")


def check_confidences(confidences: Confidences, symbols: list[str]) -> dict[str, float]:
    out = {k.strip().upper(): v for k, v in confidences.items()}
    if any(not 0 <= v <= 100 for v in out.values()):
        raise HTTPException(422, "Each confidence must be between 0 and 100.")
    extra = set(out) - set(symbols)
    if extra:
        raise HTTPException(422, f"A confidence was given for a stock that is not selected: {', '.join(sorted(extra))}.")
    return out


# Only one recommendation runs at a time; it is the one heavy computation in the backend.
_recommendation_running = threading.Lock()


# ---- status and market data ----

@app.get("/v1/status")
def status() -> dict:
    return sim().status()


@app.get("/v1/health")
def health() -> dict:
    return {"status": "ok", **sim().status()}


@app.get("/v1/market/symbols")
def symbols() -> dict:
    """Every NSE stock (EQ and BE series) as [symbol, name, series, close, tick, band %, lower band, upper band],
    for the search box and so a stock's page can open at once."""
    return sim().symbol_list()


@app.get("/v1/market/instrument/{symbol}")
async def instrument(symbol: str) -> dict:
    """A stock's rules for the day and its live quote. A stock asked for here stays live for 15 minutes."""
    symbol = require_symbol(symbol)
    sim().touch([symbol])
    await sim().activate([symbol])
    return {**sim().instruments[symbol].to_dict(), "quote": sim().market.snapshot(symbol)}


@app.get("/v1/market/quotes")
async def quotes(symbols: list[str] = Query(..., min_length=1, max_length=MAX_SUBSCRIPTIONS)) -> dict:
    wanted = [s for s in dict.fromkeys(x.strip().upper() for x in symbols) if s in sim().instruments]
    sim().touch(wanted)
    await sim().activate(wanted)
    return sim().market.snapshots(wanted)


VALID_CHART_RANGES = {"1d", "5d", "1mo", "3mo", "6mo", "ytd", "1y", "5y", "max"}
VALID_CHART_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"}

@app.get("/v1/market/chart/{symbol}")
async def chart(symbol: str, range: str = "1d", interval: str = "1m") -> dict:
    """Price bars [time, open, high, low, close, volume]. Today's 1m bars come from memory; everything else from Yahoo."""
    if range not in VALID_CHART_RANGES:
        raise HTTPException(422, f"Invalid range: {range}")
    if interval not in VALID_CHART_INTERVALS:
        raise HTTPException(422, f"Invalid interval: {interval}")
    symbol = require_symbol(symbol)
    s = sim()
    s.touch([symbol])
    if range == "1d" and interval == "1m":
        if s.bars_loaded.get(symbol) != s.session()["trading_day"] and s.live:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(s.load_bars, symbol)
        quote = s.market.snapshot(symbol)
        return {"symbol": symbol, "range": range, "interval": interval, "bars": s.market.bars(symbol),
                "prev_close": quote["prev_close"]}
    key = (symbol, range, interval)
    cached = s.charts.get(key)
    cache_ttl = config.CHART_CACHE_SECONDS.get(interval, 3600)
    if cached is None or time.time() - cached[0] > cache_ttl:
        if not s.live:
            raise HTTPException(503, "Charts need the live data feed, which is switched off.")
        try:
            data = await asyncio.to_thread(s.yahoo.chart, to_yahoo(symbol), range, interval)
        except Exception as err:
            if cached is None:
                raise HTTPException(502, f"Could not load the chart from Yahoo Finance ({type(err).__name__}).") from None
            data = cached[1]
        else:
            s.charts[key] = (time.time(), data)
    else:
        data = cached[1]
    return {"symbol": symbol, "range": range, "interval": interval, "bars": data["bars"], "prev_close": data["prev_close"]}


@app.get("/v1/market/sparklines")
def sparklines(symbols: list[str] = Query(..., min_length=1, max_length=MAX_SUBSCRIPTIONS)) -> dict[str, list[list[int]]]:
    """Today's price for each stock as about 75 [time, close] points, from the one-minute bars in memory."""
    out = {}
    for symbol in dict.fromkeys(x.strip().upper() for x in symbols):
        if symbol in sim().instruments:
            bars = sim().market.bars(symbol)
            step = max(1, len(bars) // 75)
            points = [[b[0], b[4]] for b in bars[::step]]
            if bars and points[-1][0] != bars[-1][0]:
                points.append([bars[-1][0], bars[-1][4]])
            out[symbol] = points
    return out


@app.get("/v1/market/trades/{symbol}")
def trades(symbol: str, limit: int = Query(30, ge=1, le=60)) -> list[dict]:
    return sim().market.tape(require_symbol(symbol), limit)


@app.get("/v1/market/orderbook/{symbol}")
def orderbook(symbol: str) -> dict:
    """The real best bid and offer (Yahoo does not publish the quantities or deeper levels), and your
    own orders waiting in the matching engine."""
    symbol = require_symbol(symbol)
    quote = sim().market.snapshot(symbol)
    bids, asks = sim().exchange.own_book(symbol)
    return {"symbol": symbol, "bid": quote["bid"], "ask": quote["ask"], "ltp": quote["ltp"],
            "polled_at": quote["polled_at"], "depth_available": False, "your_bids": bids, "your_asks": asks}


@app.get("/v1/market/indices")
def indices() -> list[dict]:
    return sim().market.indices()


@app.get("/v1/market/indices/all")
def all_indices() -> dict:
    """Every tracked index, grouped by region, with live prices."""
    s = sim()
    all_data = {}
    for group, names in config.INDEX_GROUPS.items():
        items = []
        for name in names:
            idx = next((i for i in s.market.indices() if i["name"] == name), None)
            ticker = config.INDICES.get(name)
            items.append({"name": name, "ticker": ticker, **(idx or {"ltp": None, "prev_close": None, "high": None, "low": None, "time": None})})
        all_data[group] = items
    return {"groups": all_data, "strip": config.STRIP_INDICES}


# ---- global market data (any exchange, view-only) ----

@app.get("/v1/market/pivot/{symbol}")
def pivot(symbol: str) -> dict:
    """Classic (Floor) pivot levels for one stock, computed from the previous session's H/L/C.

    Levels are in paise, like all other prices. Cached per trading day — only recomputes when the
    session changes. Returns error: null on success, or a reason string when levels are unavailable.
    """
    return sim().get_pivot(require_symbol(symbol))


@app.get("/v1/market/pivot")
def pivots(symbols: list[str] = Query(..., min_length=1, max_length=MAX_SUBSCRIPTIONS)) -> dict:
    """Classic pivot levels for several stocks at once."""
    cleaned = [s.strip().upper() for s in dict.fromkeys(symbols) if s.strip().upper() in sim().instruments]
    return {s: sim().get_pivot(s) for s in cleaned}


@app.get("/v1/market/indicators/{symbol}")
def indicators(symbol: str) -> dict:
    """RSI (14), MACD (12,26,9), Fibonacci (50-day) and Beta vs NIFTY 50 for one NSE stock.

    Computed from 1-year daily history fetched from Yahoo Finance. Cached per trading day.
    Each indicator is either the result dict or {"error": reason_string} when data is insufficient.
    """
    return sim().get_indicators(require_symbol(symbol))


@app.get("/v1/global/search")
async def global_search(q: str = Query(..., min_length=1, max_length=100), count: int = Query(20, ge=1, le=50)) -> dict:
    """Search Yahoo Finance for any stock, ETF, index, future or crypto worldwide."""
    if not sim().live:
        raise HTTPException(503, "Search needs the live data feed.")
    try:
        results = await asyncio.to_thread(sim().yahoo.search, q, count)
    except Exception as err:
        raise HTTPException(502, f"Yahoo search failed ({type(err).__name__}).") from None
    return {"query": q, "count": len(results), "results": results}


@app.get("/v1/global/quote")
async def global_quote(tickers: list[str] = Query(..., min_length=1, max_length=50, alias="t")) -> dict:
    """Live quotes for any Yahoo ticker(s). Prices are floats in the instrument's own currency."""
    if not sim().live:
        raise HTTPException(503, "Quotes need the live data feed.")
    cleaned = list(dict.fromkeys(t.strip() for t in tickers))
    try:
        quotes = await asyncio.to_thread(sim().yahoo.global_quotes, cleaned)
    except Exception as err:
        raise HTTPException(502, f"Could not fetch quotes ({type(err).__name__}).") from None
    return {"count": len(quotes), "quotes": quotes}


@app.get("/v1/global/chart/{ticker:path}")
async def global_chart(ticker: str, range: str = "1d", interval: str = "1m") -> dict:
    """Price chart for any Yahoo ticker. Prices are floats."""
    if range not in VALID_CHART_RANGES:
        raise HTTPException(422, f"Invalid range: {range}")
    if interval not in VALID_CHART_INTERVALS:
        raise HTTPException(422, f"Invalid interval: {interval}")
    if not sim().live:
        raise HTTPException(503, "Charts need the live data feed.")
    ticker = ticker.strip()
    key = (ticker, range, interval)
    cached = GLOBAL_CHART_CACHE.get(key)
    if cached and time.time() - cached[0] < GLOBAL_CHART_TTL:
        data = cached[1]
    else:
        try:
            data = await asyncio.to_thread(sim().yahoo.global_chart, ticker, range, interval)
        except Exception as err:
            if cached:
                data = cached[1]
            else:
                raise HTTPException(502, f"Could not load chart from Yahoo ({type(err).__name__}).") from None
        GLOBAL_CHART_CACHE[key] = (time.time(), data)
    return {"ticker": ticker, "range": range, "interval": interval, **data}


@app.get("/v1/global/profile/{ticker:path}")
async def global_profile(ticker: str) -> dict:
    """Company profile for any Yahoo ticker."""
    if not sim().live:
        raise HTTPException(503, "Profiles need the live data feed.")
    try:
        profile = await asyncio.to_thread(sim().yahoo.profile, ticker.strip())
    except Exception as err:
        raise HTTPException(502, f"Could not load profile ({type(err).__name__}).") from None
    return {"ticker": ticker.strip(), **profile}


@app.get("/v1/global/similar/{ticker:path}")
async def global_similar(ticker: str) -> dict:
    """Similar stocks for any Yahoo ticker."""
    if not sim().live:
        raise HTTPException(503, "Similar companies need the live data feed.")
    try:
        similar = await asyncio.to_thread(sim().yahoo.similar, ticker.strip())
    except Exception as err:
        raise HTTPException(502, f"Could not load similar stocks ({type(err).__name__}).") from None
    return {"ticker": ticker.strip(), "similar": similar}


@app.get("/v1/global/exchanges")
def exchanges() -> dict:
    """The supported exchange suffixes for Yahoo Finance tickers."""
    return {"exchanges": config.EXCHANGE_SUFFIXES}


@app.get("/v1/global/news/{ticker:path}")
def global_news(ticker: str) -> dict:
    """Google News headlines for any global ticker, with FinBERT sentiment, no NSE validation."""
    from . import news as _news_mod, finbert as _fb
    ticker = ticker.strip().upper()
    # Get company name from cached quote
    try:
        q = sim().yahoo.global_quotes([ticker]).get(ticker, {})
        name = q.get("shortName") or q.get("longName") or ticker
    except Exception:
        name = ticker
    search, aliases = _news_mod.company_terms(ticker, name, {})
    try:
        feed = _news_mod.fetch_feed(_news_mod.search_url(search))
        raw = _news_mod.parse_feed(feed, aliases, 40)
        titles = [a.title for a in raw]
        sentiments = _fb.score_headlines(titles, timeout=10.0)
        articles = []
        for a, s in zip(raw, sentiments):
            import dataclasses
            art = dataclasses.asdict(a)
            art["sentiment"] = {"label": s.label, "pos": s.pos, "neg": s.neg, "neu": s.neu, "score": s.score} if s else None
            articles.append(art)
        return {"stocks": {ticker: {"symbol": ticker, "company": name, "articles": articles, "error": None}}}
    except Exception as err:
        return {"stocks": {ticker: {"symbol": ticker, "company": name, "articles": [], "error": str(err)}}}


_GLOBAL_EXPLAIN_CACHE: dict[str, tuple[float, dict]] = {}
_GLOBAL_EXPLAIN_TTL = 300


@app.get("/v1/global/explain/{ticker:path}")
def global_explain(ticker: str, date: str | None = Query(None)) -> dict:
    """Why a global stock moved: price data, peers, world markets, and news with FinBERT sentiment.
    Returns an Explanation-compatible dict with float prices in the stock's own currency."""
    import dataclasses, statistics
    from datetime import datetime, timezone
    from . import news as _news_mod, finbert as _fb
    from .candles import detect_patterns
    from . import chart_cnn as _cnn
    ticker = ticker.strip().upper()
    cache_key = f"{ticker}:{date or ''}"
    cached = _GLOBAL_EXPLAIN_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _GLOBAL_EXPLAIN_TTL:
        return cached[1]

    # --- price history ---
    try:
        raw = sim().yahoo.global_chart(ticker, "6mo", "1d")
        bars = raw.get("bars", [])  # [ts, open, high, low, close, volume]
    except Exception:
        raise HTTPException(502, "Could not load price history from Yahoo.")
    if len(bars) < 5:
        raise HTTPException(404, f"Not enough price history for {ticker}.")

    utc = timezone.utc
    closes_by_date: dict[dt.date, float] = {
        datetime.fromtimestamp(b[0], utc).date(): b[4] for b in bars if b[4]
    }
    sorted_days = sorted(closes_by_date)

    # pick the explained day
    if date:
        try:
            target = dt.date.fromisoformat(date)
        except ValueError:
            raise HTTPException(422, "date must be YYYY-MM-DD.")
        if target not in closes_by_date:
            raise HTTPException(404, f"{ticker} did not trade on {date}.")
    else:
        target = sorted_days[-1]

    idx = sorted_days.index(target)
    if idx == 0:
        raise HTTPException(404, "No previous trading day found.")
    prev_date = sorted_days[idx - 1]
    prev_close = closes_by_date[prev_date]
    price = closes_by_date[target]
    change = price / prev_close - 1

    # --- market model (S&P 500 as reference) ---
    try:
        mkt_raw = sim().yahoo.global_chart("^GSPC", "6mo", "1d")
        mkt_closes: dict[dt.date, float] = {
            datetime.fromtimestamp(b[0], utc).date(): b[4]
            for b in mkt_raw.get("bars", []) if b[4]
        }
    except Exception:
        mkt_closes = {}

    beta, market_part, typical_move = None, None, None
    mkt_change_on_day = None
    if mkt_closes:
        common = sorted(d for d in closes_by_date if d in mkt_closes and d < target)
        if len(common) >= 20:
            s_rets = [closes_by_date[common[i]] / closes_by_date[common[i-1]] - 1 for i in range(1, len(common))]
            m_rets = [mkt_closes[common[i]] / mkt_closes[common[i-1]] - 1 for i in range(1, len(common))]
            mm = statistics.fmean(m_rets); ms = statistics.fmean(s_rets)
            var = sum((x - mm)**2 for x in m_rets)
            beta = round(min(max(sum((x-mm)*(y-ms) for x,y in zip(m_rets,s_rets))/var if var else 1.0, 0.0), 3.0), 3)
            own_rets = [y - beta*x for x,y in zip(m_rets, s_rets)]
            typical_move = statistics.stdev(own_rets)
        if prev_date in mkt_closes and target in mkt_closes:
            mkt_change_on_day = mkt_closes[target] / mkt_closes[prev_date] - 1
            market_part = beta * mkt_change_on_day if beta is not None else None

    # --- peers ---
    peers = []
    try:
        similar_tickers = sim().yahoo.similar(ticker)[:5]
        if similar_tickers:
            peer_quotes = sim().yahoo.global_quotes(similar_tickers)
            for pt in similar_tickers:
                q = peer_quotes.get(pt, {})
                chg_pct = q.get("regularMarketChangePercent")
                peers.append({"symbol": pt, "change": chg_pct / 100 if chg_pct is not None else None})
    except Exception:
        pass

    # --- profile ---
    profile = {"sector": None, "industry": None, "summary": None, "peers": [p["symbol"] for p in peers]}
    try:
        p = sim().yahoo.profile(ticker)
        profile.update({"sector": p.get("sector"), "industry": p.get("industry"), "summary": p.get("summary")})
    except Exception:
        pass

    # --- biggest recent moves ---
    big_days = []
    own_per_day = {}
    for i in range(1, len(sorted_days)):
        d, pd = sorted_days[i], sorted_days[i-1]
        ret = closes_by_date[d] / closes_by_date[pd] - 1
        mkt_ret = mkt_closes.get(d, mkt_closes.get(pd))
        own = ret - (beta or 0) * (mkt_closes.get(d, 0) / mkt_closes.get(pd, 1) - 1 if pd in mkt_closes else 0)
        own_per_day[d] = own
    recent = sorted_days[max(0, len(sorted_days)-63):]
    big = sorted(recent, key=lambda d: abs(own_per_day.get(d, 0)), reverse=True)[:6]
    big_days = [{"date": d.isoformat(), "change": closes_by_date[d] / closes_by_date[sorted_days[sorted_days.index(d)-1]] - 1 if sorted_days.index(d) > 0 else 0, "own": own_per_day.get(d, 0)} for d in sorted(big, reverse=True)]

    # --- OHLC bars (last 10 days) ---
    ohlc_slice = bars[max(0, idx-9):idx+1]
    ohlc_bars = [{"date": datetime.fromtimestamp(b[0], utc).date().isoformat(),
                  "open": b[1], "high": b[2], "low": b[3], "close": b[4], "volume": int(b[5] or 0)}
                 for b in ohlc_slice]

    # --- candlestick patterns ---
    ohlcv_dict = {datetime.fromtimestamp(b[0], utc).date(): (b[1], b[2], b[3], b[4], int(b[5] or 0)) for b in bars if b[4]}
    candle_patterns = {"today": [], "previous": []}
    try:
        _sd = sorted(ohlcv_dict)
        if len(_sd) >= 3:
            _pat_days = _sd[-3:]
            _ohlc_win = [(ohlcv_dict[d][0], ohlcv_dict[d][1], ohlcv_dict[d][2], ohlcv_dict[d][3]) for d in _pat_days]
            _ctx_closes = [ohlcv_dict[d][3] for d in _sd[:-3][-10:]]
            pat_today = detect_patterns(_ohlc_win, _ctx_closes)
            if len(_sd) >= 4:
                _prev_days = _sd[-4:-1]
                _ohlc_prev = [(ohlcv_dict[d][0], ohlcv_dict[d][1], ohlcv_dict[d][2], ohlcv_dict[d][3]) for d in _prev_days]
                _ctx_prev = [ohlcv_dict[d][3] for d in _sd[:-4][-10:]]
                pat_prev = detect_patterns(_ohlc_prev, _ctx_prev)
            else:
                pat_prev = []
            candle_patterns = {"today": pat_today, "previous": pat_prev}
    except Exception:
        pass

    # --- CNN prediction (same chart_for_day function as NSE explain.py) ---
    chart_cnn_result = None
    try:
        cnn_today = _cnn.chart_for_day(closes_by_date, ohlcv_dict, target)
        cnn_prev = _cnn.chart_for_day(closes_by_date, ohlcv_dict, prev_date)
        chart_cnn_result = {"today": cnn_today, "previous": cnn_prev}
    except Exception:
        pass

    # --- news + FinBERT ---
    try:
        q_info = sim().yahoo.global_quotes([ticker]).get(ticker, {})
        name = q_info.get("shortName") or q_info.get("longName") or ticker
    except Exception:
        name = ticker
    search, aliases = _news_mod.company_terms(ticker, name, {})
    headlines: dict[str, list] = {"company": [], "peers": [], "industry": [], "market": [], "global": []}
    sentiment_totals: dict[str, dict] = {}
    try:
        feed = _news_mod.fetch_feed(_news_mod.search_url(search))
        raw_articles = _news_mod.parse_items(feed)
        # classify into scopes
        from .explain import tone as calc_tone, reasons_in
        for art in raw_articles[:40]:
            t = calc_tone(art.title)
            reasons = reasons_in(art.title)
            scope = "company"
            if "Global markets" in reasons or "Interest rates" in reasons:
                scope = "global"
            elif "Trade policy" in reasons or "Economy" in reasons:
                scope = "market"
            art_dict = {"title": art.title, "source": art.source, "url": art.url,
                        "published": art.published, "scope": scope, "tone": t, "reasons": reasons}
            headlines[scope].append(art_dict)
    except Exception:
        pass

    # FinBERT on company headlines
    for scope_key, arts in headlines.items():
        if not arts:
            continue
        titles = [a["title"] for a in arts]
        sentiments = _fb.score_headlines(titles, timeout=8.0)
        for a, s in zip(arts, sentiments):
            a["sentiment"] = {"label": s.label, "pos": s.pos, "neg": s.neg, "neu": s.neu, "score": s.score} if s else None
        scored = [s.score for s in sentiments if s]
        if scored:
            pos = sum(1 for s in sentiments if s and s.label == "positive")
            neg = sum(1 for s in sentiments if s and s.label == "negative")
            neu = sum(1 for s in sentiments if s and s.label == "neutral")
            sentiment_totals[scope_key] = {"avg_score": statistics.fmean(scored), "count": len(scored), "positive": pos, "negative": neg, "neutral": neu}

    # verdict
    own_move = change - (market_part or 0)
    if typical_move and abs(own_move) > 2 * typical_move:
        verdict = "Company-specific move"
    elif mkt_change_on_day and abs(mkt_change_on_day) > 0.01 and abs(change) < abs(mkt_change_on_day) * 1.5:
        verdict = "Market-wide move"
    else:
        verdict = "Ordinary day"

    result = {
        "symbol": ticker, "date": target.isoformat(), "previous_date": prev_date.isoformat(),
        "latest_date": sorted_days[-1].isoformat(), "change": change, "price": price, "prev_close": prev_close,
        "verdict": verdict, "summary": [f"{ticker} moved {change*100:+.2f}% on {target}."],
        "market": {"name": "S&P 500", "change": mkt_change_on_day},
        "beta": beta, "market_part": market_part, "typical_move": typical_move,
        "sector": None, "peers": peers, "profile": profile, "reasons": [], "big_days": big_days,
        "headlines": headlines, "runtime_ms": 0,
        "ohlc_bars": ohlc_bars, "candle_patterns": candle_patterns, "chart_cnn": chart_cnn_result,
        "sentiment_totals": sentiment_totals, "currency": q_info.get("currency", "USD") if "q_info" in dir() else "USD",
    }
    _GLOBAL_EXPLAIN_CACHE[cache_key] = (time.time(), result)
    return result


_GLOBAL_ANALYSIS_CACHE: dict[str, tuple[float, dict]] = {}
_GLOBAL_ANALYSIS_TTL = 1800


@app.get("/v1/global/analysis/{ticker:path}")
def global_analysis(ticker: str, date: str | None = Query(None)) -> dict:
    """OpenRouter AI analysis of why a global stock moved. Reuses analysis.py logic."""
    from .analysis import ask_model, build_prompt, number_headlines, INDIA, WORLD, AnalysisError
    ticker = ticker.strip().upper()
    cache_key = f"{ticker}:{date or ''}"
    cached = _GLOBAL_ANALYSIS_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _GLOBAL_ANALYSIS_TTL:
        return cached[1]

    # Reuse the explain data
    try:
        explanation = global_explain(ticker, date)
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(502, str(err)) from None

    # Build the same prompt structure but with global market context
    name = explanation.get("profile", {}).get("sector") and ticker or ticker
    try:
        q = sim().yahoo.global_quotes([ticker]).get(ticker, {})
        name = q.get("shortName") or q.get("longName") or ticker
    except Exception:
        pass

    # Use the same evidence + prompt from analysis.py
    evidence = number_headlines(explanation)

    # World markets for context (S&P 500, NASDAQ, VIX, etc.)
    import datetime as _dt
    from datetime import timezone
    day = _dt.date.fromisoformat(explanation["date"])
    pool = sim().explainer.pool()
    world_tickers = [("^GSPC", "S&P 500", True), ("^IXIC", "NASDAQ", True), ("^VIX", "VIX", True),
                     ("BZ=F", "Brent crude", True), ("GC=F", "Gold", True), ("DX-Y.NYB", "USD Index", True)]
    world = []
    for wticker, wname, _ in world_tickers:
        try:
            wbars = sim().yahoo.global_chart(wticker, "5d", "1d")
            wbars_list = wbars.get("bars", [])
            if len(wbars_list) >= 2:
                prev_close_w = wbars_list[-2][4]
                last_close_w = wbars_list[-1][4]
                if prev_close_w:
                    world.append((wname, last_close_w / prev_close_w - 1, day.isoformat()))
        except Exception:
            pass

    # Build a simplified prompt for global stocks
    import datetime as _dt2
    prev_date = _dt2.date.fromisoformat(explanation["previous_date"])
    lines = [
        f"STOCK: {ticker} ({name}), trading on {q.get('exchange', 'global exchange') if 'q' in dir() else 'global exchange'}.",
        f"Sector: {explanation['profile'].get('sector') or 'n/a'} / {explanation['profile'].get('industry') or 'n/a'}.",
        f"Business: {(explanation['profile'].get('summary') or 'n/a')[:600]}",
        "",
        f"DAY TO EXPLAIN: {day:%A %d %B %Y} (previous trading day {prev_date:%A %d %B}).",
        f"Move: {explanation['change']*100:+.2f}%, from {explanation.get('currency','USD')} {explanation['prev_close']:.2f} to {explanation.get('currency','USD')} {explanation['price']:.2f}.",
        f"Beta against S&P 500: {explanation['beta'] if explanation['beta'] is not None else 'n/a'}.",
        f"Part explained by S&P 500 move: {(explanation['market_part'] or 0)*100:+.2f}%. Stock's own move: {(explanation['change']-(explanation['market_part'] or 0))*100:+.2f}%.",
        "",
        "SIMILAR COMPANIES TODAY: " + (", ".join(f"{p['symbol']} {(p['change'] or 0)*100:+.2f}%" for p in explanation['peers']) or "none found"),
        "WORLD MARKETS: " + ", ".join(f"{n} {c*100:+.2f}%" for n, c, _ in world),
        "",
        f"HEADLINES (numbered):",
    ]
    from .session import IST
    for h in evidence:
        import datetime
        when = datetime.datetime.fromtimestamp(h["published"], IST).strftime("%d %b %H:%M")
        sent = h.get("sentiment")
        sent_tag = f" [FinBERT: {sent['label']}, score {sent['score']:+.2f}]" if sent else ""
        scope_names = {"company": "about the company", "peers": "about similar companies", "industry": "about its industry",
                       "market": "about the market", "global": "about world markets"}
        lines.append(f"[{h['n']}] ({scope_names.get(h['scope'],'')}) {when} | {h['title']}{sent_tag} | {h['source']}")
    if not evidence:
        lines.append("(no headlines found)")
    lines += ["", f"Explain why {ticker} moved {explanation['change']*100:+.2f}% on {day:%d %B %Y}. "
              "Reply with the JSON object only."]
    prompt = "\n".join(lines)
    try:
        reply = ask_model(prompt)
    except AnalysisError as err:
        raise HTTPException(502, f"Claude could not write the analysis: {err}") from None
    result = {"symbol": ticker, "date": explanation["date"], "explanation": explanation,
              "evidence": evidence, "india": [], "world": [{"name": n, "change": round(c, 5), "date": d} for n, c, d in world],
              "analysis": reply["answer"], "raw": reply["text"], "model": reply["model"], "seconds": reply["seconds"]}
    _GLOBAL_ANALYSIS_CACHE[cache_key] = (time.time(), result)
    return result


# ---- orders ----

@app.post("/v1/orders", status_code=201)
def place_order(req: OrderRequest) -> dict:
    """A rejected order still comes back with status REJECTED and a reason, so the client can show it."""
    require_user(req.user_id)
    symbol = req.symbol.strip().upper()
    s = sim()
    s.touch([symbol])
    quote = s.market.quote(symbol) or {}
    if symbol in s.instruments and s.live and time.time() - (quote.get("polled_at") or 0) > 15:
        with contextlib.suppress(Exception):  # a stock nobody has looked at yet: get its price first
            s.apply_quotes(s.yahoo.quotes([to_yahoo(symbol)]), time.time())
    order = s.exchange.place_order(req.user_id, symbol, req.side, req.type, req.product, req.qty, req.price)
    return order.to_dict()


@app.delete("/v1/orders/{order_id}")
def cancel_order(order_id: int, user_id: str = config.DEMO_USER) -> dict:
    try:
        return sim().exchange.cancel_order(order_id, user_id).to_dict()
    except KeyError:
        raise HTTPException(404, "unknown order") from None
    except PermissionError as err:
        raise HTTPException(403, str(err)) from None
    except ValueError as err:
        raise HTTPException(409, str(err)) from None


@app.get("/v1/orders/{order_id}")
def get_order(order_id: int) -> dict:
    order = sim().exchange.get_order(order_id)
    if order is None:
        raise HTTPException(404, "unknown order")
    return order.to_dict()


@app.get("/v1/orders")
def list_orders(user_id: str = config.DEMO_USER, open_only: bool = False, limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    return sim().exchange.list_orders(require_user(user_id), open_only)[:limit]


# ---- portfolio ----

@app.get("/v1/portfolio/{user_id}")
def portfolio(user_id: str) -> dict:
    return sim().exchange.portfolio(require_user(user_id))


@app.post("/v1/portfolio/{user_id}/squareoff")
def square_off(user_id: str) -> list[dict]:
    try:
        return [order.to_dict() for order in sim().exchange.square_off(require_user(user_id))]
    except ValueError as err:
        raise HTTPException(409, str(err)) from None


# ---- recommendations ----

@app.post("/v1/recommendations")
def recommendations(req: RecommendationRequest) -> dict:
    """Runs the recommendation system on the chosen stocks with your views.

    A plain `def` endpoint, so FastAPI runs it on a worker thread and the live feed keeps running.
    """
    user_id = require_user(req.user_id)
    symbols = require_symbols(req.symbols)
    confidences = check_confidences(req.confidences, symbols)
    available = sim().exchange.portfolio(user_id)["available"]
    if req.budget > available:
        raise HTTPException(422, f"The amount to invest (Rs {req.budget / 100:,.2f}) is more than your "
                                 f"available cash (Rs {available / 100:,.2f}).")
    try:
        import recomendation_system as recommender  # heavy libraries load on first use only
    except ImportError as err:
        raise HTTPException(503, f"The recommendation system is not installed ({err.name} is missing). "
                                 "Run scripts/run.sh to install it.") from None
    if not _recommendation_running.acquire(blocking=False):
        raise HTTPException(409, "A recommendation is already running. Wait for it to finish.")
    try:
        sim().touch(symbols)
        missing = [s for s in symbols if not sim().market.ltp(s)]
        if missing and sim().live:
            with contextlib.suppress(Exception):
                sim().apply_quotes(sim().yahoo.quotes([to_yahoo(s) for s in missing]), time.time())
        # Live prices decide how many shares the money buys.
        last_prices = {s: sim().market.ltp(s) or sim().instruments[s].close for s in symbols}
        return recommender.recommend(symbols, confidences, req.budget, last_prices, loader=recommender.load_prices)
    except recommender.RecommendationError as err:
        raise HTTPException(422, str(err)) from None
    finally:
        _recommendation_running.release()


@app.post("/v1/recommendations/intraday")
async def intraday_recommendations(req: IntradayRequest) -> Response:
    """Buy, sell short or stay out for each stock, from today's live trading and your views.

    Kept fast on purpose: an `async` endpoint (the work is far too short to need a worker thread), a cheap
    cash check instead of a full portfolio valuation, and the reply encoded directly as JSON. The reply's
    `timing` says where the server's time went, in microseconds.
    """
    started = time.perf_counter_ns()
    user_id = require_user(req.user_id)
    symbols = require_symbols(req.symbols)
    confidences = check_confidences(req.confidences, symbols)
    available = sim().exchange.available(user_id)
    if req.budget > available:
        raise HTTPException(422, f"The margin to use (Rs {req.budget / 100:,.2f}) is more than your "
                                 f"available cash (Rs {available / 100:,.2f}).")
    sim().touch(symbols)
    checked = time.perf_counter_ns()
    now = time.time()
    views = sim().market.intraday_view(symbols, intraday.WINDOW_SECONDS, intraday.MOMENTUM_SECONDS, now)
    copied = time.perf_counter_ns()
    rules = {s: (sim().instruments[s].tick, sim().instruments[s].lower_band, sim().instruments[s].upper_band) for s in symbols}
    result = intraday.recommend_intraday(views, rules, confidences, req.budget, config.MIS_MARGIN_DIVISOR,
                                         sim().session(), now)
    for row in result["stocks"]:
        sym = row["symbol"]
        if sim().instruments[sym].series in config.DELIVERY_ONLY_SERIES and row["action"] in ("BUY", "SELL"):
            row.update(action="NO_TRADE", quantity=0, position_value=0, margin=0, max_loss=0, max_gain=0,
                       note="Trade-for-trade (BE series) stock: delivery only, so no intraday trades.")
        pivot_resp = sim().get_pivot(sym)
        if pivot_resp["error"] is None:
            levels = {k: pivot_resp[k] for k in ("pp", "r1", "r2", "r3", "s1", "s2", "s3")}
            row["pivot"] = {"symbol": sym, "trading_day": pivot_resp["trading_day"], **levels, "error": None}
            row["pivot_entry"] = _pivot.compute_entry_exit(levels, row["ltp"], sim().instruments[sym].tick,
                                                           row.get("vwap"))
        else:
            row["pivot"] = {"symbol": sym, "trading_day": pivot_resp["trading_day"],
                            "pp": None, "r1": None, "r2": None, "r3": None,
                            "s1": None, "s2": None, "s3": None, "error": pivot_resp["error"]}
            row["pivot_entry"] = None
        if sim().live:
            row["indicators"] = sim().get_indicators(sym)
        else:
            row["indicators"] = None
    done = time.perf_counter_ns()
    result["timing"] = {"checks_us": (checked - started) // 1000, "snapshot_us": (copied - checked) // 1000,
                        "signals_us": (done - copied) // 1000, "total_us": (done - started) // 1000}
    return Response(json.dumps(result, separators=(",", ":")), media_type="application/json")


# ---- why a stock moved ----

@app.get("/v1/explain/{symbol}")
def explain(symbol: str, date: str | None = Query(None, description="YYYY-MM-DD; the latest trading day if left out")) -> dict:
    """Why the stock moved on a day: the market's part and the stock's own part, similar companies, its
    sector index, and the headlines of that day tagged with their likely cause (see explain.py).

    A plain `def` endpoint, so FastAPI runs it on a worker thread: the first call for a stock downloads
    its price history and searches the news, which takes a second or two.
    """
    symbol = require_symbol(symbol)
    if not sim().live:
        raise HTTPException(503, "Explanations need the live data feed, which is switched off (ORDERBOOK_LIVE=0).")
    try:
        return sim().explainer.explain(symbol, to_date(date))
    except ExplainError as err:
        raise HTTPException(422, str(err)) from None


@app.get("/v1/analysis/{symbol}")
def analysis(symbol: str, date: str | None = Query(None, description="YYYY-MM-DD; the latest trading day if left out")) -> dict:
    """Why the stock moved that day, written by Claude from the evidence (analysis.py). Takes 30 to 60 seconds
    the first time for a stock and day; repeats within 30 minutes come from memory."""
    symbol = require_symbol(symbol)
    if not sim().live:
        raise HTTPException(503, "The analysis needs the live data feed, which is switched off (ORDERBOOK_LIVE=0).")
    try:
        return sim().analyst.analyse(symbol, to_date(date))
    except ExplainError as err:
        raise HTTPException(422, str(err)) from None
    except (AnalysisError, subprocess.TimeoutExpired) as err:
        raise HTTPException(502, f"Claude could not write the analysis: {err}") from None


# ---- news ----

@app.get("/v1/news")
def news(symbols: list[str] = Query(..., min_length=1, max_length=config.MAX_NEWS_SYMBOLS)) -> dict:
    """Latest headlines for each stock, e.g. /v1/news?symbols=RELIANCE&symbols=TCS."""
    wanted = list(dict.fromkeys(s.strip().upper() for s in symbols))  # drop repeats, keep order
    unknown = [s for s in wanted if s not in sim().instruments]
    if unknown:
        raise HTTPException(422, f"Unknown stock: {', '.join(unknown)}.")
    return {"source": NEWS_SOURCE, "per_stock": config.NEWS_PER_STOCK, "stocks": sim().news.latest(wanted)}


# ---- live stream ----

@app.websocket("/v1/stream/marketdata")
async def marketdata(socket: WebSocket) -> None:
    await socket.accept()
    s = sim()
    await socket.send_json({"type": "hello", "status": s.status(), "indices": s.market.indices()})
    s.sockets[socket] = set()
    try:
        while True:
            message = json.loads(await socket.receive_text())
            wanted = [x.strip().upper() for x in message.get("subscribe", []) if isinstance(x, str)]
            subscribed = {x for x in wanted if x in s.instruments}
            subscribed = set(list(dict.fromkeys(x for x in wanted if x in subscribed))[:MAX_SUBSCRIPTIONS])
            s.sockets[socket] = subscribed
            s.touch(subscribed)
            await socket.send_json({"type": "snapshot", "quotes": s.market.snapshots(subscribed),
                                    "trades": {x: s.market.tape(x, 30) for x in subscribed}})
            asyncio.create_task(s.activate(sorted(subscribed)))
    except (WebSocketDisconnect, json.JSONDecodeError, AttributeError):
        pass
    finally:
        s.sockets.pop(socket, None)


# The built frontend is served from the same address as the API.
if config.FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="frontend")
