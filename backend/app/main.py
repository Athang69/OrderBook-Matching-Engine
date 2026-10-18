"""HTTP and WebSocket API, and the wiring that starts every part.

REST (prices are integers in paise):
  GET    /v1/status                         market session, live feed health
  GET    /v1/market/symbols                 every NSE stock that can be traded: symbol, name, series, rules
  GET    /v1/market/instrument/{symbol}     one stock's rules for the day and its live quote
  GET    /v1/market/quotes?symbols=         live quotes for several stocks
  GET    /v1/market/chart/{symbol}?range=   price bars: 1d, 5d, 1mo, 6mo, 1y or 5y
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
import subprocess
import sys
import threading
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, intraday
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
        self.analyst = Analyst(self.explainer, lambda s: (self.market.quote(s) or {}).get("name") or self.instruments[s].name)
        self.requested: dict[str, float] = {}  # stock -> when it was last asked for
        self.bars_loaded: dict[str, str] = {}  # stock -> trading day its one-minute bars were loaded for
        self.charts: dict[tuple[str, str], tuple[float, dict]] = {}
        self.sockets: dict[WebSocket, set[str]] = {}
        self.feed = {"quotes_at": None, "quote_error": None}
        self.started_day: str | None = None
        self.refreshed: set[tuple[str, tuple[int, int]]] = set()
        self._symbol_list: dict | None = None

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
        chart = self.yahoo.chart(to_yahoo(symbol), "1d")
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
            tickers = [to_yahoo(s) for s in symbols] + list(config.INDICES.values())
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


@app.get("/v1/market/chart/{symbol}")
async def chart(symbol: str, range: Literal["1d", "5d", "1mo", "6mo", "1y", "5y"] = "1d") -> dict:
    """Price bars [time, open, high, low, close, volume]. Today's come from memory and move with the stream."""
    symbol = require_symbol(symbol)
    s = sim()
    s.touch([symbol])
    if range == "1d":
        if s.bars_loaded.get(symbol) != s.session()["trading_day"] and s.live:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(s.load_bars, symbol)
        quote = s.market.snapshot(symbol)
        return {"symbol": symbol, "range": range, "interval": "1m", "bars": s.market.bars(symbol),
                "prev_close": quote["prev_close"]}
    key = (symbol, range)
    cached = s.charts.get(key)
    if cached is None or time.time() - cached[0] > config.CHART_CACHE_SECONDS[range]:
        if not s.live:
            raise HTTPException(503, "Charts need the live data feed, which is switched off.")
        try:
            data = await asyncio.to_thread(s.yahoo.chart, to_yahoo(symbol), range)
        except Exception as err:
            if cached is None:
                raise HTTPException(502, f"Could not load the chart from Yahoo Finance ({type(err).__name__}).") from None
            data = cached[1]
        else:
            s.charts[key] = (time.time(), data)
    else:
        data = cached[1]
    return {"symbol": symbol, "range": range, "interval": None, "bars": data["bars"], "prev_close": data["prev_close"]}


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
        if sim().instruments[row["symbol"]].series in config.DELIVERY_ONLY_SERIES and row["action"] in ("BUY", "SELL"):
            row.update(action="NO_TRADE", quantity=0, position_value=0, margin=0, max_loss=0, max_gain=0,
                       note="Trade-for-trade (BE series) stock: delivery only, so no intraday trades.")
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
