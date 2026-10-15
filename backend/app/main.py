"""HTTP and WebSocket API for the simulator, and the wiring that starts every part.

REST (prices are integers in paise):
  POST   /v1/orders                         place an order
  DELETE /v1/orders/{order_id}              cancel an open order
  GET    /v1/orders/{order_id}              one order with its fills
  GET    /v1/orders?user_id=&open_only=     a user's orders
  GET    /v1/market/instruments             stocks, their rules and current prices
  GET    /v1/market/orderbook/{symbol}      best five bids and asks
  GET    /v1/market/trades/{symbol}         recent trades
  GET    /v1/market/history/{symbol}        price once a second, for the chart
  GET    /v1/portfolio/{user_id}            cash, holdings, intraday positions, profit and loss
  POST   /v1/portfolio/{user_id}/squareoff  close all intraday positions
  GET    /v1/sim  and  POST /v1/sim/bots    simulator status; pause or resume robot traders
  POST   /v1/recommendations                which of the chosen stocks to buy (recomendation_system)
  POST   /v1/recommendations/intraday       buy, sell short or stay out, from live market data
  GET    /v1/news?symbols=                  latest news headlines for each stock
WebSocket:
  /v1/stream/marketdata                     book and trade updates, pushed four times a second
"""
import asyncio
import contextlib
import json
import sys
import threading
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, intraday
from .audit import AuditLog
from .bots import Bots
from .engine_client import EngineClient
from .exchange import Exchange
from .instruments import load_instruments
from .market_data import MarketData
from .news import SOURCE as NEWS_SOURCE
from .news import NewsService

BROADCAST_SECONDS = 0.25


class Simulator:
    """Everything that runs behind the API."""

    def __init__(self) -> None:
        self.instruments = load_instruments(config.NSE_DATA_DIR, config.SYMBOLS, config.DEFAULT_BAND_PCT)
        self.by_symbol = {i.symbol: i for i in self.instruments}
        self.engine = EngineClient(config.ENGINE_BIN)
        self.market = MarketData(self.instruments)
        self.audit = AuditLog(config.LOG_DIR)
        self.exchange = Exchange(self.engine, self.instruments, self.market, self.audit,
                                 config.MIS_MARGIN_DIVISOR, config.MAX_ORDER_QTY, config.DEPTH_LEVELS)
        self.exchange.create_account(config.DEMO_USER, config.DEMO_CASH)
        for bot in config.BOT_USERS:
            self.exchange.create_account(bot, config.BOT_CASH, is_bot=True, shares=config.BOT_SHARES)
        self.bots = Bots(self.exchange, self.market, self.instruments, config.SESSION_SECONDS)
        companies = {s: config.COMPANIES.get(s, (s, [s])) for s in config.SYMBOLS}
        self.news = NewsService(companies, config.NEWS_PER_STOCK, config.NEWS_CACHE_SECONDS)
        self.intraday_rules = {i.symbol: intraday.StockRules(i.tick, i.lower_band, i.upper_band) for i in self.instruments}
        self.sockets: set[WebSocket] = set()

    def status(self) -> dict:
        return {"data_date": self.instruments[0].data_date, "demo_user": config.DEMO_USER,
                "margin_divisor": config.MIS_MARGIN_DIVISOR, **self.bots.status()}

    def instrument_list(self) -> list[dict]:
        snapshots = self.market.snapshots()
        return [{**i.to_dict(), "company": config.COMPANIES.get(i.symbol, (i.symbol, []))[0],
                 "avg_trade_qty": i.avg_trade_qty, "market": snapshots[i.symbol]} for i in self.instruments]

    async def broadcast_forever(self) -> None:
        ticks = 0
        while True:
            await asyncio.sleep(BROADCAST_SECONDS)
            ticks += 1
            if ticks % round(1 / BROADCAST_SECONDS) == 0:
                self.market.sample_history()
            changed, trades = self.market.drain()
            if not self.sockets or not (changed or trades or ticks % 4 == 0):
                continue
            message = {"type": "update", "symbols": changed, "trades": trades, "sim": self.status()}
            for socket in list(self.sockets):
                try:
                    await socket.send_json(message)
                except Exception:  # the client went away
                    self.sockets.discard(socket)

    def shutdown(self) -> None:
        self.bots.stop()
        self.engine.close()
        self.audit.close()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Python lets one thread run at a time and switches every 5 ms by default. With the robot traders
    # busy on their own thread, a request could wait up to that long. 0.5 ms keeps the API responsive.
    sys.setswitchinterval(0.0005)
    sim = Simulator()
    app.state.sim = sim
    sim.bots.start()
    broadcaster = asyncio.create_task(sim.broadcast_forever())
    try:
        yield
    finally:
        broadcaster.cancel()
        sim.shutdown()


app = FastAPI(title="Order Book and Matching Engine Simulator", version="0.1.0", lifespan=lifespan)
# The Vite dev server runs on another port during frontend development.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


def sim() -> Simulator:
    return app.state.sim


def require_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if symbol not in sim().by_symbol:
        raise HTTPException(404, f"unknown symbol {symbol}")
    return symbol


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


class BotsRequest(BaseModel):
    enabled: bool


class RecommendationRequest(BaseModel):
    user_id: str = config.DEMO_USER
    symbols: list[str] = Field(min_length=2, max_length=len(config.SYMBOLS),
                               description="Stocks to choose between; at least two")
    confidence: float = Field(ge=50, le=99, description="Percentage: how sure the system must be before saying buy")
    budget: int = Field(gt=0, description="Amount to invest, in paise")


class IntradayRequest(BaseModel):
    user_id: str = config.DEMO_USER
    symbols: list[str] = Field(min_length=1, max_length=len(config.SYMBOLS))
    confidence: float = Field(ge=10, le=95, description="Percentage: how strong the signals must be")
    budget: int = Field(gt=0, description="Margin money to use, in paise; positions can be 5 times this")


# Only one recommendation runs at a time; it is the one heavy computation in the backend.
_recommendation_running = threading.Lock()


# ---- orders ----

@app.post("/v1/orders", status_code=201)
def place_order(req: OrderRequest) -> dict:
    """A rejected order still comes back with status REJECTED and a reason, so the client can show it."""
    require_user(req.user_id)
    order = sim().exchange.place_order(req.user_id, req.symbol.upper(), req.side, req.type, req.product, req.qty, req.price)
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


# ---- market data ----

@app.get("/v1/market/instruments")
def instruments() -> list[dict]:
    return sim().instrument_list()


@app.get("/v1/market/orderbook/{symbol}")
def orderbook(symbol: str) -> dict:
    return sim().market.snapshot(require_symbol(symbol))


@app.get("/v1/market/trades/{symbol}")
def trades(symbol: str, limit: int = Query(30, ge=1, le=60)) -> list[dict]:
    return sim().market.tape(require_symbol(symbol), limit)


@app.get("/v1/market/history/{symbol}")
def history(symbol: str) -> list[list]:
    return sim().market.history(require_symbol(symbol))


@app.get("/v1/market/histories")
def histories() -> dict[str, list[list]]:
    """Price once a second for every stock, for the charts and sparklines in one request."""
    return {i.symbol: sim().market.history(i.symbol) for i in sim().instruments}


# ---- portfolio ----

@app.get("/v1/portfolio/{user_id}")
def portfolio(user_id: str) -> dict:
    return sim().exchange.portfolio(require_user(user_id))


@app.post("/v1/portfolio/{user_id}/squareoff")
def square_off(user_id: str) -> list[dict]:
    return [order.to_dict() for order in sim().exchange.square_off(require_user(user_id))]


# ---- recommendations ----

@app.post("/v1/recommendations")
def recommendations(req: RecommendationRequest) -> dict:
    """Runs the recommendation system on the chosen stocks.

    A plain `def` endpoint, so FastAPI runs it on a worker thread and the market keeps trading meanwhile.
    """
    user_id = require_user(req.user_id)
    symbols = [s.strip().upper() for s in req.symbols]
    if len(set(symbols)) != len(symbols):
        raise HTTPException(422, "Each stock can be selected only once.")
    unknown = [s for s in symbols if s not in sim().by_symbol]
    if unknown:
        raise HTTPException(422, f"Unknown stock: {', '.join(unknown)}.")
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
        # The simulator's current prices decide how many shares the money buys.
        last_prices = {s: sim().market.ltp(s) or sim().by_symbol[s].prev_close for s in symbols}
        return recommender.recommend(symbols, req.confidence, req.budget, last_prices, loader=recommender.load_prices)
    except recommender.RecommendationError as err:
        raise HTTPException(422, str(err)) from None
    finally:
        _recommendation_running.release()


@app.post("/v1/recommendations/intraday")
async def intraday_recommendations(req: IntradayRequest) -> Response:
    """Buy, sell short or stay out for each stock, from the last few minutes of the simulator's own data.

    Kept fast on purpose: an `async` endpoint (the work is far too short to need a worker thread), a cheap
    cash check instead of a full portfolio valuation, and the reply encoded directly as JSON. The reply's
    `timing` says where the server's time went, in microseconds.
    """
    started = time.perf_counter_ns()
    user_id = require_user(req.user_id)
    symbols = [s.strip().upper() for s in req.symbols]
    if len(set(symbols)) != len(symbols):
        raise HTTPException(422, "Each stock can be selected only once.")
    unknown = [s for s in symbols if s not in sim().by_symbol]
    if unknown:
        raise HTTPException(422, f"Unknown stock: {', '.join(unknown)}.")
    available = sim().exchange.available(user_id)
    if req.budget > available:
        raise HTTPException(422, f"The margin to use (Rs {req.budget / 100:,.2f}) is more than your "
                                 f"available cash (Rs {available / 100:,.2f}).")
    checked = time.perf_counter_ns()
    views = sim().market.intraday_view(symbols, intraday.WINDOW_SECONDS)
    copied = time.perf_counter_ns()
    result = intraday.recommend_intraday(views, sim().intraday_rules, req.confidence, req.budget,
                                         config.MIS_MARGIN_DIVISOR, time.time())
    done = time.perf_counter_ns()
    result["timing"] = {"checks_us": (checked - started) // 1000, "snapshot_us": (copied - checked) // 1000,
                        "signals_us": (done - copied) // 1000, "total_us": (done - started) // 1000}
    return Response(json.dumps(result, separators=(",", ":")), media_type="application/json")


# ---- news ----

@app.get("/v1/news")
def news(symbols: list[str] = Query(..., min_length=1, max_length=len(config.SYMBOLS))) -> dict:
    """Latest headlines for each stock, e.g. /v1/news?symbols=RELIANCE&symbols=TCS."""
    wanted = list(dict.fromkeys(s.strip().upper() for s in symbols))  # drop repeats, keep order
    unknown = [s for s in wanted if s not in sim().by_symbol]
    if unknown:
        raise HTTPException(422, f"Unknown stock: {', '.join(unknown)}.")
    return {"source": NEWS_SOURCE, "per_stock": config.NEWS_PER_STOCK, "stocks": sim().news.latest(wanted)}


# ---- simulator ----

@app.get("/v1/sim")
def sim_status() -> dict:
    return sim().status()


@app.post("/v1/sim/bots")
def set_bots(req: BotsRequest) -> dict:
    sim().bots.set_enabled(req.enabled)
    return sim().status()


@app.get("/v1/health")
def health() -> dict:
    return {"status": "ok", **sim().status()}


@app.websocket("/v1/stream/marketdata")
async def marketdata(socket: WebSocket) -> None:
    await socket.accept()
    await socket.send_json({"type": "hello", "instruments": sim().instrument_list(), "sim": sim().status()})
    sim().sockets.add(socket)
    try:
        while True:
            await socket.receive_text()  # clients only listen; this just notices a disconnect
    except WebSocketDisconnect:
        pass
    finally:
        sim().sockets.discard(socket)


# The built frontend is served from the same address as the API.
if config.FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="frontend")
