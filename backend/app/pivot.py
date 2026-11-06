"""Classic (Floor) pivot points and entry/exit/stop suggestions for intraday trading.

Pure functions, no I/O, no side effects. All prices are integers in paise.

Classic pivot formulas using the previous session's High, Low, Close:
  PP = (H + L + C) / 3
  R1 = 2*PP - L       S1 = 2*PP - H
  R2 = PP + (H - L)   S2 = PP - (H - L)
  R3 = H + 2*(PP - L) S3 = L - 2*(H - PP)

Verification (all values in paise, i.e. rupees * 100):
  H=17494, L=16574, C=17355 must produce
  PP=17141, R1=17708, R2=18061, R3=18628, S1=16788, S2=16221, S3=15868.
"""

ENTRY_ZONE_PCT = 0.005   # within 0.5% of a support level = "near it"
MIN_RR         = 1.5     # minimum risk-reward to call a setup valid


def compute_pivot(high: int, low: int, close: int) -> dict | None:
    """Classic pivot levels from the previous session's High, Low, Close (all in paise).

    Returns None for invalid inputs (non-positive, or high < low).
    Returns a dict with int paise values: pp, r1, r2, r3, s1, s2, s3.
    """
    try:
        h, l, c = int(round(high)), int(round(low)), int(round(close))
    except (TypeError, ValueError):
        return None
    if h <= 0 or l <= 0 or c <= 0 or h < l:
        return None
    pp = round((h + l + c) / 3)
    r1 = round(2 * pp - l)
    s1 = round(2 * pp - h)
    r2 = pp + (h - l)
    s2 = pp - (h - l)
    r3 = h + 2 * (pp - l)
    s3 = l - 2 * (h - pp)
    return {"pp": pp, "r1": r1, "r2": r2, "r3": r3, "s1": s1, "s2": s2, "s3": s3}


def compute_entry_exit(levels: dict | None, ltp: int | None, tick: int, vwap: int | None = None) -> dict:
    """Suggests an entry, stop-loss, and target from pivot levels and the current price.

    Always returns concrete prices based on where ltp sits relative to the pivot levels.
    valid=True when R/R >= MIN_RR; valid=False adds a caution note but still shows numbers.

    Returns a dict with:
      entry, stop_loss, target — int paise
      risk_reward              — float
      reason                   — plain-language string shown to the user
      valid                    — True when R/R >= MIN_RR (quality indicator, not a gate)
      type                     — "support_buy" or "breakout_buy"
    """
    if levels is None or ltp is None or ltp <= 0 or tick <= 0:
        return _no_setup("No price or level data")

    pp           = levels["pp"]
    r1, r2, r3   = levels["r1"], levels["r2"], levels["r3"]
    s1, s2, s3   = levels["s1"], levels["s2"], levels["s3"]

    def _r(p: int) -> str:
        return f"₹{p / 100:,.2f}"

    if ltp > r3:
        entry  = r3
        target = r3 + (r3 - r2)
        stop   = r2 - tick
        type_  = "breakout_buy"
        label  = f"Extended above R3 — wait for pullback to R3 ({_r(r3)}); target ₹{(r3+(r3-r2))/100:,.2f}"
    elif ltp > r2:
        entry  = ltp
        target = r3
        stop   = r2 - tick
        type_  = "breakout_buy"
        label  = f"Above R2; target R3 ({_r(r3)}); stop below R2 ({_r(r2)})"
    elif ltp > r1:
        entry  = ltp
        target = r2
        stop   = r1 - tick
        type_  = "breakout_buy"
        label  = f"Above R1; target R2 ({_r(r2)}); stop below R1 ({_r(r1)})"
    elif ltp > pp:
        entry  = ltp
        target = r1
        stop   = pp - tick
        type_  = "breakout_buy"
        label  = f"Above PP; target R1 ({_r(r1)}); stop below PP ({_r(pp)})"
    elif ltp > s1:
        entry  = s1
        target = pp
        stop   = s2 - tick
        type_  = "support_buy"
        label  = f"Wait for S1 ({_r(s1)}); target PP ({_r(pp)}); stop below S2 ({_r(s2)})"
    elif ltp > s2:
        entry  = s1
        target = pp
        stop   = s2 - tick
        type_  = "support_buy"
        label  = f"Near S1 ({_r(s1)}); target PP ({_r(pp)}); stop below S2 ({_r(s2)})"
    elif ltp > s3:
        entry  = s2
        target = s1
        stop   = s3 - tick
        type_  = "support_buy"
        label  = f"Near S2 ({_r(s2)}); target S1 ({_r(s1)}); stop below S3 ({_r(s3)})"
    else:
        entry  = s3
        target = s2
        stop   = s3 - (s2 - s3)
        type_  = "support_buy"
        label  = f"Below S3 — high risk; entry S3 ({_r(s3)}); target S2 ({_r(s2)})"

    if stop <= 0 or entry <= stop:
        return _no_setup("Levels too compressed to compute a stop-loss")

    rr = (target - entry) / (entry - stop)
    valid = rr >= MIN_RR
    rr_note = "" if valid else f" ⚠ R/R {rr:.1f} below {MIN_RR} — use caution"
    vwap_note = "; price above VWAP" if vwap and vwap < entry else ""

    return {
        "entry": entry, "stop_loss": stop, "target": target,
        "risk_reward": round(rr, 2), "valid": valid,
        "reason": label + rr_note + vwap_note,
        "type": type_,
    }


def _no_setup(reason: str) -> dict:
    return {"entry": None, "stop_loss": None, "target": None,
            "risk_reward": None, "valid": False, "reason": reason, "type": None}
