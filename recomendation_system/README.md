# Recommendation system

Given a few NSE stocks, a confidence percentage and an amount to invest, it says which of the stocks to buy and how much money each should get.

It is built from the portfolio project in `Automated-Portfolio-Rebalancing-and-Risk-Analysis/` (original repository: <https://github.com/Athang69/Automated-Portfolio-Rebalancing-and-Risk-Analysis>). The original was a script that downloaded prices for fixed tickers, plotted a chart and printed results. Here the same method is turned into functions that the simulator can call.

## How it decides

1. **Price history.** Daily closing prices from 1 January 2015 up to the previous trading day, from Yahoo Finance through `yfinance`, as in the original. Prices are cached in `data/history/` and downloaded at most once a day.
2. **The original method.** Daily log returns, annualised with 250 trading days. Then 20,000 random portfolios (Monte Carlo), and the SLSQP optimiser for two portfolios: the best Sharpe ratio and the lowest volatility. There is no short selling and the weights add up to 100%.
3. **Confidence.** The original has no confidence measure, so one was added. The optimiser is re-run 200 times, each time on a reshuffled copy of the price history (trading days drawn at random, with repeats). A stock's confidence is the share of those runs in which the optimiser gave it at least 5% of the money.
4. **Decision.** A stock is marked **Buy** if its confidence is at or above the confidence you asked for.
5. **Allocation.** The optimiser runs once more on just the Buy stocks to split the money. The amount is turned into whole shares at the simulator's current price.
6. **Risk.** The recommended portfolio's expected return, volatility, Sharpe ratio, and one-day Value at Risk at your confidence level: "on that share of past days, the loss was smaller than this".

Higher confidence means fewer stocks pass. With many similar stocks, the optimiser's choice changes from run to run, so confidences are lower.

## Changes from the original script

| Change | Why |
|---|---|
| The optimiser now uses the annual covariance | The original passed the daily covariance next to annual returns, mixing daily risk with yearly return in the Sharpe ratio. |
| Risk-free rate 6.5% instead of 2% | Closer to Indian treasury bill yields, since the stocks are Indian. |
| NSE symbols only, mapped to Yahoo's `.NS` tickers | The original mixed US and Indian tickers, which trade on different days. |
| Monte Carlo done as matrix operations | Same numbers, much faster. |
| No `plt.show()` | Results are returned as data; the browser draws the chart. |
| Confidence, allocation in shares, Value at Risk | New; needed for "which stocks to buy". |

## Use it

From the simulator: click **Delivery** in the order form.

From a terminal, without the simulator:

```
.venv/bin/python -m recomendation_system --symbols RELIANCE TCS INFY ICICIBANK LT --confidence 60 --budget 100000
```

From the API, while the simulator runs:

```
curl -X POST localhost:8000/v1/recommendations -H 'Content-Type: application/json' \
  -d '{"symbols":["RELIANCE","TCS","INFY"],"confidence":60,"budget":10000000}'
```

`budget` is in paise (`10000000` is Rs 1,00,000). `confidence` is a percentage from 50 to 99.

## Files

| File | What it does |
|---|---|
| `portfolio.py` | The maths: returns, Monte Carlo, SLSQP, confidence, Value at Risk |
| `data.py` | Downloads and caches the price history |
| `service.py` | `recommend()`: checks the request, runs the steps above, builds the answer |
| `__main__.py` | The terminal command |
| `tests/` | Tests on made-up price data, so no internet is needed |

## Tests

```
.venv/bin/python -m pytest recomendation_system/tests -q
```

For study only. Past returns do not predict future returns, and nothing here is investment advice.
