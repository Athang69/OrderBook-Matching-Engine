# Next task (start here, after docs/AGENT_HANDOFF.md)

## What changed since AGENT_HANDOFF.md was written (16–18 Oct 2026)

- **"Why did it move?"** section on every stock page (`frontend/src/components/quote/WhyMoved.tsx`, styles in `frontend/src/styles/why.css`, hooks `useExplanation.ts`, `useAnalysis.ts`).
  - Opened by the "Why down/up?" button next to the price, a click on any day of the chart, or the big-day chips.
- **`backend/app/explain.py`** (`Explainer`, endpoint `GET /v1/explain/{symbol}?date=`) gathers the evidence for a day:
  - from one year of daily bars (Yahoo `chart(ticker, "1y")`): beta against NIFTY 50, the market's part of the move, the stock's own part against a typical day;
  - similar companies (Yahoo `recommendationsbysymbol`, filtered by related sector) and the sector index;
  - Google News searches at five levels: company, peers, industry, market, global. Each headline gets a cause tag (keyword lists) and a keyword `tone`.
  - Results are cached.
- **`backend/app/analysis.py`** (`Analyst`, endpoint `GET /v1/analysis/{symbol}?date=`):
  1. adds that day's Indian indices and world markets (Taiwan, Korea, Japan, Hong Kong, China, the US, the US chip index, Brent, gold, USD/INR);
  2. numbers the headlines [1], [2], …;
  3. builds a prompt and calls an LLM, which returns JSON (headline, verdict, drivers with cited numbers, market_context, stock_specific, confidence, watch);
  4. caches the result for 30 minutes.
- **The LLM is OpenRouter free models only:** `nvidia/nemotron-3-ultra-550b-a55b:free`, then `google/gemma-4-31b-it:free`, then `nvidia/nemotron-3-super-120b-a12b:free`, in one request with fallback. The key is `OPENROUTER_API_KEY` in the git-ignored `.env`, which `scripts/run.sh` loads.
  - **Never use Claude** (the `claude -p` code path is kept but not called): the user has few Claude credits.
  - Verified working: 37 s for the model, about 55 s in total.
- **Already installed in `.venv`:** CPU-only `torch` and `transformers` (not yet in `backend/requirements.txt`).
- **This laptop:** 12 cores, about 2 GB of free RAM, 25 GB of free disk.

## The task

Add three things, feed all of them into the LLM's evidence, and show them on the page, end to end:

1. **FinBERT** (`ProsusAI/finbert` via transformers, CPU):
   - Score every headline in the explanation: label plus P(pos/neg/neutral). Use `score = P(pos) − P(neg)` as the headline `tone`, so the ranking uses FinBERT; keep the keyword tone as a fallback if it fails.
   - Add `sentiment` per headline, plus totals per scope.
   - Load the model lazily, or warm it at server start in a background thread. Batch the headlines and cache by title.
2. **Candlestick patterns, rule-based** from daily OHLC, for the day explained and the day before:
   - doji, hammer, hanging man, inverted hammer, shooting star, bullish/bearish engulfing, harami, piercing line, dark cloud cover, morning/evening star, three white soldiers, three black crows, marubozu;
   - use the trend context from the previous ~5–10 closes.
3. **CNN on candlestick images**, after Jiang, Kelly & Xiu (2023), "(Re-)Imag(in)ing Price Trends", Journal of Finance:
   - **Image:** 20 trading days drawn as 64×60 black-and-white, 3 px per day (open tick, high–low bar, close tick), with a 20-day moving-average line and volume bars at the bottom.
   - **Label:** whether the price is up 5 trading days later.
   - **Training script `scripts/train_cnn.py`:**
     - about 200 liquid NSE EQ stocks (top by turnover in the latest bhavcopy, excluding ETFs), daily data from 2017 via yfinance, `auto_adjust=True`;
     - one window per stock every 5 days, kept as uint8 (RAM is tight);
     - a time split: train before 2024-07-01, validation to 2025-07-01, test after;
     - a small CNN (3 conv blocks: 32, 64, 128 channels, kernel 5×3, BatchNorm, LeakyReLU, MaxPool(2,1), dropout, linear to 2), a few epochs with early stopping on validation loss.
   - **Saved to git-ignored `data/models/`:** `chart_cnn.pt` and `chart_cnn.json` with honest test metrics: accuracy, the majority-class baseline, AUC, the up rate in the top and bottom deciles. Also each pattern's count and next-5-day up rate.
   - **Serving:** for the stock and day, P(up over the next 5 days) from the chart ending that day and from the chart ending the day before ("did the chart warn before the move?"). Return the 64×60 image as a base64 PNG (write a tiny PNG with zlib, since Pillow is not installed).

**Wiring:**
- Put FinBERT, the patterns and the CNN into the `explain` result (the fast endpoint), so the page shows them while the LLM works.
- Add them to the prompt in `analysis.py`: FinBERT labels on each numbered headline, a patterns section with historical up rates, and a CNN section with the test accuracy.
- Add a `"technical_view"` field to the JSON the LLM must return.

**UI** (in `WhyMoved.tsx`):
- a "Chart model" card: the CNN image enlarged and pixelated, P(up), the test accuracy against the baseline, and the patterns found with their historical up rates;
- FinBERT badges on the evidence headlines, and sentiment totals per scope;
- the LLM's `technical_view`.

## Constraints from the user

- **Demo only, for the faculty, for 30–45 minutes.** Skip robustness work, tests and documentation, and keep token use low. Make sure it works end to end on this laptop: run the training, restart `scripts/run.sh`, and check one stock (for example AVALON on 2026-10-15 and on the latest day) through `/v1/analysis`.
- Do not read `orderBook.cpp`. Do not commit unless asked.
- Be honest about accuracy in the UI. About 52–56% is normal for this kind of model; never inflate it.
