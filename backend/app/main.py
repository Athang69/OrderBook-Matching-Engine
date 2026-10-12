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
WebSocket:
  /v1/stream/marketdata                     book and trade updates, pushed four times a second
"""
import asyncio
import contextlib
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .audit import AuditLog
from .bots import Bots
from .engine_client import EngineClient
from .exchange import Exchange
from .instruments import load_instruments
from .market_data import MarketData

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
        self.sockets: set[WebSocket] = set()

    def status(self) -> dict:
        return {"data_date": self.instruments[0].data_date, "demo_user": config.DEMO_USER,
                "margin_divisor": config.MIS_MARGIN_DIVISOR, **self.bots.status()}

    def instrument_list(self) -> list[dict]:
        snapshots = self.market.snapshots()
        return [{**i.to_dict(), "market": snapshots[i.symbol]} for i in self.instruments]

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


# ---- portfolio ----

@app.get("/v1/portfolio/{user_id}")
def portfolio(user_id: str) -> dict:
    return sim().exchange.portfolio(require_user(user_id))


@app.post("/v1/portfolio/{user_id}/squareoff")
def square_off(user_id: str) -> list[dict]:
    return [order.to_dict() for order in sim().exchange.square_off(require_user(user_id))]


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
