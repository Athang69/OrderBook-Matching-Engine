"""Intraday recommendation: buy, sell short, or stay out, from today's live trading and your own view.

Everything comes from memory (the live market data), with nothing downloaded during a request, so a
recommendation for every chosen stock takes well under a millisecond and can be refreshed every second.

Three signals from the live market, each between -1 (strong sell) and +1 (strong buy):
  momentum  the price change over the last minute, compared with the stock's normal one-minute moves today
  vwap      the last price above or below today's volume-weighted average price
  flow      shares bought by buyers who paid up, against shares sold by sellers who gave way, over
            the last five minutes (each trade is a buy if its price rose, a sell if it fell)

Their weighted average is the model's score. Your confidence that the stock will rise today, which
you give after reading its news (50% means no view), becomes your view between -1 and +1. The final
score is 60% model and 40% your view. Its sign is the direction, and a stock is a trade when the
final score is at least 0.25 either way.
"""
import math

WEIGHTS = {"momentum": 0.40, "vwap": 0.30, "flow": 0.30}
MODEL_WEIGHT = 0.6
VIEW_WEIGHT = 0.4
TRADE_THRESHOLD = 0.25
MOMENTUM_SECONDS = 60
WINDOW_SECONDS = 300  # how far back trade flow looks
MIN_MINUTES = 10  # minutes of trading today before a stock gets a signal
MAX_FLOW_TRADES = 50
HOLD_MINUTES = 15  # stop-loss and target are sized for a 15-minute hold
STOP_MOVES = 1.5  # the stop-loss sits 1.5 typical 15-minute moves away
REWARD_TO_RISK = 2.0  # the target is twice as far away as the stop-loss
QUOTE_MAX_AGE = 10  # seconds; an older best bid or offer is not used as the entry


def view_from_confidence(confidence_pct: float) -> float:
    """Your confidence that the price will rise (0 to 100) as a view from -1 (sure it falls) to +1."""
    return max(-1.0, min(1.0, (confidence_pct - 50) / 50))


def compute_signals(view: dict, now: float) -> dict | None:
    """The three signals for one stock, or None if there is not enough trading today yet."""
    ltp, sigma, reference = view["ltp"], view["sigma"], view["reference"]
    if ltp is None or sigma is None or reference is None or view["minutes"] < MIN_MINUTES:
        return None

    ref_time, ref_price = reference  # the price about a minute ago
    elapsed_minutes = max(1 / 60, (now - ref_time) / 60)
    momentum = math.tanh(math.log(ltp / ref_price) / (sigma * math.sqrt(elapsed_minutes)) / 2)

    vwap = view["vwap"] or ltp
    vwap_signal = math.tanh(math.log(ltp / vwap) / (sigma * math.sqrt(WINDOW_SECONDS / 60)))

    bought = sold = 0
    for trade in view["trades"][:MAX_FLOW_TRADES]:  # newest first
        if trade["side"] == "BUY":
            bought += trade["qty"]
        elif trade["side"] == "SELL":
            sold += trade["qty"]
    flow = (bought - sold) / (bought + sold) if bought + sold else 0.0

    signals = {"momentum": momentum, "vwap": vwap_signal, "flow": flow}
    score = sum(WEIGHTS[name] * value for name, value in signals.items())
    return {"signals": signals, "score": score, "sigma": sigma, "vwap": vwap}


def recommend_intraday(views: dict[str, dict], rules: dict[str, tuple[int, int, int]], confidences: dict[str, float],
                       budget: int, leverage: int, session: dict, now: float) -> dict:
    """`rules` is (tick, lower band, upper band) per stock. `confidences` is your confidence, 0 to 100, per
    stock. `budget` is the margin money to use, in paise; positions can be `leverage` times that."""
    rows = [_row(symbol, view, rules[symbol], confidences.get(symbol, 50.0), session, now)
            for symbol, view in views.items()]

    picks = [r for r in rows if r["action"] in ("BUY", "SELL")]
    total = sum(r["confidence"] for r in picks)
    for row in picks:
        share = budget * row["confidence"] / total
        quantity = int(share * leverage // row["entry"])
        row["quantity"] = quantity
        row["position_value"] = quantity * row["entry"]
        row["margin"] = -(-row["position_value"] // leverage)  # rounded up
        row["max_loss"] = quantity * row["risk_per_share"]
        row["max_gain"] = quantity * row["reward_per_share"]
        if quantity == 0:
            row["note"] += " Its share of the money is less than one share's margin."

    order = {"BUY": 0, "SELL": 0, "NO_TRADE": 1, "WAIT": 2}
    rows.sort(key=lambda r: (order[r["action"]], -r["confidence"]))
    traded = [r for r in picks if r["quantity"] > 0]
    return {
        "inputs": {"symbols": list(views), "confidences": {s: confidences.get(s, 50.0) for s in views}, "budget": budget},
        "session": {"state": session["state"], "intraday_open": session["intraday_open"], "label": session["label"]},
        "stocks": rows,
        "totals": {
            "trades": len(traded),
            "margin": sum(r["margin"] for r in traded),
            "exposure": sum(r["position_value"] for r in traded),
            "max_loss": sum(r["max_loss"] for r in traded),
            "max_gain": sum(r["max_gain"] for r in traded),
        },
        "method": {"weights": WEIGHTS, "model_weight": MODEL_WEIGHT, "view_weight": VIEW_WEIGHT,
                   "threshold": TRADE_THRESHOLD, "momentum_seconds": MOMENTUM_SECONDS, "window_seconds": WINDOW_SECONDS,
                   "min_minutes": MIN_MINUTES, "hold_minutes": HOLD_MINUTES, "stop_moves": STOP_MOVES,
                   "reward_to_risk": REWARD_TO_RISK, "leverage": leverage},
        "as_of": now,
    }


def _row(symbol: str, view: dict, rules: tuple[int, int, int], confidence_pct: float, session: dict, now: float) -> dict:
    tick, lower, upper = rules
    yours = view_from_confidence(confidence_pct)
    bid, ask = _fresh(view, "bid", now), _fresh(view, "ask", now)
    row = {"symbol": symbol, "action": "WAIT", "confidence": 0.0, "score": 0.0, "model_score": None,
           "your_confidence": confidence_pct, "your_view": round(yours, 3), "signals": None, "agree": 0,
           "ltp": view["ltp"], "vwap": view["vwap"], "best_bid": bid, "best_ask": ask, "entry": None,
           "stop_loss": None, "target": None, "risk_per_share": 0, "reward_per_share": 0, "quantity": 0,
           "position_value": 0, "margin": 0, "max_loss": 0, "max_gain": 0,
           "note": f"Not enough trading today yet: the signals need {MIN_MINUTES} minutes of prices."}
    result = compute_signals(view, now)
    if result is not None:
        row.update({"model_score": round(result["score"], 4), "vwap": round(result["vwap"]),
                    "signals": {name: round(value, 3) for name, value in result["signals"].items()}})
    if not session["intraday_open"]:
        row["note"] = ("Intraday trading is closed for today (new intraday positions stop at 3:20 pm)."
                       if session["state"] == "OPEN" else f"{session['label']}: intraday trades can be placed from 9:15 am.")
        return row
    if result is None:
        return row

    score = MODEL_WEIGHT * result["score"] + VIEW_WEIGHT * yours
    direction = 1 if score > 0 else -1
    agree = sum(1 for value in result["signals"].values() if value * direction > 0)
    row.update({"score": round(score, 4), "confidence": round(abs(score), 4), "agree": agree})
    model_text = f"live signals {result['score']:+.2f}"
    view_text = "no view of yours" if yours == 0 else f"your view {yours:+.2f}"
    if abs(score) < TRADE_THRESHOLD:
        row["action"] = "NO_TRADE"
        row["note"] = f"Final score {score:+.2f} ({model_text}, {view_text}) is not strong enough; a trade needs ±{TRADE_THRESHOLD:.2f}."
        return row

    # Buy at the best offer, or sell short at the best bid.
    entry = (ask if direction > 0 else bid) or view["ltp"]
    move = result["sigma"] * math.sqrt(HOLD_MINUTES) * entry
    stop_distance = max(2 * tick, _to_tick(STOP_MOVES * move, tick))
    target_distance = max(tick, _to_tick(REWARD_TO_RISK * stop_distance, tick))
    stop = min(max(entry - direction * stop_distance, lower), upper)
    target = min(max(entry + direction * target_distance, lower), upper)
    disagree = yours * result["score"] < 0 and abs(yours) > 0.2
    row.update({
        "action": "BUY" if direction > 0 else "SELL",
        "entry": entry,
        "stop_loss": stop,
        "target": target,
        "risk_per_share": abs(entry - stop),
        "reward_per_share": abs(target - entry),
        "note": f"Final score {score:+.2f} ({model_text}, {view_text}); {agree} of 3 signals point "
                f"{'up' if direction > 0 else 'down'}." + (" Your view and the live signals disagree." if disagree else ""),
    })
    return row


def _fresh(view: dict, key: str, now: float) -> int | None:
    value = view[key]
    polled = view.get("polled_at")
    if value is None or polled is None or now - polled > QUOTE_MAX_AGE:
        return None
    return value


def _to_tick(amount: float, tick: int) -> int:
    return max(tick, int(round(amount / tick)) * tick)
