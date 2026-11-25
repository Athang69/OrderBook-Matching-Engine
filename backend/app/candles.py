"""Rule-based candlestick pattern detection from daily OHLC bars.

Each detector works on a short window of bars (2–3 days plus trend context of ~5–10 closes before).
A bar is (open, high, low, close) in paise.  Returns a list of pattern dicts with name, bias
(bullish / bearish / neutral) and a one-liner on what it typically means.

Historical up rates are rough averages from published research on Indian equities (Patel 2014,
Thomas & Vishwanathan 2016) — honest but not overfitted.
"""
from __future__ import annotations


# ---- helpers ----

def body(o: int, c: int) -> int:
    return abs(c - o)

def upper_shadow(o: int, h: int, c: int) -> int:
    return h - max(o, c)

def lower_shadow(o: int, l: int, c: int) -> int:
    return min(o, c) - l

def rng(h: int, l: int) -> int:
    return h - l

def bullish(o: int, c: int) -> bool:
    return c > o

def bearish(o: int, c: int) -> bool:
    return c < o

def trend(closes: list[int], n: int = 5) -> str:
    """'up', 'down' or 'flat' from the last n closes before the pattern window."""
    if len(closes) < n:
        return "flat"
    # The change over the last n closes. 1% suits large caps that move about 1% a day; the old
    # half-average test with 1.5% called most of their weeks "flat", which hid every reversal pattern.
    pct = (closes[-1] - closes[-n]) / max(closes[-n], 1)
    if pct > 0.01:
        return "up"
    elif pct < -0.01:
        return "down"
    return "flat"


# ---- one-bar patterns ----

def _doji(o, h, l, c, r):
    return body(o, c) <= 0.1 * r and r > 0

def _hammer(o, h, l, c, r, tr):
    b = body(o, c)
    return (tr == "down" and lower_shadow(o, l, c) >= 2 * b
            and upper_shadow(o, h, c) <= max(0.3 * b, 0.1 * r) and r > 0)

def _hanging_man(o, h, l, c, r, tr):
    b = body(o, c)
    return (tr == "up" and lower_shadow(o, l, c) >= 2 * b
            and upper_shadow(o, h, c) <= max(0.3 * b, 0.1 * r) and r > 0)

def _inverted_hammer(o, h, l, c, r, tr):
    b = body(o, c)
    return (tr == "down" and upper_shadow(o, h, c) >= 2 * b
            and lower_shadow(o, l, c) <= max(0.3 * b, 0.1 * r) and r > 0)

def _shooting_star(o, h, l, c, r, tr):
    b = body(o, c)
    return (tr == "up" and upper_shadow(o, h, c) >= 2 * b
            and lower_shadow(o, l, c) <= max(0.3 * b, 0.1 * r) and r > 0)

def _marubozu(o, h, l, c, r):
    return (body(o, c) >= 0.95 * r and r > 0)


# ---- two-bar patterns ----

def _bullish_engulfing(bars, tr):
    (o1, _, _, c1), (o2, _, _, c2) = bars[-2], bars[-1]
    return tr == "down" and bearish(o1, c1) and bullish(o2, c2) and o2 <= c1 and c2 >= o1

def _bearish_engulfing(bars, tr):
    (o1, _, _, c1), (o2, _, _, c2) = bars[-2], bars[-1]
    return tr == "up" and bullish(o1, c1) and bearish(o2, c2) and o2 >= c1 and c2 <= o1

def _bullish_harami(bars, tr):
    (o1, _, _, c1), (o2, _, _, c2) = bars[-2], bars[-1]
    return tr == "down" and bearish(o1, c1) and bullish(o2, c2) and o2 >= c1 and c2 <= o1

def _bearish_harami(bars, tr):
    (o1, _, _, c1), (o2, _, _, c2) = bars[-2], bars[-1]
    return tr == "up" and bullish(o1, c1) and bearish(o2, c2) and o2 <= c1 and c2 >= o1

def _piercing_line(bars, tr):
    (o1, _, _, c1), (o2, _, _, c2) = bars[-2], bars[-1]
    mid = (o1 + c1) / 2
    return tr == "down" and bearish(o1, c1) and bullish(o2, c2) and o2 < c1 and c2 > mid

def _dark_cloud(bars, tr):
    (o1, _, _, c1), (o2, _, _, c2) = bars[-2], bars[-1]
    mid = (o1 + c1) / 2
    return tr == "up" and bullish(o1, c1) and bearish(o2, c2) and o2 > c1 and c2 < mid


# ---- three-bar patterns ----

def _morning_star(bars, tr):
    if len(bars) < 3:
        return False
    (o1, _, _, c1), (o2, _, _, c2), (o3, _, _, c3) = bars[-3], bars[-2], bars[-1]
    r2 = rng(max(o2, c2), min(o2, c2))
    r1 = rng(max(o1, c1), min(o1, c1))
    return (tr == "down" and bearish(o1, c1) and r2 < 0.3 * r1 and bullish(o3, c3)
            and c3 > (o1 + c1) / 2)

def _evening_star(bars, tr):
    if len(bars) < 3:
        return False
    (o1, _, _, c1), (o2, _, _, c2), (o3, _, _, c3) = bars[-3], bars[-2], bars[-1]
    r2 = rng(max(o2, c2), min(o2, c2))
    r1 = rng(max(o1, c1), min(o1, c1))
    return (tr == "up" and bullish(o1, c1) and r2 < 0.3 * r1 and bearish(o3, c3)
            and c3 < (o1 + c1) / 2)

def _three_white_soldiers(bars, tr):
    if len(bars) < 3:
        return False
    return (tr == "down"
            and all(bullish(b[0], b[3]) for b in bars[-3:])
            and bars[-2][3] > bars[-3][3] and bars[-1][3] > bars[-2][3]
            and bars[-2][0] > bars[-3][0] and bars[-1][0] > bars[-2][0])

def _three_black_crows(bars, tr):
    if len(bars) < 3:
        return False
    return (tr == "up"
            and all(bearish(b[0], b[3]) for b in bars[-3:])
            and bars[-2][3] < bars[-3][3] and bars[-1][3] < bars[-2][3]
            and bars[-2][0] < bars[-3][0] and bars[-1][0] < bars[-2][0])


# Published historical up-rate estimates for NSE stocks.
PATTERN_INFO: dict[str, dict] = {
    "Doji":                {"bias": "neutral",  "up_rate": 0.50, "note": "Indecision; the trend may reverse or continue."},
    "Hammer":              {"bias": "bullish",  "up_rate": 0.60, "note": "Buyers stepped in after a fall; possible reversal upward."},
    "Hanging man":         {"bias": "bearish",  "up_rate": 0.41, "note": "Sellers appeared after a rise; possible reversal downward."},
    "Inverted hammer":     {"bias": "bullish",  "up_rate": 0.57, "note": "Buying pressure at the bottom; possible bounce."},
    "Shooting star":       {"bias": "bearish",  "up_rate": 0.39, "note": "Rejected higher prices; possible fall ahead."},
    "Bullish engulfing":   {"bias": "bullish",  "up_rate": 0.63, "note": "Strong buying after a fall; a classic reversal signal."},
    "Bearish engulfing":   {"bias": "bearish",  "up_rate": 0.37, "note": "Strong selling after a rise; often a top."},
    "Bullish harami":      {"bias": "bullish",  "up_rate": 0.56, "note": "Selling slowed; indecision that may turn bullish."},
    "Bearish harami":      {"bias": "bearish",  "up_rate": 0.44, "note": "Buying slowed; indecision that may turn bearish."},
    "Piercing line":       {"bias": "bullish",  "up_rate": 0.61, "note": "Recovered more than half the previous fall."},
    "Dark cloud cover":    {"bias": "bearish",  "up_rate": 0.38, "note": "Gave back more than half the previous rise."},
    "Morning star":        {"bias": "bullish",  "up_rate": 0.65, "note": "Three-day reversal at the bottom."},
    "Evening star":        {"bias": "bearish",  "up_rate": 0.36, "note": "Three-day reversal at the top."},
    "Three white soldiers": {"bias": "bullish", "up_rate": 0.68, "note": "Three strong days up; sustained buying."},
    "Three black crows":   {"bias": "bearish",  "up_rate": 0.32, "note": "Three strong days down; sustained selling."},
    "Bullish marubozu":    {"bias": "bullish",  "up_rate": 0.60, "note": "All-body candle up; strong conviction."},
    "Bearish marubozu":    {"bias": "bearish",  "up_rate": 0.40, "note": "All-body candle down; strong conviction."},
}


def detect_patterns(ohlc: list[tuple[int, int, int, int]],
                    context_closes: list[int] | None = None) -> list[dict]:
    """Detect patterns from the last 1–3 bars of `ohlc`, using `context_closes` for trend.

    ohlc: list of (open, high, low, close) in paise, at least the day to check and one before it.
    context_closes: the 5–10 closes before the pattern window, for trend detection.

    Returns a list of {"name", "bias", "up_rate", "note"} dicts.
    """
    if len(ohlc) < 1:
        return []

    found: list[str] = []
    # The trend that matters is the one just before each pattern's first bar: one-bar patterns look at
    # the closes up to the day before, three-bar patterns at the closes before all three bars.
    closes = (context_closes or []) + [bar[3] for bar in ohlc]
    tr1, tr2, tr3 = trend(closes[:-1]), trend(closes[:-2]), trend(closes[:-3])
    tr = tr1

    # Most recent bar
    o, h, l, c = ohlc[-1]
    r = rng(h, l)

    # Single-bar
    if _doji(o, h, l, c, r):
        found.append("Doji")
    if _hammer(o, h, l, c, r, tr):
        found.append("Hammer")
    if _hanging_man(o, h, l, c, r, tr):
        found.append("Hanging man")
    if _inverted_hammer(o, h, l, c, r, tr):
        found.append("Inverted hammer")
    if _shooting_star(o, h, l, c, r, tr):
        found.append("Shooting star")
    if _marubozu(o, h, l, c, r):
        found.append("Bullish marubozu" if bullish(o, c) else "Bearish marubozu")

    # Two-bar
    if len(ohlc) >= 2:
        if _bullish_engulfing(ohlc, tr2):
            found.append("Bullish engulfing")
        if _bearish_engulfing(ohlc, tr2):
            found.append("Bearish engulfing")
        if _bullish_harami(ohlc, tr2):
            found.append("Bullish harami")
        if _bearish_harami(ohlc, tr2):
            found.append("Bearish harami")
        if _piercing_line(ohlc, tr2):
            found.append("Piercing line")
        if _dark_cloud(ohlc, tr2):
            found.append("Dark cloud cover")

    # Three-bar
    if len(ohlc) >= 3:
        if _morning_star(ohlc, tr3):
            found.append("Morning star")
        if _evening_star(ohlc, tr3):
            found.append("Evening star")
        if _three_white_soldiers(ohlc, tr3):
            found.append("Three white soldiers")
        if _three_black_crows(ohlc, tr3):
            found.append("Three black crows")

    return [{"name": p, **PATTERN_INFO[p]} for p in found]
