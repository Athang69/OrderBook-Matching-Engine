# Indian Equity Order Book Simulator — Project Plan

_Last updated: 11 October 2026. These are research notes and a build plan, not legal advice._

## 1. What we are building

A simulator of an Indian stock exchange's cash market: an order book and a matching engine, written in C++ and built for speed.

- No real users and no real money. Traders are robot programs and ourselves, using virtual cash.
- No live market data. We only use data from the previous trading day or older.
- No paid data. Everything below is free.

## 2. Scope

**In scope**

- NSE cash segment, EQ series only. This covers both delivery and intraday trading.
- An L2 view: the 5 best buy prices and 5 best sell prices per stock, with quantities.
- Matching by price-time priority: better price first; at the same price, the earlier order first.
- Virtual accounts with delivery (CNC) and intraday (MIS) rules.

**Out of scope, and why**

| Left out | Reason |
|---|---|
| Real-money trading between real people | Matching trades in listed shares outside a recognised exchange is illegal "dabba trading" under the Securities Contracts (Regulation) Act: up to 10 years and/or a ₹25 crore fine. |
| Live prices shown to the public | A SEBI circular of 24 May 2024 bars real-time prices on virtual-trading platforms. Education use is allowed with a one-day lag and no monetary incentives, which is what we follow. |
| Futures, options, currency, commodities | Not needed for delivery and intraday equity trading. |
| Paid data feeds | Budget is zero. |

Keep it free of cash prizes or any reward tied to simulated performance.

## 3. Free data sources

All of these were downloaded successfully on 11 October 2026, with no login and no payment.

### 3.1 NSE daily files (previous day, every stock)

| File | What is inside | What we use it for |
|---|---|---|
| Full bhavcopy | Per stock: previous close, open, high, low, last, close, average price, traded quantity, turnover, number of trades, delivery quantity, delivery % | Setting each stock's reference price; sizing the robot traders' order flow; the delivery versus intraday split |
| Price band list | Per stock: circuit band (2, 5, 10, 20 or no band) | Upper and lower price limits for the day |
| VaR margin file | Per stock: margin rates published by NSE Clearing | Intraday margin and leverage for virtual accounts |
| Listed securities | Symbol, company name, series, market lot, ISIN, face value | The instrument master |
| UDiFF bhavcopy | The newer standard end-of-day format | Alternative to the full bhavcopy |

URL patterns (replace the date):

```
https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv
https://nsearchives.nseindia.com/content/equities/sec_list_DDMMYYYY.csv
https://nsearchives.nseindia.com/archives/nsccl/var/C_VAR1_DDMMYYYY_1.DAT
https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv
https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip
```

Notes:

- Send a browser-style `User-Agent` header. Our requests without one timed out; with one they worked.
- Tick size is not in these files. Derive it from the previous close using the price slabs in section 7.
- The column meanings in the VaR file should be confirmed against NSE Clearing's file format note before we rely on them.

### 3.2 NSE's free sample of real order-level data

NSE publishes free sample archives on its historical data page. They contain real orders and trades for real stocks, which is the only free order-by-order data we found.

Page: <https://www.nseindia.com/static/market-data/eod-historical-data-subscription>

| Archive | Contents |
|---|---|
| `Sample_CMsegment.zip` | An orders file (300,000 order events, 579 symbols) and a trades file (300,000 trades), both from 10 April 2024 |
| `Download Sample Files for CM (.zip)` | An order book snapshot (about 500,000 resting orders across 54 symbols), a trades file, masters and bhavcopy samples |

What the orders file covers:

- The whole pre-open session (about 157,000 events, ending 09:07:42) and the first 12 seconds of normal trading (about 142,000 events).
- Mostly symbols starting with A, B and C, for example AXISBANK, BEL, BHARTIARTL, BPCL.
- Each event is a new order, a modification or a cancellation, with order number, time, side, symbol, quantity, limit price, trigger price, and flags for market, stop-loss and IOC orders.
- The trades file gives the buy order number and sell order number for every trade, so trades can be matched back to orders.

Format notes:

- Fixed-width text, one event per line. Prices are in paise.
- Time is in "jiffies": 65,536 per second, counted from midnight on 1 January 1980. The sample decodes to Indian clock time.
- The sample uses the older field widths (8-digit quantities). The current specification uses 10 digits, so a parser for the sample needs the older widths.
- Field layouts are in NSE's specification: <https://nsearchives.nseindia.com//web/mediaattachment/2026-09/NSE_Hist_Order_Trade_Data_1.19_20260902144045.pdf>

This sample is a slice, not a full day. It is enough to test the engine against reality, not enough to replay a whole session.

### 3.3 One-minute price bars (for the previous day's price path)

| Source | Cost | Status |
|---|---|---|
| Yahoo Finance via the `yfinance` library (`RELIANCE.NS` style tickers) | Free, no account | Unconfirmed. Our test call was rate-limited (HTTP 429). One-minute bars are reported to be limited to about 7 days per request. Unofficial source. |
| Angel One SmartAPI historical candles | Free, needs a broker account | Angel One lists its trading, historical and market feed APIs as free. Not tested by us. |
| Upstox and Fyers historical candle APIs | Free, needs a broker account | Listed as free in broker comparisons. Not tested by us. |

If none of these work out, the simulator still runs from the daily file alone (open, high, low, close and volume), with a coarser price path.

### 3.4 Do not commit data files

The downloaded files belong to NSE. Commit the download scripts, not the data. Add a `data/` folder to `.gitignore` and keep everything downloaded inside it.

## 4. What free data cannot give us

There is no free source of a full day's real order book, order by order or level by level, for an arbitrary day. That is a paid NSE product.

The workaround: robot traders generate the orders, and we tune them with real numbers from the previous day. Prices then follow the real path, but the individual orders are made up. We should say so plainly wherever results are shown.

## 5. What we can build

**Core**

1. **Matching engine.** It takes buy and sell orders and pairs them up: best price first, and the earlier order first when prices are equal. It outputs trades.
2. **Order book view.** For any stock, the 5 best buy prices and 5 best sell prices with quantities, updating as orders arrive.
3. **Speed benchmark.** Fire millions of orders at the engine and publish how many it handles per second and how long each one takes.

**Realism**

4. **"Yesterday's market" mode.** Each stock is set up from the previous day's free NSE files: same previous close, tick size and circuit limits. Robot traders then place orders so the price follows yesterday's real path.
5. **Real-order test.** Feed NSE's sample of real orders through our engine and check that we produce the same trades and the same opening prices NSE did. This is the proof that the engine is correct.
6. **Robot traders.** Market makers, random traders and trend followers, each with virtual cash. We can also type in orders ourselves.
7. **Exchange rules.** Tick sizes, circuit limits, the opening auction, the closing auction, stop-loss and IOC orders.
8. **Delivery and intraday accounts.** Delivery needs full cash to buy and shares in hand to sell. Intraday gets leverage from the margin file, allows short selling, and is closed out automatically before the market closes.

**Showcase**

9. **Dashboard.** A depth ladder, a trade tape, and a replay speed control (real time, 10x, as fast as possible).
10. **Replay and recovery.** Every input is logged, so any session can be re-run and gives exactly the same result.

Items 1, 2, 3 and 5 make a complete first release.

## 6. Background knowledge the team needs

| Area | What to learn |
|---|---|
| Market microstructure | Bid, ask, spread, depth, maker versus taker, price-time priority, partial fills |
| Data levels | Top of book; price-level depth (our "L2"); order-by-order feeds. NSE's own names differ: its Level 2 is 5 deep and its Level 3 is 20 deep. |
| Order types | Limit, market, stop-loss (SL and SL-M), IOC versus Day, disclosed quantity, how modifying an order affects its place in the queue |
| Sessions | Pre-open call auction, continuous trading, closing auction, post-close |
| Price rules | Tick size, price bands, market-wide circuit breakers, price protection for market orders |
| Delivery (CNC) | Full funds to buy, shares in demat to sell, settlement the next working day (T+1) |
| Intraday (MIS) | Margin of VaR plus extreme loss margin (minimum 20%, so about 5x), short selling allowed, forced square-off |
| Securities | EQ series allows intraday. BE and BZ are trade-for-trade, delivery only. Lot size is 1. |
| Costs | Securities transaction tax of 0.1% on both sides for delivery and 0.025% on the sell side for intraday; stamp duty; exchange and SEBI fees; GST |

Delivery versus intraday is not an order book concept. Both kinds of order sit in the same book. The difference belongs in the account and risk layer.

## 7. Market rules to model

| Rule | Current state |
|---|---|
| Tick size | ₹0.01 below ₹250; ₹0.05 up to ₹1,000; ₹0.10 up to ₹5,000; ₹0.50 up to ₹10,000; ₹1.00 up to ₹20,000; ₹5.00 above. Reviewed monthly. |
| Price bands | Fixed 2, 5, 10 or 20% for stocks without derivatives. Stocks with derivatives get a 10% dynamic band that can move in steps after a cooling-off period. |
| Market-wide circuit breakers | Trading halts when Nifty or Sensex moves 10, 15 or 20%. |
| Pre-open (from 7 September 2026) | 9:00 to 9:15, order entry closing at a random moment between 9:08 and 9:10. The opening price is the one that matches the most quantity; ties go to the least unmatched quantity. |
| Closing auction (from 3 August 2026) | For stocks with derivatives, 3:15 to 3:35 PM according to broker bulletins. It replaces the old average-price close. |
| Self-trade prevention | The exchange cancels an order that would trade against the same client's resting order. |
| Market orders | Capped at a percentage away from the last traded price. |
| Stop-loss orders | Kept out of the book until the trigger price is reached. |

The closing auction timings come from broker summaries. Confirm them against NSE circular NSE/CMTR/73362 before coding them.

## 8. Performance design

- **Integers only.** Prices in paise, converted to a tick index. No floating point.
- **Flat array of price levels.** Circuit limits bound the day's price range, so it is small: a ₹1,400 stock with a ₹0.10 tick and ±20% limits has 5,600 levels. Adding, cancelling and looking up are constant time, with a bitmap to find the next non-empty level.
- **First-in-first-out queue at each price.** Orders live in a pre-allocated pool with 32-bit handles. No memory allocation while matching.
- **Order lookup by direct index.** We assign sequential order numbers, so no hash table is needed.
- **One writer.** One pinned thread per group of stocks, with lock-free queues in and out.
- **Deterministic and logged.** Every input is journalled. Replaying the journal rebuilds the exact state, which gives recovery and regression tests.
- **Binary fixed-size messages.** Modelled on NSE's own feed: new, modify, cancel and trade messages with order number, stock token, side, price and quantity.
- **Measure before optimising.** Report median, 99th and 99.9th percentile latency and messages per second. A sub-microsecond median per operation on one core is a goal to test against, not a promise.

## 9. Build order

1. **Specification.** Instrument fields, order types, validation rules, message formats.
2. **Matching engine.** Limit, market, IOC, cancel and modify, plus a simple slow version to check the fast one against.
3. **Benchmark harness.** A random order generator and latency reporting.
4. **Order book output.** Top-5 snapshots and a trade feed.
5. **NSE sample parser and real-order test.** Start with the opening auction, where the sample is complete.
6. **Daily data downloader.** Bhavcopy, price bands, margin file and securities list into `data/`.
7. **Robot traders and "yesterday's market" mode.**
8. **Exchange rules.** Bands, tick checks, stop-loss, auctions, self-trade prevention.
9. **Accounts.** Delivery and intraday rules, margin, square-off, charges, profit and loss.
10. **Dashboard, replay and recovery.**

## 10. Still to verify

- Whether Yahoo Finance serves one-minute bars for NSE stocks reliably (our test was rate-limited).
- Whether the free broker historical APIs work without any paid add-on.
- Exact closing auction timings, from the NSE circular.
- Column meanings in the VaR margin file.
- Whether the sample orders file is complete for the symbols it contains. Running the opening auction and comparing with that day's published opening prices will tell us.
- NSE's terms of use for the downloaded files, before sharing anything derived from them.

## 11. Sources

- [NSE historical data page with free samples](https://www.nseindia.com/static/market-data/eod-historical-data-subscription)
- [NSE historical order and trade specification v1.19](https://nsearchives.nseindia.com//web/mediaattachment/2026-09/NSE_Hist_Order_Trade_Data_1.19_20260902144045.pdf)
- [NSE tick-by-tick feed specification v6.6](https://nsearchives.nseindia.com//web/mediaattachment/2026-09/Realtime_CM_CD_TBT_ver_6.6.pdf)
- [NSE all reports page](https://www.nseindia.com/all-reports)
- [SEBI circular on sharing real-time price data (NSDL copy)](https://nsdl.co.in/downloadables/pdf/2024-0067-Policy-SEBI_Circular_on_Norms_for_sharing_of_real_time_price_data_to_third_parties.pdf)
- [NSE warning on dabba trading](https://www.businesstoday.in/markets/story/nse-warns-investors-against-illegal-dabba-trading-platform-tradeinn-files-police-complaint-543478-2026-07-16)
- [Closing auction and pre-open changes](https://zerodha.com/marketintel/bulletin/439989/introduction-of-closing-auction-session-cas-in-the-equity-cash-segment-and-certain-modifications-in-the-pre-open-auction-session)
- [Tick size revision](https://zerodha.com/marketintel/bulletin/408151/revision-in-tick-size-for-nse-derivatives-and-cash-segment-from-april-15-2025)
- [Dynamic price bands](https://fyers.in/notice-board/revised-dynamic-price-bands-and-fo-segment-rules/)
- [Self-trade prevention](https://support.zerodha.com/category/trading-and-markets/kite-web-and-mobile/articles/what-is-nse-self-trade-prevention-mechanism)
- [Securities transaction tax rates](https://rupeezy.in/blog/stt-charges-updated-rates-key-changes)
- [Angel One SmartAPI overview](https://uatcdn.angelone.in/knowledge-center/smartapi/detailed-introduction-to-smartapi)
- [Brokers with free APIs](https://www.goodreturns.in/partner-content/10-best-brokers-with-free-api-in-india-1525473.html)
