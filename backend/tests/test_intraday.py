"""Intraday signals, your views, levels and sizing, on made-up market snapshots; and the endpoint."""
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.intraday import (MIN_MINUTES, TRADE_THRESHOLD, compute_signals, recommend_intraday,
                                  view_from_confidence)
from backend.app.main import app

NOW = 1_792_040_000.0
RULES = (10, 90_000, 110_000)  # a Rs 1,000 stock: 10 paise tick, band Rs 900 to Rs 1,100
OPEN = {"state": "OPEN", "intraday_open": True, "label": "Market open"}
CLOSED = {"state": "CLOSED", "intraday_open": False, "label": "Market closed"}


def view(trend: int, flow: int, minutes: int = 60, ltp: int = 100_000) -> dict:
    """trend and flow: +1 bullish, -1 bearish, 0 neutral."""
    sigma = 0.0008  # a typical one-minute move of 0.08%
    trades = [{"side": "BUY" if (flow > 0 or (flow == 0 and k % 2)) else "SELL", "qty": 100, "ts": NOW - k} for k in range(30)]
    return {"ltp": ltp, "vwap": ltp - trend * 300, "bid": ltp - 10, "ask": ltp + 10, "polled_at": NOW - 2,
            "tick_time": NOW, "quote_time": NOW, "trades": trades, "sigma": sigma, "minutes": minutes,
            "reference": (NOW - 60, ltp - trend * 150)}


def recommend(views: dict, confidences=None, budget=1_00_000 * 100, session=OPEN):
    return recommend_intraday(views, {s: RULES for s in views}, confidences or {}, budget, 5, session, NOW)


def test_confidence_becomes_a_view():
    assert view_from_confidence(50) == 0 and view_from_confidence(100) == 1 and view_from_confidence(0) == -1
    assert view_from_confidence(75) == 0.5


def test_bullish_market_says_buy_with_no_view():
    signals = compute_signals(view(+1, +1), NOW)
    assert all(value > 0 for value in signals["signals"].values())
    row = recommend({"UP": view(+1, +1)})["stocks"][0]
    assert row["action"] == "BUY" and row["agree"] == 3 and row["score"] >= TRADE_THRESHOLD
    assert row["entry"] == row["best_ask"]


def test_bearish_market_says_sell_short_at_the_bid():
    row = recommend({"DOWN": view(-1, -1)})["stocks"][0]
    assert row["action"] == "SELL" and row["entry"] == row["best_bid"]


def test_your_view_decides_when_the_market_is_flat():
    flat = {"FLAT": view(0, 0)}
    assert recommend(flat)["stocks"][0]["action"] == "NO_TRADE"
    assert recommend(flat, {"FLAT": 100})["stocks"][0]["action"] == "BUY"
    assert recommend(flat, {"FLAT": 0})["stocks"][0]["action"] == "SELL"


def test_a_strong_opposite_view_holds_back_a_trade():
    row = recommend({"UP": view(+1, +1)}, {"UP": 0})["stocks"][0]
    assert row["action"] == "NO_TRADE" and row["model_score"] > 0 and row["your_view"] == -1


def test_too_little_trading_today_says_wait():
    row = recommend({"NEW": view(+1, +1, minutes=MIN_MINUTES - 1)})["stocks"][0]
    assert row["action"] == "WAIT" and row["signals"] is None


def test_no_trades_when_intraday_is_closed():
    row = recommend({"UP": view(+1, +1)}, session=CLOSED)["stocks"][0]
    assert row["action"] == "WAIT" and "9:15" in row["note"]
    assert row["signals"] is not None  # the live signals are still shown


def test_levels_are_on_the_tick_and_inside_the_band():
    row = recommend({"UP": view(+1, +1)})["stocks"][0]
    tick, lower, upper = RULES
    assert lower <= row["stop_loss"] < row["entry"] < row["target"] <= upper
    for price in (row["entry"], row["stop_loss"], row["target"]):
        assert price % tick == 0
    assert row["reward_per_share"] >= 2 * row["risk_per_share"] - tick


def test_sizing_stays_within_margin_and_leverage():
    budget = 50_000 * 100
    result = recommend({"UP": view(+1, +1), "DOWN": view(-1, -1), "FLAT": view(0, 0)}, budget=budget)
    totals = result["totals"]
    assert totals["trades"] == 2
    assert totals["margin"] <= budget + 2  # each position's margin is rounded up by under a paisa
    assert totals["exposure"] <= budget * 5
    for row in result["stocks"]:
        if row["quantity"]:
            assert row["position_value"] == row["quantity"] * row["entry"]
            assert row["max_loss"] == row["quantity"] * row["risk_per_share"]
    assert result["stocks"][-1]["action"] == "NO_TRADE"  # trades are listed first


def test_twenty_stocks_take_well_under_a_millisecond_each():
    views = {f"S{i}": view((-1) ** i, (-1) ** i) for i in range(20)}
    recommend(views)  # warm up
    started = time.perf_counter()
    for _ in range(200):
        recommend(views)
    per_call_ms = (time.perf_counter() - started) / 200 * 1000
    assert per_call_ms < 10, per_call_ms  # typically under 1 ms; generous for slow machines


pytestmark_api = pytest.mark.skipif(not any(config.NSE_DATA_DIR.glob("sec_bhavdata_full_*.csv")),
                                    reason="NSE data not downloaded")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytestmark_api
def test_intraday_endpoint(client):
    response = client.post("/v1/recommendations/intraday",
                           json={"symbols": ["RELIANCE", "TCS"], "confidences": {"RELIANCE": 70}, "budget": 50_000 * 100})
    assert response.status_code == 200
    body = response.json()
    assert {r["symbol"] for r in body["stocks"]} == {"RELIANCE", "TCS"}
    assert body["inputs"]["confidences"] == {"RELIANCE": 70, "TCS": 50}
    assert body["timing"]["total_us"] < 50_000 and body["timing"]["total_us"] >= body["timing"]["signals_us"]
    assert body["method"]["leverage"] == config.MIS_MARGIN_DIVISOR
    # Offline there are no prices, so the stocks wait rather than guess.
    assert all(r["action"] == "WAIT" for r in body["stocks"])


@pytestmark_api
@pytest.mark.parametrize("body, message", [
    ({"symbols": [], "budget": 100}, None),
    ({"symbols": ["RELIANCE", "RELIANCE"], "budget": 100}, "only once"),
    ({"symbols": ["NOPE"], "budget": 100}, "Unknown stock"),
    ({"symbols": ["RELIANCE"], "confidences": {"RELIANCE": 101}, "budget": 100}, "between 0 and 100"),
    ({"symbols": ["RELIANCE"], "confidences": {"TCS": 60}, "budget": 100}, "not selected"),
    ({"symbols": ["RELIANCE"], "budget": 0}, None),
    ({"symbols": ["RELIANCE"], "budget": 10**12}, "available cash"),
])
def test_intraday_validation(client, body, message):
    response = client.post("/v1/recommendations/intraday", json=body)
    assert response.status_code == 422
    if message:
        assert message in response.json()["detail"]
