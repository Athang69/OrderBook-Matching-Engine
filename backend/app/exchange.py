"""Order management: validates orders, reserves funds, sends them to the matching
engine and applies the resulting trades to both accounts.

One lock guards all state, so orders are processed strictly one at a time. That is
the same "single writer" rule the engine follows, and it is what keeps balances,
orders and the book consistent with each other.
"""
import itertools
import threading
import time
from dataclasses import dataclass, field

from .accounts import Account, Holding
from .audit import AuditLog
from .engine_client import EngineClient, EngineTrade
from .instruments import Instrument
from .market_data import MarketData
from .risk import check_order

OPEN_STATES = ("OPEN", "PARTIALLY_FILLED")


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
            "reason": self.reason, "created_at": self.created_at, "updated_at": self.updated_at, "fills": self.fills,
        }


class Exchange:
    def __init__(self, engine: EngineClient, instruments: list[Instrument], market: MarketData, audit: AuditLog,
                 margin_divisor: int, max_order_qty: int, depth_levels: int):
        self._engine = engine
        self._instruments = {i.symbol: i for i in instruments}
        self._market = market
        self._audit = audit
        self._margin_divisor = margin_divisor
        self._max_order_qty = max_order_qty
        self._depth_levels = depth_levels
        self._lock = threading.RLock()
        self._accounts: dict[str, Account] = {}
        self._orders: dict[int, Order] = {}
        self._order_ids = itertools.count(1)
        self._trade_ids = itertools.count(1)
        for instrument in instruments:
            engine.add_symbol(instrument.symbol, instrument.tick, instrument.lower_band, instrument.upper_band)

    # ---- accounts ----

    def create_account(self, user_id: str, cash: int, is_bot: bool = False, shares: int = 0) -> None:
        """`shares` gives the account that many shares of every stock, bought at the previous close."""
        with self._lock:
            account = Account(user_id=user_id, cash=cash, is_bot=is_bot)
            if shares:
                for instrument in self._instruments.values():
                    account.holdings[instrument.symbol] = Holding(qty=shares, cost=shares * instrument.prev_close)
            self._accounts[user_id] = account

    def has_account(self, user_id: str) -> bool:
        return user_id in self._accounts

    def available(self, user_id: str) -> int:
        """Available cash only; much cheaper than a full portfolio valuation."""
        with self._lock:
            return self._accounts[user_id].available(self._margin_divisor)

    # ---- orders ----

    def place_order(self, user_id: str, symbol: str, side: str, order_type: str, product: str, qty: int,
                    price: int | None = None) -> Order:
        with self._lock:
            account = self._accounts[user_id]
            now = time.time()
            order = Order(id=next(self._order_ids), user_id=user_id, symbol=symbol, side=side, type=order_type,
                          product=product, qty=qty, price=price if order_type == "LIMIT" else None,
                          created_at=now, updated_at=now)
            instrument = self._instruments.get(symbol)

            # 1. Risk checks.
            if instrument is None:
                reason, reservation = "UNKNOWN_SYMBOL", None
            else:
                reason, reservation = check_order(account, instrument, side, order_type, product, qty, order.price,
                                                  self._margin_divisor, self._max_order_qty)
            if reason is not None:
                order.status, order.reason = "REJECTED", reason
                self._keep(order, account)
                self._log_order("ORDER_REJECTED", order, account)
                return order

            # 2. Reserve cash or shares so the same money cannot back two orders.
            account.blocked_cash += reservation.cash
            order.reserved_cash = reservation.cash
            if reservation.shares:
                account.holding(symbol).blocked += reservation.shares
            self._orders[order.id] = order
            self._log_order("ORDER_ACCEPTED", order, account)

            # 3. Match.
            result = self._engine.new_order(order.id, symbol, side, order_type, order.price or 0, qty)
            if result.reject is not None:  # the checks above mirror the engine's, so this is not expected
                self._release(order, account)
                order.status, order.reason = "REJECTED", result.reject
            else:
                # 4. Apply each trade to both sides.
                for trade in result.trades:
                    self._apply_trade(order, trade, now)
                if result.resting > 0:
                    order.status = "PARTIALLY_FILLED" if order.filled else "OPEN"
                elif order.filled == order.qty:
                    order.status = "FILLED"
                else:  # a market order ran out of orders to trade with
                    self._release(order, account)
                    order.status, order.reason = "CANCELLED", "NO_LIQUIDITY"

            self._publish_book(symbol)
            self._log_order("ORDER_" + order.status, order, account)
            self._keep(order, account)
            return order

    def cancel_order(self, order_id: int, user_id: str | None = None) -> Order:
        """Raises KeyError for an unknown order, PermissionError for someone else's, ValueError if not open."""
        with self._lock:
            order = self._orders[order_id]
            if user_id is not None and order.user_id != user_id:
                raise PermissionError("order belongs to another user")
            if order.status not in OPEN_STATES:
                raise ValueError(f"order is {order.status}, not open")
            account = self._accounts[order.user_id]
            self._engine.cancel(order_id)
            self._release(order, account)
            order.status, order.reason, order.updated_at = "CANCELLED", "USER_CANCELLED", time.time()
            self._publish_book(order.symbol)
            self._log_order("ORDER_CANCELLED", order, account)
            self._keep(order, account)
            return order

    def get_order(self, order_id: int) -> Order | None:
        with self._lock:
            return self._orders.get(order_id)

    def is_open(self, order_id: int) -> bool:
        with self._lock:
            order = self._orders.get(order_id)
            return order is not None and order.status in OPEN_STATES

    def list_orders(self, user_id: str, open_only: bool = False) -> list[dict]:
        with self._lock:
            orders = [o for o in self._orders.values() if o.user_id == user_id and (not open_only or o.status in OPEN_STATES)]
            return [o.to_dict() for o in sorted(orders, key=lambda o: o.id, reverse=True)]

    def square_off(self, user_id: str) -> list[Order]:
        """Closes every intraday position with a market order, as a broker does before the close."""
        with self._lock:
            account = self._accounts[user_id]
            closing_orders = []
            for symbol, pos in list(account.intraday.items()):
                if pos.qty == 0:
                    continue
                for order in list(self._orders.values()):
                    if order.user_id == user_id and order.symbol == symbol and order.product == "MIS" and order.status in OPEN_STATES:
                        self.cancel_order(order.id)
                side = "SELL" if pos.qty > 0 else "BUY"
                closing_orders.append(self.place_order(user_id, symbol, side, "MARKET", "MIS", abs(pos.qty)))
            return closing_orders

    # ---- portfolio ----

    def portfolio(self, user_id: str) -> dict:
        with self._lock:
            account = self._accounts[user_id]
            holdings = []
            intraday = []
            holdings_value = 0
            unrealised = 0
            for symbol, holding in account.holdings.items():
                if holding.qty == 0:
                    continue
                ltp = self._last_price(symbol)
                value = holding.qty * ltp
                holdings_value += value
                unrealised += value - holding.cost
                holdings.append({"symbol": symbol, "qty": holding.qty, "blocked": holding.blocked,
                                 "avg_price": round(holding.cost / holding.qty), "ltp": ltp, "value": value,
                                 "unrealised_pnl": value - holding.cost})
            intraday_pnl = 0
            for symbol, pos in account.intraday.items():
                if pos.qty == 0:
                    continue
                ltp = self._last_price(symbol)
                pnl = pos.qty * ltp - pos.cost if pos.qty > 0 else pos.cost - abs(pos.qty) * ltp
                intraday_pnl += pnl
                intraday.append({"symbol": symbol, "qty": pos.qty, "avg_price": round(pos.cost / abs(pos.qty)),
                                 "ltp": ltp, "margin": pos.cost // self._margin_divisor, "unrealised_pnl": pnl})
            margin = account.intraday_margin(self._margin_divisor)
            return {
                "user_id": user_id,
                "cash": account.cash,
                "blocked_for_orders": account.blocked_cash,
                "intraday_margin": margin,
                "available": account.available(self._margin_divisor),
                "holdings_value": holdings_value,
                "realised_pnl": account.realised_pnl,
                "unrealised_pnl": unrealised + intraday_pnl,
                "equity": account.cash + holdings_value + intraday_pnl,
                "holdings": holdings,
                "intraday": intraday,
            }

    # ---- internals ----

    def _apply_trade(self, taker: Order, trade: EngineTrade, now: float) -> None:
        maker = self._orders[trade.sell_id if taker.side == "BUY" else trade.buy_id]
        trade_id = next(self._trade_ids)
        for order in (taker, maker):
            self._apply_fill(order, trade.qty, trade.price, trade_id, now)
        buyer, seller = (taker, maker) if taker.side == "BUY" else (maker, taker)
        self._market.on_trade({"id": trade_id, "symbol": taker.symbol, "price": trade.price, "qty": trade.qty,
                               "side": taker.side, "ts": now})
        self._audit.write("TRADE", trade_id=trade_id, symbol=taker.symbol, price=trade.price, qty=trade.qty,
                          buy_order_id=buyer.id, sell_order_id=seller.id, buyer=buyer.user_id, seller=seller.user_id,
                          aggressor=taker.side)
        maker_account = self._accounts[maker.user_id]
        if maker.status == "FILLED":
            self._log_order("ORDER_FILLED", maker, maker_account)
        self._keep(maker, maker_account)

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
        order.filled += qty
        order.filled_value += qty * price
        order.fills.append({"trade_id": trade_id, "price": price, "qty": qty, "ts": now})
        order.updated_at = now
        order.status = "FILLED" if order.filled == order.qty else "PARTIALLY_FILLED"

    def _release(self, order: Order, account: Account) -> None:
        """Gives back whatever an order still has reserved."""
        account.blocked_cash -= order.reserved_cash
        order.reserved_cash = 0
        if order.product == "CNC" and order.side == "SELL":
            account.holding(order.symbol).blocked -= order.remaining

    def _keep(self, order: Order, account: Account) -> None:
        """Finished robot orders are dropped so a long session does not grow without bound."""
        if order.status in OPEN_STATES or not account.is_bot:
            self._orders[order.id] = order
        else:
            self._orders.pop(order.id, None)

    def _log_order(self, event: str, order: Order, account: Account) -> None:
        if account.is_bot:
            return  # robot orders are only recorded when they trade
        self._audit.write(event, order_id=order.id, user=order.user_id, symbol=order.symbol, side=order.side,
                          type=order.type, product=order.product, qty=order.qty, price=order.price,
                          filled=order.filled, status=order.status, reason=order.reason)

    def _publish_book(self, symbol: str) -> None:
        bids, asks = self._engine.depth(symbol, self._depth_levels)
        self._market.on_book(symbol, [list(level) for level in bids], [list(level) for level in asks])

    def _last_price(self, symbol: str) -> int:
        return self._market.ltp(symbol) or self._instruments[symbol].prev_close
