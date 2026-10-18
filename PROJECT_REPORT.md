# Order Book and Matching Engine Simulator with Portfolio Recommendation for the Indian Stock Market

**Project progress report: literature survey, documentation and timeline**

|                     |                                                         |
| ------------------- | ------------------------------------------------------- |
| Institution         | [fill in]                                               |
| Department / Course | [fill in]                                               |
| Team members        | [fill in]                                               |
| Project guide       | [fill in]                                               |
| Report date         | 11 October 2026                                         |
| Repository          | <https://github.com/Athang69/OrderBook-Matching-Engine> |

---

## Abstract

A stock exchange keeps all waiting buy and sell orders in an order book and uses a matching engine to turn them into trades. This project builds a simulator of that process for the Indian stock market, covering delivery and intraday trading. It shows the five best buy and sell prices for each stock and matches orders by price and then by time. The project also integrates a portfolio management module that reads news with FinBERT, studies historical prices, and uses the SLSQP optimiser to suggest how much money to put in each stock. A single frontend shows the order book together with a buy suggestion for each stock. The system uses virtual money and previous-day data only. This report presents the literature survey, the design, the work completed so far and the plan ahead.

---

## 1. Introduction

### 1.1 Background

When someone places an order to buy or sell a share, the exchange first tries to match it with an order on the opposite side. If no match is available, the order waits in the order book. The program that does the matching is called the matching engine. It must be correct, because it decides who trades with whom, and fast, because exchanges receive a very large number of orders.

Investors also face a second question: which stocks to buy, and how much money to put in each. This depends on how the stocks have performed in the past and on what the news says about them.

Our project covers both sides. One part simulates how the exchange works. The other part suggests what to buy.

### 1.2 Problem statement

To build a simulator of the Indian stock exchange's order book and matching engine, and to combine it with a portfolio management module that suggests which stocks to buy and how much money to allocate to each.

### 1.3 Objectives

1. Build an order book and matching engine that follows price-time priority.
2. Show the five best buy prices and five best sell prices for each stock.
3. Follow basic Indian market rules: tick size, price bands, and delivery and intraday trading.
4. Run the simulator with previous-day NSE data and robot traders.
5. Integrate the portfolio management module (FinBERT and SLSQP) and show its buy suggestion and allocation in the frontend.
6. Test that the engine is correct and measure how fast it is.

### 1.4 Scope

| In scope                           | Out of scope                            |
| ---------------------------------- | --------------------------------------- |
| NSE equity shares (cash market)    | Futures, options, currency, commodities |
| Delivery and intraday trading      | Real money and real users               |
| Previous-day and older data        | Live market prices                      |
| Free data sources                  | Paid data                               |
| Buy suggestions for study purposes | Investment advice                       |

The system is a simulator for learning. The buy suggestions are an academic demonstration and are not investment advice.

---

## 2. Basic concepts

| Term                   | Meaning                                                                                               |
| ---------------------- | ----------------------------------------------------------------------------------------------------- |
| Order book             | The list of all waiting buy and sell orders for a stock                                               |
| Bid and ask            | The bid is the highest price a buyer is offering. The ask is the lowest price a seller is asking.     |
| Market depth (L2)      | The total quantity waiting at each price. We show the best five prices on each side.                  |
| Matching engine        | The program that pairs buy orders with sell orders to create trades                                   |
| Price-time priority    | The better price is served first. If two orders have the same price, the earlier one is served first. |
| Limit order            | An order to buy or sell at a stated price or better                                                   |
| Market order           | An order to buy or sell immediately at the best available price                                       |
| Delivery trading       | Shares are actually bought and held; the buyer pays the full amount                                   |
| Intraday trading       | Shares are bought and sold on the same day; only a margin is needed                                   |
| Tick size              | The smallest step by which a price can change                                                         |
| Price band             | The highest and lowest price allowed for a stock in a day                                             |
| Sentiment analysis     | Deciding whether a piece of text is positive, negative or neutral                                     |
| FinBERT                | A language model trained on financial text, used for sentiment analysis                               |
| Portfolio optimisation | Deciding what share of money to put in each stock to balance return and risk                          |
| SLSQP                  | An optimisation method that finds the best values while respecting given limits                       |

---

## 3. Literature survey

We studied three areas: how order books and exchanges work, what similar systems already exist, and how portfolios are built using prices and news. Numbers in square brackets refer to the references in section 11.

### 3.1 Order books and exchanges

Harris [1] explains how stock exchanges work, including order types and the price-time priority rule that our engine follows. Gould et al. [2] summarise what researchers know about order books and how they are modelled. Gode and Sunder [3] show that even traders who place random orders within their budget produce sensible market prices, which supports using simple robot traders in a simulator. Agarwalla, Jacob and Pandey [4] study the opening auction at NSE and find that it attracts little trading and improves price discovery only slightly.

### 3.2 Existing systems

Fowler [5] describes the LMAX exchange, which does all its matching on a single thread in memory and keeps a log of every input so that the system can be replayed. ABIDES [6] is an open-source market simulator in which many software agents trade through a simulated exchange. CoinTossX [7] is an open-source matching engine built to simulate the Johannesburg Stock Exchange. These systems show that a matching engine and a simulator can be built with open tools, but none of them follows Indian market rules.

### 3.3 Portfolio management and news sentiment

Markowitz [8] founded modern portfolio theory: an investor should choose how much to invest in each stock by balancing expected return against risk. Tetlock [9] shows that the tone of financial news is linked to how the stock market moves afterwards, which is the reason to include news in investment decisions. Araci [10] introduces FinBERT, a language model trained on financial text that labels a sentence as positive, negative or neutral. Kraft [11] describes SLSQP, the optimisation method used to compute the portfolio allocation under constraints.

### 3.4 Summary

| Ref  | Work                     | What it says                                 | How we use it                                |
| ---- | ------------------------ | -------------------------------------------- | -------------------------------------------- |
| [1]  | Harris (2003)            | How exchanges and order matching work        | Rules for our matching engine                |
| [2]  | Gould et al. (2013)      | Survey of research on order books            | What a realistic order book looks like       |
| [3]  | Gode and Sunder (1993)   | Random traders still produce sensible prices | Basis for our robot traders                  |
| [4]  | Agarwalla et al. (2015)  | Study of the NSE opening auction             | Understanding of the Indian market           |
| [5]  | Fowler (2011)            | Design of the LMAX exchange                  | Single-thread design and replay log          |
| [6]  | Byrd et al. (2020)       | ABIDES market simulator                      | Example of a simulator with software traders |
| [7]  | Jericevich et al. (2021) | CoinTossX matching engine                    | Closest existing system, for another market  |
| [8]  | Markowitz (1952)         | Balance return against risk                  | Theory behind the allocation                 |
| [9]  | Tetlock (2007)           | News tone is linked to market moves          | Reason for using news sentiment              |
| [10] | Araci (2019)             | FinBERT sentiment model                      | Scoring news about each stock                |
| [11] | Kraft (1988)             | SLSQP optimisation method                    | Computing the allocation                     |

### 3.5 Gaps identified

1. **No open system for Indian rules.** The open matching engines and simulators we reviewed are built for other markets. We did not find one that follows Indian tick sizes, price bands, and delivery and intraday trading.
2. **No free order-level data for Indian stocks.** Full order-by-order data from NSE is a paid product, so a simulator with robot traders is needed.
3. **Trading simulation and portfolio advice are separate.** In the systems we reviewed, the exchange simulator and the portfolio tool are different programs. Our project shows both in one frontend.

---

## 4. Rules and data

### 4.1 Regulations that shape the project

| Rule                                                                                                                          | Source                                           | Effect on our project                                                |
| ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | -------------------------------------------------------------------- |
| Shares can be traded only on a recognised stock exchange                                                                      | Securities Contracts (Regulation) Act, 1956 [12] | We build a simulator with virtual money, not a real trading platform |
| Live prices cannot be shared with virtual trading platforms; for education, data must be at least one day old with no rewards | SEBI circular, 24 May 2024 [13]                  | We use previous-day data only and give no rewards                    |
| Exchange data belongs to the exchange                                                                                         | NSE data policy                                  | We do not upload downloaded data files to GitHub                     |

### 4.2 Market rules used in the simulator

| Rule             | Details                                                                                          |
| ---------------- | ------------------------------------------------------------------------------------------------ |
| Tick size        | Depends on the share price, from ₹0.01 for shares under ₹250 up to ₹5 for shares above ₹20,000   |
| Price band       | A stock cannot move more than a fixed percentage (2, 5, 10 or 20%) from the previous day's close |
| Delivery trading | Full amount needed to buy; shares must be owned to sell                                          |
| Intraday trading | A margin of at least 20% is needed; positions are closed the same day                            |

### 4.3 Data sources

All data is free.

| Data                                  | What it contains                                                                       | Used for                                      |
| ------------------------------------- | -------------------------------------------------------------------------------------- | --------------------------------------------- |
| NSE daily bhavcopy                    | Previous close, open, high, low, close, volume and delivery percentage for every stock | Setting up each stock in the simulator        |
| NSE price band list                   | Price band for every stock                                                             | Daily price limits                            |
| NSE sample order and trade files [14] | 300,000 real orders and 300,000 real trades from 10 April 2024                         | Checking our engine against the real exchange |
| News and historical prices            | News articles and past prices of the stocks in the portfolio                           | Input to the portfolio management module      |

We downloaded and checked the three NSE files on 11 October 2026. The NSE sample covers only part of one day, so it is used for testing and not for running a full session.

---

## 5. Proposed system

### 5.1 Architecture

```
+-----------------------------+      +-------------------------------+
| Module 1: Exchange simulator|      | Module 2: Portfolio manager   |
|                             |      |                               |
|  Previous-day NSE data      |      |  News          Historical     |
|          |                  |      |   |            prices         |
|          v                  |      |   v               |           |
|  Robot traders              |      |  FinBERT          |           |
|          |                  |      |  (sentiment)      |           |
|          v                  |      |   |               |           |
|  Matching engine            |      |   +-------+-------+           |
|  (order book per stock)     |      |           v                   |
|                             |      |  SLSQP optimiser              |
|                             |      |  (allocation per stock)       |
+--------------+--------------+      +---------------+---------------+
               |                                     |
               v                                     v
        +--------------------------------------------------+
        | Module 3: Frontend                               |
        | Best 5 bids and asks, trades, buy suggestion,    |
        | suggested allocation                             |
        +--------------------------------------------------+
```

### 5.2 Module 1: Exchange simulator

This module is the order book and matching engine.

1. Each stock is set up using the previous day's NSE data: its last closing price, tick size and price band.
2. Robot traders place buy and sell orders around the previous day's prices. We can also place orders ourselves.
3. Each order is checked: the price must follow the tick size and stay inside the price band.
4. The matching engine tries to match the order. The better price goes first; at the same price, the earlier order goes first.
5. Any unmatched part of the order waits in the order book.
6. The engine outputs the trades and the five best prices on each side.

Design choices that keep it fast and correct:

- Prices are stored as whole numbers in paise, so there are no rounding errors.
- Orders at the same price are kept in a queue, so the earliest is always served first.
- Because the price band limits how far a price can move in a day, the price levels can be kept in a simple array and found directly.
- Memory for orders is reserved in advance, so the engine does not slow down while matching.
- One thread does all the matching for a stock, so the same inputs always give the same result [5].

### 5.3 Module 2: Portfolio manager

This module suggests how to divide money among stocks.

1. It collects recent news and historical prices for the stocks in the portfolio.
2. FinBERT reads each news item and labels it positive, negative or neutral. This gives a sentiment score for each stock [10].
3. From the historical prices, it works out each stock's return and risk [8].
4. The SLSQP optimiser uses the sentiment scores and the return and risk figures to find the share of money for each stock. The shares must add up to 100% [11].
5. The output is the amount of money to allocate to each stock.

### 5.4 Module 3: Frontend and integration

The frontend brings the two modules together on one screen.

- From Module 1 it shows the five best bids and asks and the recent trades for a stock.
- From Module 2 it shows the suggested allocation and whether the stock is a buy or not.

A user can therefore see the current state of the order book and the suggestion for the same stock side by side.

### 5.5 Requirements

**Functional**

1. Accept, modify and cancel limit and market orders.
2. Match orders by price-time priority and report trades.
3. Show the five best bid and ask prices for each stock.
4. Reject orders that break the tick size or price band.
5. Handle delivery and intraday orders for virtual accounts.
6. Analyse news sentiment and compute the portfolio allocation.
7. Show the buy suggestion and allocation in the frontend.

**Non-functional**

1. Speed: the engine should handle a large number of orders quickly. We will measure orders per second and time per order.
2. Correctness: the same inputs must always give the same trades.
3. Ease of use: the frontend should be simple to read.

### 5.6 Tools and technologies

| Part              | Technology                                  |
| ----------------- | ------------------------------------------- |
| Matching engine   | C++                                         |
| Portfolio manager | Python, FinBERT, SLSQP optimiser from SciPy |
| Frontend          | [fill in]                                   |
| Version control   | Git and GitHub                              |

### 5.7 Testing plan

| What we test                     | How                                                                            |
| -------------------------------- | ------------------------------------------------------------------------------ |
| Matching rules                   | Small hand-made examples with known answers                                    |
| Agreement with the real exchange | Feed NSE sample orders to our engine and compare the trades                    |
| Speed                            | Send a large number of generated orders and measure the time                   |
| Portfolio module                 | Check sentiment labels on sample headlines and that allocations add up to 100% |

---

## 6. Work completed as of 11 October 2026

| Activity                                                              | Status                          |
| --------------------------------------------------------------------- | ------------------------------- |
| Problem definition and scope                                          | Completed                       |
| Literature survey                                                     | Completed                       |
| Study of regulations and market rules                                 | Completed                       |
| Study of free data sources                                            | Completed                       |
| System design                                                         | Completed                       |
| Project plan (`PROJECT_PLAN.md`)                                      | Completed                       |
| First prototype of the order book and matching flow (`orderBook.cpp`) | In progress                     |
| Portfolio management module                                           | Developed as a separate project |
| Integration of the portfolio module with the frontend                 | In progress                     |
| Testing and speed measurement                                         | Not started                     |

---

## 7. Timeline

### 7.1 Work done so far

| Date            | Milestone                                                                      |
| --------------- | ------------------------------------------------------------------------------ |
| 17 June 2026    | Repository created; first prototype of the order book and matching flow        |
| 22 June 2026    | Prototype revised                                                              |
| [fill in]       | Portfolio management module developed                                          |
| 11 October 2026 | Literature survey, study of rules and data sources, and project plan completed |

### 7.2 Plan ahead

| Period                | Work                                                                 | Status  |
| --------------------- | -------------------------------------------------------------------- | ------- |
| 12 to 18 Oct 2026     | Finalise order types, rules and message formats                      | Next    |
| 19 Oct to 1 Nov 2026  | Complete the matching engine and the best-five view                  | Planned |
| 2 to 15 Nov 2026      | Test with NSE sample data and measure speed                          | Planned |
| 16 to 29 Nov 2026     | Previous-day data loader, robot traders, delivery and intraday rules | Planned |
| 30 Nov to 13 Dec 2026 | Frontend and integration of the portfolio module                     | Planned |
| 14 to 20 Dec 2026     | Final testing, documentation and demonstration                       | Planned |

---

## 8. Expected outcomes

1. A working order book and matching engine for Indian stocks, with measured speed.
2. A view of the five best bids and asks for each stock.
3. A comparison of our engine's trades with real NSE sample trades.
4. A portfolio module that suggests how much money to allocate to each stock.
5. A single frontend that shows the order book and the buy suggestion together.

---

## 9. Risks

| Risk                                                        | How we handle it                                                  |
| ----------------------------------------------------------- | ----------------------------------------------------------------- |
| Full-day order data for Indian stocks is not free           | Use robot traders guided by previous-day data                     |
| The NSE sample covers only part of a day                    | Use it only for testing the engine                                |
| News sentiment may be wrong for some articles               | Combine sentiment with historical price data, not sentiment alone |
| Connecting a C++ engine and a Python module to one frontend | Agree on a simple data format between the modules early           |

---

## 10. Future scope

- Opening and closing auctions, as used by NSE.
- Stop-loss orders.
- More realistic robot traders.
- Testing the buy suggestions against past data to see how they would have performed.

---

## 11. References

[1] L. Harris, *Trading and Exchanges: Market Microstructure for Practitioners*. Oxford University Press, 2003.

[2] M. D. Gould, M. A. Porter, S. Williams, M. McDonald, D. J. Fenn and S. D. Howison, "Limit order books," *Quantitative Finance*, vol. 13, no. 11, pp. 1709–1742, 2013.

[3] D. K. Gode and S. Sunder, "Allocative efficiency of markets with zero-intelligence traders: Market as a partial substitute for individual rationality," *Journal of Political Economy*, vol. 101, no. 1, pp. 119–137, 1993.

[4] S. K. Agarwalla, J. Jacob and A. Pandey, "Impact of the introduction of call auction on price discovery: Evidence from the Indian stock market using high-frequency data," *International Review of Financial Analysis*, vol. 39, pp. 167–178, 2015.

[5] M. Fowler, "The LMAX architecture," martinfowler.com, 2011.

[6] D. Byrd, M. Hybinette and T. H. Balch, "ABIDES: Towards high-fidelity multi-agent market simulation," in *Proc. ACM SIGSIM Conference on Principles of Advanced Discrete Simulation*, 2020, pp. 11–22.

[7] I. Jericevich, D. Sing and T. Gebbie, "CoinTossX: An open-source low-latency high-throughput matching engine," arXiv:2102.10925, 2021.

[8] H. Markowitz, "Portfolio selection," *Journal of Finance*, vol. 7, no. 1, pp. 77–91, 1952.

[9] P. C. Tetlock, "Giving content to investor sentiment: The role of media in the stock market," *Journal of Finance*, vol. 62, no. 3, pp. 1139–1168, 2007.

[10] D. Araci, "FinBERT: Financial sentiment analysis with pre-trained language models," arXiv:1908.10063, 2019.

[11] D. Kraft, "A software package for sequential quadratic programming," Technical Report DFVLR-FB 88-28, German Aerospace Center, 1988.

[12] Government of India, *The Securities Contracts (Regulation) Act, 1956*.

[13] Securities and Exchange Board of India, "Norms for sharing of real time price data to third parties," circular SEBI/HO/MRD/MRD-PoD-3/P/CIR/2024/56, 24 May 2024.

[14] NSE Data & Analytics Ltd., *NSE Historical Data: Order and Trade Specification*, version 1.19, 3 August 2026.
