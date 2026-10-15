"""Run the recommendation system from a terminal, without the app:

    python -m recomendation_system --symbols RELIANCE TCS INFY HDFCBANK --budget 500000
    python -m recomendation_system --symbols RELIANCE TCS INFY --views RELIANCE=75 INFY=30

A view is your confidence, 0 to 100, that the stock will do well; stocks without one get 50 (no view).
"""
import argparse
import sys

from .data import load_prices
from .service import RecommendationError, recommend


def main() -> int:
    parser = argparse.ArgumentParser(description="Which of these NSE stocks to buy, and how much.")
    parser.add_argument("--symbols", nargs="+", required=True, help="NSE symbols, e.g. RELIANCE TCS INFY")
    parser.add_argument("--views", nargs="*", default=[], help="your confidence per stock, e.g. RELIANCE=75 INFY=30")
    parser.add_argument("--budget", type=float, default=100_000, help="rupees to invest (default 1,00,000)")
    args = parser.parse_args()

    symbols = [s.upper() for s in args.symbols]
    try:
        views = {k.upper(): float(v) for k, v in (item.split("=", 1) for item in args.views)}
    except ValueError:
        print("Error: write each view as SYMBOL=percentage, e.g. RELIANCE=75", file=sys.stderr)
        return 1
    try:
        # Outside the app, the latest closing price stands in for the market price.
        history = load_prices(symbols, "2015-01-01")
        last_prices = {s: int(round(history.prices[-1, i] * 100)) for i, s in enumerate(symbols)}
        result = recommend(symbols, views, int(args.budget * 100), last_prices, loader=lambda _symbols, _start: history)
    except RecommendationError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    data = result["data"]
    print(f"\nPrice history: {data['start']} to {data['end']} ({data['trading_days']} trading days)"
          + ("  [cached, could not refresh]" if data["stale"] else ""))
    print(f"Budget: Rs {args.budget:,.2f}\n")
    print(f"{'Stock':<12}{'Your view':>10}{'Decision':>12}{'Agreement':>11}{'History':>9}{'Weight':>9}{'Shares':>8}{'Cost (Rs)':>14}")
    for s in result["stocks"]:
        print(f"{s['symbol']:<12}{s['your_confidence']:>9.0f}%{'Buy' if s['decision'] == 'BUY' else 'Do not buy':>12}"
              f"{s['agreement'] * 100:>10.0f}%{s['history_agreement'] * 100:>8.0f}%{s['weight'] * 100:>8.1f}%"
              f"{s['quantity']:>8}{s['cost'] / 100:>14,.2f}")
    rec = result["recommended"]
    if rec is None:
        print("\nNo stock was picked in at least half of the re-runs. Try other stocks or views.")
    else:
        var = rec["value_at_risk"]
        print(f"\nRecommended portfolio: expected annual return {rec['expected_return'] * 100:.2f}% with your views "
              f"({rec['expected_return_history'] * 100:.2f}% on history alone), annual volatility "
              f"{rec['volatility'] * 100:.2f}%, Sharpe ratio {rec['sharpe']}")
        print(f"Invested Rs {rec['invested'] / 100:,.2f}, left over Rs {rec['cash_left'] / 100:,.2f}")
        print(f"One-day Value at Risk at {var['confidence']:g}% confidence: {var['one_day_fraction'] * 100:.2f}% "
              f"(Rs {var['one_day_amount'] / 100:,.2f})")
    print(f"\nFinished in {result['runtime_ms']} ms.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
