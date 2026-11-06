"""RSI, MACD, Fibonacci retracement, and Beta — pure functions, no I/O, no side effects.

All inputs are plain Python lists of floats (prices or returns). All prices stay in whatever
unit the caller uses (rupees or paise — the ratios are unit-free). Round for display only.

Verification series (hand-calculated, used in tests):
  RSI: 14-period Wilder's on closes [44,47,46,45,48,50,52,51,49,48,46,43,45,46,48,50,52,53,54,55]
       After seeding on first 14: avg_gain≈1.643, avg_loss≈0.643 → RSI≈71.9 (overbought)
  MACD: on [45]*10+[46,47,48,49,50,51,52,53,54,55]+[54,53,52,51,50]*5 (40 bars)
       fast EMA converges to values near the price, slow EMA lags — histogram sign follows trend
  Beta: stock returns [0,0.01,-0.01,0.02,-0.02,...] market returns [0,0.01,-0.01,0.02,-0.02,...]*0.8
        → beta ≈ 1 / 0.8 = 1.25 (Volatile)
"""

# ── RSI ──────────────────────────────────────────────────────────────────────

RSI_PERIOD     = 14
RSI_OVERSOLD   = 30.0
RSI_OVERBOUGHT = 70.0
RSI_MIN_BARS   = 28  # 2 × period for Wilder's warm-up

# ── MACD ─────────────────────────────────────────────────────────────────────

MACD_FAST      = 12
MACD_SLOW      = 26
MACD_SIGNAL    = 9
MACD_MIN_BARS  = MACD_SLOW + MACD_SIGNAL  # 35

# ── Fibonacci ─────────────────────────────────────────────────────────────────

FIB_LOOKBACK   = 50  # bars to find the swing high and low
FIB_NEAR_PCT   = 0.005  # 0.5% — price within this of a level is "near" it
FIB_RATIOS     = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
FIB_EXTENSIONS = [1.272, 1.618]

# ── Beta ─────────────────────────────────────────────────────────────────────

BETA_WINDOW      = 252   # trading days (≈ 1 year)
BETA_MIN_OBS     = 60    # minimum overlapping observations
BETA_BENCHMARK   = "NIFTY 50"
BETA_INVERSE     = 0.0   # < 0        → inverse
BETA_VERY_LOW    = 0.5   # 0 to 0.5  → very defensive
BETA_LOW         = 0.8   # 0.5 to 0.8→ defensive
BETA_MID         = 1.2   # 0.8 to 1.2→ tracks market
BETA_HIGH        = 1.5   # 1.2 to 1.5→ volatile
                          # > 1.5     → highly volatile


# ─────────────────────────────────────────────────────────────────────────────
# RSI
# ─────────────────────────────────────────────────────────────────────────────

def compute_rsi(closes: list[float]) -> dict:
    """Wilder's RSI(14) on a list of closing prices (oldest first).

    Returns {"value", "verdict", "reason"} or {"error": reason_string}.
    Zero-gain and zero-loss edge cases are handled explicitly (no division by zero).
    """
    if len(closes) < RSI_MIN_BARS:
        return {"error": "insufficient_data"}

    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains   = [max(0.0, c) for c in changes]
    losses  = [max(0.0, -c) for c in changes]

    # Seed: simple average of the first RSI_PERIOD bars
    avg_gain = sum(gains[:RSI_PERIOD]) / RSI_PERIOD
    avg_loss = sum(losses[:RSI_PERIOD]) / RSI_PERIOD

    # Wilder's smoothing for the rest
    for g, lo in zip(gains[RSI_PERIOD:], losses[RSI_PERIOD:]):
        avg_gain = (avg_gain * (RSI_PERIOD - 1) + g) / RSI_PERIOD
        avg_loss = (avg_loss * (RSI_PERIOD - 1) + lo) / RSI_PERIOD

    if avg_loss == 0.0:
        rsi = 100.0 if avg_gain > 0 else 50.0
    else:
        rsi = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

    rsi = max(0.0, min(100.0, rsi))

    if rsi >= RSI_OVERBOUGHT:
        verdict = "Overbought"
        reason  = f"RSI {rsi:.1f} is above {RSI_OVERBOUGHT:.0f} — recent gains are strong"
    elif rsi <= RSI_OVERSOLD:
        verdict = "Oversold"
        reason  = f"RSI {rsi:.1f} is below {RSI_OVERSOLD:.0f} — recent losses are heavy"
    else:
        verdict = "Neutral"
        reason  = f"RSI {rsi:.1f} is between {RSI_OVERSOLD:.0f} and {RSI_OVERBOUGHT:.0f}"

    return {"value": round(rsi, 2), "verdict": verdict, "reason": reason}


# ─────────────────────────────────────────────────────────────────────────────
# MACD
# ─────────────────────────────────────────────────────────────────────────────

def compute_macd(closes: list[float]) -> dict:
    """MACD(12, 26, 9) on a list of closing prices (oldest first).

    Returns {"macd", "signal", "histogram", "verdict", "reason"} or {"error": ...}.
    Verdict comes from the last two completed bars to avoid flicker from the forming candle.
    """
    if len(closes) < MACD_MIN_BARS:
        return {"error": "insufficient_data"}

    fast_ema  = _ema_series(closes, MACD_FAST)
    slow_ema  = _ema_series(closes, MACD_SLOW)

    # Align: fast_ema has MACD_FAST fewer seed points consumed; slow_ema starts one point earlier
    # Both _ema_series return len(closes)-period+1 values, so offset = MACD_SLOW - MACD_FAST
    offset    = MACD_SLOW - MACD_FAST
    macd_line = [f - s for f, s in zip(fast_ema[offset:], slow_ema)]

    signal_ema = _ema_series(macd_line, MACD_SIGNAL)

    # Histogram: MACD line aligned with signal (signal starts at index MACD_SIGNAL-1 of macd_line)
    histo = [m - s for m, s in zip(macd_line[MACD_SIGNAL - 1:], signal_ema)]

    if len(histo) < 2:
        return {"error": "insufficient_data"}

    macd_val  = macd_line[-1]
    sig_val   = signal_ema[-1]
    last_h    = histo[-1]
    prev_h    = histo[-2]

    if prev_h <= 0.0 and last_h > 0.0:
        verdict = "Bullish crossover"
        reason  = "MACD just crossed above the signal line"
    elif prev_h >= 0.0 and last_h < 0.0:
        verdict = "Bearish crossover"
        reason  = "MACD just crossed below the signal line"
    elif macd_val > 0.0 and last_h > 0.0:
        verdict = "Bullish"
        reason  = "MACD is above zero and above the signal line"
    elif macd_val < 0.0 and last_h < 0.0:
        verdict = "Bearish"
        reason  = "MACD is below zero and below the signal line"
    else:
        verdict = "Neutral"
        reason  = "MACD is near zero or near the signal line"

    return {
        "macd":      round(macd_val, 4),
        "signal":    round(sig_val,  4),
        "histogram": round(last_h,   4),
        "verdict":   verdict,
        "reason":    reason,
    }


def _ema_series(values: list[float], period: int) -> list[float]:
    """EMA of a series. Returns one value per input starting from index period-1.
    Seed = SMA of the first `period` values, then Wilder-style exponential smoothing."""
    k    = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out  = [seed]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1.0 - k))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Fibonacci
# ─────────────────────────────────────────────────────────────────────────────

def compute_fibonacci(
    bars: list[tuple],
    current_price: float,
) -> dict:
    """Fibonacci retracement and extension levels from a swing high and low.

    bars: list of (open, high, low, close) tuples, oldest first, at least FIB_LOOKBACK items.
    current_price: the latest trade price (same unit as bar prices).

    Returns a dict with levels, verdict, and swing anchors, or {"error": reason_string}.
    """
    if len(bars) < FIB_LOOKBACK:
        return {"error": "insufficient_data"}

    window = bars[-FIB_LOOKBACK:]
    highs  = [b[1] for b in window]   # index 1 = high
    lows   = [b[2] for b in window]   # index 2 = low

    swing_high = max(highs)
    swing_low  = min(lows)

    if swing_high <= swing_low or swing_high == 0:
        return {"error": "no_clear_swing"}

    hi_idx = max(i for i, h in enumerate(highs) if h == swing_high)
    lo_idx = min(i for i, lo in enumerate(lows) if lo == swing_low)

    # Uptrend: low happened before high → retrace down from the high
    # Downtrend: high happened before low → retrace up from the low
    trend = "uptrend" if lo_idx < hi_idx else "downtrend"
    diff  = swing_high - swing_low

    if trend == "uptrend":
        levels     = [{"ratio": r, "price": round(swing_high - r * diff, 4)} for r in FIB_RATIOS]
        extensions = [{"ratio": r, "price": round(swing_high + (r - 1.0) * diff, 4)} for r in FIB_EXTENSIONS]
    else:
        levels     = [{"ratio": r, "price": round(swing_low + r * diff, 4)} for r in FIB_RATIOS]
        extensions = [{"ratio": r, "price": round(swing_low - (r - 1.0) * diff, 4)} for r in FIB_EXTENSIONS]

    prices = [lv["price"] for lv in levels]
    prices_above = [p for p in prices if p > current_price]
    prices_below = [p for p in prices if p < current_price]

    nearest_above = min(prices_above) if prices_above else None
    nearest_below = max(prices_below) if prices_below else None

    ratio_above = next((lv["ratio"] for lv in levels if lv["price"] == nearest_above), None)
    ratio_below = next((lv["ratio"] for lv in levels if lv["price"] == nearest_below), None)

    # Verdict: is price within FIB_NEAR_PCT of the nearest level?
    if nearest_below is not None and abs(current_price - nearest_below) / current_price <= FIB_NEAR_PCT:
        verdict = (f"Price near the {ratio_below * 100:.1f}% level "
                   f"({'support' if trend == 'uptrend' else 'resistance'} in a {trend})")
    elif nearest_above is not None and abs(nearest_above - current_price) / current_price <= FIB_NEAR_PCT:
        verdict = (f"Price near the {ratio_above * 100:.1f}% level "
                   f"({'resistance' if trend == 'uptrend' else 'support'} in a {trend})")
    else:
        below_str = f"{ratio_below * 100:.1f}%" if ratio_below is not None else "none"
        above_str = f"{ratio_above * 100:.1f}%" if ratio_above is not None else "none"
        verdict   = f"Between Fib levels — support {below_str}, resistance {above_str}"

    return {
        "levels":              levels,
        "extensions":          extensions,
        "swing_high":          swing_high,
        "swing_low":           swing_low,
        "trend":               trend,
        "nearest_above":       nearest_above,
        "nearest_below":       nearest_below,
        "nearest_ratio_above": ratio_above,
        "nearest_ratio_below": ratio_below,
        "verdict":             verdict,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Beta
# ─────────────────────────────────────────────────────────────────────────────

def compute_beta(
    stock_series:  list[tuple[str, float]],
    market_series: list[tuple[str, float]],
) -> dict:
    """Beta of a stock against a market benchmark.

    Both inputs are [(date_string, close_price), ...] sorted ascending (oldest first).
    Only days present in both series are used. At most BETA_WINDOW overlapping days are used
    (the most recent ones).

    Returns {"value", "verdict", "reason", "window_days", "benchmark"} or {"error": ...}.
    """
    stock_map  = {d: p for d, p in stock_series  if p and p > 0}
    market_map = {d: p for d, p in market_series if p and p > 0}

    common = sorted(d for d in stock_map if d in market_map)
    # +1 because we need N+1 prices for N returns
    common = common[-(BETA_WINDOW + 1):]

    if len(common) < BETA_MIN_OBS + 1:
        return {"error": "insufficient_data"}

    s_rets = [stock_map[common[i]]  / stock_map[common[i - 1]]  - 1.0 for i in range(1, len(common))]
    m_rets = [market_map[common[i]] / market_map[common[i - 1]] - 1.0 for i in range(1, len(common))]

    n      = len(s_rets)
    m_mean = sum(m_rets) / n
    s_mean = sum(s_rets) / n

    cov = sum((m - m_mean) * (s - s_mean) for m, s in zip(m_rets, s_rets)) / n
    var = sum((m - m_mean) ** 2 for m in m_rets) / n

    if var == 0.0:
        return {"error": "market_flat"}

    beta = cov / var

    if beta < BETA_INVERSE:
        verdict, reason = "Inverse",         "Tends to move opposite to the market"
    elif beta < BETA_VERY_LOW:
        verdict, reason = "Very defensive",  f"Much less volatile than {BETA_BENCHMARK}"
    elif beta < BETA_LOW:
        verdict, reason = "Defensive",       f"Less volatile than {BETA_BENCHMARK}"
    elif beta <= BETA_MID:
        verdict, reason = "Tracks market",   f"Moves roughly with {BETA_BENCHMARK}"
    elif beta <= BETA_HIGH:
        verdict, reason = "Volatile",        f"More volatile than {BETA_BENCHMARK}"
    else:
        verdict, reason = "Highly volatile", f"Significantly amplifies {BETA_BENCHMARK} moves"

    return {
        "value":       round(beta, 2),
        "verdict":     verdict,
        "reason":      reason,
        "window_days": n,
        "benchmark":   BETA_BENCHMARK,
    }
