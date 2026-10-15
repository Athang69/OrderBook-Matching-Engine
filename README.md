# Order Book and Matching Engine Simulator

A simulator of the Indian equity cash market. It has a C++ matching engine, a Python backend that manages orders, accounts and risk checks, robot traders that keep the books busy, a React frontend, and a recommendation system that suggests which stocks to buy for delivery.

It uses virtual money and the previous trading day's free NSE data. It is a study project, not a trading platform, and nothing in it is investment advice.

## Run it

```
scripts/run.sh
```

Then open <http://localhost:8000>.

The script builds whatever is missing (the engine, the Python environment, the frontend), downloads the latest previous-day NSE files into `data/`, and starts the server. The first run needs an internet connection; later runs work offline with the data already downloaded.

Requirements: a C++20 compiler, CMake 3.16+, Python 3.10+, Node.js 18+. Built and tested on Ubuntu 22.04.

## What you can do in it

- Watch eight NSE stocks trade, with the best five bids and asks for each.
- Place limit and market orders, for delivery or intraday.
- See an order rejected by a risk check: try a price outside the band, or buy more than your cash allows.
- Sell short with an intraday order, then square off.
- Pause the robot traders and match your own orders against each other.
- Click **Delivery** to ask the recommendation system which of the stocks you tick to buy, at the confidence you choose, and buy them in one click.
- Click **Intraday** for live intraday signals: buy, sell short or stay out for each stock you tick, with entry, stop-loss, target and size, refreshed every second.
- Read the three latest news headlines for the stock you are looking at, and for every stock in a recommendation, before you decide.

## A five-minute demonstration

1. Open the page. Point out the order book (best five each side) and the trades appearing.
2. Buy 25 shares at market, delivery. The order fills, cash goes down, and the holding appears under Positions.
3. Place a limit buy far below the market. It waits under Open orders, and the Funds tab shows the cash blocked for it. Cancel it and the cash comes back.
4. Try a limit price outside the allowed range. It is rejected with the reason shown.
5. Switch to Intraday and sell 30 shares you do not own. A short position appears with 20% margin blocked. Click "Square off all intraday positions".
6. Click Delivery. Tick five stocks, set the confidence to 60% and the amount to Rs 1,00,000, and click Get recommendation. Walk through the decision table and the risk-against-return chart, then buy the recommended stocks.
7. Click Intraday. Select all stocks at 25% confidence and click Show live signals. Point out the server time and round trip, and the signals changing every second. Place the trades, then square off under Your portfolio.
8. Run `./engine/build/ob_bench` in a terminal to show the engine's speed.

## Project layout

| Path | What it is |
|---|---|
| `engine/` | C++ matching engine: order book, tests, speed test |
| `backend/app/` | Python backend: API, order management, risk checks, accounts, market data, robot traders |
| `backend/tests/` | Backend tests (they run against the real engine) |
| `frontend/src/` | React and TypeScript user interface: `api/` (types and calls), `hooks/` (live data), `components/` by area (`layout`, `quote`, `market`, `trading`, `news`, `recommendations`, `ui`), `styles/` (tokens and one stylesheet per area) |
| `recomendation_system/` | Which stocks to buy: Markowitz portfolio optimisation (Monte Carlo and SLSQP) on price history. See its README. |
| `scripts/run.sh` | Builds and starts everything |
| `scripts/fetch_nse_data.py` | Downloads the previous day's NSE files |
| `docs/DESIGN.md` | Design decisions and how it works inside |
| `data/`, `logs/` | Downloaded NSE data and audit logs. Not committed. |
| `orderBook.cpp` | The team's earlier prototype. Not used by the simulator. |

## Tests and speed test

```
cmake -S engine -B engine/build && cmake --build engine/build
./engine/build/ob_tests                      # engine tests
.venv/bin/python -m pytest backend/tests recomendation_system/tests -q  # backend and recommendation tests
./engine/build/ob_bench                      # engine speed test
```

## API

Prices are integers in paise, so Rs 1,179.40 is `117940`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/orders` | Place an order |
| DELETE | `/v1/orders/{id}` | Cancel an open order |
| GET | `/v1/orders/{id}` | One order with its fills |
| GET | `/v1/orders` | The user's orders |
| GET | `/v1/market/instruments` | Stocks, their rules and current prices |
| GET | `/v1/market/orderbook/{symbol}` | Best five bids and asks |
| GET | `/v1/market/trades/{symbol}` | Recent trades |
| GET | `/v1/portfolio/{user}` | Cash, holdings, intraday positions, profit and loss |
| POST | `/v1/portfolio/{user}/squareoff` | Close all intraday positions |
| POST | `/v1/sim/bots` | Pause or resume the robot traders |
| POST | `/v1/recommendations` | Which of the chosen stocks to buy, and how much |
| POST | `/v1/recommendations/intraday` | Buy, sell short or stay out now, from live market data |
| GET | `/v1/market/histories` | Price once a second for every stock |
| GET | `/v1/news?symbols=RELIANCE&symbols=TCS` | The three latest news headlines for each stock |
| WebSocket | `/v1/stream/marketdata` | Live book and trade updates |

Interactive API documentation is at <http://localhost:8000/docs> while the server runs.

Example:

```
curl -X POST localhost:8000/v1/orders -H 'Content-Type: application/json' \
  -d '{"symbol":"RELIANCE","side":"BUY","type":"MARKET","product":"CNC","qty":10}'
```

## Frontend development

```
scripts/run.sh                 # backend on port 8000
cd frontend && npm run dev     # frontend with live reload on port 5173
```

## Not built yet

- **Saving state.** Accounts and orders live in memory and reset when the server restarts.
- **Login.** There is one demo account.

## Data

The NSE files are downloaded to `data/nse/`, and the recommendation system's price history to `data/history/`. Neither is committed. Only data up to the previous trading day is used.
