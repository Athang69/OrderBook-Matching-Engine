"""Order management for paper trading against the live NSE market.

Your orders go to the C++ matching engine, which keeps them in price-time priority. The real market
takes part through orders placed for it, at real prices and for real quantities:

  * An order that can trade now (a market order, or a limit order at or better than the real best
    price) trades at the real best offer when buying, or the real best bid when selling.
  * An order that cannot trade yet waits in the engine. Each time a real trade is reported for the
    stock, that trade is replayed in the engine at its real price and quantity, so waiting orders at
    that price or better fill, in price-time priority, up to the quantity that really traded.

Outside market hours, delivery orders are kept as after-market orders (AMO) and enter the market at
its first trade of the next session. Orders still open at the close expire (they are day orders), and
intraday positions are squared off at 3:20 pm. Charges are worked out on every fill (charges.py).

One lock guards all state, so orders are processed strictly one at a time. That is the same "single
writer" rule the engine follows, and it keeps balances, orders and the book consistent.
"""
import itertools
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from . import charges as fees
from .accounts import Account
from .audit import AuditLog
from .engine_client import EngineClient, EngineTrade
from .instruments import Instrument
from .market_data import MarketData
from .risk import check_order

OPEN_STATES = ("OPEN", "PARTIALLY_FILLED")
MARKET_IDS_START = 10**12  # ids of the orders placed for the real market; yours stay far below
QUOTE_MAX_AGE = 10  # seconds: an older best bid or offer is not used to price a trade
QUOTE_MAX_GAP = 0.005  # nor one more than 0.5% away from the last traded price
PRICE_MAX_AGE = 60  # seconds without any price update before trading in a stock is refused
CROSS_LEVELS = 100  # price levels looked at when counting your orders a market order would reach


@dataclass
class Order:
    id: int
    user_id: str
    symbol: str
    side: str  # BUY | SELL
    type: str  # LIMIT | MARKET
    product: str  # CNC (delivery) | MIS (intraday)
    qty: int
    price: int | None
    created_at: float
    updated_at: float
    status: str = "PENDING"  # then OPEN | PARTIALLY_FILLED | FILLED | CANCELLED | REJECTED
    filled: int = 0
    filled_value: int = 0
    reason: str | None = None  # why it was rejected or cancelled
    reserved_cash: int = 0
    amo: bool = False  # placed while the market was closed
    tag: str | None = None  # AUTO_SQUARE_OFF for the broker's own closing orders
    charges: fees.Charges = field(default_factory=fees.Charges)
    fills: list[dict] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        return self.qty - self.filled

    def to_dict(self) -> dict:
        return {
            "id": self.id, "user_id": self.user_id, "symbol": self.symbol, "side": self.side, "type": self.type,
            "product": self.product, "qty": self.qty, "price": self.price, "status": self.status,
            "filled": self.filled, "remaining": self.remaining if self.status in OPEN_STATES else 0,
            "avg_price": round(self.filled_value / self.filled) if self.filled else None,
            "reason": self.reason, "amo": self.amo, "tag": self.tag, "charges": self.charges.to_dict(),
            "created_at": self.created_at, "updated_at": self.updated_at, "fills": self.fills,
        }


class Exchange:
    def __init__(self, engine: EngineClient, instruments: dict[str, Instrument], market: MarketData, audit: AuditLog,
                 session: Callable[[], dict], margin_divisor: int, max_order_qty: int, depth_levels: int,
                 delivery_only_series: tuple[str, ...] = ("BE",), clock: Callable[[], float] = time.time):
        self._engine = engine
        self._instruments = instruments
        self._market = market
        self._audit = audit
        self._session = session
        self._margin_divisor = margin_divisor
        self._max_order_qty = max_order_qty
        self._depth_levels = depth_levels
        self._delivery_only = delivery_only_series
        self._clock = clock
        self._lock = threading.RLock()
        self._accounts: dict[str, Account] = {}
        self._orders: dict[int, Order] = {}
        self._order_ids = itertools.count(1)
        self._trade_ids = itertools.count(1)
        self._market_ids = itertools.count(MARKET_IDS_START)
        self._books: set[str] = set()  # stocks registered in the engine, added when first traded
        self._resting: dict[str, set[int]] = {}  # stock -> your orders waiting in the engine
        self._amo: list[int] = []  # after-market orders not yet in the market, oldest first
        self._last_state: str | None = None
        self._squared_off_on: str | None = None

    # ---- accounts and reference data ----

    def create_account(self, user_id: str, cash: int) -> None:
        with self._lock:
            self._accounts[user_id] = Account(user_id=user_id, cash=cash)

    def has_account(self, user_id: str) -> bool:
        return user_id in self._accounts

    def available(self, user_id: str) -> int:
        """Available cash only; much cheaper than a full portfolio valuation."""
        with self._lock:
            return self._accounts[user_id].available(self._margin_divisor)

    def set_instruments(self, instruments: dict[str, Instrument]) -> None:
        """A new day's reference data: each empty book in the engine takes its new price band."""
        with self._lock:
            self._instruments = instruments
            for symbol in list(self._books):
                if not self._resting.get(symbol) and symbol in instruments:
                    i = instruments[symbol]
                    self._engine.add_symbol(symbol, i.tick, i.lower_band, i.upper_band)

    def symbols_in_use(self) -> set[str]:
        """Stocks with an open order, a holding or an intraday position: their prices must stay live."""
        with self._lock:
            symbols = {o.symbol for o in self._orders.values() if o.status in OPEN_STATES}
            for account in self._accounts.values():
                symbols.update(s for s, h in account.holdings.items() if h.qty)
                symbols.update(s for s, p in account.intraday.items() if p.qty)
            return symbols

    # ---- orders ----

    def place_order(self, user_id: str, symbol: str, side: str, order_type: str, product: str, qty: int,
                    price: int | None = None, tag: str | None = None) -> Order:
        with self._lock:
            account = self._accounts[user_id]
            now = self._clock()
            order = Order(id=next(self._order_ids), user_id=user_id, symbol=symbol, side=side, type=order_type,
                          product=product, qty=qty, price=price if order_type == "LIMIT" else None,
                          created_at=now, updated_at=now, tag=tag)
            instrument = self._instruments.get(symbol)
            session = self._session()
            market_open = session["state"] == "OPEN"
            touch = None

            # 1. Checks: the session, the order and the money.
            reservation = None
            if instrument is None:
                reason = "UNKNOWN_SYMBOL"
            elif product == "MIS" and instrument.series in self._delivery_only:
                reason = "INTRADAY_NOT_ALLOWED"
            elif product == "MIS" and not session["intraday_open"] and not (
                    market_open and qty <= account.closable_qty(symbol, side)):
                reason = "INTRADAY_CLOSED"  # after 3:20 pm an intraday order may only close a position
            else:
                reason, reservation = check_order(account, instrument, side, order_type, product, qty, order.price,
                                                  self._margin_divisor, self._max_order_qty)
            if reason is None and market_open:
                touch = self._touch(symbol, side, now)
                if touch is None:
                    reason = "NO_LIVE_PRICE"
                elif not instrument.lower_band <= touch <= instrument.upper_band:
                    reason = "OUTSIDE_PRICE_BAND"
                else:
                    reason = self._self_trade(order, touch)
            if reason is not None:
                order.status, order.reason = "REJECTED", reason
                self._orders[order.id] = order
                self._log_order("ORDER_REJECTED", order)
                return order

            # 2. Reserve cash or shares so the same money cannot back two orders.
            account.blocked_cash += reservation.cash
            order.reserved_cash = reservation.cash
            if reservation.shares:
                account.holding(symbol).blocked += reservation.shares
            self._orders[order.id] = order

            # 3. Outside market hours a delivery order waits for the next session.
            if not market_open:
                order.amo, order.status = True, "OPEN"
                self._amo.append(order.id)
                self._log_order("ORDER_AMO", order)
                return order

            self._log_order("ORDER_ACCEPTED", order)
            self._execute(order, touch, now)
            return order

    def cancel_order(self, order_id: int, user_id: str | None = None, reason: str = "USER_CANCELLED") -> Order:
        """Raises KeyError for an unknown order, PermissionError for someone else's, ValueError if not open."""
        with self._lock:
            order = self._orders[order_id]
            if user_id is not None and order.user_id != user_id:
                raise PermissionError("order belongs to another user")
            if order.status not in OPEN_STATES:
                raise ValueError(f"order is {order.status}, not open")
            if order_id in self._amo:
                self._amo.remove(order_id)
            else:
                self._engine.cancel(order_id)
                self._resting.get(order.symbol, set()).discard(order_id)
            self._release(order, self._accounts[order.user_id])
            order.status, order.reason, order.updated_at = "CANCELLED", reason, self._clock()
            self._log_order("ORDER_CANCELLED", order)
            return order

    def get_order(self, order_id: int) -> Order | None:
        with self._lock:
            return self._orders.get(order_id)

    def list_orders(self, user_id: str, open_only: bool = False) -> list[dict]:
        with self._lock:
            orders = [o for o in self._orders.values() if o.user_id == user_id and (not open_only or o.status in OPEN_STATES)]
            return [o.to_dict() for o in sorted(orders, key=lambda o: o.id, reverse=True)]

    def square_off(self, user_id: str, tag: str | None = None) -> list[Order]:
        """Closes every intraday position with a market order. Raises ValueError when the market is closed."""
        with self._lock:
            if self._session()["state"] != "OPEN":
                raise ValueError("The market is closed, so positions cannot be squared off now.")
            account = self._accounts[user_id]
            closing = []
            for symbol, pos in list(account.intraday.items()):
                if pos.qty == 0:
                    continue
                for order in list(self._orders.values()):
                    if order.user_id == user_id and order.symbol == symbol and order.product == "MIS" and order.status in OPEN_STATES:
                        self.cancel_order(order.id, reason=tag or "USER_CANCELLED")
                side = "SELL" if pos.qty > 0 else "BUY"
                closing.append(self.place_order(user_id, symbol, side, "MARKET", "MIS", abs(pos.qty), tag=tag))
            return closing

    def own_book(self, symbol: str) -> tuple[list, list]:
        """Your orders waiting in the engine for this stock, as price levels (best five each side)."""
        with self._lock:
            if symbol not in self._books:
                return [], []
            bids, asks = self._engine.depth(symbol, self._depth_levels)
            return [list(level) for level in bids], [list(level) for level in asks]

    # ---- the real market ----

    def on_market_trade(self, symbol: str, price: int, qty: int) -> None:
        """A real trade on NSE: `qty` shares of `symbol` at `price`."""
        with self._lock:
            if self._session()["state"] != "OPEN":
                return  # Yahoo also sends the official closing price after 3:30 pm; that is not a trade
            now = self._clock()
            self._enter_amos(symbol, price, now)
            if qty <= 0 or not self._resting.get(symbol):
                return
            instrument = self._instruments[symbol]
            tick = instrument.tick
            # The market's sell reaches your buys at or above the price; its buy your sells at or below.
            for side, at in (("SELL", -(-price // tick) * tick), ("BUY", price // tick * tick)):
                if instrument.lower_band <= at <= instrument.upper_band:
                    market_id = self._place_for_market(symbol, side, at, qty, now)
                    self._engine.cancel(market_id)

    def on_clock(self) -> None:
        """Called every second: squares off intraday positions at 3:20 pm and closes the day at 3:30 pm."""
        with self._lock:
            session = self._session()
            state, previous = session["state"], self._last_state
            self._last_state = state
            if state == "OPEN" and not session["intraday_open"] and self._squared_off_on != session["trading_day"]:
                self._squared_off_on = session["trading_day"]
                for user_id in self._accounts:
                    self.square_off(user_id, tag="AUTO_SQUARE_OFF")
            if previous == "OPEN" and state != "OPEN":
                self._end_of_day()

    # ---- portfolio ----

    def portfolio(self, user_id: str) -> dict:
        with self._lock:
            account = self._accounts[user_id]
            holdings, intraday = [], []
            holdings_value = unrealised = 0
            for symbol, holding in account.holdings.items():
                if holding.qty == 0:
                    continue
                ltp, prev_close = self._prices(symbol)
                value = holding.qty * ltp
                holdings_value += value
                unrealised += value - holding.cost
                holdings.append({"symbol": symbol, "qty": holding.qty, "blocked": holding.blocked,
                                 "avg_price": round(holding.cost / holding.qty), "ltp": ltp, "prev_close": prev_close,
                                 "value": value, "unrealised_pnl": value - holding.cost})
            intraday_pnl = 0
            for symbol, pos in account.intraday.items():
                if pos.qty == 0:
                    continue
                ltp, _ = self._prices(symbol)
                pnl = pos.qty * ltp - pos.cost if pos.qty > 0 else pos.cost - abs(pos.qty) * ltp
                intraday_pnl += pnl
                intraday.append({"symbol": symbol, "qty": pos.qty, "avg_price": round(pos.cost / abs(pos.qty)),
                                 "ltp": ltp, "margin": pos.cost // self._margin_divisor, "unrealised_pnl": pnl})
            return {
                "user_id": user_id,
                "cash": account.cash,
                "blocked_for_orders": account.blocked_cash,
                "intraday_margin": account.intraday_margin(self._margin_divisor),
                "available": account.available(self._margin_divisor),
                "holdings_value": holdings_value,
                "realised_pnl": account.realised_pnl,
                "unrealised_pnl": unrealised + intraday_pnl,
                "charges": account.charges.to_dict(),
                "net_pnl": account.realised_pnl + unrealised + intraday_pnl - account.charges.total,
                "equity": account.cash + holdings_value + intraday_pnl,
                "holdings": holdings,
                "intraday": intraday,
            }

    # ---- internals ----

    def _touch(self, symbol: str, side: str, now: float) -> int | None:
        """The real price a buy (best offer) or sell (best bid) trades at now, on the tick grid, never
        better than the real price; the last traded price when the best bid or offer is old or odd."""
        quote = self._market.quote(symbol)
        if not quote or quote["ltp"] is None:
            return None
        updated = max(quote["tick_time"] or 0, quote["polled_at"] or 0)
        if now - updated > PRICE_MAX_AGE:
            return None
        ltp = quote["ltp"]
        best = quote["ask"] if side == "BUY" else quote["bid"]
        fresh = (best is not None and quote["polled_at"] is not None and now - quote["polled_at"] <= QUOTE_MAX_AGE
                 and abs(best - ltp) <= ltp * QUOTE_MAX_GAP)
        price = best if fresh else ltp
        tick = self._instruments[symbol].tick
        return -(-price // tick) * tick if side == "BUY" else price // tick * tick

    def _self_trade(self, order: Order, touch: int) -> str | None:
        """Your buy may not trade with your own sell (or the reverse); NSE prevents self-trades too."""
        if order.symbol not in self._books or not self._resting.get(order.symbol):
            return None
        bids, asks = self._engine.depth(order.symbol, 1)
        reach = touch if self._marketable(order, touch) else order.price
        if order.side == "BUY" and asks and asks[0][0] <= reach:
            return "SELF_TRADE"
        if order.side == "SELL" and bids and bids[0][0] >= reach:
            return "SELF_TRADE"
        return None

    @staticmethod
    def _marketable(order: Order, touch: int) -> bool:
        if order.type == "MARKET":
            return True
        return order.price >= touch if order.side == "BUY" else order.price <= touch

    def _execute(self, order: Order, touch: int, now: float) -> None:
        """Sends an accepted order into the engine, with the market's order at `touch` if it can trade now."""
        symbol = order.symbol
        account = self._accounts[order.user_id]
        self._ensure_book(symbol)
        market_id = None
        if self._marketable(order, touch):
            market_id = self._place_for_market(symbol, "SELL" if order.side == "BUY" else "BUY", touch,
                                               order.remaining, now, for_new_order=True)
        result = self._engine.new_order(order.id, symbol, order.side, order.type, order.price or 0, order.remaining)
        if market_id is not None:
            self._engine.cancel(market_id)
        if result.reject is not None:  # the checks above mirror the engine's, so this is not expected
            self._release(order, account)
            order.status, order.reason = "REJECTED", result.reject
        else:
            for trade in result.trades:
                self._apply_trade(trade, now)
            if result.resting > 0:
                order.status = "PARTIALLY_FILLED" if order.filled else "OPEN"
                self._resting.setdefault(symbol, set()).add(order.id)
            elif order.filled == order.qty:
                order.status = "FILLED"
            else:  # a market order with nothing left to trade with
                self._release(order, account)
                order.status, order.reason = "CANCELLED", "NO_LIQUIDITY"
        order.updated_at = now
        self._log_order("ORDER_" + order.status, order)

    def _place_for_market(self, symbol: str, side: str, price: int, qty: int, now: float,
                          for_new_order: bool = False) -> int:
        """Puts the real market's order into the engine. Returns its id; the caller cancels whatever is left.

        Your waiting orders that it reaches trade with it first. When `qty` is meant for a new order, it is
        made larger by their quantity so the new order still gets all of `qty`; when it replays a real
        trade, `qty` is what really traded and is shared out in price-time priority."""
        reach = 0
        if for_new_order and self._resting.get(symbol):
            bids, asks = self._engine.depth(symbol, CROSS_LEVELS)
            if side == "SELL":
                reach = sum(level[1] for level in bids if level[0] >= price)
            else:
                reach = sum(level[1] for level in asks if level[0] <= price)
        market_id = next(self._market_ids)
        result = self._engine.new_order(market_id, symbol, side, "LIMIT", price, qty + reach if reach else qty)
        for trade in result.trades:
            self._apply_trade(trade, now)
        return market_id

    def _enter_amos(self, symbol: str, price: int, now: float) -> None:
        """After-market orders for this stock enter the market at its first trade of the session."""
        waiting = [oid for oid in self._amo if self._orders[oid].symbol == symbol]
        for order_id in waiting:
            self._amo.remove(order_id)
            order = self._orders[order_id]
            touch = price
            reason = self._self_trade(order, touch)
            if reason is not None:
                self._release(order, self._accounts[order.user_id])
                order.status, order.reason, order.updated_at = "CANCELLED", reason, now
                self._log_order("ORDER_CANCELLED", order)
                continue
            self._execute(order, touch, now)

    def _apply_trade(self, trade: EngineTrade, now: float) -> None:
        """Applies a trade to your order in it. The real market's side has no account to update."""
        trade_id = next(self._trade_ids)
        mine = [self._orders[oid] for oid in (trade.buy_id, trade.sell_id) if oid < MARKET_IDS_START]
        for order in mine:
            was_waiting = order.id in self._resting.get(order.symbol, ())
            self._apply_fill(order, trade.qty, trade.price, trade_id, now)
            if was_waiting and order.status == "FILLED":
                self._resting[order.symbol].discard(order.id)
                self._log_order("ORDER_FILLED", order)
        self._audit.write("TRADE", trade_id=trade_id, symbol=mine[0].symbol if mine else None, price=trade.price,
                          qty=trade.qty, buy_order_id=trade.buy_id, sell_order_id=trade.sell_id)

    def _apply_fill(self, order: Order, qty: int, price: int, trade_id: int, now: float) -> None:
        account = self._accounts[order.user_id]
        # Release this fill's share of the reservation, then move the real money or shares.
        release = order.reserved_cash * qty // order.remaining
        order.reserved_cash -= release
        account.blocked_cash -= release
        if order.product == "CNC":
            if order.side == "BUY":
                account.fill_delivery_buy(order.symbol, qty, price)
            else:
                account.fill_delivery_sell(order.symbol, qty, price)
        else:
            account.fill_intraday(order.symbol, order.side, qty, price)
        cost = fees.for_fill(order.product, order.side, qty * price, order.charges.brokerage)
        account.pay_charges(cost)
        order.charges.add(cost)
        order.filled += qty
        order.filled_value += qty * price
        order.fills.append({"trade_id": trade_id, "price": price, "qty": qty, "ts": now, "charges": cost.total})
        order.updated_at = now
        order.status = "FILLED" if order.filled == order.qty else "PARTIALLY_FILLED"

    def _release(self, order: Order, account: Account) -> None:
        """Gives back whatever an order still has reserved."""
        account.blocked_cash -= order.reserved_cash
        order.reserved_cash = 0
        if order.product == "CNC" and order.side == "SELL":
            account.holding(order.symbol).blocked -= order.remaining

    def _end_of_day(self) -> None:
        """Open orders expire at the close; any intraday position still open is closed at the last price."""
        now = self._clock()
        for order in list(self._orders.values()):
            if order.status in OPEN_STATES:
                self.cancel_order(order.id, reason="EXPIRED")
        for account in self._accounts.values():
            for symbol, pos in account.intraday.items():
                if pos.qty == 0:
                    continue
                side = "SELL" if pos.qty > 0 else "BUY"
                qty, (ltp, _) = abs(pos.qty), self._prices(symbol)
                account.fill_intraday(symbol, side, qty, ltp)
                account.pay_charges(fees.for_fill("MIS", side, qty * ltp))
                self._audit.write("INTRADAY_SETTLED", user=account.user_id, symbol=symbol, side=side, qty=qty, price=ltp)
        self._audit.write("END_OF_DAY", at=now)

    def _ensure_book(self, symbol: str) -> None:
        if symbol not in self._books:
            i = self._instruments[symbol]
            self._engine.add_symbol(symbol, i.tick, i.lower_band, i.upper_band)
            self._books.add(symbol)

    def _prices(self, symbol: str) -> tuple[int, int]:
        """Last price and previous close: live when known, otherwise the reference close."""
        quote = self._market.quote(symbol)
        close = self._instruments[symbol].close if symbol in self._instruments else 0
        ltp = (quote or {}).get("ltp") or close
        prev_close = (quote or {}).get("prev_close") or close
        return ltp, prev_close

    def _log_order(self, event: str, order: Order) -> None:
        self._audit.write(event, order_id=order.id, user=order.user_id, symbol=order.symbol, side=order.side,
                          type=order.type, product=order.product, qty=order.qty, price=order.price,
                          filled=order.filled, status=order.status, reason=order.reason, amo=order.amo, tag=order.tag)
