"""What the market is doing now, for every stock being followed: the live quote, today's one-minute
bars, the latest trades and the volume-weighted average price (VWAP).

Two feeds fill it (see yahoo.py): the stream, with each new last price and the day's volume so far,
and the quote poll every few seconds, with the best bid and offer, the day's range and valuation.
The shares traded between two stream messages are the rise in the day's volume; the trade is
marked as buyer- or seller-initiated by the tick test: a price above the previous one is a buy.
"""
import itertools
import math
import threading
import time
from collections import deque

from .instruments import Instrument

TAPE_LENGTH = 60  # latest trades kept for each stock
TICK_HISTORY = 900  # latest prices kept for each stock, for momentum
MAX_BARS = 400  # a session has 375 minutes

QUOTE_FIELDS = ("prev_close", "bid", "ask", "name", "week52_high", "week52_low", "market_cap", "pe", "eps",
                "dividend_yield", "price_to_book", "avg_volume", "market_state")


class MarketData:
    def __init__(self, instruments: dict[str, Instrument]):
        self._lock = threading.Lock()
        self._instruments = instruments
        self._state: dict[str, dict] = {}
        self._tape: dict[str, deque] = {}
        self._ticks: dict[str, deque] = {}
        self._bars: dict[str, list[list[int]]] = {}
        self._sigma: dict[str, float | None] = {}  # spread of one-minute returns today
        self._vwap: dict[str, list] = {}  # [sum of price x quantity, quantity]
        self._indices: dict[str, dict] = {}
        self._dirty: set[str] = set()
        self._dirty_indices: set[str] = set()
        self._new_trades: list[dict] = []
        self._trade_ids = itertools.count(1)

    def set_instruments(self, instruments: dict[str, Instrument]) -> None:
        with self._lock:
            self._instruments = instruments

    def new_day(self) -> None:
        """Forgets the previous session's range, volume, bars and trades before a new session starts."""
        with self._lock:
            for symbol in list(self._state):
                last = self._state.pop(symbol)["ltp"]
                self._ensure(symbol)["ltp"] = last
                self._dirty.add(symbol)

    # ---- feeds ----

    def on_quote(self, symbol: str, quote: dict, received: float | None = None) -> None:
        with self._lock:
            s = self._ensure(symbol)
            s["polled_at"] = received if received is not None else time.time()
            for key in QUOTE_FIELDS:
                if quote.get(key) is not None:
                    s[key] = quote[key]
            stale = s["tick_time"] is not None and quote["quote_time"] is not None and quote["quote_time"] < s["tick_time"]
            if quote["ltp"] is not None and not stale:
                s["ltp"] = quote["ltp"]
            if quote["quote_time"]:
                s["quote_time"] = quote["quote_time"]
            # Yahoo's day figures are the official ones; the stream only moves them between polls.
            for key, pick in (("open", None), ("high", max), ("low", min)):
                value = quote.get(key)
                if value is not None:
                    s[key] = value if (pick is None or not stale or s[key] is None) else pick(s[key], value)
            s["volume"] = max(s["volume"], quote.get("volume") or 0)
            self._dirty.add(symbol)

    def on_tick(self, symbol: str, price: int, day_volume: int, ts: float) -> int:
        """A new last traded price. Returns the shares traded since the previous message (0 if unknown)."""
        with self._lock:
            s = self._ensure(symbol)
            previous_price = s["ltp"]
            previous_volume = s["stream_volume"]
            traded = day_volume - previous_volume if previous_volume and day_volume > previous_volume else 0
            if day_volume > previous_volume:
                s["stream_volume"] = day_volume
            s["volume"] = max(s["volume"], day_volume)
            s["ltp"] = price
            s["tick_time"] = ts
            s["open"] = s["open"] or price
            s["high"] = price if s["high"] is None else max(s["high"], price)
            s["low"] = price if s["low"] is None else min(s["low"], price)
            if previous_price is not None and price != previous_price:
                s["last_side"] = "BUY" if price > previous_price else "SELL"
            self._ticks[symbol].append((ts, price))
            if traded > 0:
                vwap = self._vwap[symbol]
                vwap[0] += price * traded
                vwap[1] += traded
                s["vwap"] = round(vwap[0] / vwap[1])
                trade = {"id": next(self._trade_ids), "symbol": symbol, "price": price, "qty": traded,
                         "side": s["last_side"], "ts": ts}
                self._tape[symbol].appendleft(trade)
                self._new_trades.append(trade)
            self._add_to_bar(symbol, int(ts), price, traded)
            self._dirty.add(symbol)
            return traded

    def set_bars(self, symbol: str, bars: list[list[int]]) -> None:
        """Today's one-minute bars from Yahoo, when a stock is first followed; the stream extends them."""
        with self._lock:
            s = self._ensure(symbol)
            aligned = [[b[0] - b[0] % 60, *b[1:]] for b in bars][-MAX_BARS:]
            mine = self._bars[symbol]
            # Keep the minutes the stream has already built that are newer than Yahoo's last bar.
            newer = [b for b in mine if aligned and b[0] > aligned[-1][0]]
            self._bars[symbol] = aligned + newer
            if aligned and self._vwap[symbol][1] == 0:
                turnover = sum((b[2] + b[3] + b[4]) / 3 * b[5] for b in aligned)
                volume = sum(b[5] for b in aligned)
                if volume:
                    self._vwap[symbol] = [turnover, volume]
                    s["vwap"] = round(turnover / volume)
            self._sigma[symbol] = _minute_sigma(self._bars[symbol])
            self._dirty.add(symbol)

    def on_index(self, name: str, quote: dict) -> None:
        with self._lock:
            index = self._indices.setdefault(name, {"name": name, "ltp": None, "prev_close": None, "high": None,
                                                    "low": None, "time": None})
            for key in ("ltp", "prev_close", "high", "low"):
                if quote.get(key) is not None:
                    index[key] = quote[key]
            index["time"] = quote.get("quote_time") or quote.get("time") or index["time"]
            self._dirty_indices.add(name)

    # ---- reads ----

    def has(self, symbol: str) -> bool:
        with self._lock:
            return symbol in self._state

    def ltp(self, symbol: str) -> int | None:
        with self._lock:
            state = self._state.get(symbol)
            return state["ltp"] if state else None

    def quote(self, symbol: str) -> dict | None:
        with self._lock:
            state = self._state.get(symbol)
            return dict(state) if state else None

    def snapshot(self, symbol: str) -> dict:
        with self._lock:
            return _public(self._ensure(symbol))

    def snapshots(self, symbols) -> dict[str, dict]:
        with self._lock:
            return {s: _public(self._state[s]) for s in symbols if s in self._state}

    def indices(self) -> list[dict]:
        with self._lock:
            return [dict(i) for i in self._indices.values()]

    def tape(self, symbol: str, limit: int) -> list[dict]:
        with self._lock:
            return list(self._tape.get(symbol, ()))[:limit]

    def bars(self, symbol: str) -> list[list[int]]:
        with self._lock:
            return [list(b) for b in self._bars.get(symbol, ())]

    def intraday_view(self, symbols: list[str], seconds: int, momentum_seconds: int, now: float) -> dict[str, dict]:
        """What the intraday signals need, copied under one lock so it is consistent."""
        cutoff = now - seconds
        with self._lock:
            view = {}
            for symbol in symbols:
                s = self._ensure(symbol)
                ticks = self._ticks[symbol]
                view[symbol] = {
                    "ltp": s["ltp"], "vwap": s["vwap"], "bid": s["bid"], "ask": s["ask"],
                    "tick_time": s["tick_time"], "quote_time": s["quote_time"], "polled_at": s["polled_at"],
                    "trades": [t for t in self._tape[symbol] if t["ts"] >= cutoff],
                    "sigma": self._sigma.get(symbol),  # per minute
                    "minutes": len(self._bars[symbol]),
                    "reference": _price_before(ticks, self._bars[symbol], now - momentum_seconds),
                }
            return view

    def drain(self) -> tuple[dict[str, dict], list[dict], list[dict]]:
        """Everything that changed since the last call, for the WebSocket broadcaster."""
        with self._lock:
            changed = {symbol: _public(self._state[symbol]) for symbol in self._dirty}
            indices = [dict(self._indices[name]) for name in self._dirty_indices]
            trades = self._new_trades
            self._dirty, self._dirty_indices, self._new_trades = set(), set(), []
            return changed, trades, indices

    # ---- internals (called with the lock held) ----

    def _ensure(self, symbol: str) -> dict:
        state = self._state.get(symbol)
        if state is None:
            instrument = self._instruments.get(symbol)
            state = {
                "symbol": symbol, "name": None, "ltp": None,
                "prev_close": instrument.close if instrument else None,
                "open": None, "high": None, "low": None, "volume": 0, "stream_volume": 0, "vwap": None,
                "bid": None, "ask": None, "quote_time": None, "polled_at": None, "tick_time": None, "last_side": None,
                "week52_high": None, "week52_low": None, "market_cap": None, "pe": None, "eps": None,
                "dividend_yield": None, "price_to_book": None, "avg_volume": None, "market_state": None,
            }
            self._state[symbol] = state
            self._tape.setdefault(symbol, deque(maxlen=TAPE_LENGTH)).clear()
            self._ticks.setdefault(symbol, deque(maxlen=TICK_HISTORY)).clear()
            self._bars[symbol] = []
            self._vwap[symbol] = [0.0, 0]
            self._sigma[symbol] = None
        return state

    def _add_to_bar(self, symbol: str, t: int, price: int, qty: int) -> None:
        minute = t - t % 60
        bars = self._bars[symbol]
        if bars and bars[-1][0] == minute:
            bar = bars[-1]
            bar[2] = max(bar[2], price)
            bar[3] = min(bar[3], price)
            bar[4] = price
            bar[5] += qty
        elif not bars or minute > bars[-1][0]:
            bars.append([minute, price, price, price, price, qty])
            if len(bars) > MAX_BARS:
                del bars[0]
            self._sigma[symbol] = _minute_sigma(bars)  # once a minute, when a bar closes


def _public(state: dict) -> dict:
    out = {k: v for k, v in state.items() if k not in ("stream_volume", "last_side")}
    out["live"] = state["tick_time"] is not None or state["polled_at"] is not None
    return out


def _minute_sigma(bars: list[list[int]]) -> float | None:
    """Standard deviation of one-minute log returns over the completed bars."""
    closes = [b[4] for b in bars[:-1] if b[4]]
    if len(closes) < 6:
        return None
    returns = [math.log(b / a) for a, b in zip(closes, closes[1:])]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return max(math.sqrt(variance), 1e-5)


def _price_before(ticks: deque, bars: list[list[int]], when: float) -> tuple[float, int] | None:
    """The newest (time, price) at or before `when`: from the stream's recent prices, or else from the
    one-minute bars. Walks back about a minute at most."""
    for i in range(len(ticks) - 1, -1, -1):
        if ticks[i][0] <= when:
            return ticks[i]
    for bar in reversed(bars):
        if bar[0] + 60 <= when:
            return (bar[0] + 60, bar[4])
    if ticks:
        return ticks[0]
    return None
