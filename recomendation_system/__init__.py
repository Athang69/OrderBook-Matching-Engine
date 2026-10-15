"""Stock recommendation system: which of the chosen stocks to buy, using Markowitz portfolio
optimisation (Monte Carlo + SLSQP) on daily price history."""
from .data import PriceDataError, PriceHistory, load_prices
from .service import RecommendationError, Settings, recommend

__all__ = ["recommend", "RecommendationError", "Settings", "load_prices", "PriceHistory", "PriceDataError"]
