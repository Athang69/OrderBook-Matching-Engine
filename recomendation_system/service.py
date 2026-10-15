"""The recommendation system's entry point: which of the chosen stocks to buy, and how much, combining
the price history with your own view of each stock.

Steps:
  1. Load daily closing prices for the chosen stocks (data.py).
  2. Your views. For each stock you read its latest news and say how confident you are that it will
     do well (0 to 100%; 50% means no view). This moves the stock's expected annual return up or down
     by up to half of its annual volatility: at 100% it rises by half a volatility, at 0% it falls by
     the same. This is a simplified form of the Black-Litterman idea of blending an investor's views
     with the market's history.
  3. Run the original method (portfolio.py) with those returns: Monte Carlo portfolios, then SLSQP for
     the maximum Sharpe ratio and minimum volatility portfolios.
  4. Agreement: re-run the maximum Sharpe optimisation on 200 resamples of the history, with your views
     and, for comparison, without them. A stock's agreement is how often it received at least 5% of
     the money.
  5. Recommend BUY for every stock picked in at least half of the re-runs with your views.
  6. Re-optimise over just those stocks, split the budget, and convert it to whole shares.
"""
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from . import portfolio as pf
from .data import PriceDataError, PriceHistory, load_prices


class RecommendationError(ValueError):
    """A problem with the request or the data, worded for the user."""


@dataclass(frozen=True)
class Settings:
    history_start: str = "2015-01-01"  # as in the original script
    risk_free_rate: float = 0.065  # Changed: the original used 2%; this is closer to Indian treasury bill yields
    monte_carlo_portfolios: int = 20_000  # as in the original script
    resamples: int = 200
    min_weight: float = 0.05  # a stock "counts" in a run if it gets at least 5% of the money
    buy_agreement: float = 0.5  # BUY when picked in at least half of the runs
    view_strength: float = 0.5  # a 100% or 0% view moves the expected return by half a volatility
    var_confidence: float = 95  # for the one-day value at risk
    min_trading_days: int = 250
    frontier_points: int = 1500  # how many Monte Carlo portfolios to send back for the chart
    seed: int = 42  # same inputs give the same answer
    max_stocks: int = 10


Loader = Callable[[list[str], str], PriceHistory]


def view_tilts(confidences: list[float], volatilities: np.ndarray, strength: float) -> np.ndarray:
    """How much each view adds to the expected annual return: from -strength to +strength volatilities."""
    views = np.clip((np.asarray(confidences, dtype=float) - 50.0) / 50.0, -1.0, 1.0)
    return strength * views * volatilities


def recommend(symbols: list[str], confidences: dict[str, float], budget: int, last_prices: dict[str, int],
              loader: Loader = load_prices, settings: Settings = Settings()) -> dict:
    """`budget` and `last_prices` are in paise. `confidences` holds your confidence in each stock, 0 to 100."""
    started = time.perf_counter()
    symbols, yours = _validate(symbols, confidences, budget, last_prices, settings)

    try:
        history = loader(symbols, settings.history_start)
    except PriceDataError as err:
        raise RecommendationError(str(err)) from err
    if len(history.dates) < settings.min_trading_days + 1:
        raise RecommendationError(
            f"Only {len(history.dates)} trading days of shared price history were found for these stocks; "
            f"at least {settings.min_trading_days} are needed. A recently listed stock shortens the shared history; "
            "try without it.")

    rng = np.random.default_rng(settings.seed)
    returns = pf.log_returns(history.prices)
    annual_returns, annual_cov = pf.annualise(returns)
    volatilities = np.sqrt(np.diag(annual_cov))
    tilts = view_tilts(yours, volatilities, settings.view_strength)
    viewed_returns = annual_returns + tilts
    rf = settings.risk_free_rate

    # The original method, with your views in the expected returns.
    cloud_returns, cloud_vols, cloud_sharpes = pf.monte_carlo(viewed_returns, annual_cov, rf,
                                                              settings.monte_carlo_portfolios, rng)
    history_weights = pf.max_sharpe_weights(annual_returns, annual_cov, rf)
    sharpe_weights = pf.max_sharpe_weights(viewed_returns, annual_cov, rf)
    min_vol_weights = pf.min_volatility_weights(annual_cov)

    # Agreement, with and without your views, and the decision.
    history_agreement, agreement = pf.selection_confidence(returns, rf, settings.resamples, settings.min_weight, rng,
                                                           tilts=[np.zeros(len(symbols)), tilts])
    buy = [i for i in range(len(symbols)) if agreement[i] >= settings.buy_agreement - 1e-9]

    # The recommended portfolio: re-optimised over the stocks marked BUY.
    weights = np.zeros(len(symbols))
    if len(buy) == 1:
        weights[buy[0]] = 1.0
    elif len(buy) > 1:
        weights[buy] = pf.max_sharpe_weights(viewed_returns[buy], annual_cov[np.ix_(buy, buy)], rf)

    stocks = []
    invested = 0
    for i, symbol in enumerate(symbols):
        price = last_prices[symbol]
        amount = int(budget * weights[i])
        quantity = amount // price if weights[i] > 0 else 0
        cost = quantity * price
        invested += cost
        decision = "BUY" if i in buy else "DONT_BUY"
        stocks.append({
            "symbol": symbol,
            "decision": decision,
            "your_confidence": yours[i],
            "return_shift": round(float(tilts[i]), 4),
            "agreement": round(float(agreement[i]), 4),
            "history_agreement": round(float(history_agreement[i]), 4),
            "weight": round(float(weights[i]), 4),
            "amount": amount,
            "last_price": price,
            "quantity": int(quantity),
            "cost": int(cost),
            "history_weight": round(float(history_weights[i]), 4),
            "max_sharpe_weight": round(float(sharpe_weights[i]), 4),
            "min_vol_weight": round(float(min_vol_weights[i]), 4),
            "expected_return": round(float(annual_returns[i]), 4),
            "expected_return_with_view": round(float(viewed_returns[i]), 4),
            "volatility": round(float(volatilities[i]), 4),
            "note": _note(decision, agreement[i], history_agreement[i], settings.buy_agreement, weights[i], quantity),
        })
    stocks.sort(key=lambda s: (s["decision"] != "BUY", -s["weight"], -s["agreement"]))

    recommended = None
    if buy:
        rec_vol = pf.portfolio_volatility(weights, annual_cov)
        rec_ret = pf.portfolio_return(weights, viewed_returns)
        var = pf.value_at_risk(weights, returns, settings.var_confidence)
        recommended = {
            "symbols": [symbols[i] for i in buy],
            "expected_return": round(rec_ret, 4),
            "expected_return_history": round(pf.portfolio_return(weights, annual_returns), 4),
            "volatility": round(rec_vol, 4),
            "sharpe": round((rec_ret - rf) / rec_vol, 3) if rec_vol > 0 else None,
            "value_at_risk": {"confidence": settings.var_confidence, "one_day_fraction": round(var, 5),
                              "one_day_amount": int(var * invested)},
            "invested": int(invested),
            "cash_left": int(budget - invested),
        }

    sample = rng.choice(len(cloud_returns), size=min(settings.frontier_points, len(cloud_returns)), replace=False)
    return {
        "inputs": {"symbols": symbols, "confidences": dict(zip(symbols, yours)), "budget": budget},
        "data": {"source": history.source, "start": history.dates[0], "end": history.dates[-1],
                 "trading_days": len(history.dates), "stale": history.stale},
        "method": {"monte_carlo_portfolios": settings.monte_carlo_portfolios, "resamples": settings.resamples,
                   "min_weight": settings.min_weight, "buy_agreement": settings.buy_agreement,
                   "view_strength": settings.view_strength, "risk_free_rate": rf,
                   "trading_days_per_year": pf.TRADING_DAYS},
        "stocks": stocks,
        "recommended": recommended,
        "reference_portfolios": {
            "history_only": _summary(history_weights, annual_returns, annual_cov, rf, symbols),
            "max_sharpe": _summary(sharpe_weights, viewed_returns, annual_cov, rf, symbols),
            "min_volatility": _summary(min_vol_weights, viewed_returns, annual_cov, rf, symbols),
        },
        "frontier": {
            "points": [[round(float(cloud_vols[k]), 4), round(float(cloud_returns[k]), 4), round(float(cloud_sharpes[k]), 3)]
                       for k in sample],
        },
        "runtime_ms": int((time.perf_counter() - started) * 1000),
    }


def _validate(symbols: list[str], confidences: dict[str, float], budget: int, last_prices: dict[str, int],
              settings: Settings) -> tuple[list[str], list[float]]:
    cleaned = [s.strip().upper() for s in symbols]
    if len(set(cleaned)) != len(cleaned):
        raise RecommendationError("Each stock can be selected only once.")
    if len(cleaned) < 2:
        raise RecommendationError("Select at least two stocks: a portfolio needs more than one to divide money between.")
    if len(cleaned) > settings.max_stocks:
        raise RecommendationError(f"Select at most {settings.max_stocks} stocks.")
    given = {k.strip().upper(): v for k, v in confidences.items()}
    yours = [float(given.get(s, 50.0)) for s in cleaned]
    if any(not 0 <= c <= 100 for c in yours):
        raise RecommendationError("Each confidence must be between 0% and 100%.")
    if budget <= 0:
        raise RecommendationError("The amount to invest must be more than zero.")
    missing = [s for s in cleaned if not last_prices.get(s)]
    if missing:
        raise RecommendationError(f"No current price for {', '.join(missing)}.")
    return cleaned, yours


def _note(decision: str, agreement: float, history_agreement: float, needed: float, weight: float, quantity: int) -> str:
    shown = f"{round(agreement * 100, 1):g}%"
    before = f"{round(history_agreement * 100, 1):g}%"
    change = "" if abs(agreement - history_agreement) < 0.005 else f" ({before} on price history alone)"
    if decision == "DONT_BUY":
        return f"Picked in {shown} of re-runs with your views{change}; a buy needs {needed * 100:g}%."
    if quantity == 0:
        return f"Picked in {shown} of re-runs with your views{change}, but its share of the money is less than one share's price."
    return f"Picked in {shown} of re-runs with your views{change}; gets {weight * 100:.1f}% of the money."


def _summary(weights: np.ndarray, annual_returns: np.ndarray, annual_cov: np.ndarray, rf: float,
             symbols: list[str]) -> dict:
    ret = pf.portfolio_return(weights, annual_returns)
    vol = pf.portfolio_volatility(weights, annual_cov)
    return {"expected_return": round(ret, 4), "volatility": round(vol, 4),
            "sharpe": round((ret - rf) / vol, 3) if vol > 0 else None,
            "weights": {s: round(float(w), 4) for s, w in zip(symbols, weights)}}
