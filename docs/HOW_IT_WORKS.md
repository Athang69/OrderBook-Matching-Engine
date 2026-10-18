# How OrderBook Works — End to End

> A complete guide to every part of the system: what it does, how it does it, and why.
> Written so anyone can read it from scratch and explain it to a faculty audience.

---

## Table of contents

1. [What the project is](#1-what-the-project-is)
2. [The big picture](#2-the-big-picture)
3. [Layer 1 — The matching engine (C++)](#3-layer-1--the-matching-engine-c)
4. [Layer 2 — The backend (Python)](#4-layer-2--the-backend-python)
5. [Layer 3 — The frontend (React)](#5-layer-3--the-frontend-react)
6. [How a trade happens — the full flow](#6-how-a-trade-happens--the-full-flow)
7. [Live prices — how Yahoo Finance data reaches the screen](#7-live-prices--how-yahoo-finance-data-reaches-the-screen)
8. [The recommender systems](#8-the-recommender-systems)
9. ["Why did it move?" — the explanation engine](#9-why-did-it-move--the-explanation-engine)
10. [FinBERT — AI sentiment on headlines](#10-finbert--ai-sentiment-on-headlines)
11. [Candlestick pattern recognition](#11-candlestick-pattern-recognition)
12. [Chart CNN — reading price charts like a human](#12-chart-cnn--reading-price-charts-like-a-human)
13. [The LLM analysis — putting it all together](#13-the-llm-analysis--putting-it-all-together)
14. [The candlestick chart with zoom and pan](#14-the-candlestick-chart-with-zoom-and-pan)
15. [How everything connects — the master flow](#15-how-everything-connects--the-master-flow)
16. [References](#16-references)

---

## 1. What the project is

**OrderBook** is a paper-trading application for the Indian stock market (NSE).

- **Paper trading** means virtual money (₹10,00,000), real prices. No actual money is risked.
- It covers all **2,914 stocks** on the NSE's EQ and BE series.
- Prices are **live and real** — about 2 seconds behind the actual NSE, streamed from Yahoo Finance.
- The core is a **C++ matching engine** that simulates how the real exchange matches buyers and sellers.
- On top of that, the system explains **why a stock moved** on any day, using news sentiment analysis (FinBERT), candlestick pattern recognition, a CNN trained on chart images, and a large language model that writes the final analysis.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        What the user sees                          │
│                                                                    │
│   Live prices  ·  Candlestick charts  ·  Place orders  ·  P&L     │
│   News  ·  Recommendations  ·  "Why did it move?"  ·  AI analysis │
└──────────────────────────────────────────────────────────────────────┘
                              ▲
                              │  HTTP + WebSocket
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     Python backend (FastAPI)                        │
│                                                                    │
│   Orders · Risk · Accounts · Live feed · News · Recommendations    │
│   Explain · FinBERT · Candle patterns · Chart CNN · LLM analysis   │
└───────────────────────┬──────────────────────────────────────────────┘
                        │  stdin/stdout pipe
                        ▼
              ┌───────────────────────┐
              │  C++ matching engine  │
              │  Price-time priority  │
              │  ~5 million ops/sec   │
              └───────────────────────┘
```

---

## 2. The big picture

There are three layers. Each layer does one job and talks to the next through a clean interface.

### Layer 1 — C++ matching engine
The exchange simulator. It maintains an **order book** for every stock: all the buy orders and sell orders waiting to be matched. When a new order arrives, it matches it against the best available price on the other side. This is exactly how the real NSE works — **price-time priority**: the best price always gets filled first, and among equal prices, the order that came first wins.

### Layer 2 — Python backend
The brain. It handles:
- Fetching **live prices** from Yahoo Finance (WebSocket stream + polling)
- Managing the **user's account** (cash, holdings, charges)
- Running **risk checks** before every order
- Placing **market orders** in the engine that simulate real NSE trades
- Gathering **news** and building explanations for why stocks moved
- Running **FinBERT** (sentiment AI), **candlestick pattern detection**, and the **chart CNN**
- Calling a **large language model** to write the final analysis

### Layer 3 — React frontend
The face. A single-page app that looks like a brokerage platform:
- Live-updating candlestick charts with zoom and pan
- Order placement (buy/sell, limit/market)
- Portfolio and P&L tracking
- Stock recommendations
- The "Why did it move?" section with all the AI analysis

---

## 3. Layer 1 — The matching engine (C++)

### What is an order book?

An order book is a list of all the buy orders (bids) and sell orders (asks) waiting for a stock. It looks like this:

```
        BIDS (buyers)                    ASKS (sellers)
   Price     Qty    Orders          Price     Qty    Orders
   ₹725.00   500   3 orders        ₹725.50   200   1 order
   ₹724.50   800   5 orders        ₹726.00   350   2 orders
   ₹724.00   150   1 order         ₹727.00   1000  4 orders
```

The **best bid** (highest buy price) and **best ask** (lowest sell price) are at the top. The gap between them is called the **spread**.

### How matching works — price-time priority

When a new buy order arrives at ₹726.00:

1. Check the asks: is there a sell order at ₹726.00 or lower? **Yes** — there's one at ₹725.50.
2. Match against that order: the buyer gets the stock at ₹725.50 (the seller's price — better for the buyer).
3. If the buy order still has quantity left, check the next ask (₹726.00). Match again.
4. If there are no more asks at ₹726.00 or below, the remaining quantity becomes a resting bid at ₹726.00.

**Time priority**: if two sellers offer the same price, the one who placed the order first gets matched first. This is fair — first come, first served.

### The data structure

```
┌────────────────────────────────────────────────┐
│                  Order Book                     │
│                                                │
│  Price band: ₹690 to ₹760 (from NSE files)     │
│                                                │
│  ┌──────────────────────────────────────────┐  │
│  │  Flat array: one slot per tick price      │  │
│  │  Index 0 = ₹690.00                       │  │
│  │  Index 1 = ₹690.05  (tick = ₹0.05)       │  │
│  │  ...                                     │  │
│  │  Index 1400 = ₹760.00                    │  │
│  │                                          │  │
│  │  Each slot holds a FIFO queue of orders  │  │
│  └──────────────────────────────────────────┘  │
│                                                │
│  Hash map: order ID → pointer (for cancels)    │
│  Node pool: pre-allocated memory (no malloc)   │
└────────────────────────────────────────────────┘
```

**Why a flat array?** Because NSE stocks have a fixed price band (usually ±5% or ±20% of the previous close) and a fixed tick size (₹0.05 for most stocks). So we know every possible price in advance. Looking up a price level is O(1) — just an array index. No trees, no searching.

**Why a node pool?** Creating and destroying objects on the heap (malloc/free) is slow. Instead, we pre-allocate a block of memory and reuse nodes from it. This is how real exchanges do it.

**Performance**: ~5 million operations per second, median latency ~130 nanoseconds per operation. That's fast enough that order matching never slows the app down.

### The text protocol

The engine runs as a separate process. The backend talks to it through stdin/stdout:

```
Backend sends:    ADD BUY RELIANCE 120000 100 order_42
Engine replies:   FILL order_42 120000 50 sell_order_17
                  FILL order_42 120000 50 sell_order_23
                  RESTING order_42 0
```

Commands: `ADD` (new order), `CANCEL` (cancel by ID), `RESET` (clear a book for a new day), `SYMBOL` (register a new stock with its price band and tick).

---

## 4. Layer 2 — The backend (Python)

### FastAPI

The backend is a Python web server using **FastAPI**. It serves both the REST API and the static frontend files on `http://localhost:8000`.

Key modules:

| Module | What it does |
|--------|-------------|
| `exchange.py` | Order management: validates, sends to engine, tracks fills |
| `risk.py` | Pre-trade checks: do you have enough money? Is the price in band? |
| `accounts.py` | Cash, holdings, intraday positions, charges |
| `charges.py` | Calculates brokerage, STT, exchange fees, stamp duty, GST |
| `yahoo.py` | Fetches live quotes, charts, and streams from Yahoo Finance |
| `market_data.py` | Maintains the live state of each followed stock |
| `instruments.py` | Loads every NSE stock's rules from daily files |
| `session.py` | Knows if the market is open, closed, or in pre-open |
| `news.py` | Fetches headlines from Google News RSS |
| `explain.py` | Builds the "why did it move?" evidence pack |
| `finbert.py` | FinBERT sentiment scoring on headlines |
| `candles.py` | Candlestick pattern detection |
| `chart_cnn.py` | Chart CNN predictions |
| `analysis.py` | Calls the LLM to write the final analysis |

### How paper trading works against the real market

The system doesn't invent fake prices. It uses **real trades** from the NSE (via Yahoo Finance) to fill the user's orders:

```
  Real NSE trade:  RELIANCE sold at ₹1,215.30, volume 500 shares
                            │
                            ▼
  Backend sees the trade via Yahoo's live stream
                            │
                            ▼
  Backend places a SELL order at ₹1,215.30 for 500 shares
  into the C++ engine, representing the real market
                            │
                            ▼
  If the user has a BUY order at ₹1,215.30 or higher,
  the engine matches them → the user gets filled
                            │
                            ▼
  The fill updates the user's holdings, cash, and P&L
```

This means:
- The user can only buy at prices where real trades actually happened
- Volume matters — if only 100 shares traded, the user can't buy 10,000
- The matching follows real exchange rules (price-time priority)

### Money is in paise

All money in the system is stored as **integers in paise** (1/100th of a rupee). ₹1,215.30 is stored as `121530`. This avoids floating-point rounding errors that would make the P&L wrong.

---

## 5. Layer 3 — The frontend (React)

The frontend is a single-page React + TypeScript app built with Vite. It has these sections:

```
┌─────────────────────────────────────────────────────────────┐
│  Top bar: search any stock · market status · indices strip  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Quote header: stock name, live price, change               │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Candlestick chart (1D/5D/1M/6M/1Y/5Y)               │  │
│  │  Toggle: candle ↔ line  ·  scroll zoom  ·  drag pan   │  │
│  │  Volume bars at bottom  ·  previous close baseline     │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  Key stats · Order book (best bid/ask) · Movers             │
│                                                             │
│  Order ticket: BUY/SELL, LIMIT/MARKET, CNC/MIS              │
│  Account: cash, holdings, intraday positions, P&L           │
│                                                             │
│  News panel: latest headlines for the stock                 │
│  Recommendations: delivery (Markowitz) + intraday (signals) │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  "Why did it move?" section                           │  │
│  │                                                       │  │
│  │  AI analysis card (LLM verdict + drivers + citations) │  │
│  │  Chart model card (CNN image + candle patterns)       │  │
│  │  Market facts (NIFTY, sectors, peers, world markets)  │  │
│  │  Evidence: all headlines with FinBERT sentiment badges │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Live updates

The frontend opens a **WebSocket** to the backend. Every 250ms, the backend pushes the latest prices for the stocks the user is looking at. The charts, prices, and order book update in real time without the user refreshing.

---

## 6. How a trade happens — the full flow

Here is exactly what happens when the user clicks "BUY 100 shares of RELIANCE at market price":

```
Step 1: Frontend sends POST /v1/orders
        { symbol: "RELIANCE", side: "BUY", type: "MARKET", product: "CNC", qty: 100 }
                │
                ▼
Step 2: Backend validates
        ✓ Is the market open?
        ✓ Does RELIANCE exist in the instrument list?
        ✓ Is the quantity valid (> 0, whole number)?
                │
                ▼
Step 3: Risk check (risk.py)
        ✓ CNC (delivery): does the user have enough cash?
          Cash needed = 100 × best ask price + estimated charges
        ✓ Block that cash so it can't be used twice
                │
                ▼
Step 4: Send to the C++ engine
        Backend writes: "ADD BUY RELIANCE 0 100 order_42"
        (price 0 = market order: match at any price)
                │
                ▼
Step 5: Engine matches
        Finds the best available sell orders and matches them.
        Replies with FILL messages: price, quantity, counterparty.
                │
                ▼
Step 6: Backend processes fills
        - Updates the order status (FILLED, avg price)
        - Adds shares to the user's holdings
        - Deducts cash (exact fill price × quantity)
        - Calculates and deducts charges (STT, brokerage, etc.)
        - Logs the trade to the audit file
                │
                ▼
Step 7: Frontend updates
        The WebSocket pushes the new portfolio state.
        The user sees: order filled, shares in holdings, cash reduced.
```

**Charges** follow the real NSE/SEBI schedule:
- **STT** (Securities Transaction Tax): 0.1% on buy delivery
- **Exchange transaction charge**: 0.00345%
- **SEBI fee**: ₹10 per crore
- **Stamp duty**: 0.015% on buy
- **GST**: 18% on brokerage + exchange charge
- **Brokerage**: ₹0 (we simulate a discount broker)

---

## 7. Live prices — how Yahoo Finance data reaches the screen

```
Yahoo Finance                    Backend                      Browser
─────────────                    ───────                      ───────

  WebSocket stream ──────────►  YahooStream class
  (protobuf messages,            │ decodes each tick
   ~10 per second)               │ updates MarketData
                                 │         │
  REST API (quotes) ◄────────── poll every 5s
  (bid, ask, volume,             │ for each followed stock
   52-week high/low)             │ merges into MarketData
                                 │         │
  REST API (chart) ◄──────────  on demand (user opens a stock
  (OHLCV bars for                │ or changes the chart range)
   1D/5D/1M/6M/1Y/5Y)           │
                                 │
                                 ▼
                              MarketData ──────► WebSocket push
                              (one object         every 250ms
                               per stock)         to the browser
                                                      │
                                                      ▼
                                               React components
                                               re-render with
                                               new prices
```

### The ticker mapping

Yahoo Finance uses tickers like `RELIANCE.NS` for NSE stocks. The backend maps between NSE symbols (`RELIANCE`) and Yahoo tickers (`RELIANCE.NS`), handling edge cases where the Yahoo ticker doesn't follow the simple `.NS` pattern.

### Why two data sources?

- The **WebSocket stream** gives the latest trade price instantly — as fast as Yahoo gets it from the exchange (about 2 seconds behind NSE).
- The **REST poll** gives the full quote: bid, ask, day high/low, volume, 52-week range. This data doesn't come through the stream.

Together, they give a complete and current picture of each stock.

---

## 8. The recommender systems

### Delivery recommendation — Markowitz portfolio optimisation

This answers: "Given these stocks and my views, how should I allocate my money for delivery (holding) trades?"

The method:

```
Step 1: Download 1 year of daily prices for each stock (yfinance, cached)

Step 2: Calculate expected returns and the covariance matrix
        (how much each stock moves, and how they move together)

Step 3: The user's confidence (0–100 per stock, 50 = no view)
        shifts the expected return up or down for each stock

Step 4: Monte Carlo simulation: generate 10,000 random portfolios
        Each portfolio is a random allocation of money across the stocks

Step 5: Find the efficient frontier — the set of portfolios where
        you can't get more return without more risk

Step 6: SLSQP optimisation: find the portfolio on the frontier
        with the best Sharpe ratio (return per unit of risk)

Step 7: Resample 50 times (bootstrap the history) to get a
        robust allocation that doesn't overfit to one history path
```

```
Expected return
     ▲
     │            ★ Optimal (max Sharpe ratio)
     │           ╱
     │         ╱   Efficient frontier
     │       ╱
     │     ╱
     │   · · ·  10,000 random portfolios
     │ · · · · ·
     │· · · · · ·
     └──────────────────────► Risk (volatility)
```

The user's views matter: if you're 80% confident in RELIANCE (bullish), the optimiser tilts the portfolio toward RELIANCE. If you're 20% confident (bearish), it tilts away.

### Intraday recommendation — live signals

This answers: "Should I buy or sell this stock right now for an intraday trade?"

Three real-time signals, each between −1 (strong sell) and +1 (strong buy):

| Signal | What it measures | How |
|--------|-----------------|-----|
| **Momentum** | Is the price accelerating up or down? | Compare the price now to the price N seconds ago, normalised by volatility |
| **VWAP** | Is the price above or below fair value? | VWAP = total money traded ÷ total volume. Price above VWAP → buyers are aggressive |
| **Flow** | Are more shares being bought or sold? | Track whether each trade was a buy or sell (tick test), accumulate the net flow |

The final score blends these three signals (60%) with the user's view (40%). A score above a threshold → BUY; below → SELL; in between → WAIT.

---

## 9. "Why did it move?" — the explanation engine

This is the centrepiece of the project. When the user asks "Why did RELIANCE fall 3% on 15 Oct?", the system builds a **complete evidence pack** from scratch:

```
┌────────────────────────────────────────────────────────────────────┐
│                    The explanation pipeline                        │
│                                                                   │
│  1. PRICE DATA                                                    │
│     Download 1 year of daily prices for the stock, NIFTY 50,      │
│     the sector index, and similar companies (from Yahoo Finance)   │
│                                                                   │
│  2. MARKET MODEL (event study methodology)                         │
│     Split the stock's move into two parts:                        │
│     ┌──────────────────────────────────────────────────────┐      │
│     │  Total move = Market part + Stock's own part          │      │
│     │                                                      │      │
│     │  Market part = β × NIFTY 50's move that day           │      │
│     │  (β is from a regression of the stock's daily         │      │
│     │   returns against NIFTY 50's, over the past year)     │      │
│     │                                                      │      │
│     │  Stock's own part = Total − Market part               │      │
│     │  Compare with a typical day: was this unusual?        │      │
│     └──────────────────────────────────────────────────────┘      │
│                                                                   │
│  3. SIMILAR COMPANIES                                             │
│     Yahoo's "similar stocks" list, filtered to the same sector.   │
│     Did they move the same way? If yes → industry-wide move.      │
│                                                                   │
│  4. NEWS HEADLINES (Google News RSS)                               │
│     Search at five levels:                                        │
│     • About the company itself                                    │
│     • About similar companies                                     │
│     • About its industry                                          │
│     • About the Indian market (Sensex, Nifty)                     │
│     • About world markets (US, Asia, oil, gold, geopolitics)      │
│                                                                   │
│     Each headline is tagged with:                                 │
│     • Scope: company / peers / industry / market / global         │
│     • FinBERT sentiment: positive / negative / neutral + score    │
│     • Cause tags: earnings, broker rating, rate cut, oil, etc.    │
│                                                                   │
│  5. CANDLESTICK PATTERNS                                          │
│     Rule-based detection on the day's OHLC bars                   │
│                                                                   │
│  6. CHART CNN                                                     │
│     20-day chart image → CNN → P(up next 5 days)                  │
│                                                                   │
│  7. VERDICT                                                       │
│     All evidence is scored and ranked. The system writes a         │
│     rule-based first reading: "Market-wide move" / "Industry-     │
│     wide" / "Company-specific" / "Ordinary day"                   │
│                                                                   │
│  8. LLM ANALYSIS                                                  │
│     Everything above + Indian and world market data is given       │
│     to a large language model, which writes a cited analysis.      │
└────────────────────────────────────────────────────────────────────┘
```

### The beta and market model

**Beta (β)** measures how sensitive a stock is to the overall market.

- β = 1.0: the stock moves exactly with the market
- β = 1.5: the stock moves 50% more than the market (more volatile)
- β = 0.5: the stock moves half as much as the market (defensive)

The calculation uses **OLS regression** (ordinary least squares):

```
For each trading day over the past year:
    stock_return[day] = α + β × market_return[day] + ε[day]

Where:
    stock_return  = (close_today − close_yesterday) / close_yesterday
    market_return = same, for NIFTY 50
    β             = covariance(stock, market) / variance(market)
    ε             = the stock's own move (the residual)
```

If NIFTY 50 fell 1% and RELIANCE has β = 1.3, then the market explains 1.3% of RELIANCE's fall. If RELIANCE actually fell 3%, the stock's own part is 1.7%. That's the part the news needs to explain.

---

## 10. FinBERT — AI sentiment on headlines

### What is FinBERT?

**FinBERT** is a version of Google's BERT language model that was fine-tuned specifically on financial text (Araci, 2019). BERT itself is a "transformer" — the same architecture behind ChatGPT, but much smaller (110 million parameters vs hundreds of billions).

### How BERT works (simplified)

```
Input:    "HDFC Bank Q2 profit rises 25% on strong loan growth"
              │
              ▼
         Tokenizer: splits into subword tokens
         ["HDFC", "Bank", "Q2", "profit", "rises", "25", "%", "on", "strong", ...]
              │
              ▼
         12 transformer layers: each token attends to every other token
         The model learns which words matter for sentiment
         ("rises" + "profit" + "strong" → positive)
              │
              ▼
         Classification head: three outputs
         P(positive) = 0.92    ← the model is 92% sure this is positive
         P(negative) = 0.02
         P(neutral)  = 0.06
              │
              ▼
         Score = P(positive) − P(negative) = 0.90
         Label = "positive"
```

### Why FinBERT, not just positive/negative word lists?

A word list would say "falls" is negative. But:

> "HDFC Bank **falls** less than peers amid sector selloff"

This is actually **positive** (relative strength). FinBERT understands this because it reads the whole sentence, not individual words. It was trained on 50,000 financial sentences from analyst reports, earnings calls, and financial news.

### How we use it

```python
# In backend/app/finbert.py

# 1. Model loads once at server start (in a background thread, ~10 seconds)
warm()  # starts loading ProsusAI/finbert from Hugging Face cache

# 2. When a stock's explanation is built, all headlines are scored in one batch
sentiments = score_headlines(["HDFC Bank profit rises 25%", "Nifty falls 200 points", ...])

# 3. Each headline gets:
#    - label: "positive" / "negative" / "neutral"
#    - pos, neg, neu: the three probabilities
#    - score: P(pos) − P(neg), from −1 to +1

# 4. The FinBERT score REPLACES the old keyword-based tone
#    This means headline ranking now uses AI, not word lists

# 5. Sentiment totals per scope are calculated:
#    "Company headlines: avg score +0.14, 46 headlines, 14 positive, 7 negative, 25 neutral"
```

**Batching**: all headlines are scored in one forward pass through the model. This is much faster than scoring them one by one because the GPU (or CPU) can process them in parallel.

**Caching**: each headline title is cached so the same headline is never scored twice in a session.

---

## 11. Candlestick pattern recognition

### What is a candlestick?

A candlestick shows four prices for one time period:

```
         │          High (the highest price traded)
         │
    ┌────┤          Close (if close > open, the candle is green/hollow)
    │    │
    │    │          The "body" shows the range between open and close
    │    │
    ├────┘          Open
    │
    │               Low (the lowest price traded)

    Green/hollow    Red/filled
    (close > open)  (close < open)
    = UP day        = DOWN day
```

The thin lines above and below the body are called **wicks** or **shadows**. They show how far the price went before coming back.

### The patterns we detect

We detect **17 patterns** from the last 1–3 days of trading data. Each pattern has a historical up-rate from published research on Indian equities:

**Single-candle patterns:**

```
Doji               Hammer           Shooting Star       Marubozu
   │                  │                  │
  ─┼─              ┌──┤               ├──┐              ┌────┐
   │               │  │               │  │              │    │
   │               │  │               │  │              │    │
                   │  │               ├──┘              │    │
                   ├──┘                  │              └────┘
                      │                  │
                      │                                All body,
Tiny body,        Long lower        Long upper         no wicks.
indecision.       shadow after      shadow after       Strong
                  a downtrend.      an uptrend.        conviction.
50% up rate       60% up rate       39% up rate        60%/40%
```

**Two-candle patterns:**

```
Bullish Engulfing         Bearish Engulfing
                         
   ┌──┐  ┌────┐            ┌────┐  ┌──┐
   │░░│  │    │            │    │  │░░│
   │░░│  │    │            │    │  │░░│
   └──┘  │    │            │    │  │░░│
         └────┘            └────┘  └──┘

Green candle               Red candle
completely wraps           completely wraps
the previous               the previous
red candle.                green candle.
63% up rate                37% up rate
```

**Three-candle patterns:**

```
Morning Star              Three White Soldiers
                         
┌──┐        ┌────┐        ┌──┐
│░░│  ─┼─   │    │        │  │ ┌──┐
│░░│        │    │        │  │ │  │ ┌──┐
└──┘        │    │        └──┘ │  │ │  │
            └────┘             └──┘ │  │
                                    └──┘
Big red, tiny body,       Three consecutive
big green = reversal      green candles = strong
at the bottom.            sustained buying.
65% up rate               68% up rate
```

### How detection works

```python
# In backend/app/candles.py

# 1. Get the trend from the previous 5–10 closes
trend = trend(context_closes)  # "up", "down", or "flat"

# 2. Check each pattern's rules on the latest bars
#    Example: Hammer detection
def _hammer(open, high, low, close, range, trend):
    body = abs(close - open)
    lower_shadow = min(open, close) - low
    upper_shadow = high - max(open, close)
    return (
        trend == "down" and           # Must be in a downtrend
        lower_shadow >= 2 * body and  # Lower shadow at least 2× the body
        upper_shadow <= 0.3 * body    # Almost no upper shadow
    )

# 3. Return all patterns found with their historical stats
# [{"name": "Hammer", "bias": "bullish", "up_rate": 0.60,
#   "note": "Buyers stepped in after a fall; possible reversal upward."}]
```

**Trend context matters**: a hammer after a downtrend is bullish (reversal signal), but the same shape after an uptrend is a "hanging man" (bearish). The detector uses the previous 5–10 closes to determine the trend before applying pattern rules.

---

## 12. Chart CNN — reading price charts like a human

This is based on the paper **"(Re-)Imag(in)ing Price Trends"** by Jiang, Kelly & Xiu, published in the *Journal of Finance* (2023). The idea: **if a human trader can look at a chart and predict direction, a CNN should be able to learn the same visual patterns.**

### The image

Each 20-trading-day window is rendered as a **64×60 pixel black-and-white image**:

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  60 pixels wide = 20 days × 3 pixels per day                │
│                                                              │
│  For each day (3 columns):                                   │
│    Column 1: open price tick mark                            │
│    Column 2: high-to-low vertical bar (the wick)             │
│    Column 3: close price tick mark                           │
│                                                              │
│  A 20-day moving average line connects through the candles   │
│                                                              │
│  ├────────────────────── 54 px for price ──────────────────┤ │
│  │                                                          │ │
│  │   ·  │  ·    ·│ ·     · │·       ·│ ·                   │ │
│  │   · ·│· ·   · │· ·   ·  │ ·    ·  │· ·  ← candles      │ │
│  │    · │ ·     · │ ·     · │  ·  ·   │ ·                  │ │
│  │      │        ·│·        │   ··    │                     │ │
│  │                                                          │ │
│  ├────────────────────── 10 px for volume ─────────────────┤ │
│  │  ███ ██ █████ ███ ██████ ████ ██ ████                   │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                              │
│  64 pixels tall                                              │
└──────────────────────────────────────────────────────────────┘
```

**Why black and white?** The paper shows that colour adds no predictive value. The CNN learns from the **shape** of the chart — the arrangement of candles relative to each other and the moving average — not from colours.

### The label

For each image, the label is binary:
- **1 (up)**: the stock's close price 5 trading days after the image ends is higher than the close on the last day of the image
- **0 (down/flat)**: it's lower or equal

### The CNN architecture

```
Input: 64×60×1 grayscale image
           │
           ▼
┌─────────────────────────────┐
│  Conv Block 1               │
│  32 filters, kernel 5×3     │  ← detects small patterns (individual candles)
│  BatchNorm → LeakyReLU      │
│  MaxPool(2,1) → Dropout     │
│  Output: 32×60×32           │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  Conv Block 2               │
│  64 filters, kernel 5×3     │  ← detects medium patterns (2-3 candle combos)
│  BatchNorm → LeakyReLU      │
│  MaxPool(2,1) → Dropout     │
│  Output: 16×60×64           │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  Conv Block 3               │
│  128 filters, kernel 5×3    │  ← detects large patterns (trends, support/resistance)
│  BatchNorm → LeakyReLU      │
│  MaxPool(2,1) → Dropout     │
│  Output: 8×60×128           │
└─────────────┬───────────────┘
              │
              ▼
         Flatten (61,440)
              │
              ▼
┌─────────────────────────────┐
│  Dense 64 → LeakyReLU       │
│  Dropout 50%                │
│  Dense 2 (up / down)        │
│  Softmax → P(up), P(down)   │
└─────────────────────────────┘
              │
              ▼
         Output: P(up next 5 days) = 0.63
```

### Why kernel 5×3?

- **5 pixels tall**: spans enough of the price range to see candle bodies and wicks
- **3 pixels wide**: spans exactly one trading day (3 columns per day), so the first layer learns to recognise individual candlestick shapes

The **MaxPool(2,1)** pools only vertically (halving height, keeping width). This preserves the time axis — the model shouldn't blur together Monday and Wednesday.

### Training

```
Data:     ~200 most liquid NSE stocks, daily data from 2017 to present
          Downloaded via yfinance, auto-adjusted for splits and dividends

Samples:  One image every 5 trading days per stock (~76,000 total)
          Stored as uint8 (1 byte per pixel) to fit in RAM

Split:    Train: before July 2024
          Validation: July 2024 to July 2025
          Test: after July 2025
          (Time split — no future data leaks into training)

Training: Adam optimiser, learning rate 0.001
          Cross-entropy loss, batch size 64
          Early stopping on validation loss (patience = 2 epochs)

Expected: Accuracy 52–56% (against a ~50% baseline)
          This is typical for this kind of model.
          It's not a crystal ball — it's a weak signal that adds to the evidence.
```

### Honest about accuracy

The UI always shows:
- The model's test accuracy
- The majority-class baseline (what you'd get by always guessing "up" or "down")
- A note: "Not a trading signal"

We never inflate the numbers. About 53% accuracy is genuine for price prediction — even 1–2% above baseline is statistically meaningful with enough samples.

### The tiny PNG writer

Since Pillow is not installed, we write PNG files manually using Python's `struct` and `zlib`:

```python
def image_to_png(img):  # img is a 64×60 numpy uint8 array
    # PNG file = magic bytes + IHDR chunk + IDAT chunk + IEND chunk
    # IHDR: width, height, bit depth (8), colour type (0 = grayscale)
    # IDAT: zlib-compressed rows, each prefixed with a filter byte (0 = none)
    # IEND: empty
    # Total: about 300 bytes for a 64×60 grayscale image
```

This produces valid PNG files that any browser can display, without needing any image library.

---

## 13. The LLM analysis — putting it all together

### The prompt

All the evidence is packed into a single text prompt:

```
STOCK: RELIANCE (Reliance Industries Ltd), listed on NSE.
Sector: Energy / Oil & Gas Refining & Marketing.
Business: [one-paragraph summary from Yahoo]

DAY TO EXPLAIN: Wednesday 15 October 2026.
Move: −3.12%, from ₹1,245.30 to ₹1,206.45.
Beta: 1.14. Market part: −0.57%. Stock's own move: −2.55%.
Typical daily own move: 1.02% (this was 2.5 times a typical day).

SIMILAR COMPANIES: BPCL −2.8%, HPCL −3.1%, IOC −1.9%
SECTOR INDEX: NIFTY ENERGY −1.8%

INDIAN MARKET: NIFTY 50 −0.50%, SENSEX −0.48%, NIFTY BANK +0.12%, ...
WORLD MARKETS: Brent crude −4.2%, US S&P 500 −0.3%, ...

CANDLESTICK PATTERNS:
  15 Oct: Bearish engulfing (bearish) — historical up rate 37%
  14 Oct: Doji (neutral) — historical up rate 50%

CHART CNN:
  Chart ending 15 Oct: P(up next 5 days) = 38%  (test accuracy 54%, baseline 51%)
  Chart ending 14 Oct: P(up next 5 days) = 52%  → chart turned more bearish

HEADLINES (numbered, with FinBERT sentiment):
[1] (about the company) 15 Oct 14:30 | Reliance Q2 earnings miss estimates [FinBERT: negative, score −0.91] | ET
[2] (about the company) 15 Oct 11:00 | Jio tariff hike boosts ARPU outlook [FinBERT: positive, score +0.85] | Mint
[3] (about its industry) 15 Oct 09:15 | Brent crude crashes 4% on OPEC+ output surge [FinBERT: negative, score −0.88]
...
[43] (about world markets) 15 Oct 23:00 | US inflation data spooks global markets [FinBERT: negative, score −0.72]

Explain why RELIANCE moved −3.12% on 15 October 2026. Include a technical_view.
Reply with JSON only.
```

### The model

We use **free models on OpenRouter** (never Claude — to save credits):
1. `nvidia/nemotron-3-ultra-550b` (first choice)
2. `google/gemma-4-31b-it` (fallback)
3. `nvidia/nemotron-3-super-120b` (second fallback)

OpenRouter routes to whichever model is available. Typical response time: 30–50 seconds.

### The response

The model returns structured JSON:

```json
{
  "headline": "Reliance fell 3.1% as Q2 earnings missed estimates and a 4% crash in Brent crude hit refining margins, compounding a sector-wide sell-off in oil & gas stocks.",
  "verdict": "Mixed",
  "drivers": [
    {
      "title": "Q2 earnings miss",
      "explanation": "Reliance's quarterly results fell short of analyst expectations [1], triggering selling. The stock's own move of −2.55% was 2.5 times a typical day, confirming this was a company-specific event beyond the market's −0.50% drag.",
      "impact": "major",
      "direction": "negative",
      "evidence": [1]
    },
    {
      "title": "Crude oil crash",
      "explanation": "Brent crude fell 4.2% on OPEC+ output surge [3], directly hitting Reliance's refining margins. Peers BPCL (−2.8%), HPCL (−3.1%) and IOC (−1.9%) fell in tandem.",
      "impact": "moderate",
      "direction": "negative",
      "evidence": [3]
    }
  ],
  "market_context": "The broader market was nearly flat (NIFTY −0.50%) ...",
  "stock_specific": "The earnings miss was the dominant factor ...",
  "technical_view": "The bearish engulfing pattern (37% historical up rate) following a Doji signals a trend reversal. The chart CNN's probability of a 5-day rise dropped from 52% to 38%, confirming the shift in momentum.",
  "confidence": "high",
  "confidence_reason": "The earnings miss headline directly explains the outsized own move, and crude oil's crash explains the industry component.",
  "watch": ["Q2 earnings call commentary on Jio and retail", "OPEC+ next meeting date", "Brent crude support at $70"]
}
```

Every claim cites a headline number `[1]`, `[3]`. The user can click on these citations to jump to the source headline.

---

## 14. The candlestick chart with zoom and pan

The main price chart renders **real candlesticks** on all timeframes (1D minute bars, 5D, 1M, 6M, 1Y, 5Y) using inline SVG:

### Features

- **Toggle**: switch between candlestick and line chart with one click
- **Scroll wheel zoom**: zoom in to see fewer bars in detail, zoom out to see the full range. The zoom anchors at the mouse position (like Google Maps).
- **Drag to pan**: when zoomed in, click and drag to scroll through time
- **Volume bars**: at the bottom of the chart, proportional to the day's volume, coloured by the candle direction
- **Crosshair**: horizontal and vertical lines follow the mouse
- **Previous close baseline**: dashed line on 1D showing yesterday's close
- **Price tags**: the current price and previous close shown as labels on the Y axis
- **Tooltip**: shows O/H/L/C and volume on hover

### How zoom works

```
State:  visibleEnd   = index of the rightmost bar shown
        visibleCount = how many bars are visible

Zoom in (scroll up):
        visibleCount × 0.87  (show ~13% fewer bars)
        Anchor: the bar under the mouse stays in place

Zoom out (scroll down):
        visibleCount × 1.15  (show ~15% more bars)
        Capped at the total number of bars

Pan (drag):
        dx pixels of mouse movement
        → shift = dx × (visibleCount / chartWidth) bars
        → visibleEnd += shift

Reset:  visibleCount = null → show all bars
```

The chart slices `bars[vStart..vEnd]` and recalculates geometry only for the visible window. This keeps rendering fast even with thousands of bars.

---

## 15. How everything connects — the master flow

Here is the complete flow when a user opens a stock and clicks "Why did it fall?":

```
USER clicks "Why down 3.12%?" on RELIANCE
        │
        ▼
FRONTEND calls GET /v1/explain/RELIANCE?date=2026-10-15
        │
        ▼
BACKEND (explain.py) — the fast endpoint, ~3 seconds:
        │
        ├── Download 1 year of daily bars for RELIANCE, NIFTY 50,
        │   sector index, and 5 similar companies (Yahoo Finance, parallel)
        │
        ├── Calculate beta, market part, stock's own part, typical move
        │
        ├── Search Google News at 5 levels (company, peers, industry,
        │   market, global) — parallel
        │
        ├── Score ALL headlines with FinBERT (one batched forward pass)
        │   Replace keyword tones with AI sentiment scores
        │
        ├── Detect candlestick patterns on the explained day and day before
        │   (from daily OHLC data, with trend context)
        │
        ├── Run the Chart CNN: render 20-day chart image → P(up next 5 days)
        │   (for both the explained day and the day before)
        │
        ├── Rank headlines by scope, sentiment, and cause tags
        │   Build the rule-based verdict
        │
        └── Return the evidence pack (JSON):
            prices, beta, model, peers, sector, headlines with FinBERT,
            sentiment totals, candle patterns, CNN predictions, OHLC bars
        │
        ▼
FRONTEND renders immediately:
        • Stat cards (change, market, beta, own move)
        • Chart model card (CNN image + patterns)
        • Candlestick chart of recent days
        • Headlines with FinBERT sentiment badges
        • Quick reading (rule-based verdict)
        │
        ▼
FRONTEND calls GET /v1/analysis/RELIANCE?date=2026-10-15
        │
        ▼
BACKEND (analysis.py) — the slow endpoint, ~30–60 seconds:
        │
        ├── Reuse the explanation from above (cached)
        │
        ├── Fetch Indian indices + world markets for that day (parallel)
        │
        ├── Build the LLM prompt: all evidence + FinBERT labels
        │   on each headline + patterns + CNN + Indian/world markets
        │
        ├── Call OpenRouter (free LLM) with the prompt
        │   Wait for the model to write its analysis (~30 seconds)
        │
        └── Parse the JSON response, cache for 30 minutes
        │
        ▼
FRONTEND renders the AI analysis:
        • Headline verdict with citations [1] [3]
        • Driver cards with impact and direction
        • Technical view (patterns + CNN interpretation)
        • Market context, stock-specific, confidence, what to watch
        • Clickable citation numbers that scroll to the source headline
```

---

## 16. References

1. MacKinlay, A. C. (1997). Event studies in economics and finance. *Journal of Economic Literature*, 35(1), 13–39. — The market model (beta decomposition) used to split a stock's move into market and own parts.

2. Araci, D. (2019). FinBERT: Financial Sentiment Analysis with Pre-trained Language Models. *arXiv:1908.10063*. — The FinBERT model we use for headline sentiment scoring.

3. Devlin, J., Chang, M.-W., Lee, K., & Toutanova, K. (2019). BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding. *NAACL-HLT*. — The BERT architecture that FinBERT is built on.

4. Jiang, J., Kelly, B., & Xiu, D. (2023). (Re-)Imag(in)ing Price Trends. *Journal of Finance*, 78(6), 3193–3249. — The chart CNN method: rendering price data as images and training a CNN to predict returns.

5. Markowitz, H. (1952). Portfolio Selection. *Journal of Finance*, 7(1), 77–91. — Mean-variance portfolio optimisation, the foundation of the delivery recommender.

6. Nison, S. (1991). *Japanese Candlestick Charting Techniques*. — The candlestick patterns and their interpretation.

7. Patel, M. (2014). Technical Analysis and Candlestick Patterns of Indian Stock Market. *International Journal of Research*, 1(7). — Historical up-rates for candlestick patterns on Indian equities.

8. Thomas, T. C., & Vishwanathan, K. G. (2016). Candlestick Charting: An Empirical Analysis of Indian Stock Market. *Indian Journal of Finance*, 10(3). — Further evidence on candlestick pattern performance on NSE stocks.

9. LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. *Nature*, 521, 436–444. — The convolutional neural network architecture used in the chart CNN.

10. Sharpe, W. F. (1966). Mutual Fund Performance. *Journal of Business*, 39(1), 119–138. — The Sharpe ratio used to select the optimal portfolio.

---

*This document describes the system as of October 2026. Prices are from Yahoo Finance (personal use). The system runs on localhost only and is not publicly hosted. Not investment advice.*
