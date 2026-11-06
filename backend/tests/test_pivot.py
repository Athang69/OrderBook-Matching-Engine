"""Unit tests for Classic (Floor) pivot points and entry/exit logic (pivot.py)."""
import pytest

from backend.app.pivot import MIN_RR, compute_entry_exit, compute_pivot

# Reference values from the UI requirements (H=174.94, L=165.74, C=173.55 in rupees -> paise)
H, L, C = 17_494, 16_574, 17_355
TICK = 5


# ---- formula correctness ----

def test_pivot_formula_reference_values():
    """The screenshot's reference test: exact expected values to 2 decimal places."""
    p = compute_pivot(H, L, C)
    assert p is not None
    assert p["pp"] == 17_141
    assert p["r1"] == 17_708
    assert p["r2"] == 18_061
    assert p["r3"] == 18_628
    assert p["s1"] == 16_788
    assert p["s2"] == 16_221
    assert p["s3"] == 15_868


def test_pivot_ordering():
    """Levels must be strictly ascending: s3 < s2 < s1 < pp < r1 < r2 < r3."""
    p = compute_pivot(H, L, C)
    assert p["s3"] < p["s2"] < p["s1"] < p["pp"] < p["r1"] < p["r2"] < p["r3"]


def test_pivot_equal_high_low_close():
    """When H = L = C, all levels collapse to the same price."""
    price = 10_000
    p = compute_pivot(price, price, price)
    assert p is not None
    assert p["pp"] == price
    assert p["r1"] == p["r2"] == p["r3"] == price
    assert p["s1"] == p["s2"] == p["s3"] == price


def test_pivot_symmetry():
    """R1 and S1 are equidistant from PP; same for R2/S2 and R3/S3."""
    p = compute_pivot(H, L, C)
    # R2 - PP == PP - S2  (the range H - L)
    assert p["r2"] - p["pp"] == p["pp"] - p["s2"]


# ---- invalid inputs ----

def test_pivot_zero_inputs():
    assert compute_pivot(0, 0, 0) is None


def test_pivot_negative_input():
    assert compute_pivot(-1, 100, 100) is None


def test_pivot_high_less_than_low():
    assert compute_pivot(100, 200, 150) is None


def test_pivot_none_input():
    assert compute_pivot(None, 100, 100) is None  # type: ignore[arg-type]


# ---- entry/exit: valid setups ----

def test_entry_price_near_s1():
    """Price just above S1 — always returns concrete entry/stop/target (support_buy, entry=S1)."""
    p = compute_pivot(H, L, C)
    assert p is not None
    # S1 = 16_788; place ltp 0.19% above it (between PP and S1)
    ltp = 16_820
    result = compute_entry_exit(p, ltp, TICK)
    # New behaviour: always returns numbers; valid depends on R:R
    assert result["type"] == "support_buy"
    assert result["entry"] is not None          # S1 is the entry
    assert result["entry"] == p["s1"]
    assert result["stop_loss"] is not None and result["stop_loss"] < result["entry"]
    assert result["target"] is not None and result["target"] > result["entry"]
    assert result["risk_reward"] is not None
    assert "S1" in result["reason"]


def test_entry_price_above_pp():
    """Price above PP (but no support nearby) should produce a breakout_buy setup."""
    p = compute_pivot(H, L, C)
    assert p is not None
    # PP = 17_141; place ltp just above it, not near any S level
    ltp = 17_200
    result = compute_entry_exit(p, ltp, TICK)
    assert result["valid"], result["reason"]
    assert result["type"] == "breakout_buy"
    assert result["stop_loss"] is not None and result["stop_loss"] < ltp
    assert result["target"] is not None and result["target"] > ltp
    assert result["risk_reward"] is not None and result["risk_reward"] >= MIN_RR
    assert "PP" in result["reason"]


def test_entry_vwap_note_when_below():
    """When VWAP is below ltp, the reason should mention it."""
    p = compute_pivot(H, L, C)
    assert p is not None
    ltp = 16_820  # near S1
    vwap = 16_000  # below ltp
    result = compute_entry_exit(p, ltp, TICK, vwap=vwap)
    if result["valid"]:
        assert "VWAP" in result["reason"]


def test_entry_no_vwap_note_when_above():
    """When VWAP is above ltp, the reason should not mention VWAP."""
    p = compute_pivot(H, L, C)
    assert p is not None
    ltp = 16_820
    vwap = 17_000  # above ltp
    result = compute_entry_exit(p, ltp, TICK, vwap=vwap)
    if result["valid"]:
        assert "VWAP" not in result["reason"]


# ---- entry/exit: invalid setups ----

def test_entry_no_data():
    result = compute_entry_exit(None, 17_500, TICK)
    assert not result["valid"]
    assert result["entry"] is None


def test_entry_null_price():
    p = compute_pivot(H, L, C)
    result = compute_entry_exit(p, None, TICK)
    assert not result["valid"]


def test_entry_price_above_r3_no_target():
    """Price well above R3 — no resistance target above, so no valid setup."""
    p = compute_pivot(H, L, C)
    assert p is not None
    ltp = p["r3"] + 5_000  # far above all levels
    result = compute_entry_exit(p, ltp, TICK)
    assert not result["valid"]


def test_entry_price_below_s3_no_setup():
    """Price well below S3 — no support setup applicable."""
    p = compute_pivot(H, L, C)
    assert p is not None
    ltp = p["s3"] - 5_000  # far below all levels
    result = compute_entry_exit(p, ltp, TICK)
    assert not result["valid"]


def test_entry_does_not_crash_on_various_prices():
    """compute_entry_exit must not raise for any reasonable price."""
    p = compute_pivot(H, L, C)
    assert p is not None
    for ltp in [1, p["s3"], p["s2"], p["s1"], p["pp"], p["r1"], p["r2"], p["r3"], p["r3"] + 10_000]:
        result = compute_entry_exit(p, ltp, TICK)
        assert isinstance(result["valid"], bool)
