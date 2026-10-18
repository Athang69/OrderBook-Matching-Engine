# OrderBook: paper trading on the live Indian stock market

A paper-trading app for the NSE cash market (delivery and intraday). Prices are real and live, about two seconds behind the exchange, for every one of NSE's 2,914 stocks in the EQ and BE series. The money is virtual. Your orders are matched by our own C++ matching engine in price-time priority against the real market's prices and volumes. Two recommendation tools help decide what to buy: you read each stock's latest news, say how confident you are in it, and the tool combines your view with the data.

It is a study project, meant to run on your own computer. Nothing in it is investment advice.

## Run it

```
scripts/run.sh
```

Then open <http://localhost:8000>.

The script builds whatever is missing (the engine, the Python environment, the frontend), downloads NSE's latest daily files into `data/`, and starts the server. It needs an internet connection for live prices. `ORDERBOOK_LIVE=0 scripts/run.sh` starts without live prices, for working offline.

Requirements: a C++20 compiler, CMake 3.16+, Python 3.10+, Node.js 18+. Built and tested on Ubuntu 22.04.

## What you can do in it

- Search any NSE stock by symbol or company name, and see its live price, chart (one day to five years), day range, 52-week range, market value, P/E, and its latest news.
- Follow NIFTY 50, SENSEX and NIFTY BANK, and keep your own watchlist (the star next to the stock's name).
- See the real best bid and offer, the real trades as they happen, and your own orders waiting in the matching engine.
- Place limit and market orders, for delivery or intraday. Market orders fill at the real best price. Limit orders wait and fill only when NSE actually trades at your price, up to the quantity that traded.
- Place orders while the market is closed: they become after-market orders and go in with the first trade of the next session.
- Sell short intraday, with 20% margin. Positions are squared off automatically at 3:20 pm, and open orders expire at 3:30 pm.
- See brokerage, STT, stamp duty, exchange charges and GST on every fill, and your profit and loss before and after charges.
- Click **Delivery**: choose stocks, read each one's headlines, set your confidence in each, and get which to buy and how much, from portfolio optimisation on ten years of prices with your views built in. Buy them in one click.
- Click **Intraday**: choose stocks, read their news, set your confidence that each will rise today, and get buy, sell short or stay out for each, with entry, stop-loss, target and size, refreshed every second from live signals and your views.

## A ten-minute demonstration (market hours, 9:15 am to 3:30 pm)

1. Open the page. Point out the live status (top right), the indices, and RELIANCE's price and trades moving. Compare the price with any broker app.
2. Search "tata m" and open Tata Motors. Star it to add it to the watchlist.
3. Buy 5 shares at market, delivery. It fills at the real best offer shown in the order book; the charges appear with the fill.
4. Place a limit buy just below the live price. It waits under "Your orders in the matching engine". Wait for the market to trade down to it, and it fills at your price.
5. Try a limit price outside the price band: rejected, with the reason. Try a sell that would trade with your own buy: rejected as a self-trade.
6. Switch to Intraday and sell 20 shares you do not own. A short position appears with 20% margin blocked. Square it off.
7. Click Delivery. Choose four stocks, Next, read the headlines, set a high confidence on one and a low one on another, and get the recommendation. Show how each view changed the decision ("with your views" against "on history alone").
8. Click Intraday. Add your watchlist, Next, set a view, Show live signals. Point out the server time and the signals changing every second.
9. Run `./engine/build/ob_bench` in a terminal to show the engine's speed.

Outside market hours the prices shown are the last session's, orders become after-market orders, and intraday trading is closed, as in a broker's app.

## Project layout

| Path                        | What it is                                                                                                                                                |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `engine/`                   | C++ matching engine: order book, tests, speed test                                                                                                        |
| `backend/app/`              | Python backend: API, live feed from Yahoo Finance, market data, order management, risk checks, accounts and charges, market clock, news, intraday signals |
| `backend/tests/`            | Backend tests (they run against the real engine, without the internet)                                                                                    |
| `frontend/src/`             | React and TypeScript interface: `api/` (types and calls), `hooks/` (live data), `components/` by area, `styles/`                                          |
| `recomendation_system/`     | Which stocks to buy: Markowitz portfolio optimisation (Monte Carlo and SLSQP) with your views. See its README.                                            |
| `scripts/run.sh`            | Builds and starts everything                                                                                                                              |
| `scripts/fetch_nse_data.py` | Downloads NSE's latest daily files                                                                                                                        |
| `docs/DESIGN.md`            | How it works inside, and why                                                                                                                              |
| `data/`, `logs/`            | Downloaded data and audit logs. Not committed.                                                                                                            |
| `orderBook.cpp`             | The team's earlier prototype. Not used by the app.                                                                                                        |

## Tests and speed test

```
cmake -S engine -B engine/build && cmake --build engine/build
./engine/build/ob_tests                      # engine tests
.venv/bin/python -m pytest backend/tests recomendation_system/tests -q  # backend and recommendation tests
./engine/build/ob_bench                      # engine speed test
```

## API

Prices are integers in paise, so Rs 1,179.40 is `117940`.

| Method    | Path                                 | Purpose                                                                    |
| --------- | ------------------------------------ | -------------------------------------------------------------------------- |
| GET       | `/v1/status`                         | Market session (open, pre-open, closed) and live feed health               |
| GET       | `/v1/market/symbols`                 | Every NSE stock that can be traded, with its rules for the day             |
| GET       | `/v1/market/instrument/{symbol}`     | One stock's rules and live quote                                           |
| GET       | `/v1/market/quotes?symbols=`         | Live quotes                                                                |
| GET       | `/v1/market/chart/{symbol}?range=1d` | Price bars: `1d`, `5d`, `1mo`, `6mo`, `1y`, `5y`                           |
| GET       | `/v1/market/sparklines?symbols=`     | Today's price in about 75 points per stock                                 |
| GET       | `/v1/market/trades/{symbol}`         | Latest real trades                                                         |
| GET       | `/v1/market/orderbook/{symbol}`      | Real best bid and offer, and your orders in the engine                     |
| GET       | `/v1/market/indices`                 | NIFTY 50, SENSEX, NIFTY BANK                                               |
| POST      | `/v1/orders`                         | Place an order                                                             |
| DELETE    | `/v1/orders/{id}`                    | Cancel an open order                                                       |
| GET       | `/v1/orders/{id}`, `/v1/orders`      | One order with its fills; your orders                                      |
| GET       | `/v1/portfolio/{user}`               | Cash, holdings, intraday positions, profit and loss, charges               |
| POST      | `/v1/portfolio/{user}/squareoff`     | Close all intraday positions                                               |
| POST      | `/v1/recommendations`                | Which of the chosen stocks to buy, with your confidence in each            |
| POST      | `/v1/recommendations/intraday`       | Buy, sell short or stay out now, from live signals and your views          |
| GET       | `/v1/news?symbols=`                  | The three latest headlines for each stock                                  |
| WebSocket | `/v1/stream/marketdata`              | Send `{"subscribe": ["RELIANCE", ...]}`; live quotes and trades are pushed |

Interactive API documentation is at <http://localhost:8000/docs> while the server runs.

Example:

```
curl -X POST localhost:8000/v1/orders -H 'Content-Type: application/json' \
  -d '{"symbol":"RELIANCE","side":"BUY","type":"MARKET","product":"CNC","qty":10}'

curl -X POST localhost:8000/v1/recommendations -H 'Content-Type: application/json' \
  -d '{"symbols":["RELIANCE","TCS","INFY"],"confidences":{"RELIANCE":75,"INFY":30},"budget":10000000}'
```

## Frontend development

```
scripts/run.sh                 # backend on port 8000
cd frontend && npm run dev     # frontend with live reload on port 5173
```

## Data, and using it responsibly

| Data                                    | From                                                           |
| --------------------------------------- | -------------------------------------------------------------- |
| Live prices, quotes, charts, indices    | Yahoo Finance (free, no account), about two seconds behind NSE |
| List of stocks, price bands, tick sizes | NSE's daily files, downloaded to `data/nse/`                   |
| Price history for recommendations       | Yahoo Finance via `yfinance`, cached in `data/history/`        |
| News headlines                          | Google News                                                    |

Neither data folder is committed. Yahoo's data is for personal use, and SEBI does not allow live exchange prices to be passed on to others for virtual trading or games. Run the app on your own computer for your own study; do not host it for other people.

NSE's full market depth (quantities at the best five prices) is not available free. It needs an account with a broker that offers a market-data API.

## Not built yet

- **Saving state.** Accounts and orders live in memory and reset when the server restarts.
- **Login.** There is one account.
- **Market depth** from a broker's data feed.
