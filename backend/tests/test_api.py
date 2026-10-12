"""API tests: start the whole simulator (engine, robot traders, API) and call it over HTTP."""
import pytest
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.main import app

pytestmark = pytest.mark.skipif(not any(config.NSE_DATA_DIR.glob("sec_bhavdata_full_*.csv")),
                                reason="NSE data not downloaded; run scripts/fetch_nse_data.py")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_instruments_come_from_nse_data(client):
    instruments = client.get("/v1/market/instruments").json()
    assert [i["symbol"] for i in instruments] == config.SYMBOLS
    for inst in instruments:
        assert inst["lower_band"] < inst["prev_close"] < inst["upper_band"]
        assert inst["lower_band"] % inst["tick"] == 0 and inst["upper_band"] % inst["tick"] == 0


def test_place_query_and_cancel_an_order(client):
    inst = client.get("/v1/market/instruments").json()[0]
    placed = client.post("/v1/orders", json={"symbol": inst["symbol"], "side": "BUY", "type": "LIMIT",
                                             "product": "CNC", "qty": 5, "price": inst["lower_band"]})
    assert placed.status_code == 201
    order = placed.json()
    assert order["status"] == "OPEN"  # far below the market, so it waits in the book

    assert client.get(f"/v1/orders/{order['id']}").json()["status"] == "OPEN"
    assert order["id"] in [o["id"] for o in client.get("/v1/orders", params={"open_only": True}).json()]
    portfolio = client.get(f"/v1/portfolio/{config.DEMO_USER}").json()
    assert portfolio["blocked_for_orders"] >= 5 * inst["lower_band"]

    assert client.delete(f"/v1/orders/{order['id']}").json()["status"] == "CANCELLED"
    assert client.delete(f"/v1/orders/{order['id']}").status_code == 409


def test_rejections_and_errors(client):
    inst = client.get("/v1/market/instruments").json()[0]
    rejected = client.post("/v1/orders", json={"symbol": inst["symbol"], "side": "BUY", "qty": 1,
                                               "price": inst["upper_band"] + inst["tick"]}).json()
    assert rejected["status"] == "REJECTED" and rejected["reason"] == "OUTSIDE_PRICE_BAND"
    assert client.post("/v1/orders", json={"symbol": inst["symbol"], "side": "HOLD", "qty": 1}).status_code == 422
    assert client.get("/v1/market/orderbook/NOPE").status_code == 404
    assert client.get("/v1/portfolio/nobody").status_code == 404
    assert client.get("/v1/orders/99999999").status_code == 404


def test_websocket_sends_instruments_on_connect(client):
    with client.websocket_connect("/v1/stream/marketdata") as socket:
        hello = socket.receive_json()
        assert hello["type"] == "hello"
        assert len(hello["instruments"]) == len(config.SYMBOLS)
        assert hello["sim"]["bots_enabled"] is True
