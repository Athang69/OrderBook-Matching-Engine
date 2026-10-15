# Design and How It Works

This document explains what the simulator is made of, why it is built this way, and what happens inside when an order is placed.

## 1. The parts

```
 Browser (React)
    |  REST: place, cancel, portfolio            ^  WebSocket: books and trades,
    v                                            |  pushed 4 times a second
+----------------------------------------------------------------------+
| Backend (Python, FastAPI)                               one process  |
|                                                                      |
|   API  -->  Order management  -->  Risk checks  -->  Accounts        |
|                  |    ^                                              |
|                  |    |  trades          Market data  --> WebSocket  |
|   Robot traders -+    |                  Audit log    --> file       |
+------------------|----|----------------------------------------------+
                   v    |   text commands over a pipe (stdin / stdout)
          +-----------------------------+
          | Matching engine (C++)       |   separate process, single thread,
          | one order book per stock    |   everything in memory
          +-----------------------------+

 Previous-day NSE files (data/nse) --> tick size, price band, price path
```

| Part | Language | Job |
|---|---|---|
| Matching engine | C++20 | Keeps the order books and matches orders. Knows nothing about users or money. |
| Order management | Python | Assigns order numbers, runs risk checks, reserves money, applies trades to accounts. |
| Risk checks | Python | Decides whether an order may go to the engine. |
| Accounts | Python | Cash, delivery holdings, intraday positions. |
| Market data | Python | Last price, day statistics, best five levels, recent trades. |
| Robot traders | Python | Generate orders so the books have activity. |
| Frontend | React, TypeScript | Shows the market and sends the user's orders. |

## 2. What happens when you place an order

Take "buy 25 RELIANCE at market, delivery" as the example.

1. **Browser.** The form sends `POST /v1/orders` with the symbol, side, type, product and quantity.
2. **API** (`backend/app/main.py`). FastAPI checks the request has valid fields and calls `Exchange.place_order`.
3. **Lock.** The exchange takes its lock. From here until the order is finished, no other order is processed. This is what keeps balances and the book consistent.
4. **Risk checks** (`risk.py`). Three checks, in order:
   - the order is valid for the stock: quantity, tick size, price band;
   - a delivery buy has enough available cash for the full value;
   - a delivery sell has the shares, and they are not already promised to another order.

   A market order has no price, so it is checked against the worst case, the upper price band. If a check fails, the order is stored as `REJECTED` with the reason and never reaches the engine.
5. **Reservation.** The cash (or the shares) is blocked. Blocked cash cannot be used by another order. Nothing is spent yet.
6. **Engine.** The backend writes one line to the engine's input: `NEW 4159 RELIANCE B M 0 25`.
7. **Matching** (`engine/src/order_book.cpp`). The engine walks the sell side from the best price, earliest order first, and writes back one `TRD` line per trade, then a `FIN` line with how much filled, how much is resting, and how much was cancelled.
8. **Applying trades** (`exchange.py`). For each trade the backend updates both orders and both accounts: the buyer's cash goes down and holding goes up, the seller's the reverse. The matching share of the reservation is released.
9. **Publishing.** The backend asks the engine for the new best five levels, updates the market data, and writes the trade to the audit log.
10. **Response.** The order comes back to the browser with its status and fills. Within a quarter of a second the WebSocket pushes the changed book and the new trade to every open page.

Measured on the development laptop, steps 3 to 9 take about 90 microseconds (median). The engine's share of that is well under one microsecond; the rest is Python and the pipe.

## 3. Inside the matching engine

### 3.1 Data structures

```
 price levels (flat array, one slot per tick inside the price band)

   slot:     0        1        2      ...     k      ...
   price:  1060.20  1060.30  1060.40  ...  1179.40  ...  1295.80
                                              |
                                              v
                              queue of orders at this price (first in, first out)
                              [ order 607 ] <-> [ order 612 ] <-> [ order 640 ]
                                   ^ head (oldest: trades first)        ^ tail (newest)

 order id --> slot in the order pool     (hash map, used by cancel)
 best bid, best ask                      (two integers: array indexes)
```

- **Prices are integers in paise.** Rs 1,179.40 is stored as 117940. There is no floating point anywhere, so there are no rounding errors.
- **A flat array of price levels.** NSE gives every stock a daily price band, so the set of valid prices is known in advance. For RELIANCE at Rs 1,178 with a 10 paise tick and a 10% band, that is 2,357 slots. A price maps to its slot with one subtraction and one division: `slot = (price - lower_band) / tick`. This is the main trick in the design: a rule of the Indian market makes the fastest possible data structure usable.
- **A queue per price level.** Orders at the same price are kept in arrival order in a doubly linked list. The oldest order is at the head and trades first. This is time priority.
- **A preallocated pool.** Order records live in one array and are reused through a free list, so matching does not ask the operating system for memory.
- **A hash map from order id to its record.** Cancelling an order is a lookup and an unlink, without searching the book.
- **Best bid and best ask as indexes.** The next order to match is always known directly.

### 3.2 Cost of each operation

| Operation | Work done |
|---|---|
| Add an order that rests | Compute the slot, append to that queue, update best bid or ask |
| Add an order that trades | The same, plus one step per order it trades against |
| Cancel | Hash lookup, unlink from its queue |
| Best five levels | Walk outward from the best price until five non-empty levels are found |

When a price level empties, the engine scans to the next non-empty slot. The scan is bounded by the size of the band and is usually one or two steps.

### 3.3 Matching rules

- **Price priority.** A buy order trades with the lowest-priced sell orders first; a sell order with the highest-priced buys first.
- **Time priority.** At the same price, the order that arrived first trades first.
- **Trade price.** A trade happens at the price of the order that was already waiting, not the incoming order's limit.
- **Limit orders.** Trade as far as the limit allows; any remainder rests in the book.
- **Market orders.** Trade against whatever is available inside the band; any remainder is cancelled.

### 3.4 The engine's protocol

The engine reads one command per line and ends every reply with `END`.

```
SYM RELIANCE 10 106020 129580           register a stock: tick, lower band, upper band
NEW 9 RELIANCE B L 117940 70            new order: id, symbol, B/S, L/M, price, quantity
  -> ACK 9
     TRD 9 1 117930 50                  trade: buy id, sell id, price, quantity
     TRD 9 3 117930 20
     FIN 9 70 0 0                       filled, resting, cancelled
CXL 3                                   cancel
DEP RELIANCE 5                          best five levels
```

## 4. Design decisions

| Decision | Why | What it costs |
|---|---|---|
| Engine in C++, everything else in Python | The engine is the only part where speed matters. Python is quicker to write for accounts, API and robots. | Two languages and a boundary between them. |
| Engine as a separate process, talked to over a pipe with text lines | The simplest possible boundary. The engine can be run and tested by hand in a terminal. | Each order costs a round trip of tens of microseconds, far more than the matching itself. |
| Single-threaded engine | With one thread, orders are applied strictly in arrival order, so the result is always the same for the same input. No locks are needed. | One engine uses one CPU core. To scale, run one engine per group of stocks. |
| One lock around order management | Balances, orders and the book change together or not at all. | Orders are processed one at a time in the backend too. |
| Flat array of price levels | Constant-time access, and the price band makes it small. | Memory is allocated for every price in the band, used or not. |
| Reserve cash when the order is placed | The same money cannot back two orders, and a fill can never fail for lack of funds. | Money is tied up while an order waits. |
| Everything in memory | Fast and simple. | State is lost when the server restarts. |
| Audit log as an append-only file | A permanent record of every trade and every user order event, in order. | It is a log, not a database; it is not read back on restart. |
| WebSocket pushes every 250 ms, not on every change | A person cannot read faster updates, and it bounds the load on the browser. | The screen can be up to a quarter of a second behind. |
| Robot traders use the normal order path | They exercise the same risk checks and accounting as a user. | Their orders pay the same cost as real ones. |

## 5. Money and accounts

All amounts are integers in paise.

### 5.1 Available cash

```
available = cash - blocked for open orders - blocked as intraday margin
```

New orders are checked against `available`, not `cash`.

### 5.2 Delivery (CNC)

| Event | Effect |
|---|---|
| Buy order placed | Full value blocked |
| Buy fills | Blocked amount released, actual cost deducted from cash, shares added to holdings |
| Sell order placed | Shares blocked |
| Sell fills | Shares removed, proceeds added to cash, profit or loss recorded |
| Order cancelled | Whatever is still blocked is released |

If a limit buy at Rs 101 fills at Rs 100, the extra rupee per share that was blocked is released.

### 5.3 Intraday (MIS)

- Only 20% of the order value is blocked as margin, so buying power is five times the cash.
- Selling without owning the shares is allowed. The position is recorded as negative (short).
- No cash moves when the position is opened. When it is reduced or closed, the profit or loss is added to cash.
- "Square off" cancels open intraday orders and closes each position with a market order, as a broker does before the market closes.

Example: sell 30 at Rs 1,179.10 intraday, buy back at Rs 1,179.20. Margin blocked while open: 20% of Rs 35,373 = Rs 7,074.60. Loss on closing: 30 x Rs 0.10 = Rs 3.

## 6. Market rules from NSE data

Each morning's setup comes from two free NSE files for the previous trading day.

| Rule | Source | How it is applied |
|---|---|---|
| Reference price | Bhavcopy: previous close | Centre of the price band |
| Tick size | NSE price slabs | Rs 0.01 below Rs 250; Rs 0.05 up to Rs 1,000; Rs 0.10 up to Rs 5,000; and so on |
| Price band | Price band list | 2, 5, 10 or 20%. Stocks with derivatives are listed as "No Band"; the simulator gives them 10%. |
| Price path | Bhavcopy: open, high, low, close | The robots' fair price follows open to low to high to close (or high first on a falling day) |
| Order sizes | Bhavcopy: volume divided by number of trades | Typical size of a robot order |

The band is rounded inwards so both ends are valid prices.

## 7. Robot traders

There is no free order-by-order data for Indian stocks, so the orders are generated. What is real is the path the price follows.

| Robot | What it does |
|---|---|
| `mm1`, `mm2` | Market makers. Keep buy and sell quotes at several prices on both sides of the fair price. When the fair price moves, they cancel quotes that are out of place and add new ones. |
| `retail` | Places small limit orders near the fair price and cancels its oldest ones. |
| `taker` | Sends market orders, more often towards the fair price. These create the trades. |

A full session is compressed into 15 minutes. The robots can be paused from the page.

## 8. Market data

After every order, the backend stores the stock's best five levels and any trades. A background task wakes four times a second and sends each connected browser only the stocks that changed, plus the new trades. A page that has just connected first receives a full picture of every stock.

Account data (orders, positions, cash) is not pushed; the page asks for it every 1.5 seconds and immediately after placing or cancelling an order.

## 9. Recommendation system

Clicking **Delivery** in the order form opens a pop-up where you tick stocks, choose a confidence percentage and an amount, and ask which to buy.

```
 Pop-up (React)  --POST /v1/recommendations-->  Backend: validate, take current prices
                                                     |
                                                     v
                                         recomendation_system.recommend()
                                           1. price history (Yahoo Finance, cached daily)
                                           2. Monte Carlo + SLSQP (the original method)
                                           3. confidence from 200 re-runs on reshuffled history
                                           4. Buy if confidence >= what you asked
                                           5. split the money, whole shares, Value at Risk
                                                     |
 Pop-up shows decisions, chart, numbers  <-----------+
 "Buy recommended stocks" --> normal POST /v1/orders (market, delivery), same risk checks
```

| Decision | Why |
|---|---|
| The recommender is its own package, called as a function | It can also run alone from a terminal, and its tests need no simulator. |
| The endpoint is a plain function that FastAPI runs on a worker thread | A run takes under a second of computing; the market keeps trading meanwhile. |
| One run at a time | It is the only heavy computation in the backend; a second request gets a clear "already running" answer. |
| Its libraries load on first use | The trading part still starts even if those libraries are missing. |
| Fixed random seed | The same request on the same day gives the same answer, which makes it easy to check. |
| Price history cached for the day | Yahoo Finance limits how often it can be asked; repeat runs are instant. |
| Quantities use the simulator's current price | The shares are bought in the simulator, so its price is the one that matters. |
| Buying goes through the normal order path | The purchase passes the same risk checks as any other order. |

Validation happens twice: the pop-up checks before sending (at least two stocks, confidence 50 to 99, an amount no larger than your available cash), and the server checks the same rules again along with unknown and duplicate stocks.

The confidence measure, the changes from the original script and the terminal command are described in `recomendation_system/README.md`.

### News headlines

The order form's stock, and every stock in a recommendation, show their three latest news headlines so you can read them before deciding. They are shown for you to read; the recommendation does not use them.

| Step | How |
|---|---|
| Source | Google News search as an RSS feed (no key needed): the company's name, past seven days |
| Relevance | A headline must name the company, as a whole word (for example "Reliance" or "RIL"; "L&T" or "Larsen") |
| Clean-up | Quote and price pages are dropped, repeats of the same story are dropped, the newest three are kept |
| Caching | Each stock is fetched at most once every ten minutes; the page refreshes every five minutes or on demand |
| Failures | If a refresh fails, the last headlines are shown with a note; a failure is not cached, so the next request tries again |
| Safety | The feed is parsed with a hardened XML parser, links must be http(s), and they open in a new tab |

### Intraday recommendations

Clicking **Intraday** in the order form opens a pop-up with live signals for the ticked stocks. It suits a minutes-long horizon, so it uses the simulator's own last few minutes of trading, never downloaded history.

| Signal | What it measures | Range |
|---|---|---|
| Momentum | The last minute's price change, divided by the stock's normal one-second swings | -1 to +1 |
| Price vs VWAP | The last price above or below the session's volume-weighted average price | -1 to +1 |
| Order book | Quantity waiting to buy against quantity waiting to sell, best five levels | -1 to +1 |
| Trade flow | Shares bought by buyers who crossed the spread against shares sold by sellers who did, last five minutes | -1 to +1 |

The score is the weighted average (30%, 20%, 25%, 25%). Its sign is the direction; its size is the confidence. A stock with confidence at or above the user's level is a **Buy** or a **Sell short**; otherwise it is **No trade**. A stock with under 20 seconds of prices shows **Waiting**. Entry is the best offer for a buy or the best bid for a short sale. The stop-loss sits 1.5 typical 15-minute moves away and the target twice as far. The margin is split by confidence, and positions can be five times the margin.

How it is kept fast:

| Step | How |
|---|---|
| Volatility | Updated as each one-second price sample arrives, with running sums (constant time), not recalculated per request |
| Request | Copies the latest numbers under one lock, then does a few dozen arithmetic steps per stock |
| Endpoint | `async`, so no worker-thread hop; a cheap cash check; the reply encoded straight to JSON |
| Python scheduling | The interpreter's thread switch interval is lowered from 5 ms to 0.5 ms so the robot traders' thread cannot hold up a request |
| Browser | Asks once a second, skips a tick if the last answer has not arrived, and shows server time and round trip |

Measured with all eight stocks while the robot traders were running: a median of 0.64 ms on the server and about 3 ms for the whole HTTP round trip. Before these changes it was 1.2 ms and 3.7 ms. The reply includes `timing`, which splits the server time into checks, data copy and signal calculation.

## 10. Frontend structure

| Folder | Contents |
|---|---|
| `api/` | `types.ts` (every API shape) and `client.ts` (every call) |
| `hooks/` | Live market data over the WebSocket, account polling, price history for charts, news, intraday polling, theme, the active page section |
| `components/layout/` | Top bar with stock search, the stock strip with sparklines, the section menu, the footer |
| `components/quote/` | Quote header, price chart with range tabs, key statistics, other stocks |
| `components/market/` | Order book with buy and sell pressure, time and sales, top movers |
| `components/trading/` | Order form, account summary, portfolio tabs |
| `components/news/` | Headline list, the page's news section, news inside recommendations |
| `components/recommendations/` | The recommendations section, the delivery and intraday pop-ups, the risk-against-return chart |
| `components/ui/` | Small shared pieces: modal, segmented control, sparkline, signal bar, confidence meter |
| `styles/` | `tokens.css` (colours, sizes, dark and light themes), `base.css`, and one stylesheet per area |

The page is dark by default, with a light theme switch. It reflows from three columns to two at 1,279 px and to one at 1,023 px. Charts carry text alternatives, buy and sell are shown with words as well as colours, and the pop-ups are native dialogs.

## 11. How this maps to the system design

| Design item | In this prototype |
|---|---|
| Order placement | Built: limit and market orders, cancel |
| Matching engine, price-time priority | Built in C++ |
| Order book | Built: best five levels per stock |
| Risk checks | Built: three checks (validity and price band, funds, shares) plus order size |
| Cash balance with reservation | Built |
| Portfolio | Built: holdings, intraday positions, profit and loss |
| Market data feed | Built in simple form: one WebSocket, no separate fan-out servers |
| Circuit breakers | Per-stock price band only |
| Settlement | Immediate at trade time; no T+1 process |
| Audit | Append-only file |
| Single thread per symbol | One thread for all symbols; the design allows one engine per group |
| Message queue, cache, databases | Not used; everything is in memory |
| Stop orders, market-wide halts, login | Not built |

## 12. Measured performance

Measured on the development laptop. Run `./engine/build/ob_bench` to reproduce the first row.

| What | Result |
|---|---|
| Engine alone, random mix of limit orders, market orders and cancels | About 5 million operations per second; median about 130 ns, 99th percentile about 0.7 microseconds |
| One order through the whole backend path | About 8,000 orders per second; median about 90 microseconds |
| One order over HTTP on the same machine | About 3.5 milliseconds |

The engine is roughly a thousand times faster than the layer around it. In this prototype the limit is Python and the pipe, not the matching.

## 13. Testing

| Test | What it checks |
|---|---|
| `engine/tests` unit tests | Price priority, time priority, partial fills, market orders, cancel, rejections |
| `engine/tests` random test | 60,000 random operations compared, trade by trade and level by level, against a slow and simple reference book |
| `backend/tests/test_exchange.py` | Reservation and release, both sides of a trade, every rejection, partial fills, intraday margin, short selling, square-off |
| `backend/tests/test_api.py` | The running system over HTTP and WebSocket |
| `backend/tests/test_recommendations_api.py` | The recommendation endpoint and its validation |
| `recomendation_system/tests` | Optimiser results, confidence, decisions, budget split, Value at Risk, invalid requests |
| `backend/tests/test_news.py` | Headline filtering, repeats, unsafe links, caching, failures, the news endpoint |
| `backend/tests/test_intraday.py` | Signal directions, waiting for data, levels on the tick and inside the band, sizing within margin, rolling volatility, speed, the endpoint |

## 14. Known limits

- State is not saved; a restart starts fresh.
- One demo user and no login.
- A user's own buy and sell orders can trade with each other; a real exchange prevents this.
- Tick size is taken from the previous close. NSE fixes it monthly, so a stock near a slab boundary may differ.
- Intraday positions are not closed automatically at the end of the session; use the square-off button.
- Recommendations rely on Yahoo Finance for price history; without internet, only a stock already cached can be used.
- News relevance is decided by the company's name, so a headline about a similarly named company can occasionally appear.
- Intraday stop-losses and targets are suggestions; the simulator has no stop orders, so open positions must be watched or squared off.
