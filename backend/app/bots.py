"""Robot traders that keep the order books busy.

There is no free order-by-order data for Indian stocks, so the orders are generated.
What is real is the price path: each stock walks from the previous day's open to its
high and low and on to its close, compressed into a short session.

  mm1, mm2  market makers: keep buy and sell quotes on both sides of the fair price
  retail    places small limit orders near the fair price and cancels old ones
  taker     sends market orders, leaning towards the fair price, which creates trades
"""
import random
import threading
import time
from collections import deque

from .engine_client import EngineError
from .exchange import OPEN_STATES, Exchange
from .instruments import Instrument
from .market_data import MarketData


class Bots(threading.Thread):
    STEP_SECONDS = 1.0  # each stock is visited about once per second

    def __init__(self, exchange: Exchange, market: MarketData, instruments: list[Instrument], session_seconds: int,
                 seed: int = 7):
        super().__init__(daemon=True, name="robot-traders")
        self._exchange = exchange
        self._market = market
        self._instruments = instruments
        self._session = session_seconds
        self._rng = random.Random(seed)
        self._running = threading.Event()
        self._running.set()
        self._stopping = threading.Event()
        self._elapsed = 0.0
        self._quotes: dict[tuple[str, str], dict[int, tuple[str, int]]] = {}
        self._retail: dict[str, deque] = {i.symbol: deque() for i in instruments}
        self._noise: dict[str, int] = {i.symbol: 0 for i in instruments}

    # ---- control ----

    @property
    def enabled(self) -> bool:
        return self._running.is_set()

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self._running.set()
        else:
            self._running.clear()

    def stop(self) -> None:
        self._stopping.set()

    def status(self) -> dict:
        return {
            "bots_enabled": self.enabled,
            "session_seconds": self._session,
            "elapsed_seconds": round(min(self._elapsed, self._session), 1),
            "progress": round(min(1.0, self._elapsed / self._session), 4),
        }

    # ---- main loop ----

    def run(self) -> None:
        pause = self.STEP_SECONDS / len(self._instruments)
        last = time.monotonic()
        while not self._stopping.is_set():
            for instrument in self._instruments:
                now = time.monotonic()
                if self.enabled:
                    self._elapsed += now - last  # the session clock stops while the robots are paused
                    try:
                        self._step(instrument)
                    except EngineError:
                        return  # the engine has gone away; nothing more to do
                last = now
                if self._stopping.wait(pause):
                    return

    def _step(self, inst: Instrument) -> None:
        fair = self._fair_price(inst)
        self._quote("mm1", inst, fair, offsets=(1, 2, 3, 4, 5), size=1.5)
        self._quote("mm2", inst, fair, offsets=(2, 4, 6, 8), size=3.0)
        self._retail_order(inst, fair)
        self._taker_order(inst, fair)

    # ---- price path ----

    def _fair_price(self, inst: Instrument) -> int:
        """Previous day's open -> low -> high -> close (or high first on a down day), plus small noise."""
        progress = min(1.0, self._elapsed / self._session)
        points = [inst.open, inst.low, inst.high, inst.close] if inst.close >= inst.open else [inst.open, inst.high, inst.low, inst.close]
        marks = [0.0, 0.3, 0.7, 1.0]
        base = points[-1]
        for i in range(3):
            if progress <= marks[i + 1]:
                share = (progress - marks[i]) / (marks[i + 1] - marks[i])
                base = points[i] + (points[i + 1] - points[i]) * share
                break
        noise = self._noise[inst.symbol] + self._rng.choice((-1, 0, 0, 1))
        self._noise[inst.symbol] = noise = max(-4, min(4, noise))
        fair = round(base / inst.tick) * inst.tick + noise * inst.tick
        # Keep quotes clear of the band edges.
        return max(inst.lower_band + 10 * inst.tick, min(inst.upper_band - 10 * inst.tick, fair))

    # ---- the robots ----

    def _quote(self, bot: str, inst: Instrument, fair: int, offsets: tuple[int, ...], size: float) -> None:
        live = self._quotes.setdefault((bot, inst.symbol), {})
        for order_id in [oid for oid in live if not self._exchange.is_open(oid)]:
            del live[order_id]  # filled since the last visit
        wanted = {("BUY", fair - k * inst.tick) for k in offsets} | {("SELL", fair + k * inst.tick) for k in offsets}
        for order_id, quote in list(live.items()):
            if quote not in wanted:  # the fair price moved away from this quote
                self._cancel(order_id)
                del live[order_id]
        for side, price in sorted(wanted - set(live.values())):
            qty = max(1, int(inst.avg_trade_qty * size * self._rng.uniform(0.6, 2.4)))
            order = self._exchange.place_order(bot, inst.symbol, side, "LIMIT", "CNC", qty, price)
            if order.status in OPEN_STATES:
                live[order.id] = (side, price)

    def _retail_order(self, inst: Instrument, fair: int) -> None:
        if self._rng.random() >= 0.35:
            return
        side = self._rng.choice(("BUY", "SELL"))
        distance = self._rng.randint(1, 6) * inst.tick
        price = fair - distance if side == "BUY" else fair + distance
        qty = max(1, int(inst.avg_trade_qty * self._rng.uniform(0.2, 1.2)))
        order = self._exchange.place_order("retail", inst.symbol, side, "LIMIT", "CNC", qty, price)
        resting = self._retail[inst.symbol]
        if order.status in OPEN_STATES:
            resting.append(order.id)
        while len(resting) > 10:
            self._cancel(resting.popleft())

    def _taker_order(self, inst: Instrument, fair: int) -> None:
        if self._rng.random() >= 0.55:
            return
        ltp = self._market.ltp(inst.symbol)
        # Buy more often when the last price is below fair, sell more often when above.
        buy_chance = 0.5 if ltp is None or ltp == fair else (0.72 if ltp < fair else 0.28)
        side = "BUY" if self._rng.random() < buy_chance else "SELL"
        qty = max(1, int(inst.avg_trade_qty * self._rng.uniform(0.3, 2.2)))
        self._exchange.place_order("taker", inst.symbol, side, "MARKET", "CNC", qty)

    def _cancel(self, order_id: int) -> None:
        try:
            self._exchange.cancel_order(order_id)
        except (KeyError, ValueError):
            pass  # already filled or cancelled
