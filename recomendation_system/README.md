# Recommendation system

Given a few NSE stocks, your confidence in each one and an amount to invest, it says which of the stocks to buy and how much money each should get.

It is built from the portfolio project in `Automated-Portfolio-Rebalancing-and-Risk-Analysis/` (original repository: <https://github.com/Athang69/Automated-Portfolio-Rebalancing-and-Risk-Analysis>). The original was a script that downloaded prices for fixed tickers, plotted a chart and printed results. Here the same method is turned into functions the app can call, and your own views are added to it.

## How it decides

1. **Price history.** Daily closing prices from 1 January 2015 up to the previous trading day, from Yahoo Finance through `yfinance`, as in the original. Prices are cached in `data/history/` and downloaded at most once a day.
2. **Your views.** In the app you first read each stock's latest news, then set how confident you are that it will do well, from 0% (sure it falls) through 50% (no view) to 100% (sure it rises). A confidence `c` becomes a view `v = (c - 50) / 50`, and the stock's expected annual return is moved by `0.5 x v x its annual volatility`. For a stock with 25% volatility, 100% adds 12.5 percentage points and 0% takes 12.5 away. This is a simple form of the Black-Litterman idea: start from the history and tilt it towards the investor's views, in proportion to how sure the investor is and how much the stock usually moves.
3. **The original method.** Daily log returns, annualised with 250 trading days, with your views added to the returns. Then 20,000 random portfolios (Monte Carlo), and the SLSQP optimiser for two portfolios: the best Sharpe ratio and the lowest volatility. No short selling; the weights add up to 100%.
4. **Agreement.** The original has no confidence measure, so one was added. The optimiser is re-run 200 times, each time on a resampled copy of the price history (trading days drawn at random, with repeats). A stock's agreement is the share of runs in which it got at least 5% of the money. The same runs are done with your views and without them, so you can see how much your view changed each stock.
5. **Decision.** A stock is marked **Buy** if it was picked in at least half of the runs with your views.
6. **Allocation.** The optimiser runs once more on just the Buy stocks to split the money. The amount is turned into whole shares at the live price.
7. **Risk.** The recommended portfolio's expected return (with your views and on history alone), volatility, Sharpe ratio, and one-day Value at Risk at 95%: "on 95% of past days, the loss was smaller than this".

With many similar stocks, the optimiser's choice changes from run to run, so agreement is lower.

## Changes from the original script

| Change | Why |
|---|---|
| The optimiser now uses the annual covariance | The original passed the daily covariance next to annual returns, mixing daily risk with yearly return in the Sharpe ratio. |
| Risk-free rate 6.5% instead of 2% | Closer to Indian treasury bill yields, since the stocks are Indian. |
| NSE symbols only, mapped to Yahoo's `.NS` tickers | The original mixed US and Indian tickers, which trade on different days. |
| Monte Carlo done as matrix operations | Same numbers, much faster. |
| No `plt.show()` | Results are returned as data; the browser draws the chart. |
| Your views, agreement, allocation in shares, Value at Risk | New; needed for "which stocks to buy". |

## Use it

From the app: click **Delivery** in the order form.

From a terminal, without the app (stocks without a view get 50%):

```
.venv/bin/python -m recomendation_system --symbols RELIANCE TCS INFY ICICIBANK LT --views RELIANCE=75 INFY=30 --budget 100000
```

From the API, while the app runs:

```
curl -X POST localhost:8000/v1/recommendations -H 'Content-Type: application/json' \
  -d '{"symbols":["RELIANCE","TCS","INFY"],"confidences":{"RELIANCE":75,"INFY":30},"budget":10000000}'
```

`budget` is in paise (`10000000` is Rs 1,00,000). Each confidence is a percentage from 0 to 100.

## Files

| File | What it does |
|---|---|
| `portfolio.py` | The maths: returns, Monte Carlo, SLSQP, agreement with and without views, Value at Risk |
| `data.py` | Downloads and caches the price history |
| `service.py` | `recommend()`: checks the request, applies your views, runs the steps above, builds the answer |
| `__main__.py` | The terminal command |
| `tests/` | Tests on made-up price data, so no internet is needed |

## Tests

```
.venv/bin/python -m pytest recomendation_system/tests -q
```

For study only. Past returns do not predict future returns, and nothing here is investment advice.
