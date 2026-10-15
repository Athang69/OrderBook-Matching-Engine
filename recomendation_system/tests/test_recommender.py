"""Tests for the recommendation system. They use made-up price histories, so no network is needed."""
import numpy as np
import pytest

from recomendation_system import portfolio as pf
from recomendation_system.data import PriceHistory
from recomendation_system.service import RecommendationError, Settings, recommend

FAST = Settings(monte_carlo_portfolios=3000, resamples=80, frontier_points=200)
PRICES = {"AAA": 100_00, "BBB": 250_00, "CCC": 50_00}

# Daily (mean, volatility) of log returns: AAA is clearly the best, CCC loses money.
STRONG, MIDDLING, LOSING = (0.0015, 0.008), (0.0001, 0.012), (-0.0008, 0.015)


def history(specs=(STRONG, MIDDLING, LOSING), days=1500, seed=1) -> PriceHistory:
    rng = np.random.default_rng(seed)
    returns = np.column_stack([rng.normal(mean, vol, days) for mean, vol in specs])
    prices = np.vstack([np.full(len(specs), 100.0), 100.0 * np.exp(np.cumsum(returns, axis=0))])
    return PriceHistory([f"2020-01-{i}" for i in range(len(prices))], prices, "synthetic", False)


def run(confidence=70, budget=10_00_000 * 100, h=None, symbols=("AAA", "BBB", "CCC")):
    data = h or history()
    return recommend(list(symbols), confidence, budget, PRICES, loader=lambda _s, _start: data, settings=FAST)


def test_optimal_weights_are_valid():
    returns = pf.log_returns(history().prices)
    mu, cov = pf.annualise(returns)
    for weights in (pf.max_sharpe_weights(mu, cov, 0.065), pf.min_volatility_weights(cov)):
        assert weights.sum() == pytest.approx(1.0)
        assert (weights >= 0).all() and (weights <= 1).all()


def test_optimisers_beat_every_random_portfolio():
    returns = pf.log_returns(history().prices)
    mu, cov = pf.annualise(returns)
    rets, vols, sharpes = pf.monte_carlo(mu, cov, 0.065, 5000, np.random.default_rng(0))
    best = pf.max_sharpe_weights(mu, cov, 0.065)
    safest = pf.min_volatility_weights(cov)
    assert -pf.negative_sharpe_ratio(best, mu, cov, 0.065) >= sharpes.max() - 1e-6
    assert pf.portfolio_volatility(safest, cov) <= vols.min() + 1e-6


def test_confidence_separates_strong_and_losing_stocks():
    returns = pf.log_returns(history().prices)
    confidence = pf.selection_confidence(returns, 0.065, 100, 0.05, np.random.default_rng(0))
    assert confidence[0] > 0.9  # the strong stock is picked in almost every run
    assert confidence[2] < 0.1  # the losing stock almost never


def test_recommends_only_confident_stocks_and_splits_the_budget():
    result = run(confidence=70)
    by_symbol = {s["symbol"]: s for s in result["stocks"]}
    for stock in result["stocks"]:
        assert (stock["decision"] == "BUY") == (stock["confidence"] * 100 >= 70)
        assert stock["cost"] == stock["quantity"] * stock["last_price"] <= stock["amount"]
    assert by_symbol["AAA"]["decision"] == "BUY"
    assert by_symbol["CCC"]["decision"] == "DONT_BUY" and by_symbol["CCC"]["quantity"] == 0
    rec = result["recommended"]
    assert sum(s["weight"] for s in result["stocks"]) == pytest.approx(1.0, abs=1e-3)
    assert rec["invested"] + rec["cash_left"] == 10_00_000 * 100
    assert rec["invested"] == sum(s["cost"] for s in result["stocks"])
    assert result["stocks"][0]["decision"] == "BUY"  # buys are listed first


def test_nothing_to_buy_when_no_stock_is_confident_enough():
    # Three similar stocks: the optimiser's choice is never stable, so 99% is out of reach.
    similar = history(specs=((0.0003, 0.012),) * 3, seed=3)
    result = run(confidence=99, h=similar)
    assert result["recommended"] is None
    assert all(s["decision"] == "DONT_BUY" and s["quantity"] == 0 for s in result["stocks"])


def test_value_at_risk_grows_with_confidence():
    returns = pf.log_returns(history().prices)
    weights = np.array([0.5, 0.3, 0.2])
    assert pf.value_at_risk(weights, returns, 95) > pf.value_at_risk(weights, returns, 60) > 0


def test_same_inputs_give_the_same_answer():
    first, second = run(), run()
    first.pop("runtime_ms"), second.pop("runtime_ms")
    assert first == second


def test_result_describes_data_and_method():
    result = run()
    assert result["data"]["trading_days"] == 1501
    assert result["method"]["resamples"] == FAST.resamples
    assert len(result["frontier"]["points"]) == FAST.frontier_points
    assert set(result["reference_portfolios"]) == {"max_sharpe", "min_volatility"}


@pytest.mark.parametrize("kwargs, message", [
    ({"symbols": ("AAA",)}, "at least two"),
    ({"symbols": ("AAA", "AAA")}, "only once"),
    ({"confidence": 40}, "between 50% and 99%"),
    ({"confidence": 100}, "between 50% and 99%"),
    ({"budget": 0}, "more than zero"),
    ({"symbols": ("AAA", "ZZZ")}, "No current price for ZZZ"),
])
def test_invalid_requests_are_refused(kwargs, message):
    with pytest.raises(RecommendationError, match=message):
        run(**kwargs)


def test_too_little_history_is_refused():
    with pytest.raises(RecommendationError, match="trading days"):
        run(h=history(days=100))
