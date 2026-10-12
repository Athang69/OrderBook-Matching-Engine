"""In-memory market data: last price, day statistics, best five levels and recent trades."""
import threading
import time
from collections import deque

from .instruments import Instrument


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
                "trades": 0,
                "bids": [],
                "asks": [],
            }
            for i in instruments
        }
        self._tape: dict[str, deque] = {i.symbol: deque(maxlen=60) for i in instruments}
        self._history: dict[str, deque] = {i.symbol: deque(maxlen=1800) for i in instruments}
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

    def sample_history(self) -> None:
        """Records one price point per symbol; called once a second for the price chart."""
        now = int(time.time())
        with self._lock:
            for symbol, state in self._state.items():
                if state["ltp"] is not None:
                    self._history[symbol].append((now, state["ltp"]))

    def drain(self) -> tuple[dict[str, dict], list[dict]]:
        """Everything that changed since the last call, for the WebSocket broadcaster."""
        with self._lock:
            changed = {symbol: dict(self._state[symbol]) for symbol in self._dirty}
            trades = self._new_trades
            self._dirty = set()
            self._new_trades = []
            return changed, trades
