"""API tests: start the whole app (engine, API) without the live feed and call it over HTTP.
Prices and the market session are fed in by the tests."""
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.main import app

pytestmark = pytest.mark.skipif(not any(config.NSE_DATA_DIR.glob("sec_bhavdata_full_*.csv")),
                                reason="NSE data not downloaded; run scripts/fetch_nse_data.py")


def session(state: str) -> dict:
    return {"state": state, "label": state.title(), "intraday_open": state == "OPEN", "trading_day": "2026-10-15",
            "now": time.time(), "opens_at": 0, "closes_at": 0, "square_off_at": 0}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sim(client):
    s = app.state.sim
    s.session = lambda: session("OPEN")
    yield s
    s.session = lambda: session("CLOSED")


def live_quote(sim, symbol: str) -> dict:
    """Gives a stock a live price a little above its reference close."""
    close = sim.instruments[symbol].close
    tick = sim.instruments[symbol].tick
    ltp = close + 10 * tick
    sim.market.on_quote(symbol, {"ltp": ltp, "bid": ltp - tick, "ask": ltp + tick, "quote_time": int(time.time()) + 1,
                                 "prev_close": close, "volume": 1000})
    return {"ltp": ltp, "bid": ltp - tick, "ask": ltp + tick, "tick": tick}


def test_every_nse_stock_can_be_searched(client):
    body = client.get("/v1/market/symbols").json()
    assert body["count"] > 2000 and body["count"] == len(body["symbols"])
    names = {row[0]: (row[1], row[2]) for row in body["symbols"]}
    assert names["RELIANCE"] == ("RELIANCE INDUSTRIES LIMITED", "EQ")
    symbol, _, _, close, tick, _, lower, upper = next(r for r in body["symbols"] if r[0] == "RELIANCE")
    assert lower < close < upper and lower % tick == 0
    assert set(body["watchlist"]) <= set(names)
    assert {series for _, series in names.values()} == {"EQ", "BE"}


def test_instrument_rules_come_from_nse_data(client):
    for symbol in ("RELIANCE", "M&M", "TCS"):
        inst = client.get(f"/v1/market/instrument/{symbol}").json()
        assert inst["lower_band"] < inst["close"] < inst["upper_band"]
        assert inst["lower_band"] % inst["tick"] == 0 and inst["upper_band"] % inst["tick"] == 0
        assert inst["quote"]["symbol"] == symbol
    assert client.get("/v1/market/instrument/NOPE").status_code == 404


def test_status_says_whether_prices_are_live(client):
    status = client.get("/v1/status").json()
    assert status["live"] is False and status["demo_user"] == config.DEMO_USER
    assert status["session"]["state"] in ("OPEN", "PRE_OPEN", "CLOSED")


def test_market_order_trades_at_the_live_price(client, sim):
    q = live_quote(sim, "TCS")
    order = client.post("/v1/orders", json={"symbol": "TCS", "side": "BUY", "type": "MARKET", "qty": 2}).json()
    assert order["status"] == "FILLED" and order["avg_price"] == q["ask"] and order["charges"]["total"] > 0
    holding = next(h for h in client.get(f"/v1/portfolio/{config.DEMO_USER}").json()["holdings"] if h["symbol"] == "TCS")
    assert holding["qty"] == 2 and holding["ltp"] == q["ltp"]


def test_place_query_and_cancel_an_order(client, sim):
    q = live_quote(sim, "RELIANCE")
    inst = client.get("/v1/market/instrument/RELIANCE").json()
    placed = client.post("/v1/orders", json={"symbol": "RELIANCE", "side": "BUY", "type": "LIMIT",
                                             "product": "CNC", "qty": 5, "price": inst["lower_band"]})
    assert placed.status_code == 201
    order = placed.json()
    assert order["status"] == "OPEN" and not order["amo"]  # far below the market, so it waits in the engine
    book = client.get("/v1/market/orderbook/RELIANCE").json()
    assert book["your_bids"] == [[inst["lower_band"], 5, 1]] and book["ask"] == q["ask"]

    assert client.get(f"/v1/orders/{order['id']}").json()["status"] == "OPEN"
    assert order["id"] in [o["id"] for o in client.get("/v1/orders", params={"open_only": True}).json()]
    portfolio = client.get(f"/v1/portfolio/{config.DEMO_USER}").json()
    assert portfolio["blocked_for_orders"] >= 5 * inst["lower_band"]

    assert client.delete(f"/v1/orders/{order['id']}").json()["status"] == "CANCELLED"
    assert client.delete(f"/v1/orders/{order['id']}").status_code == 409


def test_orders_wait_for_the_market_to_open(client, sim):
    sim.session = lambda: session("CLOSED")
    inst = client.get("/v1/market/instrument/INFY").json()
    order = client.post("/v1/orders", json={"symbol": "INFY", "side": "BUY", "qty": 1, "price": inst["close"]}).json()
    assert order["status"] == "OPEN" and order["amo"]
    intraday = client.post("/v1/orders", json={"symbol": "INFY", "side": "BUY", "qty": 1, "type": "MARKET", "product": "MIS"}).json()
    assert intraday["status"] == "REJECTED" and intraday["reason"] == "INTRADAY_CLOSED"
    assert client.post(f"/v1/portfolio/{config.DEMO_USER}/squareoff").status_code == 409
    client.delete(f"/v1/orders/{order['id']}")


def test_rejections_and_errors(client, sim):
    live_quote(sim, "ITC")
    inst = client.get("/v1/market/instrument/ITC").json()
    rejected = client.post("/v1/orders", json={"symbol": "ITC", "side": "BUY", "qty": 1,
                                               "price": inst["upper_band"] + inst["tick"]}).json()
    assert rejected["status"] == "REJECTED" and rejected["reason"] == "OUTSIDE_PRICE_BAND"
    assert client.post("/v1/orders", json={"symbol": "ITC", "side": "HOLD", "qty": 1}).status_code == 422
    assert client.get("/v1/market/orderbook/NOPE").status_code == 404
    assert client.get("/v1/portfolio/nobody").status_code == 404
    assert client.get("/v1/orders/99999999").status_code == 404


def test_websocket_sends_the_stocks_subscribed_to(client, sim):
    live_quote(sim, "SBIN")
    with client.websocket_connect("/v1/stream/marketdata") as socket:
        hello = socket.receive_json()
        assert hello["type"] == "hello" and "session" in hello["status"]
        socket.send_json({"subscribe": ["SBIN", "sbin", "NOPE"]})
        snapshot = socket.receive_json()
        assert snapshot["type"] == "snapshot" and list(snapshot["quotes"]) == ["SBIN"]
        assert snapshot["quotes"]["SBIN"]["ltp"] is not None


def test_todays_chart_comes_from_memory(client, sim):
    body = client.get("/v1/market/chart/RELIANCE", params={"range": "1d"}).json()
    assert body["range"] == "1d" and isinstance(body["bars"], list)
    assert client.get("/v1/market/chart/RELIANCE", params={"range": "2d"}).status_code == 422
