"""The recommendation system's entry point: which of the chosen stocks to buy, and how much.

Steps:
  1. Load daily closing prices for the chosen stocks (data.py).
  2. Run the original method (portfolio.py): Monte Carlo portfolios, then SLSQP for the
     maximum Sharpe ratio and minimum volatility portfolios.
  3. Confidence: re-run the maximum Sharpe optimisation on resampled history. A stock's
     confidence is how often it received at least 5% of the money.
  4. Recommend BUY for every stock whose confidence is at or above the confidence the user asked for.
  5. Re-optimise over just those stocks, split the budget, and convert it to whole shares.
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
    min_trading_days: int = 250
    frontier_points: int = 1500  # how many Monte Carlo portfolios to send back for the chart
    seed: int = 42  # same inputs give the same answer
    min_confidence: float = 50
    max_confidence: float = 99
    max_stocks: int = 10


Loader = Callable[[list[str], str], PriceHistory]


def recommend(symbols: list[str], confidence: float, budget: int, last_prices: dict[str, int],
              loader: Loader = load_prices, settings: Settings = Settings()) -> dict:
    """`budget` and `last_prices` are in paise. `confidence` is a percentage, e.g. 80."""
    started = time.perf_counter()
    symbols = _validate(symbols, confidence, budget, last_prices, settings)

    try:
        history = loader(symbols, settings.history_start)
    except PriceDataError as err:
        raise RecommendationError(str(err)) from err
    if len(history.dates) < settings.min_trading_days + 1:
        raise RecommendationError(
            f"Only {len(history.dates)} trading days of shared price history were found for these stocks; "
            f"at least {settings.min_trading_days} are needed.")

    rng = np.random.default_rng(settings.seed)
    returns = pf.log_returns(history.prices)
    annual_returns, annual_cov = pf.annualise(returns)
    rf = settings.risk_free_rate

    # The original method over all the chosen stocks.
    cloud_returns, cloud_vols, cloud_sharpes = pf.monte_carlo(annual_returns, annual_cov, rf,
                                                              settings.monte_carlo_portfolios, rng)
    sharpe_weights = pf.max_sharpe_weights(annual_returns, annual_cov, rf)
    min_vol_weights = pf.min_volatility_weights(annual_cov)

    # Confidence and the decision.
    stock_confidence = pf.selection_confidence(returns, rf, settings.resamples, settings.min_weight, rng)
    buy = [i for i in range(len(symbols)) if stock_confidence[i] * 100 >= confidence - 1e-9]

    # The recommended portfolio: re-optimised over the stocks marked BUY.
    weights = np.zeros(len(symbols))
    if len(buy) == 1:
        weights[buy[0]] = 1.0
    elif len(buy) > 1:
        weights[buy] = pf.max_sharpe_weights(annual_returns[buy], annual_cov[np.ix_(buy, buy)], rf)

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
            "confidence": round(float(stock_confidence[i]), 4),
            "weight": round(float(weights[i]), 4),
            "amount": amount,
            "last_price": price,
            "quantity": int(quantity),
            "cost": int(cost),
            "max_sharpe_weight": round(float(sharpe_weights[i]), 4),
            "min_vol_weight": round(float(min_vol_weights[i]), 4),
            "expected_return": round(float(annual_returns[i]), 4),
            "volatility": round(float(np.sqrt(annual_cov[i, i])), 4),
            "note": _note(decision, stock_confidence[i], confidence, weights[i], quantity, price),
        })
    stocks.sort(key=lambda s: (s["decision"] != "BUY", -s["weight"], -s["confidence"]))

    recommended = None
    if buy:
        rec_ret = pf.portfolio_return(weights, annual_returns)
        rec_vol = pf.portfolio_volatility(weights, annual_cov)
        var = pf.value_at_risk(weights, returns, confidence)
        recommended = {
            "symbols": [symbols[i] for i in buy],
            "expected_return": round(rec_ret, 4),
            "volatility": round(rec_vol, 4),
            "sharpe": round((rec_ret - rf) / rec_vol, 3) if rec_vol > 0 else None,
            "value_at_risk": {"confidence": confidence, "one_day_fraction": round(var, 5),
                              "one_day_amount": int(var * invested)},
            "invested": int(invested),
            "cash_left": int(budget - invested),
        }

    sample = rng.choice(len(cloud_returns), size=min(settings.frontier_points, len(cloud_returns)), replace=False)
    return {
        "inputs": {"symbols": symbols, "confidence": confidence, "budget": budget},
        "data": {"source": history.source, "start": history.dates[0], "end": history.dates[-1],
                 "trading_days": len(history.dates), "stale": history.stale},
        "method": {"monte_carlo_portfolios": settings.monte_carlo_portfolios, "resamples": settings.resamples,
                   "min_weight": settings.min_weight, "risk_free_rate": rf, "trading_days_per_year": pf.TRADING_DAYS},
        "stocks": stocks,
        "recommended": recommended,
        "reference_portfolios": {
            "max_sharpe": _summary(sharpe_weights, annual_returns, annual_cov, rf, symbols),
            "min_volatility": _summary(min_vol_weights, annual_returns, annual_cov, rf, symbols),
        },
        "frontier": {
            "points": [[round(float(cloud_vols[k]), 4), round(float(cloud_returns[k]), 4), round(float(cloud_sharpes[k]), 3)]
                       for k in sample],
        },
        "runtime_ms": int((time.perf_counter() - started) * 1000),
    }


def _validate(symbols: list[str], confidence: float, budget: int, last_prices: dict[str, int],
              settings: Settings) -> list[str]:
    cleaned = [s.strip().upper() for s in symbols]
    if len(set(cleaned)) != len(cleaned):
        raise RecommendationError("Each stock can be selected only once.")
    if len(cleaned) < 2:
        raise RecommendationError("Select at least two stocks: a portfolio needs more than one to divide money between.")
    if len(cleaned) > settings.max_stocks:
        raise RecommendationError(f"Select at most {settings.max_stocks} stocks.")
    if not settings.min_confidence <= confidence <= settings.max_confidence:
        raise RecommendationError(f"Confidence must be between {settings.min_confidence:g}% and {settings.max_confidence:g}%.")
    if budget <= 0:
        raise RecommendationError("The amount to invest must be more than zero.")
    missing = [s for s in cleaned if not last_prices.get(s)]
    if missing:
        raise RecommendationError(f"No current price for {', '.join(missing)}.")
    return cleaned


def _note(decision: str, stock_conf: float, wanted: float, weight: float, quantity: int, price: int) -> str:
    shown = f"{round(stock_conf * 100, 1):g}%"
    if decision == "DONT_BUY":
        return f"Confidence {shown} is below the {wanted:g}% you asked for."
    if quantity == 0:
        return f"Confidence {shown} meets {wanted:g}%, but its share of the budget is less than one share's price."
    return f"Confidence {shown} meets {wanted:g}%; gets {weight * 100:.1f}% of the budget."


def _summary(weights: np.ndarray, annual_returns: np.ndarray, annual_cov: np.ndarray, rf: float,
             symbols: list[str]) -> dict:
    ret = pf.portfolio_return(weights, annual_returns)
    vol = pf.portfolio_volatility(weights, annual_cov)
    return {"expected_return": round(ret, 4), "volatility": round(vol, 4),
            "sharpe": round((ret - rf) / vol, 3) if vol > 0 else None,
            "weights": {s: round(float(w), 4) for s, w in zip(symbols, weights)}}
