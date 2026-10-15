"""In-memory market data: last price, day statistics, best five levels and recent trades."""
import threading
import time
from collections import deque

from .instruments import Instrument
from .intraday import MOMENTUM_SECONDS, RollingVolatility


class MarketData:
    def __init__(self, instruments: list[Instrument]):
        self._lock = threading.Lock()
        self._state: dict[str, dict] = {
            i.symbol: {
                "symbol": i.symbol,
                "ltp": None,  # last traded price in this session
                "prev_close": i.prev_close,
                "open": None,
                "high": None,
                "low": None,
                "volume": 0,
                "turnover": 0,  # sum of price x quantity, for the volume-weighted average price
                "trades": 0,
                "bids": [],
                "asks": [],
            }
            for i in instruments
        }
        self._tape: dict[str, deque] = {i.symbol: deque(maxlen=60) for i in instruments}
        self._history: dict[str, deque] = {i.symbol: deque(maxlen=1800) for i in instruments}
        self._volatility = {i.symbol: RollingVolatility() for i in instruments}
        self._dirty: set[str] = set()
        self._new_trades: list[dict] = []

    def on_trade(self, trade: dict) -> None:
        with self._lock:
            state = self._state[trade["symbol"]]
            price = trade["price"]
            state["ltp"] = price
            state["open"] = state["open"] or price
            state["high"] = price if state["high"] is None else max(state["high"], price)
            state["low"] = price if state["low"] is None else min(state["low"], price)
            state["volume"] += trade["qty"]
            state["turnover"] += price * trade["qty"]
            state["trades"] += 1
            self._tape[trade["symbol"]].appendleft(trade)
            self._new_trades.append(trade)
            self._dirty.add(trade["symbol"])

    def on_book(self, symbol: str, bids: list, asks: list) -> None:
        with self._lock:
            state = self._state[symbol]
            if state["bids"] != bids or state["asks"] != asks:
                state["bids"] = bids
                state["asks"] = asks
                self._dirty.add(symbol)

    def ltp(self, symbol: str) -> int | None:
        with self._lock:
            return self._state[symbol]["ltp"]

    def snapshot(self, symbol: str) -> dict:
        with self._lock:
            return dict(self._state[symbol])

    def snapshots(self) -> dict[str, dict]:
        with self._lock:
            return {symbol: dict(state) for symbol, state in self._state.items()}

    def tape(self, symbol: str, limit: int) -> list[dict]:
        with self._lock:
            return list(self._tape[symbol])[:limit]

    def history(self, symbol: str) -> list[list]:
        with self._lock:
            return [list(point) for point in self._history[symbol]]

    def intraday_view(self, symbols: list[str], seconds: int) -> dict[str, dict]:
        """What the intraday signals need, copied under one lock so it is consistent: last price,
        VWAP, best five levels, recent trades (newest first), the rolling one-second volatility,
        how many seconds of prices there are, and the price about a minute ago.

        Nothing here loops over the price history except a short walk back of about a minute."""
        now = time.time()
        cutoff = now - seconds
        with self._lock:
            view = {}
            for symbol in symbols:
                state = self._state[symbol]
                history = self._history[symbol]
                view[symbol] = {
                    "ltp": state["ltp"],
                    "vwap": state["turnover"] / state["volume"] if state["volume"] else None,
                    "bids": state["bids"],  # replaced, never changed in place, so sharing is safe
                    "asks": state["asks"],
                    "trades": [t for t in self._tape[symbol] if t["ts"] >= cutoff],
                    "sigma": self._volatility[symbol].value(),
                    "points": len(history),  # one price sample per second
                    "reference": _point_before(history, now - MOMENTUM_SECONDS),
                }
            return view

    def sample_history(self) -> None:
        """Records one price point per symbol; called once a second for the price chart."""
        now = int(time.time())
        with self._lock:
            for symbol, state in self._state.items():
                if state["ltp"] is not None:
                    self._history[symbol].append((now, state["ltp"]))
                    self._volatility[symbol].add(now, state["ltp"])

    def drain(self) -> tuple[dict[str, dict], list[dict]]:
        """Everything that changed since the last call, for the WebSocket broadcaster."""
        with self._lock:
            changed = {symbol: dict(self._state[symbol]) for symbol in self._dirty}
            trades = self._new_trades
            self._dirty = set()
            self._new_trades = []
            return changed, trades


def _point_before(history: deque, when: float) -> tuple[int, int] | None:
    """The newest (time, price) at or before `when`, or the oldest one; None if there is no history.
    Samples are one second apart, so this walks back about a minute at most."""
    if not history:
        return None
    for i in range(len(history) - 1, -1, -1):
        if history[i][0] <= when:
            return history[i]
    return history[0]
