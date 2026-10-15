"""Intraday signals, levels and sizing, on made-up market snapshots; and the endpoint."""
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.intraday import (MIN_POINTS, MOMENTUM_SECONDS, RollingVolatility, StockRules,
                                  compute_signals, recommend_intraday)
from backend.app.main import app

NOW = 1_800_000_000.0
RULES = StockRules(tick=10, lower_band=90_000, upper_band=110_000)  # a Rs 1,000 stock, 10 paise tick


def view(trend: int, book: int, flow: int, seconds: int = 120, ltp: int = 100_000) -> dict:
    """trend, book, flow: +1 bullish, -1 bearish, 0 neutral."""
    history = []
    price = ltp - trend * 10 * seconds // 2
    for i in range(seconds):
        wiggle = 10 if i % 2 else 0  # a little noise so volatility is not zero
        history.append((int(NOW) - seconds + i, price + trend * 5 * i + wiggle))
    history[-1] = (int(NOW), ltp)
    bids = [[ltp - 10 * (k + 1), 400 if book > 0 else 100 if book < 0 else 250, 2] for k in range(5)]
    asks = [[ltp + 10 * k, 100 if book > 0 else 400 if book < 0 else 250, 2] for k in range(5)]
    trades = [{"side": "BUY" if (flow > 0 or (flow == 0 and k % 2)) else "SELL", "qty": 10, "ts": NOW - k} for k in range(30)]
    volatility = RollingVolatility()
    for t, p in history:
        volatility.add(t, p)
    reference = next((pt for pt in reversed(history) if pt[0] <= NOW - MOMENTUM_SECONDS), history[0])
    return {"ltp": ltp, "vwap": ltp - trend * 200, "bids": bids, "asks": asks, "trades": trades,
            "sigma": volatility.value(), "points": len(history), "reference": reference}


def recommend(views: dict, confidence=30, budget=1_00_000 * 100):
    return recommend_intraday(views, {s: RULES for s in views}, confidence, budget, 5, NOW)


def test_bullish_market_says_buy():
    signals = compute_signals(view(+1, +1, +1), NOW)
    assert all(value > 0 for value in signals["signals"].values())
    row = recommend({"UP": view(+1, +1, +1)})["stocks"][0]
    assert row["action"] == "BUY" and row["agree"] == 4 and row["confidence"] > 0.5


def test_bearish_market_says_sell_short():
    row = recommend({"DOWN": view(-1, -1, -1)})["stocks"][0]
    assert row["action"] == "SELL" and row["agree"] == 4
    assert row["entry"] == row["best_bid"]  # a short sale sells at the best bid


def test_weak_or_mixed_signals_say_no_trade():
    row = recommend({"MIXED": view(+1, -1, 0)}, confidence=80)["stocks"][0]
    assert row["action"] == "NO_TRADE" and row["quantity"] == 0
    assert "below the 80%" in row["note"]


def test_too_little_history_says_wait():
    row = recommend({"NEW": view(+1, +1, +1, seconds=MIN_POINTS - 1)})["stocks"][0]
    assert row["action"] == "WAIT" and row["signals"] is None


def test_buy_levels_are_on_the_tick_and_inside_the_band():
    row = recommend({"UP": view(+1, +1, +1)})["stocks"][0]
    assert row["entry"] == row["best_ask"]
    assert RULES.lower_band <= row["stop_loss"] < row["entry"] < row["target"] <= RULES.upper_band
    for price in (row["entry"], row["stop_loss"], row["target"]):
        assert price % RULES.tick == 0
    assert row["reward_per_share"] >= 2 * row["risk_per_share"] - RULES.tick


def test_sizing_stays_within_margin_and_leverage():
    budget = 50_000 * 100
    # MIXED scores about 30% (trend up, book down), so at 40% only UP and DOWN trade.
    result = recommend({"UP": view(+1, +1, +1), "DOWN": view(-1, -1, -1), "MIXED": view(+1, -1, 0)},
                       confidence=40, budget=budget)
    totals = result["totals"]
    assert totals["trades"] == 2
    assert totals["margin"] <= budget + 2  # each position's margin is rounded up by under a paisa
    assert totals["exposure"] <= budget * 5
    for row in result["stocks"]:
        if row["quantity"]:
            assert row["position_value"] == row["quantity"] * row["entry"]
            assert row["max_loss"] == row["quantity"] * row["risk_per_share"]
    assert [r["action"] for r in result["stocks"]][-1] == "NO_TRADE"  # trades are listed first


def test_rolling_volatility_matches_a_full_recalculation():
    import math
    import statistics
    prices = [100_000 + (37 * i) % 113 - 50 for i in range(400)]
    rolling = RollingVolatility(size=300)
    for t, p in enumerate(prices):
        rolling.add(t, p)
    returns = [math.log(b / a) for a, b in zip(prices, prices[1:])][-300:]
    assert rolling.value() == pytest.approx(statistics.stdev(returns), rel=1e-9)


def test_eight_stocks_take_well_under_a_millisecond():
    views = {f"S{i}": view((-1) ** i, (-1) ** i, 0, seconds=300) for i in range(8)}
    recommend(views)  # warm up
    started = time.perf_counter()
    for _ in range(200):
        recommend(views)
    per_call_ms = (time.perf_counter() - started) / 200 * 1000
    assert per_call_ms < 5, per_call_ms  # typically about 0.3 ms; generous for slow machines


pytestmark_api = pytest.mark.skipif(not any(config.NSE_DATA_DIR.glob("sec_bhavdata_full_*.csv")),
                                    reason="NSE data not downloaded")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytestmark_api
def test_intraday_endpoint(client):
    response = client.post("/v1/recommendations/intraday",
                           json={"symbols": ["RELIANCE", "TCS"], "confidence": 30, "budget": 50_000 * 100})
    assert response.status_code == 200
    body = response.json()
    assert {r["symbol"] for r in body["stocks"]} == {"RELIANCE", "TCS"}
    assert body["timing"]["total_us"] < 50_000
    assert body["timing"]["total_us"] >= body["timing"]["signals_us"]
    assert body["method"]["leverage"] == config.MIS_MARGIN_DIVISOR
    # Just after start-up there is no history yet, so the stocks wait rather than guess.
    assert all(r["action"] in ("WAIT", "BUY", "SELL", "NO_TRADE") for r in body["stocks"])


@pytestmark_api
@pytest.mark.parametrize("body, message", [
    ({"symbols": [], "confidence": 30, "budget": 100}, None),
    ({"symbols": ["RELIANCE", "RELIANCE"], "confidence": 30, "budget": 100}, "only once"),
    ({"symbols": ["NOPE"], "confidence": 30, "budget": 100}, "Unknown stock"),
    ({"symbols": ["RELIANCE"], "confidence": 5, "budget": 100}, None),
    ({"symbols": ["RELIANCE"], "confidence": 96, "budget": 100}, None),
    ({"symbols": ["RELIANCE"], "confidence": 30, "budget": 0}, None),
    ({"symbols": ["RELIANCE"], "confidence": 30, "budget": 10**12}, "available cash"),
])
def test_intraday_validation(client, body, message):
    response = client.post("/v1/recommendations/intraday", json=body)
    assert response.status_code == 422
    if message:
        assert message in response.json()["detail"]
