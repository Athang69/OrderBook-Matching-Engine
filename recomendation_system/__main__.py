"""Run the recommendation system from a terminal, without the simulator:

    python -m recomendation_system --symbols RELIANCE TCS INFY HDFCBANK --confidence 80 --budget 500000
"""
import argparse
import sys

from .data import load_prices
from .service import RecommendationError, recommend


def main() -> int:
    parser = argparse.ArgumentParser(description="Which of these NSE stocks to buy, and how much.")
    parser.add_argument("--symbols", nargs="+", required=True, help="NSE symbols, e.g. RELIANCE TCS INFY")
    parser.add_argument("--confidence", type=float, default=80, help="percentage, 50 to 99 (default 80)")
    parser.add_argument("--budget", type=float, default=100_000, help="rupees to invest (default 1,00,000)")
    args = parser.parse_args()

    symbols = [s.upper() for s in args.symbols]
    try:
        # Outside the simulator, the latest closing price stands in for the market price.
        history = load_prices(symbols, "2015-01-01")
        last_prices = {s: int(round(history.prices[-1, i] * 100)) for i, s in enumerate(symbols)}
        result = recommend(symbols, args.confidence, int(args.budget * 100), last_prices,
                           loader=lambda _symbols, _start: history)
    except RecommendationError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    data = result["data"]
    print(f"\nPrice history: {data['start']} to {data['end']} ({data['trading_days']} trading days)"
          + ("  [cached, could not refresh]" if data["stale"] else ""))
    print(f"Confidence asked for: {args.confidence:g}%   Budget: Rs {args.budget:,.2f}\n")
    print(f"{'Stock':<12}{'Decision':<11}{'Confidence':>11}{'Weight':>9}{'Shares':>8}{'Cost (Rs)':>14}")
    for s in result["stocks"]:
        print(f"{s['symbol']:<12}{'Buy' if s['decision'] == 'BUY' else 'Do not buy':<11}{s['confidence'] * 100:>10.0f}%"
              f"{s['weight'] * 100:>8.1f}%{s['quantity']:>8}{s['cost'] / 100:>14,.2f}")
    rec = result["recommended"]
    if rec is None:
        print("\nNo stock reached the confidence asked for. Try a lower confidence or other stocks.")
    else:
        var = rec["value_at_risk"]
        print(f"\nRecommended portfolio: expected annual return {rec['expected_return'] * 100:.2f}%, "
              f"annual volatility {rec['volatility'] * 100:.2f}%, Sharpe ratio {rec['sharpe']}")
        print(f"Invested Rs {rec['invested'] / 100:,.2f}, left over Rs {rec['cash_left'] / 100:,.2f}")
        print(f"One-day Value at Risk at {var['confidence']:g}% confidence: {var['one_day_fraction'] * 100:.2f}% "
              f"(Rs {var['one_day_amount'] / 100:,.2f})")
    print(f"\nFinished in {result['runtime_ms']} ms.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
