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
    body = {"symbols": ["RELIANCE", "TCS", "ITC"], "confidences": {"RELIANCE": 60}, "budget": 2_00_000 * RS}
    body.update(overrides)
    return client.post("/v1/recommendations", json=body)


def test_recommendation_end_to_end(client):
    response = ask(client)
    assert response.status_code == 200
    result = response.json()
    stocks = {s["symbol"]: s for s in result["stocks"]}
    assert set(stocks) == {"RELIANCE", "TCS", "ITC"}
    assert stocks["RELIANCE"]["decision"] == "BUY" and stocks["RELIANCE"]["quantity"] > 0
    assert stocks["RELIANCE"]["your_confidence"] == 60 and stocks["TCS"]["your_confidence"] == 50
    assert stocks["ITC"]["decision"] == "DONT_BUY"
    # Without live prices (the tests run offline) quantities use NSE's reference close.
    instrument = client.get("/v1/market/instrument/RELIANCE").json()
    assert stocks["RELIANCE"]["last_price"] in (instrument["quote"]["ltp"], instrument["close"])
    assert result["recommended"]["invested"] <= 2_00_000 * RS
    assert result["data"]["source"] == "test data"


def test_a_negative_view_can_drop_a_stock(client):
    stocks = {s["symbol"]: s for s in ask(client, confidences={"RELIANCE": 0, "TCS": 100}).json()["stocks"]}
    assert stocks["RELIANCE"]["agreement"] < stocks["RELIANCE"]["history_agreement"]
    assert stocks["TCS"]["agreement"] >= stocks["TCS"]["history_agreement"]


@pytest.mark.parametrize("overrides, status, message", [
    ({"symbols": ["RELIANCE"]}, 422, None),
    ({"symbols": ["RELIANCE", "RELIANCE"]}, 422, "only once"),
    ({"symbols": ["RELIANCE", "NOPE"]}, 422, "Unknown stock: NOPE"),
    ({"confidences": {"RELIANCE": 101}}, 422, "between 0 and 100"),
    ({"confidences": {"INFY": 60}}, 422, "not selected"),
    ({"budget": 0}, 422, None),
    ({"budget": 50_00_000 * RS}, 422, "more than your available cash"),
])
def test_invalid_requests(client, overrides, status, message):
    response = ask(client, **overrides)
    assert response.status_code == status
    if message:
        assert message in response.json()["detail"]
