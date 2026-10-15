# Design and How It Works

This document explains what the app is made of, why it is built this way, and what happens inside when an order is placed. In short: it is paper trading on the live Indian stock market. Prices are real and arrive about two seconds after they trade on NSE; the money is virtual; your orders are matched by our own C++ matching engine against the real market's prices and volumes.

## 1. The parts

```
 Browser (React)
    |  REST: orders, portfolio, charts,          ^  WebSocket: live quotes and trades
    |  recommendations, news                     |  for the stocks on screen, 4 times a second
    v                                            |
+----------------------------------------------------------------------------+
| Backend (Python, FastAPI)                                     one process  |
|                                                                            |
|   API  -->  Order management  -->  Risk checks  -->  Accounts, charges     |
|                 |    ^      ^                                              |
|                 |    |      |  real trades          Market data --> WebSocket
|                 |    |   Live feed (Yahoo Finance) ---^                    |
|                 |    |   - stream: each new price and the day's volume     |
|                 |    |   - quote poll every 5 s: bid, offer, day range     |
|                 |    |   - chart bars                    Audit log --> file|
+-----------------|----|-----------------------------------------------------+
                  v    |   text commands over a pipe (stdin / stdout)
         +-----------------------------+
         | Matching engine (C++)       |   separate process, single thread,
         | one order book per stock    |   everything in memory
         +-----------------------------+

 NSE's daily files (data/nse) --> every stock, its name, tick size and price band
```

| Part | File | Job |
|---|---|---|
| Matching engine | `engine/` (C++20) | Keeps the order books and matches orders by price and time. Knows nothing about users or money. |
| Live feed | `backend/app/yahoo.py` | Talks to Yahoo Finance: the price stream, the quote poll, chart bars. |
| Market data | `backend/app/market_data.py` | The live state of every stock being followed: quote, today's one-minute bars, recent trades, VWAP. |
| Market clock | `backend/app/session.py` | Whether NSE is open, in pre-open or closed, and when it opens next. |
| Order management | `backend/app/exchange.py` | Risk checks, reservations, sending orders to the engine, placing the real market's side, applying fills. |
| Risk checks | `backend/app/risk.py` | Decides whether an order may go to the engine. |
| Accounts and charges | `backend/app/accounts.py`, `charges.py` | Cash, delivery holdings, intraday positions; brokerage, taxes and fees on every fill. |
| Reference data | `backend/app/instruments.py` | Every NSE stock in the EQ and BE series from NSE's daily files. |
| Recommendations | `recomendation_system/`, `backend/app/intraday.py` | Delivery: portfolio optimisation with your views. Intraday: live signals with your views. |
| News | `backend/app/news.py` | The latest headlines for any stock, from Google News. |
| Frontend | `frontend/src/` | Search, quote, chart, order book, order form, portfolio, recommendation pop-ups. |

## 2. Where the data comes from

| Data | Source | Cost | How fresh |
|---|---|---|---|
| Last traded price and the day's volume | Yahoo Finance price stream (a WebSocket) | Free, no account | About 2 seconds behind NSE; about one update a second for busy stocks, every few seconds for quiet ones |
| Best bid and best offer, open, day's range, volume, 52-week range, market value, P/E, EPS, dividend yield | Yahoo Finance quote service, polled every 5 seconds for the followed stocks, 50 to a request | Free | A few seconds |
| NIFTY 50, SENSEX, NIFTY BANK | The same stream and quote service | Free | As above |
| Charts | Yahoo Finance chart service: one-minute bars for today, up to weekly bars for five years | Free | Today's bars are extended live by the stream |
| Every stock's name, series, price band, reference close, tick size | NSE's daily bhavcopy and price band list | Free | Downloaded at start-up, at 8:45 am and at 7 pm |
| News headlines | Google News search (RSS) | Free | Cached five minutes |
| Daily price history since 2015 for recommendations | Yahoo Finance via `yfinance` | Free | Downloaded once a day |

What is **not** available free: NSE's full market depth (the quantities at the best five prices on each side) and every individual trade. Brokers receive those from NSE and pass them to their own customers; using them here needs an account with a broker that offers a market-data API. Yahoo gives the best bid and offer without quantities, and its stream reports the volume traded between two price updates, which is used as the trade size.

Not every stock is streamed at once. The backend follows up to 100: the default watchlist, every stock with an order or position, and whatever the open pages are showing (kept for 15 minutes after the last look).

**Use.** Yahoo's data is for personal use, and SEBI does not allow live exchange prices to be passed on to others for virtual trading. The app is meant to run on your own computer for your own study, not to be hosted for others.

## 3. Paper trading against the live market

Your orders are real orders in our matching engine. The other side is the real market, which takes part through orders placed for it at real prices and for real quantities.

| Situation | What happens |
|---|---|
| A market order, or a limit order at or better than the live price | It trades at once, at the real best offer when buying or the real best bid when selling. If the quote is more than 10 seconds old or more than 0.5% away from the last trade, the last traded price is used. Prices are put on the tick grid, never better than the real price. |
| A limit order that cannot trade yet | It waits in the engine in price-time priority with your other orders. Each time NSE reports a trade in the stock, that trade is replayed in the engine at its real price and for its real quantity. Your waiting orders at that price or better fill, best price first, then earliest first, up to the quantity that really traded. A waiting order fills at its own limit price, as a resting order on the exchange would. |
| Market closed or pre-open | A delivery order is accepted as an after-market order (AMO) and waits outside the engine. It enters with the stock's first real trade of the next session, at that price if it can trade. Intraday orders are refused. |
| Your buy would trade with your own sell (or the reverse) | Refused, as NSE's self-trade prevention does. |
| 3:20 pm | Intraday positions are closed with market orders at the live price; after that, intraday orders may only close a position. |
| 3:30 pm | Orders still open expire (they are day orders). Any intraday position still open is closed at the last price. |
| No price for 60 seconds | Orders in that stock are refused until prices arrive again. |

In the engine this works as follows. For an order that can trade now, the backend first places the market's opposite order at the real price (`NEW <id> RELIANCE S L 118010 25`), then your order, which matches it; whatever is left of the market's order is cancelled. For a real trade of 400 shares at Rs 1,180.00, the backend places a market sell for 400 at Rs 1,180.00 (reaching your buys at Rs 1,180.00 or more) and a market buy for 400 at Rs 1,180.00 (reaching your sells at Rs 1,180.00 or less), and cancels what is left of each. The market's orders have no account, so only your side of each trade changes any balance.

**What this leaves out.** Real orders already waiting at the same price would trade before yours; here your order fills as soon as the market trades at its price. A large market order would move through several prices; here it fills completely at the best price. So fills here are a little more generous than real ones, mostly for large orders or quiet stocks.

## 4. What happens when you place an order

Take "buy 25 RELIANCE at market, delivery" while the market is open, with the live best offer at Rs 1,180.10.

1. **Browser.** The form sends `POST /v1/orders` with the symbol, side, type, product and quantity.
2. **API** (`main.py`). If no quote for the stock has arrived in the last 15 seconds (a stock nobody has looked at), one is fetched first.
3. **Lock.** The exchange takes its lock. Until the order is finished, no other order and no market trade is processed.
4. **Checks.** The session (is intraday allowed now; BE stocks are delivery only), then the risk checks in `risk.py`: quantity and size limit; limit price inside the band and on the tick; enough available cash for the value plus charges (a market buy is checked at the upper band, the worst price it could trade at); for a delivery sell, enough free shares. Then a live price must exist and must be inside the band, and the order must not trade with your own.
5. **Reservation.** The cash (or the shares) is blocked, so it cannot back another order.
6. **Engine.** The market's sell for 25 at Rs 1,180.10 goes in, then `NEW 4159 RELIANCE B M 0 25`. The engine matches them and replies with a `TRD` line and a `FIN` line.
7. **Applying the trade** (`exchange.py`). Your order is marked filled, the reservation released, the cost and the charges taken from cash, the shares added to holdings. The trade is written to the audit log.
8. **Response.** The order comes back with its fills and charges. The page refreshes the portfolio straight away.

Measured on the development laptop, steps 3 to 7 take a median of 55 microseconds for a market order and 23 for a limit order that waits (section 13).

## 5. Inside the matching engine

### 5.1 Data structures

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

### 5.2 Cost of each operation

| Operation | Work done |
|---|---|
| Add an order that rests | Compute the slot, append to that queue, update best bid or ask |
| Add an order that trades | The same, plus one step per order it trades against |
| Cancel | Hash lookup, unlink from its queue |
| Best five levels | Walk outward from the best price until five non-empty levels are found |

When a price level empties, the engine scans to the next non-empty slot. The scan is bounded by the size of the band and is usually one or two steps.

### 5.3 Matching rules

- **Price priority.** A buy order trades with the lowest-priced sell orders first; a sell order with the highest-priced buys first.
- **Time priority.** At the same price, the order that arrived first trades first.
- **Trade price.** A trade happens at the price of the order that was already waiting, not the incoming order's limit.
- **Limit orders.** Trade as far as the limit allows; any remainder rests in the book.
- **Market orders.** Trade against whatever is available inside the band; any remainder is cancelled.

### 5.4 The engine's protocol

The engine reads one command per line and ends every reply with `END`.

```
SYM RELIANCE 10 106020 129580           register a stock (tick, lower band, upper band), or give an empty book a new day's band
NEW 9 RELIANCE B L 117940 70            new order: id, symbol, B/S, L/M, price, quantity
  -> ACK 9
     TRD 9 1 117930 50                  trade: buy id, sell id, price, quantity
     TRD 9 3 117930 20
     FIN 9 70 0 0                       filled, resting, cancelled
CXL 3                                   cancel
DEP RELIANCE 5                          best five levels
```

A stock is registered in the engine the first time it is traded, so the 2,914 listed stocks do not all take memory. Each new trading day, a book with no waiting orders takes the day's new price band.

## 6. Design decisions

| Decision | Why | What it costs |
|---|---|---|
| Engine in C++, everything else in Python | The engine is the only part where speed matters. Python is quicker to write for accounts, the live feed and the API. | Two languages and a boundary between them. |
| Engine as a separate process, talked to over a pipe with text lines | The simplest possible boundary. The engine can be run and tested by hand in a terminal. | Each command costs a round trip of tens of microseconds, far more than the matching itself. |
| The real market is represented by orders in the engine | Your orders are matched by the same engine and the same price-time rules whether the other side is the market or not. | The market's order book beyond the best price is not known, so fills are a little generous (section 3). |
| Waiting orders fill only on real trades, capped by the real volume | A price that was only quoted, never traded, does not fill anything; a 10,000-share order cannot fill on a 50-share trade. | Fills depend on how often Yahoo reports trades: about every second for busy stocks, less often for quiet ones. |
| Yahoo Finance for live data | Free, needs no account, covers every NSE stock and the indices, and has a real-time stream. | No market depth; about two seconds behind NSE; it can refuse requests that come too often, so the quote poll is every 5 seconds. |
| Single-threaded engine and one lock around order management | Orders and market trades are applied strictly one at a time, so balances, orders and the book change together or not at all. | One engine uses one CPU core. |
| Flat array of price levels | Constant-time access, and the price band makes it small. | Memory is allocated for every price in the band, used or not. |
| Reserve cash and charges when the order is placed | The same money cannot back two orders, and a fill can never fail for lack of funds. | Money is tied up while an order waits. |
| Everything in memory | Fast and simple. | Accounts and orders are lost when the server restarts. |
| WebSocket pushes every 250 ms, only for the stocks each page follows | A person cannot read faster updates, and each page gets only what it shows. | The screen can be up to a quarter of a second behind the server. |

## 7. Money, accounts and charges

All amounts are integers in paise.

```
available = cash - blocked for open orders - blocked as intraday margin
```

New orders are checked against `available`, not `cash`.

**Delivery (CNC).** A buy blocks its full value plus charges; when it fills, the blocked amount is released and the actual cost and charges are taken from cash. A sell needs shares you hold that are not promised to another order. If a limit buy at Rs 101 fills at Rs 100, the extra rupee a share is released.

**Intraday (MIS).** Only 20% of the order value is blocked as margin, so positions can be five times the cash. Selling without owning the shares is allowed (a short position). Profit or loss is settled in cash when the position is reduced or closed. Positions are closed at 3:20 pm.

**Charges** (`charges.py`), worked out on every fill, as a discount broker's contract note shows them (published rates for 2025; brokers differ and rates change):

| Charge | Delivery | Intraday |
|---|---|---|
| Brokerage | None | 0.03% or Rs 20 an order, whichever is lower |
| STT (securities transaction tax) | 0.1% on buys and sells | 0.025% on sells |
| Exchange transaction charge | 0.00297% | 0.00297% |
| SEBI fee | Rs 10 a crore | Rs 10 a crore |
| Stamp duty | 0.015% on buys | 0.003% on buys |
| GST | 18% of brokerage, exchange charge and SEBI fee | the same |

Example: buying Rs 1 lakh of shares for delivery costs Rs 100 STT + Rs 15 stamp duty + Rs 2.97 exchange charge + Rs 0.10 SEBI fee + Rs 0.55 GST = about Rs 118.62. The portfolio shows profit and loss before and after charges.

## 8. Market rules and the session

| Rule | Source | How it is applied |
|---|---|---|
| Which stocks | NSE price band list and bhavcopy | Every stock in the EQ series (2,689 on 14 Oct 2026, including ETFs) and the BE series (225, trade for trade: delivery only) |
| Reference price | Bhavcopy: the latest closing price | Centre of the price band |
| Tick size | NSE price slabs | Rs 0.01 below Rs 250; Rs 0.05 up to Rs 1,000; Rs 0.10 up to Rs 5,000; and so on |
| Price band | Price band list | 2, 5, 10 or 20%. Stocks with derivatives are listed as "No Band"; they get 10%, like NSE's starting operating range. |
| Session | `session.py` | Pre-open 9:00 to 9:15 am, normal market 9:15 am to 3:30 pm, Monday to Friday, Indian time. A holiday is recognised from Yahoo's market state for the NIFTY 50. |

NSE publishes the day's files in the evening. The app downloads them at start-up, at 8:45 am and at 7 pm, so the next session's price bands are ready before it opens.

## 9. Live market data inside the backend

Three background tasks run beside the API:

| Task | Every | What it does |
|---|---|---|
| Price stream | As prices arrive | Keeps one WebSocket open to Yahoo, subscribed to the followed stocks and the three indices; reconnects by itself, waiting longer after each failure. Each price updates the stock's last price, day range, one-minute bar and VWAP. The rise in the day's volume since the previous price is recorded as a trade, marked buy or sell by the tick test (a rise is a buy), and replayed in the engine for your waiting orders. |
| Quote poll | 5 seconds | Fetches quotes for the followed stocks in groups of 50: best bid and offer, open, day range, volume, 52-week range, valuation. Loads today's one-minute bars for newly followed stocks. |
| Clock | 1 second | Squares off intraday positions at 3:20 pm, expires orders at 3:30 pm, resets the day's figures when a new session starts, and downloads NSE's new files. |

A fourth task wakes four times a second and sends each open page the quotes and trades that changed, for the stocks that page follows. Account data (orders, positions, cash) is not pushed; the page asks for it every 1.5 seconds and straight after placing or cancelling an order.

## 10. Recommendations

Both recommendation pop-ups now work in three steps:

1. **Choose stocks.** Search any of the 2,914 NSE stocks, or add from your watchlist.
2. **Read the news and give your view.** Each stock shows its live price and its three latest headlines. You set how confident you are in it, from 0% (sure it falls) through 50% (no view) to 100% (sure it rises).
3. **See the result**, which combines your views with the data, and place the orders in one click.

### 10.1 Delivery: which stocks to buy

```
 Pop-up --POST /v1/recommendations {symbols, confidences, budget}-->  Backend: validate, live prices
                                                                         |
                                                                         v
                                                      recomendation_system.recommend()
                                                        1. daily prices since 2015 (Yahoo, cached daily)
                                                        2. your views move each expected return
                                                        3. Monte Carlo + SLSQP (the original method)
                                                        4. 200 re-runs on resampled history,
                                                           with your views and without
                                                        5. Buy if picked in at least half the runs
                                                        6. split the money, whole shares, Value at Risk
                                                                         |
 Pop-up shows decisions, chart, numbers  <-------------------------------+
 "Buy recommended stocks" --> normal POST /v1/orders (market, delivery), same checks
```

**How a view changes the numbers.** A confidence `c` becomes a view `v = (c - 50) / 50`, from -1 to +1. The stock's expected annual return is moved by `0.5 x v x its annual volatility`. For a stock with 25% volatility, 100% confidence adds 12.5 percentage points to its expected return and 0% takes 12.5 away; 75% adds 6.25. This is a simple form of the Black-Litterman idea: start from what the history says, then tilt it towards the investor's own views, in proportion to how sure the investor is and how much the stock usually moves.

**Decision.** The maximum-Sharpe optimisation is re-run 200 times on resampled history with the views applied. A stock is a **Buy** if it got at least 5% of the money in at least half of the runs. The same 200 runs are also done without the views, so the page shows how much your view changed each stock ("picked in 82% with your views, 56% on history alone"). The money is then split over the Buy stocks by the optimiser and turned into whole shares at the live price.

### 10.2 News

| Step | How |
|---|---|
| Source | Google News search as an RSS feed (no key needed), past seven days |
| Search words | For a few large companies, hand-written names (for example "Reliance" or "RIL"). For every other stock, its name from Yahoo or NSE without "Limited"; a long name is searched by its first two words ("Adani Ports") |
| Relevance | A headline must contain the name, its first two words, or a symbol of three or more letters |
| Clean-up | Quote pages and repeats of the same story are dropped; the newest three are kept |
| Caching | Each stock is fetched at most once every five minutes |
| Failures | The last headlines are shown with a note; a failure is not cached |

The headlines are for you to read. The recommendations use your confidence, not the headlines themselves.

### 10.3 Intraday: what to trade now

Three signals from today's real trading, each from -1 (strong sell) to +1 (strong buy):

| Signal | What it measures | Weight |
|---|---|---|
| Momentum | The price change over the last minute, compared with the stock's normal one-minute moves today | 40% |
| Price vs VWAP | The live price above or below today's volume-weighted average price | 30% |
| Trade flow | Shares traded on up-ticks against shares traded on down-ticks, last five minutes | 30% |

The model score is their weighted average. Your confidence that the stock will rise today becomes your view, from -1 to +1. **Final score = 60% model + 40% your view.** A final score of +0.25 or more is a **Buy**; -0.25 or less a **Sell short**; anything in between is **No trade**. So with no view, the live signals alone must be strong (+0.42); a 100% view on a flat stock is just enough; and a strong view against strong signals cancels the trade. A stock needs 10 minutes of trading today before it gets a signal.

Entry is the live best offer for a buy and the best bid for a short sale. The stop-loss sits 1.5 typical 15-minute moves away and the target twice as far. The margin is split by the size of the final score, and positions can be five times the margin. The signals are refreshed every second. Everything comes from memory, so a request for eight stocks takes about 0.25 ms on the server.

## 11. Frontend structure

| Folder | Contents |
|---|---|
| `api/` | `types.ts` (every API shape) and `client.ts` (every call) |
| `hooks/` | The live market over the WebSocket, the stock list, the watchlist (kept in the browser), a stock's rules, charts, sparklines, your orders in the book, account polling, news, intraday polling, the clock, theme |
| `components/layout/` | Top bar with the search over every NSE stock and the market status, the index and watchlist strip, the section menu, the footer |
| `components/quote/` | Quote header with the watchlist star, the chart (1 day to 5 years), key statistics, the watchlist |
| `components/market/` | Best bid and offer, your orders in the matching engine, time and sales, watchlist movers |
| `components/trading/` | Order form (session-aware, with a charges estimate), account summary, portfolio tabs with funds and charges |
| `components/news/` | Headline list, the page's news section |
| `components/recommendations/` | The recommendations section; the delivery and intraday pop-ups; the stock picker; the news-and-views step; the risk-against-return chart |
| `components/ui/` | Small shared pieces: modal, segmented control, sparkline, signal bar, confidence meter |
| `styles/` | `tokens.css` (colours, sizes, dark and light themes), `base.css`, and one stylesheet per area |

Times are always shown in Indian time. The page reflows from three columns to two at 1,279 px and to one at 1,023 px.

## 12. How this maps to the system design

| Design item | In this app |
|---|---|
| Order placement | Built: limit and market orders, cancel, after-market orders |
| Matching engine, price-time priority | Built in C++; the real market takes part through orders placed for it |
| Order book | Your orders in the engine; the real best bid and offer. Full real depth needs a broker data feed. |
| Risk checks | Built: validity and price band, funds with charges, shares, order size, session, self-trade |
| Cash balance with reservation | Built |
| Portfolio | Built: holdings, intraday positions, profit and loss before and after charges |
| Market data feed | Built: live stream and quotes in, one WebSocket out with per-page subscriptions |
| Circuit breakers | Per-stock price band only |
| Settlement | Immediate at trade time; no T+1 process |
| Audit | Append-only file |
| Message queue, cache, databases | Not used; everything is in memory |
| Stop orders, market-wide halts, login | Not built |

## 13. Measured performance

Measured on the development laptop on 15 Oct 2026, during market hours.

| What | Result |
|---|---|
| Engine alone, random mix of limit orders, market orders and cancels (`./engine/build/ob_bench`) | About 5 million operations per second; median about 130 ns |
| A market order through the whole backend path, including the market's order | Median 55 microseconds, 99th percentile 245 |
| A limit order that waits | Median 23 microseconds |
| Replaying one real trade with 3,000 of your orders waiting | Median 29 microseconds |
| Intraday signals for eight stocks | 0.25 ms on the server; about 1.5 ms for the whole HTTP round trip |
| Live price delay | About 2 seconds from NSE to the screen (Yahoo's stream) |

## 14. Testing

| Test | What it checks |
|---|---|
| `engine/tests` unit tests | Price priority, time priority, partial fills, market orders, cancel, rejections, a new day's band for an empty book |
| `engine/tests` random test | 60,000 random operations compared, trade by trade and level by level, against a slow and simple reference book |
| `backend/tests/test_exchange.py` | Fills at the real offer, falling back to the last price, waiting orders filling only on real trades and only their volume, price-time priority, self-trade prevention, every rejection, intraday margin and short selling, after-market orders, expiry at the close, the 3:20 pm square-off, a new day's band, charges |
| `backend/tests/test_live.py` | Reading Yahoo's quotes, bars and stream messages; trades from the rise in volume and the tick test; bars and VWAP; the market clock and holidays |
| `backend/tests/test_api.py` | The running app over HTTP and WebSocket, without the internet |
| `backend/tests/test_intraday.py` | Signal directions, your view deciding a flat market and cancelling a trade, waiting and closed sessions, levels on the tick and inside the band, sizing, speed, the endpoint |
| `backend/tests/test_recommendations_api.py`, `recomendation_system/tests` | Optimiser results, views moving returns, agreement with and without views, decisions, budget split, Value at Risk, invalid requests |
| `backend/tests/test_news.py` | Headline filtering, search words for any stock, repeats, unsafe links, caching, failures, the news endpoint |

The tests never use the internet: `ORDERBOOK_LIVE=0` switches the live feed off and the tests feed in their own quotes and trades.

## 15. Known limits

- No market depth: Yahoo publishes only the best bid and offer, without quantities. Real five-level depth needs an account with a broker that offers a market-data API.
- Fills are a little generous: there is no queue of other people's orders ahead of yours at the same price, and a market order fills completely at the best price.
- Prices are about two seconds behind NSE, and quiet stocks are reported only every few seconds.
- Yahoo can refuse requests that come too often; the app then backs off and shows the problem in the market status tooltip.
- State is not saved; a restart starts fresh. One user and no login.
- Tick size is taken from the reference close; NSE fixes it monthly, so a stock near a slab boundary may differ.
- Settlement is immediate; there is no T+1 and no DP charge on delivery sells.
- Intraday stop-losses and targets are suggestions; there are no stop orders.
- News relevance is decided by the company's name, so a headline about a similarly named company can occasionally appear.
- For personal use on your own computer only (section 2).
