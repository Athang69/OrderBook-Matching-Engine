# Agent handoff: OrderBook project, everything done so far

Give this file to any coding agent before it works on this repository. It records what the project is, what the team decided and why, how every part works, the current state, and what is left. Written on 15 Oct 2026. Where this file and the code disagree, the code is right; check it.

---

## 0. Rules for the agent (read first)

1. **Do not read `orderBook.cpp`** (repository root). The user asked for this on 11 Oct 2026 and never lifted it. It is the team's earlier prototype, it is not used by the app, and it has a small uncommitted change by the team. Leave it alone.
2. **It is a team project for a college faculty guide.** The user writes "we". Faculty-facing documents (`PROJECT_PLAN.md`, `PROJECT_REPORT.md`, `PROJECT_REPORT.docx`) must stay simple enough for the team to explain: plain language, about 10 to 15 references, a simple timeline. **Do not edit them without asking.** The user edits the `.docx` by hand.
3. **Realism over simulation.** The user said: "I don't want any dummy thing, I want everything to be realistic." Prefer real, free data and real broker behaviour. When something real is not available for free (market depth), say so plainly in the UI and docs. Never fake it.
4. **Money is integers in paise everywhere** (Rs 1,179.40 is `117940`). Times are shown in Indian Standard Time (IST, UTC+5:30).
5. **Indian market conventions:** NSE cash segment only (delivery CNC and intraday MIS). No futures and options, currency or commodities.
6. **Live prices are for personal, local use.** SEBI's circular of 24 May 2024 restricts passing real-time prices to others for virtual trading, and Yahoo's data is for personal use. Never host the app publicly or suggest it.
7. Commit or push only when the user asks. The user pushes with HTTPS. The `gh` CLI is not installed; git's credential helper points to a missing `/usr/bin/gh`, so pushes prompt for a username and token.
8. Keep code in the style already used: short docstrings that explain why, plain-English names, no new abstractions without need.

---

## 1. The project in one paragraph

**OrderBook** is a paper-trading app for the Indian stock market (NSE cash segment). Prices are live and real, about two seconds behind NSE, for all 2,914 NSE stocks in the EQ and BE series. The money is virtual (Rs 10,00,000 demo account). The core is the team's **C++20 matching engine** (price-time priority, one order book per stock). User orders are matched in it against the real market, which is represented by orders the backend places at real prices and for real traded volumes. A **Python FastAPI backend** handles the live feed, accounts, risk checks, charges, the market session, news and two recommenders. A **React + TypeScript frontend** looks like a Yahoo Finance-style brokerage page (own brand "OrderBook", dark by default). The two recommenders both ask the user, after showing each stock's live news, how confident they are in each stock:
- **Delivery:** Markowitz Monte Carlo + SLSQP portfolio optimisation, refactored from a friend's project, with the user's views tilting expected returns.
- **Intraday:** live signals from real trades, blended with the user's views.

Repository: `https://github.com/Athang69/OrderBook-Matching-Engine` (branch `main`). Local path on the main laptop: `/home/athang/Desktop/Dev/OrderBook`.

---

## 2. History: what was done, in order, and why

### 11 Oct 2026: scope (original)
- Simulator only: no real users, no real money. Matching real people's trades in listed shares outside an exchange is illegal "dabba trading" under the Securities Contracts (Regulation) Act.
- Previous-day data only (because of the SEBI 24 May 2024 circular), no paid data, free NSE files. Top 5 bids and asks; price-time priority.
- **This was reversed on 15 Oct (see below).** The faculty documents still describe this original scope.

### 12 Oct 2026: first prototype (commit `ac8f5e3`)
- `engine/`: C++ matching engine (flat price-level array inside the daily price band, FIFO queue per level, node pool, hash index for cancels). It speaks a text protocol over stdin/stdout. Tests: random comparison against a reference book. Benchmark: about 5 million operations a second, median about 130 ns.
- `backend/app/`: FastAPI order management, three risk checks, CNC and MIS accounts, robot traders replaying the previous day's open→high/low→close path over 15 minutes, audit log.
- `frontend/`: React UI. `scripts/run.sh` builds and starts everything. `docs/DESIGN.md`, `PROJECT_PLAN.md` and `PROJECT_REPORT.md`/`.docx` written.

### 14 Oct 2026: recommendations and news (commit `c2ebe3c`, with 15 Oct work)
- The user's "FinBERT + SLSQP" project turned out to be a friend's repository, `recomendation_system/Automated-Portfolio-Rebalancing-and-Risk-Analysis/`. It is a nested git clone of `github.com/Athang69/Automated-Portfolio-Rebalancing-and-Risk-Analysis`, git-ignored and left untouched.
  - It contains one Markowitz script (yfinance, Monte Carlo, SLSQP). **It has no FinBERT, no news and no confidence input.** `PROJECT_REPORT.md` still mentions FinBERT; that is the team's to fix.
- It was refactored into the package `recomendation_system/`. Two bugs in the original were fixed: it mixed daily covariance with annual returns, and it used a 2% risk-free rate (now 6.5%, closer to Indian treasury bills). A bootstrap "confidence" was added.
- News: Google News RSS, top 3 headlines per stock, shown on the page and in recommendations.

### 15 Oct 2026, morning: intraday signals and frontend redesign (in commit `c2ebe3c`)
- Intraday recommendation with live signals. The user stressed very low latency; the server median was 0.64 ms at the time.
- Frontend redesigned in a Yahoo Finance-style layout: `frontend/src/{api,hooks,components/<area>,styles}`.

### 15 Oct 2026: the live rebuild (commit `3a626a7`)
The user asked for:
1. Fix a bug where typing in the search scrolled the page up.
2. A per-stock human confidence, given after reading that stock's live news, feeding the recommendation.
3. Real, current market data like a brokerage app, with nothing dummy.
4. Every Indian stock searchable, as in a real broker app.

What was done:
- **Search scroll bug fixed.** Cause: `html { scroll-padding-top }` combined with the focused input inside the sticky top bar. Fix: removed it, and added `main [id] { scroll-margin-top: calc(var(--header-h) + 16px) }` in `frontend/src/styles/base.css`. Verified in a headless browser: scroll position stays constant while typing.
- **Live data from Yahoo Finance (free, no account)**, after testing what is available:
  - **Stream:** `wss://streamer.finance.yahoo.com/?version=2`, protobuf messages. About one update a second for busy stocks, about 2 s behind NSE (measured 2.3 s). Carries price, time, cumulative day volume.
  - **Batch quote:** `https://query1.finance.yahoo.com/v7/finance/quote`, 50 symbols a request, about 0.6 s. Carries bid and ask (sizes always 0 for NSE), OHLC, volume, 52-week range, market cap, P/E, EPS, dividend yield, P/B, marketState.
  - **Chart:** `https://query2.finance.yahoo.com/v8/finance/chart/{ticker}`.
  - **Not available free:** market depth (5-level quantities) and every individual trade. They need a broker API account (Angel One SmartAPI, Upstox and Fyers are free with an account; Zerodha Kite costs Rs 500/month). The user has not set one up. Scraping NSE's website JSON was ruled out (terms of use).
- **Robot traders and the replay were removed** (`backend/app/bots.py` deleted).
- **All NSE stocks:** 2,914 EQ + BE stocks from NSE's bhavcopy and price band list. The engine registers a stock lazily on its first order. Engine `SYM` now also resets an empty book with a new day's band (engine test count went to 53).
- **Paper fills through the engine against the real market** (section 5.3), plus:
  - after-market orders (AMO) when the market is closed;
  - expiry of open orders at 3:30 pm;
  - automatic MIS square-off at 3:20 pm;
  - self-trade prevention;
  - BE series delivery-only;
  - charges on every fill;
  - market clock with holiday detection.
- **Recommenders rebuilt around per-stock views.** The pop-ups now have three steps: choose stocks → read news and set confidence → result. Details in section 6.
- **Frontend rebuilt:**
  - search over all stocks; indices strip (NIFTY 50, SENSEX, NIFTY BANK); watchlist kept in browser storage;
  - charts from 1D to 5Y; real key stats; real best bid/offer; real time and sales; your orders in the engine;
  - session-aware order ticket with a charges estimate; funds and charges tab.
- Docs rewritten: `README.md`, `docs/DESIGN.md`, `recomendation_system/README.md`. The faculty documents were deliberately **not** changed.
- Quote poll slowed from 3 s to 5 s after Yahoo returned HTTP 429 (Too Many Requests) once.

### 15 Oct 2026, afternoon: another laptop (WSL on Windows)
- A teammate cloned the repo with Git for Windows into `C:\Users\...\OneDrive\Desktop\...` and ran `scripts/run.sh` in WSL. It failed with `env: 'bash\r': No such file or directory`. Cause: Git for Windows converted line endings to CRLF on checkout.
- Fix written: `.gitattributes` with `* text=auto eol=lf` (and `*.docx`, `*.pdf`, `*.png`, `*.jpg` binary). It was tested by reproducing a Windows checkout (`git -c core.autocrlf=true clone`): without it, CRLF and the same error; with it, LF and the script parses.
- **`.gitattributes` is created but NOT committed or pushed yet** (section 11).
- A clean clone of the pushed commit was tested with `PORT=8011 scripts/run.sh`. It built the engine, installed the Python packages (several minutes on the first run), downloaded the NSE files, ran `npm install` and the build, and started the server with the live stream connected.

---

## 3. Architecture

```
 Browser (React)
    |  REST: orders, portfolio, charts,          ^  WebSocket: live quotes and trades
    |  recommendations, news                     |  for the stocks each page follows, 4 times a second
    v                                            |
+----------------------------------------------------------------------------+
| Backend (Python 3.10, FastAPI, one process)                               |
|   API -> Order management (exchange.py) -> Risk checks -> Accounts, charges|
|                |  ^       ^                                                |
|                |  |       | real trades       Market data --> WebSocket    |
|                |  |   Live feed (yahoo.py): stream + 5 s quote poll + bars |
|                v  |                           Audit log --> logs/*.jsonl   |
+----------------|--|--------------------------------------------------------+
                 v  |  text commands over a pipe (stdin/stdout)
        +---------------------------+
        | Matching engine (C++20)   |  separate process, single thread, in memory
        +---------------------------+
 NSE daily files (data/nse) --> every stock's name, series, reference close, band, tick
```

### 3.1 Files

| Path                                                            | Purpose                                                                                                                                                                                                                                    |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `engine/include/ob/order_book.hpp`, `engine/src/order_book.cpp` | One order book: flat array of price levels inside the band, FIFO per level, node pool, `unordered_map` id index                                                                                                                            |
| `engine/include/ob/engine.hpp`                                  | Many books; `add_symbol` (adds, or resets an empty book), routing, cancel by id                                                                                                                                                            |
| `engine/src/main.cpp`                                           | Text protocol (section 5.1)                                                                                                                                                                                                                |
| `engine/tests/test_order_book.cpp`                              | 53 checks, including 60,000 random operations against a slow reference book                                                                                                                                                                |
| `engine/bench/bench.cpp`                                        | Speed test (`./engine/build/ob_bench`)                                                                                                                                                                                                     |
| `backend/app/config.py`                                         | All settings (section 4)                                                                                                                                                                                                                   |
| `backend/app/instruments.py`                                    | Loads EQ/BE stocks from the newest bhavcopy + price band list; tick slabs; band rounding                                                                                                                                                   |
| `backend/app/yahoo.py`                                          | Yahoo quotes, charts, stream (`YahooClient`, `YahooStream`), parsers, ticker mapping                                                                                                                                                       |
| `backend/app/market_data.py`                                    | Live state per followed stock: quote, one-minute bars, tape, VWAP, per-minute volatility, indices, WebSocket diff                                                                                                                          |
| `backend/app/session.py`                                        | Market clock: OPEN / PRE_OPEN / CLOSED, holiday from Yahoo, next open, 3:20 pm cut-off                                                                                                                                                     |
| `backend/app/exchange.py`                                       | Order management and paper fills against the market (section 5.3)                                                                                                                                                                          |
| `backend/app/risk.py`                                           | Pre-trade checks and reservations, including estimated charges                                                                                                                                                                             |
| `backend/app/accounts.py`                                       | Cash, holdings, intraday positions, charges paid                                                                                                                                                                                           |
| `backend/app/charges.py`                                        | Brokerage, STT, exchange charge, SEBI fee, stamp duty, GST                                                                                                                                                                                 |
| `backend/app/engine_client.py`                                  | Starts the engine process and speaks its protocol                                                                                                                                                                                          |
| `backend/app/news.py`                                           | Google News RSS, filtering, caching, search terms for any stock                                                                                                                                                                            |
| `backend/app/intraday.py`                                       | Intraday signals and recommendation with views                                                                                                                                                                                             |
| `backend/app/audit.py`                                          | Append-only JSON-lines audit log in `logs/`                                                                                                                                                                                                |
| `backend/app/main.py`                                           | `Simulator` (wiring, background tasks), REST and WebSocket endpoints                                                                                                                                                                       |
| `backend/tests/`                                                | `conftest.py` sets `ORDERBOOK_LIVE=0`; tests for exchange, live data, API, intraday, recommendations API, news                                                                                                                             |
| `recomendation_system/`                                         | `portfolio.py` (maths), `data.py` (yfinance history, cached in `data/history/`), `service.py` (`recommend()`), `__main__.py` (CLI), `tests/`                                                                                               |
| `frontend/src/api/`                                             | `types.ts` (every API shape), `client.ts` (every REST call)                                                                                                                                                                                |
| `frontend/src/hooks/`                                           | `useLiveMarket`, `useSymbols`, `useWatchlist`, `useInstrument` (+ `instrumentOf`), `useChart`, `useSparklines`, `useOrderBook`, `useAccount`, `useNews`, `useIntradaySignals`, `useNow`, `useTheme`, `useElementWidth`, `useActiveSection` |
| `frontend/src/components/layout/`                               | `TopBar`, `StockSearch`, `MarketStatus`, `MarketStrip`, `SectionNav`, `Footer`                                                                                                                                                             |
| `frontend/src/components/quote/`                                | `QuoteHeader` (watchlist star), `PriceChart` (1D–5Y), `KeyStats`, `Watchlist`                                                                                                                                                              |
| `frontend/src/components/market/`                               | `OrderBook.tsx` (`MarketDepth`: best bid/offer, your orders, time and sales), `Movers`                                                                                                                                                     |
| `frontend/src/components/trading/`                              | `OrderTicket`, `AccountSummary`, `AccountTabs`                                                                                                                                                                                             |
| `frontend/src/components/news/`                                 | `News.tsx` (`NewsList`, `NewsPanel`, `NewsSection`)                                                                                                                                                                                        |
| `frontend/src/components/recommendations/`                      | `DeliveryModal` (+ shared `Steps`, `StatCard`, `Outcomes`), `IntradayModal`, `StockPicker`, `YourViews`, `RecommendationsPanel`, `FrontierChart`, `placeOrders.ts`                                                                         |
| `frontend/src/components/ui/`                                   | `Modal` (native dialog), `Segmented`, `Sparkline`, `SignalBar`, `ConfidenceMeter`                                                                                                                                                          |
| `frontend/src/lib/`                                             | `format.ts` (paise to rupees, IST times, reason texts, `companyName`), `charges.ts` (client-side estimate)                                                                                                                                 |
| `frontend/src/styles/`                                          | `tokens.css` (dark/light), `base.css`, `ui.css`, `layout.css`, `quote.css`, `market.css`, `trading.css`, `news.css`, `recommendations.css`                                                                                                 |
| `scripts/run.sh`                                                | Builds everything missing and starts the app (section 8)                                                                                                                                                                                   |
| `scripts/fetch_nse_data.py`                                     | Downloads NSE's newest daily files (standard library only)                                                                                                                                                                                 |
| `docs/DESIGN.md`                                                | Full design explanation (plain language)                                                                                                                                                                                                   |

---

## 4. Settings (`backend/app/config.py`)

| Setting                                                          | Value                                                    | Meaning                                            |
| ---------------------------------------------------------------- | -------------------------------------------------------- | -------------------------------------------------- |
| `LIVE`                                                           | from `ORDERBOOK_LIVE` (default on; `0` = offline)        | Live feed on or off; tests run offline             |
| `SERIES` / `DELIVERY_ONLY_SERIES`                                | `("EQ", "BE")` / `("BE",)`                               | BE is trade-for-trade, so no intraday              |
| `DEFAULT_WATCHLIST`                                              | RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK, SBIN, ITC, LT  | First watchlist; always kept live                  |
| `INDICES`                                                        | NIFTY 50 `^NSEI`, SENSEX `^BSESN`, NIFTY BANK `^NSEBANK` | Shown in the strip                                 |
| `QUOTE_POLL_SECONDS`                                             | 5                                                        | Was 3; Yahoo returned 429 once                     |
| `MAX_LIVE_SYMBOLS`                                               | 100                                                      | Stocks followed at once                            |
| `CHART_CACHE_SECONDS`                                            | 1d 60, 5d 300, 1mo 900, 6mo/1y/5y 3600                   | Server chart cache                                 |
| `DEFAULT_BAND_PCT`                                               | 10                                                       | For "No Band" (F&O) stocks                         |
| `PRE_OPEN`, `MARKET_OPEN`, `MARKET_CLOSE`, `INTRADAY_SQUARE_OFF` | 9:00, 9:15, 15:30, 15:20 IST                             | Session                                            |
| `DEMO_USER`, `DEMO_CASH`                                         | `"demo"`, Rs 10,00,000                                   | One account, no login                              |
| `MIS_MARGIN_DIVISOR`                                             | 5                                                        | 20% margin, 5x leverage                            |
| `MAX_ORDER_QTY`                                                  | 100,000                                                  | Order size limit                                   |
| `COMPANIES`                                                      | 23 hand-written news search terms                        | For stocks where the NSE name finds the wrong news |
| `NEWS_PER_STOCK`, `NEWS_CACHE_SECONDS`, `MAX_NEWS_SYMBOLS`       | 3, 300, 10                                               | News                                               |

---

## 5. How it works

### 5.1 Engine protocol
One command per line; every reply ends with `END`. Prices in paise.
```
SYM <symbol> <tick> <lower> <upper>   -> OK | ERR   (adds a stock, or resets an empty book's band)
NEW <id> <symbol> <B|S> <L|M> <price> <qty> -> ACK, TRD <buy_id> <sell_id> <price> <qty>..., FIN <id> <filled> <resting> <cancelled> | REJ <id> <reason>
CXL <id>                              -> CXD <id> <qty> | REJ <id> UNKNOWN_ORDER
DEP <symbol> <levels>                 -> BID <price> <qty> <orders>..., ASK ...
PING                                  -> PONG
```
Trades happen at the resting (maker) order's price. Market orders sweep inside the band; any remainder is cancelled.

### 5.2 Reference data and rules (`instruments.py`, `scripts/fetch_nse_data.py`)
- **Files:** `sec_bhavdata_full_DDMMYYYY.csv` (from `https://nsearchives.nseindia.com/products/content/`) and `sec_list_DDMMYYYY.csv` (from `/content/equities/`), saved in `data/nse/` (git-ignored). The script starts from today and goes back up to 10 days, because today's files appear only after the close. It needs browser-like headers.
- **Reference close:** the latest bhavcopy `CLOSE_PRICE`. The band is centred on it (2/5/10/20%; "No Band" becomes 10%) and rounded inwards to the tick.
- **Tick slabs (paise):** below Rs 250 → 1; up to 1,000 → 5; up to 5,000 → 10; up to 10,000 → 50; up to 20,000 → 100; above → 500.
- **Refresh:** the server re-runs the fetch script and reloads instruments at 8:45 and 19:00 IST. Empty engine books take the new band.

### 5.3 Paper trading against the live market (`exchange.py`)
- **Marketable order** (market, or a limit at or better than the touch):
  1. **The touch price.** Use the ask for a buy or the bid for a sell, but only if the quote is at most 10 s old (`QUOTE_MAX_AGE`) and within 0.5% of the last price (`QUOTE_MAX_GAP`). Otherwise use the last traded price.
  2. **Tick grid.** A buy rounds up and a sell rounds down, so a fill is never better than the real price.
  3. **Market's order.** The backend places the market's opposite order at that price for the order's quantity, plus any of the user's own resting orders it would reach first (`_place_for_market(for_new_order=True)`).
  4. **Match.** It then sends the user's order, which matches it, and cancels whatever is left of the market's order.
- **Resting order:** waits in the engine. On each real trade from the stream (`on_market_trade(symbol, price, qty)`), with `qty` = the rise in day volume since the previous stream message:
  - the backend places a market SELL at `ceil_to_tick(price)` for `qty`, which fills user buys at or above it;
  - then a market BUY at `floor_to_tick(price)` for `qty`, which fills user sells at or below it;
  - each is cancelled afterwards.
  - Fills are at the user's limit (maker price), in price-time priority, capped by the real volume.
- **Market-order ids** start at `10**12` (`MARKET_IDS_START`); only user orders below that touch accounts.
- **Refusals:**
  - no price update for 60 s (`PRICE_MAX_AGE`) → `NO_LIVE_PRICE`;
  - touch price outside the band → `OUTSIDE_PRICE_BAND`;
  - would trade with the user's own opposite resting order → `SELF_TRADE`.
- **Closed or pre-open:** CNC orders become AMO (`amo=True`, status OPEN, reserved, outside the engine). They enter at the stock's first real trade of the session, at that price if marketable. MIS is refused (`INTRADAY_CLOSED`).
- **3:20 pm** (`on_clock`): `square_off(user, tag="AUTO_SQUARE_OFF")`. After that, MIS orders may only reduce a position.
- **Leaving OPEN** (3:30 pm): every open order is cancelled with reason `EXPIRED`. Any MIS position left is settled at the last price with charges.
- **Reject and cancel reasons** (shown in plain words by `frontend/src/lib/format.ts`): `INSUFFICIENT_FUNDS`, `INSUFFICIENT_SHARES`, `OUTSIDE_PRICE_BAND`, `BAD_TICK`, `BAD_QUANTITY`, `ORDER_SIZE_EXCEEDED`, `PRICE_REQUIRED`, `UNKNOWN_SYMBOL`, `NO_LIVE_PRICE`, `SELF_TRADE`, `INTRADAY_CLOSED`, `INTRADAY_NOT_ALLOWED`, `NO_LIQUIDITY`, `USER_CANCELLED`, `EXPIRED`.
- **Known optimism:** there is no queue of other people's orders ahead of yours, and a market order fills completely at the touch.

### 5.4 Risk, accounts and charges
- `available = cash - blocked_for_orders - intraday_margin`.
- **CNC buy:** blocks `qty × price + estimated charges`. A market order is reserved at the upper band.
- **CNC sell:** blocks shares.
- **MIS:** blocks `opening_qty × price / 5 + estimated charges`. Short selling is allowed. P&L is settled to cash when the position is reduced.
- **Charges per fill** (`charges.py`; published 2025 rates for a discount broker):

| Charge          | Rate                                                        |
| --------------- | ----------------------------------------------------------- |
| Brokerage       | CNC 0; MIS min(0.03%, Rs 20 per order, capped across fills) |
| STT             | CNC 0.1% on both sides; MIS 0.025% on sells                 |
| Exchange charge | 0.00297%                                                    |
| SEBI fee        | 0.0001% (Rs 10 a crore)                                     |
| Stamp duty      | CNC 0.015% on buys; MIS 0.003% on buys                      |
| GST             | 18% of (brokerage + exchange + SEBI)                        |

  Example: a Rs 1 lakh delivery buy costs Rs 118.62. DP charges are not modelled.
- **Portfolio** returns `charges` (breakdown) and `net_pnl` = realised + unrealised − charges. Holdings carry `prev_close` for the day's change.

### 5.5 Live feed and market data (`yahoo.py`, `market_data.py`, `main.py`)
- **Background tasks** in `lifespan`:
  - `broadcast_forever` (every 0.25 s);
  - `clock_forever` (1 s: `exchange.on_clock`, new-day reset, NSE refresh);
  - `poll_quotes_forever` (5 s; backs off to 60 s on errors; loads 1-minute bars for up to 4 new stocks per cycle);
  - `stream.run()` (reconnects with back-off 1 → 30 s; resubscribes every 15 s).
- **Followed stocks** (`Simulator.wanted()`), capped at 100:
  - the default watchlist;
  - stocks with orders, holdings or positions;
  - stocks requested by REST or WebSocket in the last 15 minutes.
- **Stream message → `market.on_tick`:**
  - traded quantity = rise in the stream's own day volume (the first message only sets the base);
  - side by the tick test (a rise is a buy);
  - updates LTP, high/low, one-minute bars, VWAP and the tape (60 trades).
  - Then `exchange.on_market_trade`. Index tickers go to `on_index`.
- **Quote → `on_quote`:**
  - a quote older than the last stream price does not overwrite LTP;
  - high and low are merged only when the quote is stale;
  - `polled_at` records when it was fetched.
- **Volatility:** standard deviation of one-minute log returns from today's completed bars (needs 6 or more), recomputed when a bar closes.
- **Holiday:** inside session hours, if Yahoo's NIFTY 50 `marketState` (at most 5 minutes old) is not `REGULAR`, the state is CLOSED (holiday).

### 5.6 API (all under `/v1`)

| Method       | Path                                                    | Notes                                                                                                                                                                                           |
| ------------ | ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GET          | `/status`, `/health`                                    | session, feed health, `live`, `demo_user`, `margin_divisor`                                                                                                                                     |
| GET          | `/market/symbols`                                       | `{data_date, count, watchlist, symbols: [[symbol, name, series, close, tick, band_pct, lower, upper], ...]}`, gzip                                                                              |
| GET          | `/market/instrument/{symbol}`                           | rules + `quote`; activates the stock (fetches the quote and bars at once)                                                                                                                       |
| GET          | `/market/quotes?symbols=`                               | up to 60                                                                                                                                                                                        |
| GET          | `/market/chart/{symbol}?range=1d                        | 5d                                                                                                                                                                                              | 1mo | 6mo | 1y | 5y` | bars `[t, o, h, l, c, v]`; `1d` comes from memory |
| GET          | `/market/sparklines?symbols=`                           | about 75 `[t, close]` points from memory                                                                                                                                                        |
| GET          | `/market/trades/{symbol}`                               | real tape                                                                                                                                                                                       |
| GET          | `/market/orderbook/{symbol}`                            | `bid`, `ask`, `polled_at`, `depth_available: false`, `your_bids`, `your_asks` (engine levels)                                                                                                   |
| GET          | `/market/indices`                                       |                                                                                                                                                                                                 |
| POST         | `/orders`                                               | `{symbol, side, type, product, qty, price?}`; fetches a quote first if none in the last 15 s                                                                                                    |
| DELETE / GET | `/orders/{id}`; GET `/orders`                           |                                                                                                                                                                                                 |
| GET          | `/portfolio/{user}`; POST `/portfolio/{user}/squareoff` | square-off returns 409 when closed                                                                                                                                                              |
| POST         | `/recommendations`                                      | `{symbols (2–10), confidences {SYM: 0–100}, budget}`; one run at a time                                                                                                                         |
| POST         | `/recommendations/intraday`                             | `{symbols (1–20), confidences, budget}`; reply includes `timing` in microseconds                                                                                                                |
| GET          | `/news?symbols=`                                        | up to 10                                                                                                                                                                                        |
| WS           | `/stream/marketdata`                                    | server sends `hello {status, indices}`; client sends `{"subscribe": [...]}` (max 60); server replies `snapshot {quotes, trades}`, then `update {quotes, trades, indices, status?}` every 0.25 s |

---

## 6. The two recommenders

### 6.1 Delivery (`recomendation_system/service.py`, `portfolio.py`)
- **Data:** daily closes since 2015-01-01 from yfinance (`auto_adjust=True`), cached per stock in `data/history/SYMBOL.csv` and refetched once a day. Only days on which every chosen stock traded are used; at least 250 are needed.
- **View:** `v = (c - 50) / 50` in [-1, 1].
- **Tilt:** `0.5 × v × annual volatility` added to the expected annual return (`view_tilts`). This is a simplified Black-Litterman idea.
- **Method:**
  - log returns × 250;
  - 20,000 Monte Carlo portfolios on the viewed returns;
  - SLSQP max-Sharpe (on history, and with views) and min-volatility; risk-free rate 6.5%; no shorts; weights add up to 1.
- **Agreement:** 200 bootstrap resamples of days, each re-running max-Sharpe both with the tilt and without it (paired: same resamples). Agreement = share of runs in which the stock got at least 5% of the money.
- **Decision:** BUY if agreement with views ≥ 50%. The final weights come from max-Sharpe on the viewed returns over the BUY stocks, turned into whole shares at the live price.
- **Also returned:**
  - one-day historical VaR at 95%;
  - reference portfolios `history_only`, `max_sharpe`, `min_volatility`;
  - 1,500 frontier points;
  - for each stock: `your_confidence`, `return_shift`, `agreement`, `history_agreement`, `weight`, `quantity`, `cost`, `expected_return`, `expected_return_with_view`, `volatility`, `note`.
- **Seed:** fixed at 42, so the same inputs give the same answer.
- **CLI:** `.venv/bin/python -m recomendation_system --symbols RELIANCE TCS INFY --views RELIANCE=75 INFY=30 --budget 100000`.

### 6.2 Intraday (`backend/app/intraday.py`)
- **Signals**, each from -1 to +1:
  - momentum = `tanh(log(ltp/price_1_min_ago) / (sigma_min × sqrt(elapsed_min)) / 2)`;
  - VWAP signal = `tanh(log(ltp/vwap) / (sigma_min × sqrt(5)))`;
  - flow = `(up-tick volume − down-tick volume) / total`, over the last 5 minutes (at most 50 trades).
- **Weights:** momentum 0.4, VWAP 0.3, flow 0.3, giving the model score.
- **Final score** = 0.6 × model + 0.4 × your view. BUY if ≥ +0.25; SELL short if ≤ −0.25; otherwise NO_TRADE.
- **WAIT** when there are fewer than 10 one-minute bars today, or when intraday is closed (the signals are still shown).
- **Levels:**
  - entry = fresh best offer for a buy, best bid for a sell (else LTP);
  - stop = 1.5 × typical 15-minute move;
  - target = 2 × the stop distance;
  - all on the tick grid and inside the band.
- **Size:** margin split by the size of the final score; positions up to 5× the margin. BE-series rows are forced to NO_TRADE in `main.py`.
- **Speed:** about 0.25 ms server time for 8 stocks; the browser refreshes every second.

### 6.3 News (`backend/app/news.py`)
- **Query:** Google News RSS `"{search name}" share when:7d`, with `hl=en-IN`, `gl=IN`, `ceid=IN:en`. Parsed with `defusedxml`.
- **A headline is kept only if:**
  - it contains an alias as a whole word;
  - it is not a quote or listing page (`NOT_NEWS` regex);
  - it is not a repeat of the same story (first 70 normalised characters);
  - it is among the newest 3.
- **Search terms** (`company_terms`):
  - the overrides in `config.COMPANIES`; otherwise
  - the Yahoo or NSE name without "Limited"/"Ltd";
  - its first two words (names of 3 or more words; skips a leading "The");
  - a long name (4 or more words) is searched by those two words;
  - the symbol is an alias if it is alphabetic and 3 or more letters.
- **Cache and failures:** cached 5 minutes. A failure returns the last headlines with a note and is not cached.

---

## 7. Frontend behaviour
- **Data flow:**
  - `useSymbols` loads all 2,914 rows once, so a stock page opens instantly from `instrumentOf(row)`.
  - `useLiveMarket` subscribes to: the stock on screen, the watchlist, holdings, positions, open-order stocks, and any stocks chosen in an open pop-up (`onFollow`).
  - `useAccount` polls the portfolio and orders every 1.5 s.
- **Browser storage keys:** watchlist `orderbook-watchlist`; theme `orderbook-theme`.
- **Search** (`StockSearch`):
  - ranking: exact symbol, symbol prefix, name word prefix, symbol substring, name substring; at most 12 results;
  - shows the watchlist when the box is empty; arrow keys and Enter work; BE stocks get a tag.
- **One-day chart:** positioned by the minute across the 375-minute session (9:15 to 15:30), with axis labels every 75 minutes. Other ranges are spaced by bar index. The last bar follows the live price.
- **Order ticket:**
  - "(AMO)" in the button when the market is closed;
  - a session note: intraday closed, after 3:20 pm, BE delivery-only;
  - a charges estimate from `lib/charges.ts`;
  - clicking Delivery or Intraday opens the pop-up.
- **Pop-ups:**
  - Step 1: stock picker (search plus quick-add from the watchlist; at most 10 stocks for delivery, 20 for intraday) and the amount.
  - Step 2: `YourViews` (live price, 3 headlines, a slider and a number box per stock; labels from "Sure it falls" to "Sure it rises").
  - Step 3: the result, with one-click market orders (`placeOrders.ts`, sent one at a time).
- **Layout:** three columns at 1,280 px and above, two from 1,024 px, one below. Verified with no horizontal overflow at 1440, 1100 and 390 px.

---

## 8. Running, testing, environments

### 8.1 Run
```
scripts/run.sh                    # http://localhost:8000
PORT=9000 scripts/run.sh
ORDERBOOK_LIVE=0 scripts/run.sh   # offline: no prices, everything else works
```
`run.sh` does four things:
1. builds the engine with CMake;
2. creates `.venv` and installs `backend/requirements.txt` and `recomendation_system/requirements.txt` if the imports fail;
3. runs `fetch_nse_data.py`, or keeps going with the existing files;
4. runs `npm install` and `npm run build` when the sources are newer.

It then starts uvicorn on `127.0.0.1`. The frontend dev server is `cd frontend && npm run dev` on port 5173 (CORS allowed).

### 8.2 Tests
```
cmake -S engine -B engine/build && cmake --build engine/build && ./engine/build/ob_tests   # 53 checks
.venv/bin/python -m pytest backend/tests recomendation_system/tests -q                      # 91 tests
./engine/build/ob_bench
cd frontend && npm run build    # runs tsc --noEmit, then vite build
```
Per file: `test_api` 9, `test_exchange` 19, `test_intraday` 18, `test_live` 9, `test_news` 10, `test_recommendations_api` 9, `test_recommender` 17. The tests never use the network: they feed in their own quotes and trades, and replace `Simulator.session` to choose open or closed. The one warning (Starlette's httpx deprecation) comes from the library.

### 8.3 Measured (15 Oct 2026, market hours, this laptop)

| What                                                           | Result                                                      |
| -------------------------------------------------------------- | ----------------------------------------------------------- |
| Engine                                                         | About 5 million operations/s; median about 130 ns           |
| Market order through the backend, including the market's order | Median 55 µs, 99th percentile 245 µs                        |
| Resting limit order                                            | Median 23 µs                                                |
| Replaying one real trade with 3,000 orders resting             | Median 29 µs                                                |
| Intraday signals for 8 stocks                                  | 0.25 ms on the server; about 1.5 ms for the HTTP round trip |
| Delivery recommendation, 3 stocks, cached history              | About 0.4 s                                                 |

### 8.4 Main laptop
Ubuntu 22.04, g++ 11.4, CMake 3.22, Python 3.10.12 (`.venv` in the repo), Node 24 via nvm (apt's nodejs is v12, too old). Headless browser checks were done with `playwright-core@1.48.2` and `/usr/bin/google-chrome` from a scratch folder outside the repo. The Chrome DevTools MCP connection was broken in these sessions ("Target closed"); the user can reconnect it with `/mcp`.

### 8.5 New laptop setup (what to install)
- **Ubuntu 22.04 or newer:**
  ```
  sudo apt install -y git build-essential cmake python3 python3-venv python3-pip
  ```
  Then Node 18+ through nvm (`nvm install 20`). Then clone and run `scripts/run.sh`.
- **Common problems:**
  - missing `python3-venv` → "ensurepip is not available";
  - Node from apt is v12 → the Vite build fails.
- **Windows:** WSL Ubuntu. Clone **inside WSL's home folder (`~`)** with WSL's own git, not under `/mnt/c/...` or OneDrive: it is slow there, OneDrive tries to sync the libraries, and Windows' Git converts line endings. Open `http://localhost:8000` in the Windows browser.
- **macOS:** `xcode-select --install`, `brew install cmake python@3.12 node`. Untested.
- **Internet:** needed on the first run, and for live prices every time.

---

## 9. Data sources and their limits

| Data                                               | Source                                | Notes                                                        |
| -------------------------------------------------- | ------------------------------------- | ------------------------------------------------------------ |
| Live price, day volume                             | Yahoo stream                          | About 2 s behind NSE. Quiet stocks update every few seconds. |
| Bid/ask (no sizes), OHLC, 52-week range, valuation | Yahoo v7 quote, every 5 s             | Rate limits: a 429 was seen once at 3 s; the poll backs off  |
| Charts                                             | Yahoo v8 chart                        | 1d=1m, 5d=5m, 1mo=30m, 6mo=1d, 1y=1d, 5y=1wk                 |
| Indices                                            | Yahoo (`^NSEI`, `^BSESN`, `^NSEBANK`) | SENSEX updates less often                                    |
| Stocks, bands, ticks                               | NSE bhavcopy + price band list        | Free daily files. Never committed (`data/` is git-ignored).  |
| News                                               | Google News RSS                       | Name-based relevance                                         |
| History for recommendations                        | yfinance daily                        | Cached daily                                                 |
| Market depth (5 levels with quantities)            | **Not available free**                | Needs a broker API account                                   |

---

## 10. Known limits

- No real market depth; the order book shows the real best bid and offer plus the user's own orders in the engine.
- Fills are a little generous: no queue position, and market orders fill fully at the touch.
- About 2 s of delay; quiet stocks rarely print, so resting orders in them fill slowly.
- Everything is in memory: a restart resets the account and orders. One user, no login.
- Tick size comes from the reference close; NSE revises it monthly, so a stock near a slab boundary may differ.
- Settlement is immediate (no T+1). No DP charges. No stop orders: intraday stop-loss and target are suggestions only.
- News relevance is name-based, so a similarly named company can slip in.
- After 3:30 pm, AMOs use the band from the files loaded at that moment, until the 19:00 refresh.
- When DNS or the internet drops, the stream reconnects with back-off. A harmless "Future exception was never retrieved … gaierror" line can appear in the log from inside the websockets library.

---

## 11. Current repository state (15 Oct 2026)

- Commits on `main`, pushed to GitHub: `ac8f5e3` (prototype), `c2ebe3c` (recommendations, news, intraday, new frontend), `3a626a7` (live paper trading, all stocks, views).
- **Uncommitted in the working tree:**
  - `.gitattributes` (new): **needs commit and push** so that clones made with Windows' Git work under WSL;
  - `PROJECT_REPORT.md`, `PROJECT_REPORT.docx`: the user's own edits; do not touch;
  - `README.md`: only table-alignment reformatting by the user's editor;
  - `orderBook.cpp`: the team's change; do not read.
- **Suggested commit for `.gitattributes`:**
  ```
  git add .gitattributes
  git commit -m "Keep Linux line endings so scripts/run.sh works when cloned on Windows"
  git push
  ```
- **Not in git:** `data/`, `logs/`, `.venv/`, `engine/build/`, `frontend/node_modules/`, `frontend/dist/`, `recomendation_system/Automated-Portfolio-Rebalancing-and-Risk-Analysis/` (friend's nested repo).

---

## 12. Open items and possible next steps (for the team to choose)

1. **Commit and push `.gitattributes`** (section 11).
2. **Faculty documents are out of date** and are the team's decision. Outdated statements are around:
   - `PROJECT_PLAN.md` lines 9–10 and 27 ("no live market data", the SEBI reasoning);
   - `PROJECT_REPORT.md`:
     - "previous-day data only": lines 18, 41, 51, 128, 163, 187;
     - "robot traders": lines 103, 166, 188, 294, 314, 325;
     - "FinBERT": lines 42, 75, 110, 166, 207, 244.
   
   The report must also decide how to describe live prices in light of the SEBI circular: personal local use, not shared or hosted.
3. **Real market depth:** add an optional broker data provider (Angel One SmartAPI is free with an account: REST quote in FULL mode gives 5-level depth; a WebSocket gives ticks). It needs the user's own credentials, so it cannot be built and tested without them.
4. **Persistence:** SQLite for accounts, orders and the audit replay, so a restart keeps state. Login if more than one user is ever needed (local only).
5. **Realism extras:** T+1 settlement and holdings bought today; DP charge on delivery sells; stop-loss orders (SL, SL-M); GTT; queue-position modelling for fills; NSE tick-size table instead of slabs from the close.
6. **FinBERT:** the report mentions FinBERT sentiment, but no code has it. If wanted, it would score the fetched headlines and show the score next to the user's own confidence. It must stay a separate signal, since the user wants the human view to decide.

---

## 13. Glossary

| Term                | Meaning                                                                     |
| ------------------- | --------------------------------------------------------------------------- |
| CNC / delivery      | Buy and hold; full cash needed; shares go to the demat account              |
| MIS / intraday      | Same-day position with 20% margin; short selling allowed; closed by 3:20 pm |
| AMO                 | After-market order: placed while closed, sent at the next open              |
| LTP                 | Last traded price                                                           |
| VWAP                | Volume-weighted average price for the day                                   |
| Bid / offer (ask)   | Best price buyers are paying / sellers are asking                           |
| Tick                | Smallest price step                                                         |
| Price band          | Daily limit on how far a price may move from the reference close            |
| EQ / BE series      | Normal market / trade-for-trade (delivery only)                             |
| Bhavcopy            | NSE's daily file of every stock's prices and volumes                        |
| STT                 | Securities transaction tax                                                  |
| Square-off          | Closing an intraday position                                                |
| Price-time priority | Best price first; at the same price, earliest order first                   |
| Paise               | 1/100 rupee; all money in the code is integer paise                         |
