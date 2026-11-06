"""Unit tests for RSI, MACD, Fibonacci, and Beta (indicators.py).

Reference values are verified by running compute_* on small, hand-checkable series.
To cross-check RSI and MACD against TradingView after implementation:
  1. Open RELIANCE.NS on TradingView daily chart.
  2. Add RSI(14) and MACD(12,26,9).
  3. Compare the latest closed bar's values with what this code produces from
     the same date range fetched via yahoo.global_chart("RELIANCE.NS","1y","1d").
"""
import math
import pytest

from backend.app.indicators import (
    BETA_MIN_OBS,
    BETA_WINDOW,
    FIB_LOOKBACK,
    MACD_MIN_BARS,
    RSI_MIN_BARS,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    compute_beta,
    compute_fibonacci,
    compute_macd,
    compute_rsi,
)


# ─────────────────────────────────────────────────────────────────────────────
# RSI
# ─────────────────────────────────────────────────────────────────────────────

# 30-bar series (≥ RSI_MIN_BARS=28); final 6 bars all rise → overbought territory
RSI_RISING = [100.0 + i * 0.5 for i in range(RSI_MIN_BARS + 2)]
# 30-bar series; final 6 bars all fall → oversold territory
RSI_FALLING = [130.0 - i * 0.5 for i in range(RSI_MIN_BARS + 2)]


def test_rsi_returns_required_keys():
    result = compute_rsi(RSI_RISING)
    assert {"value", "verdict", "reason"} <= result.keys()
    assert "error" not in result


def test_rsi_value_in_range():
    result = compute_rsi(RSI_RISING)
    assert 0 <= result["value"] <= 100


def test_rsi_overbought_verdict():
    # All-up series → RSI near 100
    closes = [float(i) for i in range(1, 60)]
    result = compute_rsi(closes)
    assert result["verdict"] == "Overbought"
    assert result["value"] >= RSI_OVERBOUGHT


def test_rsi_oversold_verdict():
    # All-down series → RSI near 0
    closes = [float(100 - i) for i in range(60)]
    result = compute_rsi(closes)
    assert result["verdict"] == "Oversold"
    assert result["value"] <= RSI_OVERSOLD


def test_rsi_neutral_verdict():
    # Zigzag → balanced gains and losses → Neutral
    closes = [100.0 + (1.0 if i % 2 == 0 else -1.0) for i in range(60)]
    result = compute_rsi(closes)
    assert result["verdict"] == "Neutral"


def test_rsi_insufficient_data():
    result = compute_rsi([100.0] * (RSI_MIN_BARS - 1))
    assert result.get("error") == "insufficient_data"


def test_rsi_exactly_min_bars():
    closes = [float(i) for i in range(RSI_MIN_BARS)]
    result = compute_rsi(closes)
    assert "value" in result


def test_rsi_flat_price_no_crash():
    # All closes identical → no gains or losses → avg_gain == avg_loss == 0
    closes = [100.0] * 40
    result = compute_rsi(closes)
    assert "error" not in result
    assert result["value"] == 50.0  # the neutral fallback when both avg_gain and avg_loss are 0


def test_rsi_all_gains_no_zero_division():
    closes = [float(i) for i in range(10, 10 + 60)]
    result = compute_rsi(closes)
    assert "error" not in result
    assert result["value"] == 100.0


def test_rsi_all_losses_no_zero_division():
    closes = [float(100 - i) for i in range(60)]
    result = compute_rsi(closes)
    assert "error" not in result
    assert result["value"] == 0.0


def test_rsi_overbought_boundary_inclusive():
    # Force RSI exactly to 100 (all gains)
    result = compute_rsi([float(i) for i in range(10, 10 + 60)])
    assert result["verdict"] == "Overbought"


def test_rsi_oversold_boundary_inclusive():
    result = compute_rsi([float(100 - i) for i in range(60)])
    assert result["verdict"] == "Oversold"


# ─────────────────────────────────────────────────────────────────────────────
# MACD
# ─────────────────────────────────────────────────────────────────────────────

def _flat_then_rise(n_flat: int = 40, n_rise: int = 20, step: float = 2.0) -> list[float]:
    """Flat section seeds the EMAs, then a sharp rise creates a positive histogram."""
    return [100.0] * n_flat + [100.0 + i * step for i in range(1, n_rise + 1)]


def _flat_then_fall(n_flat: int = 40, n_fall: int = 20, step: float = 2.0) -> list[float]:
    return [100.0] * n_flat + [100.0 - i * step for i in range(1, n_fall + 1)]


def test_macd_returns_required_keys():
    result = compute_macd(_flat_then_rise())
    assert {"macd", "signal", "histogram", "verdict", "reason"} <= result.keys()
    assert "error" not in result


def test_macd_bullish_after_sharp_rise():
    result = compute_macd(_flat_then_rise())
    assert result["verdict"] in ("Bullish", "Bullish crossover")
    assert result["histogram"] > 0


def test_macd_bearish_after_sharp_fall():
    result = compute_macd(_flat_then_fall())
    assert result["verdict"] in ("Bearish", "Bearish crossover")
    assert result["histogram"] < 0


def test_macd_neutral_on_flat():
    closes = [100.0] * 60
    result = compute_macd(closes)
    assert "error" not in result
    # Flat price → all EMAs equal → MACD = 0, histogram = 0 → Neutral
    assert abs(result["macd"]) < 1e-9
    assert abs(result["histogram"]) < 1e-9
    assert result["verdict"] == "Neutral"


def test_macd_insufficient_data():
    result = compute_macd([100.0] * (MACD_MIN_BARS - 1))
    assert result.get("error") == "insufficient_data"


def test_macd_exactly_min_bars():
    closes = [float(i) for i in range(MACD_MIN_BARS)]
    result = compute_macd(closes)
    assert "macd" in result


def test_macd_signal_and_macd_are_finite():
    result = compute_macd(_flat_then_rise())
    assert math.isfinite(result["macd"])
    assert math.isfinite(result["signal"])
    assert math.isfinite(result["histogram"])


def test_macd_histogram_matches_macd_minus_signal():
    result = compute_macd(_flat_then_rise())
    assert result["histogram"] == pytest.approx(result["macd"] - result["signal"], abs=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# Fibonacci
# ─────────────────────────────────────────────────────────────────────────────

def _uptrend_bars(n: int = FIB_LOOKBACK + 5, lo: float = 100.0, hi: float = 200.0) -> list[tuple]:
    """Synthetic OHLC bars: uptrend from lo to hi with a 2-point daily range."""
    bars = []
    for i in range(n):
        pct  = i / (n - 1)
        base = lo + pct * (hi - lo)
        bars.append((base, base + 2.0, base - 2.0, base))  # open, high, low, close
    return bars


def _downtrend_bars(n: int = FIB_LOOKBACK + 5, lo: float = 100.0, hi: float = 200.0) -> list[tuple]:
    """Synthetic OHLC bars: downtrend from hi to lo."""
    bars = []
    for i in range(n):
        pct  = i / (n - 1)
        base = hi - pct * (hi - lo)
        bars.append((base, base + 2.0, base - 2.0, base))
    return bars


def test_fib_returns_required_keys():
    result = compute_fibonacci(_uptrend_bars(), 150.0)
    assert {"levels", "extensions", "swing_high", "swing_low", "trend", "verdict"} <= result.keys()


def test_fib_level_count():
    result = compute_fibonacci(_uptrend_bars(), 150.0)
    assert len(result["levels"]) == 7
    assert len(result["extensions"]) == 2


def test_fib_all_level_ratios_present():
    result = compute_fibonacci(_uptrend_bars(), 150.0)
    ratios = {lv["ratio"] for lv in result["levels"]}
    assert ratios == {0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0}


def test_fib_uptrend_detected():
    result = compute_fibonacci(_uptrend_bars(), 150.0)
    assert result["trend"] == "uptrend"


def test_fib_downtrend_detected():
    result = compute_fibonacci(_downtrend_bars(), 150.0)
    assert result["trend"] == "downtrend"


def test_fib_uptrend_zero_ratio_is_swing_high():
    result = compute_fibonacci(_uptrend_bars(), 150.0)
    zero_level = next(lv for lv in result["levels"] if lv["ratio"] == 0.0)
    assert zero_level["price"] == pytest.approx(result["swing_high"], abs=0.01)


def test_fib_uptrend_hundred_ratio_is_swing_low():
    result = compute_fibonacci(_uptrend_bars(), 150.0)
    full_level = next(lv for lv in result["levels"] if lv["ratio"] == 1.0)
    assert full_level["price"] == pytest.approx(result["swing_low"], abs=0.01)


def test_fib_nearest_above_is_above_price():
    result = compute_fibonacci(_uptrend_bars(), 150.0)
    if result.get("nearest_above") is not None:
        assert result["nearest_above"] > 150.0


def test_fib_nearest_below_is_below_price():
    result = compute_fibonacci(_uptrend_bars(), 150.0)
    if result.get("nearest_below") is not None:
        assert result["nearest_below"] < 150.0


def test_fib_swing_high_above_swing_low():
    result = compute_fibonacci(_uptrend_bars(), 150.0)
    assert result["swing_high"] > result["swing_low"]


def test_fib_insufficient_data():
    bars   = _uptrend_bars(FIB_LOOKBACK - 1)
    result = compute_fibonacci(bars, 150.0)
    assert result.get("error") == "insufficient_data"


def test_fib_flat_price_no_swing():
    bars   = [(100.0, 100.0, 100.0, 100.0)] * (FIB_LOOKBACK + 5)
    result = compute_fibonacci(bars, 100.0)
    assert result.get("error") == "no_clear_swing"


def test_fib_extension_beyond_swing_high():
    result = compute_fibonacci(_uptrend_bars(), 150.0)
    ext_prices = [e["price"] for e in result["extensions"]]
    # In an uptrend, extensions project beyond the swing high
    assert all(p > result["swing_high"] for p in ext_prices)


# ─────────────────────────────────────────────────────────────────────────────
# Beta
# ─────────────────────────────────────────────────────────────────────────────

def _random_paired(n: int, beta_target: float, seed: int = 42) -> tuple:
    """Generate (stock_series, market_series) where beta ≈ beta_target."""
    import random
    rng = random.Random(seed)
    stock, market = [], []
    ps = pm = 100.0
    for i in range(n + 1):
        date = f"2024-{(i // 28 + 1):02d}-{(i % 28 + 1):02d}"
        stock.append((date, ps))
        market.append((date, pm))
        mkt_ret = rng.gauss(0.0, 0.01)
        pm *= (1.0 + mkt_ret)
        ps *= (1.0 + beta_target * mkt_ret + rng.gauss(0.0, 0.002))
    return stock, market


def test_beta_tracks_market():
    stock, market = _random_paired(BETA_MIN_OBS + 50, beta_target=1.0)
    result = compute_beta(stock, market)
    assert "error" not in result
    assert result["value"] == pytest.approx(1.0, abs=0.3)
    assert result["verdict"] == "Tracks market"


def test_beta_volatile():
    stock, market = _random_paired(BETA_MIN_OBS + 50, beta_target=1.8)
    result = compute_beta(stock, market)
    assert "error" not in result
    assert result["value"] > 1.5
    assert result["verdict"] == "Highly volatile"


def test_beta_defensive():
    stock, market = _random_paired(BETA_MIN_OBS + 50, beta_target=0.4)
    result = compute_beta(stock, market)
    assert "error" not in result
    assert result["value"] < 0.5
    assert result["verdict"] == "Very defensive"


def test_beta_inverse():
    stock, market = _random_paired(BETA_MIN_OBS + 50, beta_target=-0.5)
    result = compute_beta(stock, market)
    assert "error" not in result
    assert result["value"] < 0
    assert result["verdict"] == "Inverse"


def test_beta_insufficient_data():
    stock, market = _random_paired(BETA_MIN_OBS - 2, beta_target=1.0)
    result = compute_beta(stock, market)
    assert result.get("error") == "insufficient_data"


def test_beta_missing_overlap():
    stock  = [("2024-01-01", 100.0), ("2024-01-02", 101.0)]
    market = [("2025-05-01", 100.0), ("2025-05-02", 101.0)]
    result = compute_beta(stock, market)
    assert result.get("error") == "insufficient_data"


def test_beta_flat_market():
    n     = BETA_MIN_OBS + 10
    dates = [f"2024-{(i // 28 + 1):02d}-{(i % 28 + 1):02d}" for i in range(n)]
    stock  = [(d, 100.0 + i * 0.5) for i, d in enumerate(dates)]
    market = [(d, 100.0) for d in dates]
    result = compute_beta(stock, market)
    assert result.get("error") == "market_flat"


def test_beta_uses_at_most_window_days():
    stock, market = _random_paired(BETA_WINDOW + 50, beta_target=1.0)
    result = compute_beta(stock, market)
    assert "error" not in result
    assert result["window_days"] <= BETA_WINDOW


def test_beta_returns_benchmark_name():
    stock, market = _random_paired(BETA_MIN_OBS + 10, beta_target=1.0)
    result = compute_beta(stock, market)
    assert "error" not in result
    assert result.get("benchmark") == "NIFTY 50"


def test_beta_returns_window_days():
    stock, market = _random_paired(BETA_MIN_OBS + 10, beta_target=1.0)
    result = compute_beta(stock, market)
    assert "error" not in result
    assert isinstance(result["window_days"], int)
    assert result["window_days"] >= BETA_MIN_OBS
