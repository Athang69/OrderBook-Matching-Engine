"""Tests for the candlestick pattern detection module."""
import pytest
from backend.app.candles import detect_patterns, trend


# ── trend() ──────────────────────────────────────────────────────────────────

def test_trend_returns_down_for_declining_series():
    # First half avg > second half avg by > 1.5%
    ctx = [1250.0, 1240.0, 1230.0, 1220.0, 1210.0]
    assert trend(ctx) == "down"


def test_trend_returns_up_for_rising_series():
    ctx = [1200.0, 1210.0, 1220.0, 1230.0, 1250.0]
    assert trend(ctx) == "up"


def test_trend_returns_flat_for_sideways():
    ctx = [1200.0, 1200.0, 1200.0, 1200.0, 1200.0]
    assert trend(ctx) == "flat"


def test_trend_uses_only_last_n_items():
    # Long list: first 5 items are rising steeply (would give "up" if used),
    # but the LAST 5 items are declining → should return "down".
    ctx = [1000.0, 1050.0, 1100.0, 1150.0, 1200.0,  # rising (not used)
           1250.0, 1240.0, 1230.0, 1220.0, 1210.0]  # declining (used)
    assert trend(ctx) == "down"


def test_trend_fewer_than_n_items_is_flat():
    assert trend([1200.0, 1190.0, 1180.0], n=5) == "flat"


# ── single-bar patterns ───────────────────────────────────────────────────────

def test_doji_detected_with_tiny_body():
    # Range=20, body=1 → body/range=0.05 ≤ 0.10
    ohlc = [(1300.0, 1310.0, 1290.0, 1301.0)]
    result = detect_patterns(ohlc, [])
    names = [p["name"] for p in result]
    assert "Doji" in names


def test_no_doji_when_body_is_large():
    ohlc = [(1300.0, 1320.0, 1298.0, 1318.0)]  # body=18, range=22 → 82% → not a doji
    result = detect_patterns(ohlc, [])
    names = [p["name"] for p in result]
    assert "Doji" not in names


# ── trend-dependent patterns ──────────────────────────────────────────────────

def _downtrend_ctx():
    return [1250.0, 1240.0, 1230.0, 1220.0, 1210.0, 1200.0, 1190.0, 1180.0, 1170.0, 1160.0]


def _uptrend_ctx():
    return [1150.0, 1160.0, 1170.0, 1180.0, 1190.0, 1200.0, 1210.0, 1220.0, 1230.0, 1250.0]


def test_bullish_engulfing_requires_downtrend():
    # Day 1 bearish, day 2 bullish and engulfs
    ohlc = [
        (1170.0, 1172.0, 1162.0, 1163.0),
        (1160.0, 1175.0, 1159.0, 1174.0),
    ]
    with_down = detect_patterns(ohlc, _downtrend_ctx())
    with_up   = detect_patterns(ohlc, _uptrend_ctx())
    assert any(p["name"] == "Bullish engulfing" for p in with_down)
    assert not any(p["name"] == "Bullish engulfing" for p in with_up)


def test_shooting_star_requires_uptrend():
    # Small bearish body at bottom, long upper wick, no lower wick
    # O=1250, C=1248 (body=2), H=1270 (upper shadow=20), L=1248 (no lower shadow)
    ohlc = [(1250.0, 1270.0, 1248.0, 1248.0)]
    with_up   = detect_patterns(ohlc, _uptrend_ctx())
    with_down = detect_patterns(ohlc, _downtrend_ctx())
    assert any(p["name"] == "Shooting star" for p in with_up)
    assert not any(p["name"] == "Shooting star" for p in with_down)


def test_three_white_soldiers_in_downtrend():
    ohlc = [
        (1155.0, 1162.0, 1154.0, 1161.0),
        (1160.0, 1168.0, 1159.0, 1167.0),
        (1166.0, 1174.0, 1165.0, 1173.0),
    ]
    result = detect_patterns(ohlc, _downtrend_ctx())
    names = [p["name"] for p in result]
    assert "Three white soldiers" in names


def test_pattern_dict_has_required_keys():
    ohlc = [(1300.0, 1310.0, 1290.0, 1301.0)]  # doji
    result = detect_patterns(ohlc, [])
    for p in result:
        assert "name" in p and p["name"]
        assert "bias" in p and p["bias"] in ("bullish", "bearish", "neutral")
        assert "up_rate" in p
        assert "note" in p


def test_empty_bars_returns_empty():
    assert detect_patterns([], []) == []
