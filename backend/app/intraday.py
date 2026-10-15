"""Intraday recommendation: buy, sell short, or stay out, from the last few minutes of trading.

Everything comes from the simulator's memory, with nothing downloaded, so a recommendation for every
stock is worked out in a fraction of a millisecond and can be refreshed every second.

Four signals, each between -1 (strong sell) and +1 (strong buy):
  momentum  the price change over the last minute, compared with the stock's normal one-second swings
  vwap      the last price above or below the session's volume-weighted average price
  book      more quantity waiting to buy than to sell in the best five levels, or the reverse
  flow      more shares bought by buyers who crossed the spread than sold by sellers who did, recently

The score is their weighted average. Its sign gives the direction and its size, as a percentage, is
the confidence. A stock is a trade only if that confidence reaches the level the user asked for.
"""
import math
from collections import deque
from dataclasses import dataclass

WEIGHTS = {"momentum": 0.30, "vwap": 0.20, "book": 0.25, "flow": 0.25}
MOMENTUM_SECONDS = 60
WINDOW_SECONDS = 300  # how far back volatility and trade flow look
MIN_POINTS = 20  # seconds of price history needed before a stock gets a signal
MAX_FLOW_TRADES = 50
HOLD_SECONDS = 900  # stop-loss and target are sized for a 15-minute hold
STOP_MOVES = 1.5  # the stop-loss sits 1.5 typical 15-minute moves away
REWARD_TO_RISK = 2.0  # the target is twice as far away as the stop-loss


class RollingVolatility:
    """Standard deviation of one-second log returns over the last `size` samples, kept up to date
    in constant time per sample (running sums), so a request never has to loop over history."""

    def __init__(self, size: int = WINDOW_SECONDS):
        self._returns: deque = deque(maxlen=size)
        self._sum = 0.0
        self._squares = 0.0
        self._last: tuple[int, int] | None = None

    def add(self, t: int, price: int) -> None:
        if self._last is not None and t > self._last[0]:
            r = math.log(price / self._last[1]) / math.sqrt(t - self._last[0])
            if len(self._returns) == self._returns.maxlen:
                old = self._returns[0]
                self._sum -= old
                self._squares -= old * old
            self._returns.append(r)
            self._sum += r
            self._squares += r * r
        self._last = (t, price)

    def value(self) -> float:
        n = len(self._returns)
        if n < 2:
            return 1e-4
        variance = max(0.0, (self._squares - self._sum * self._sum / n) / (n - 1))
        return max(math.sqrt(variance), 1e-5)


@dataclass(frozen=True)
class StockRules:
    tick: int
    lower_band: int
    upper_band: int


def compute_signals(view: dict, now: float) -> dict | None:
    """The four signals for one stock, or None if there is not enough trading yet."""
    ltp = view["ltp"]
    if ltp is None or view["points"] < MIN_POINTS or not view["bids"] or not view["asks"]:
        return None

    sigma = view["sigma"]  # kept up to date as prices arrive; see RollingVolatility
    ref_time, ref_price = view["reference"]  # the price about a minute ago
    elapsed = max(1.0, now - ref_time)
    momentum = math.tanh(math.log(ltp / ref_price) / (sigma * math.sqrt(elapsed)) / 2)

    vwap = view["vwap"] or ltp
    vwap_signal = math.tanh(math.log(ltp / vwap) / (sigma * math.sqrt(WINDOW_SECONDS)))

    bid_qty = sum(level[1] for level in view["bids"])
    ask_qty = sum(level[1] for level in view["asks"])
    book = (bid_qty - ask_qty) / (bid_qty + ask_qty)

    bought = sold = 0
    for trade in view["trades"][:MAX_FLOW_TRADES]:  # newest first
        if trade["side"] == "BUY":
            bought += trade["qty"]
        else:
            sold += trade["qty"]
    flow = (bought - sold) / (bought + sold) if bought + sold else 0.0

    signals = {"momentum": momentum, "vwap": vwap_signal, "book": book, "flow": flow}
    score = sum(WEIGHTS[name] * value for name, value in signals.items())
    return {"signals": signals, "score": score, "sigma": sigma, "vwap": vwap}


def recommend_intraday(views: dict[str, dict], rules: dict[str, StockRules], confidence_pct: float, budget: int,
                       leverage: int, now: float) -> dict:
    """`budget` is the margin money to use, in paise. Positions can be `leverage` times that."""
    threshold = confidence_pct / 100
    rows = []
    for symbol, view in views.items():
        rows.append(_row(symbol, view, rules[symbol], threshold, now))

    picks = [r for r in rows if r["action"] in ("BUY", "SELL")]
    total_confidence = sum(r["confidence"] for r in picks)
    for row in picks:
        share = budget * row["confidence"] / total_confidence
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
        "inputs": {"symbols": list(views), "confidence": confidence_pct, "budget": budget},
        "stocks": rows,
        "totals": {
            "trades": len(traded),
            "margin": sum(r["margin"] for r in traded),
            "exposure": sum(r["position_value"] for r in traded),
            "max_loss": sum(r["max_loss"] for r in traded),
            "max_gain": sum(r["max_gain"] for r in traded),
        },
        "method": {"weights": WEIGHTS, "momentum_seconds": MOMENTUM_SECONDS, "window_seconds": WINDOW_SECONDS,
                   "hold_seconds": HOLD_SECONDS, "stop_moves": STOP_MOVES, "reward_to_risk": REWARD_TO_RISK,
                   "leverage": leverage},
        "as_of": now,
    }


def _row(symbol: str, view: dict, rules: StockRules, threshold: float, now: float) -> dict:
    row = {"symbol": symbol, "action": "WAIT", "confidence": 0.0, "score": 0.0, "signals": None, "agree": 0,
           "ltp": view["ltp"], "vwap": None, "best_bid": view["bids"][0][0] if view["bids"] else None,
           "best_ask": view["asks"][0][0] if view["asks"] else None, "entry": None, "stop_loss": None,
           "target": None, "risk_per_share": 0, "reward_per_share": 0, "quantity": 0, "position_value": 0,
           "margin": 0, "max_loss": 0, "max_gain": 0,
           "note": f"Not enough trading yet: needs {MIN_POINTS} seconds of prices and orders on both sides."}
    result = compute_signals(view, now)
    if result is None:
        return row

    score = result["score"]
    direction = 1 if score > 0 else -1
    row.update({
        "score": round(score, 4),
        "confidence": round(abs(score), 4),
        "signals": {name: round(value, 3) for name, value in result["signals"].items()},
        "agree": sum(1 for value in result["signals"].values() if value * direction > 0),
        "vwap": round(result["vwap"]),
    })
    if abs(score) < threshold:
        row["action"] = "NO_TRADE"
        row["note"] = f"Confidence {abs(score) * 100:.0f}% is below the {threshold * 100:g}% you asked for."
        return row

    # Buy at the best offer, or sell short at the best bid.
    entry = row["best_ask"] if direction > 0 else row["best_bid"]
    move = result["sigma"] * math.sqrt(HOLD_SECONDS) * entry
    stop_distance = max(2 * rules.tick, _to_tick(STOP_MOVES * move, rules.tick))
    target_distance = max(rules.tick, _to_tick(REWARD_TO_RISK * stop_distance, rules.tick))
    stop = min(max(entry - direction * stop_distance, rules.lower_band), rules.upper_band)
    target = min(max(entry + direction * target_distance, rules.lower_band), rules.upper_band)
    row.update({
        "action": "BUY" if direction > 0 else "SELL",
        "entry": entry,
        "stop_loss": stop,
        "target": target,
        "risk_per_share": abs(entry - stop),
        "reward_per_share": abs(target - entry),
        "note": f"{row['agree']} of 4 signals point {'up' if direction > 0 else 'down'}; "
                f"confidence {abs(score) * 100:.0f}% meets {threshold * 100:g}%.",
    })
    return row


def _to_tick(amount: float, tick: int) -> int:
    return max(tick, int(round(amount / tick)) * tick)
