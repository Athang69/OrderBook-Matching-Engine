"""The recommendation endpoint, with made-up price history so no network is needed."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

import recomendation_system
from backend.app import config
from backend.app.main import app
from recomendation_system.data import PriceHistory

pytestmark = pytest.mark.skipif(not any(config.NSE_DATA_DIR.glob("sec_bhavdata_full_*.csv")),
                                reason="NSE data not downloaded; run scripts/fetch_nse_data.py")

RS = 100


def fake_prices(symbols, start):
    """A clear winner (the first stock), a middling stock and losers."""
    rng = np.random.default_rng(7)
    specs = [(0.0015, 0.008), (0.0001, 0.012)] + [(-0.0008, 0.015)] * (len(symbols) - 2)
    returns = np.column_stack([rng.normal(m, v, 1200) for m, v in specs])
    prices = np.vstack([np.full(len(symbols), 100.0), 100.0 * np.exp(np.cumsum(returns, axis=0))])
    return PriceHistory([f"d{i}" for i in range(len(prices))], prices, "test data", False)


@pytest.fixture(scope="module")
def client():
    patch = pytest.MonkeyPatch()
    patch.setattr(recomendation_system, "load_prices", fake_prices)
    with TestClient(app) as test_client:
        yield test_client
    patch.undo()


def ask(client, **overrides):
    body = {"symbols": ["RELIANCE", "TCS", "ITC"], "confidence": 70, "budget": 2_00_000 * RS}
    body.update(overrides)
    return client.post("/v1/recommendations", json=body)


def test_recommendation_end_to_end(client):
    response = ask(client)
    assert response.status_code == 200
    result = response.json()
    stocks = {s["symbol"]: s for s in result["stocks"]}
    assert set(stocks) == {"RELIANCE", "TCS", "ITC"}
    assert stocks["RELIANCE"]["decision"] == "BUY" and stocks["RELIANCE"]["quantity"] > 0
    assert stocks["ITC"]["decision"] == "DONT_BUY"
    # Quantities use the simulator's current price, not the history's.
    market = client.get("/v1/market/orderbook/RELIANCE").json()
    instrument = next(i for i in client.get("/v1/market/instruments").json() if i["symbol"] == "RELIANCE")
    assert stocks["RELIANCE"]["last_price"] in (market["ltp"], instrument["prev_close"])
    assert result["recommended"]["invested"] <= 2_00_000 * RS
    assert result["data"]["source"] == "test data"


@pytest.mark.parametrize("overrides, status, message", [
    ({"symbols": ["RELIANCE"]}, 422, None),
    ({"symbols": ["RELIANCE", "RELIANCE"]}, 422, "only once"),
    ({"symbols": ["RELIANCE", "NOPE"]}, 422, "Unknown stock: NOPE"),
    ({"confidence": 49}, 422, None),
    ({"confidence": 99.5}, 422, None),
    ({"budget": 0}, 422, None),
    ({"budget": 50_00_000 * RS}, 422, "more than your available cash"),
])
def test_invalid_requests(client, overrides, status, message):
    response = ask(client, **overrides)
    assert response.status_code == status
    if message:
        assert message in response.json()["detail"]
