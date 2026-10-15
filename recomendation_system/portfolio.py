"""Markowitz portfolio maths, refactored from the original script
Automated-Portfolio-Rebalancing-and-Risk-Analysis/Automated_Portfolio_Rebalancing_and_Risk_Analysis.py.

The method is the same as the original:
  * daily log returns, annualised with 250 trading days;
  * a Monte Carlo cloud of random portfolios (weights normalised to add up to 1);
  * SLSQP to find the maximum Sharpe ratio portfolio and the minimum volatility portfolio,
    with no short selling (each weight between 0 and 1) and weights adding up to 1.

Changes from the original are marked "Changed:".
"""
import numpy as np
from scipy.optimize import minimize

TRADING_DAYS = 250


def log_returns(prices: np.ndarray) -> np.ndarray:
    """Daily log returns. `prices` has one row per day and one column per stock."""
    return np.diff(np.log(prices), axis=0)


def annualise(returns: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Average annual return of each stock and the annual covariance matrix."""
    return returns.mean(axis=0) * TRADING_DAYS, np.atleast_2d(np.cov(returns, rowvar=False)) * TRADING_DAYS


def portfolio_return(weights: np.ndarray, annual_returns: np.ndarray) -> float:
    return float(weights @ annual_returns)


def portfolio_volatility(weights: np.ndarray, annual_cov: np.ndarray) -> float:
    return float(np.sqrt(weights @ annual_cov @ weights))


def negative_sharpe_ratio(weights: np.ndarray, annual_returns: np.ndarray, annual_cov: np.ndarray,
                          risk_free_rate: float) -> float:
    """SciPy minimises this, which maximises the Sharpe ratio."""
    volatility = portfolio_volatility(weights, annual_cov)
    if volatility < 1e-12:
        return 1e6
    return -(portfolio_return(weights, annual_returns) - risk_free_rate) / volatility


def _optimise(objective, n_assets: int, args: tuple) -> np.ndarray:
    bounds = tuple((0.0, 1.0) for _ in range(n_assets))  # no short selling
    constraints = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)  # fully invested
    start = np.full(n_assets, 1.0 / n_assets)  # equal weights, as in the original
    result = minimize(objective, start, args=args, method="SLSQP", bounds=bounds, constraints=constraints)
    weights = np.clip(result.x, 0.0, None)  # remove tiny negative values left by rounding
    return weights / weights.sum()


def max_sharpe_weights(annual_returns: np.ndarray, annual_cov: np.ndarray, risk_free_rate: float) -> np.ndarray:
    # Changed: the original passed the daily covariance here while passing annual returns,
    # mixing daily risk with yearly return. Both are annual now.
    return _optimise(negative_sharpe_ratio, len(annual_returns), (annual_returns, annual_cov, risk_free_rate))


def min_volatility_weights(annual_cov: np.ndarray) -> np.ndarray:
    # Changed: annual covariance here too, for the same reason.
    return _optimise(portfolio_volatility, len(annual_cov), (annual_cov,))


def monte_carlo(annual_returns: np.ndarray, annual_cov: np.ndarray, risk_free_rate: float, count: int,
                rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return, volatility and Sharpe ratio of `count` random portfolios.

    Changed: the original loop is done as matrix operations, which gives the same numbers
    much faster.
    """
    weights = rng.random((count, len(annual_returns)))
    weights /= weights.sum(axis=1, keepdims=True)
    returns = weights @ annual_returns
    volatility = np.sqrt(np.einsum("ij,jk,ik->i", weights, annual_cov, weights))
    return returns, volatility, (returns - risk_free_rate) / volatility


def selection_confidence(returns: np.ndarray, risk_free_rate: float, resamples: int, min_weight: float,
                         rng: np.random.Generator) -> np.ndarray:
    """For each stock, the share of resampled runs in which the maximum Sharpe portfolio gives it
    at least `min_weight` of the money.

    New: the original script has no confidence measure. Each run draws the trading days again at
    random (with replacement) from the history and re-optimises. A stock the optimiser picks in
    almost every run is a stable choice; one it picks only sometimes depends on luck in the data.
    """
    days, assets = returns.shape
    picked = np.zeros(assets)
    for _ in range(resamples):
        sample = returns[rng.integers(0, days, size=days)]
        annual_returns, annual_cov = annualise(sample)
        picked += max_sharpe_weights(annual_returns, annual_cov, risk_free_rate) >= min_weight
    return picked / resamples


def value_at_risk(weights: np.ndarray, returns: np.ndarray, confidence_pct: float) -> float:
    """One-day historical Value at Risk, as a fraction of the amount invested.

    New: "with `confidence_pct`% confidence, a day's loss was not larger than this" in the history.
    """
    daily = (np.exp(returns) - 1.0) @ weights  # each day's portfolio return
    return float(max(0.0, -np.percentile(daily, 100.0 - confidence_pct)))
