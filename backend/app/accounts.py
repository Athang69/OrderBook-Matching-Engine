"""Virtual accounts: cash, delivery holdings and intraday positions.

Delivery (CNC): a buy pays the full amount and adds to holdings; a sell needs the shares.
Intraday (MIS): only a 20% margin is blocked, short selling is allowed, and profit or
loss is settled in cash when the position is reduced or closed.
"""
from dataclasses import dataclass, field


@dataclass
class Holding:
    qty: int = 0
    cost: int = 0  # total paid for the shares currently held
    blocked: int = 0  # shares reserved by open delivery sell orders


@dataclass
class IntradayPosition:
    qty: int = 0  # positive is long, negative is short
    cost: int = 0  # total entry value of the open quantity


@dataclass
class Account:
    user_id: str
    cash: int
    is_bot: bool = False
    blocked_cash: int = 0  # reserved by open orders
    realised_pnl: int = 0
    holdings: dict[str, Holding] = field(default_factory=dict)
    intraday: dict[str, IntradayPosition] = field(default_factory=dict)

    def intraday_margin(self, divisor: int) -> int:
        """Margin blocked against open intraday positions."""
        return sum(pos.cost // divisor for pos in self.intraday.values())

    def available(self, divisor: int) -> int:
        return self.cash - self.blocked_cash - self.intraday_margin(divisor)

    def holding(self, symbol: str) -> Holding:
        return self.holdings.setdefault(symbol, Holding())

    def position(self, symbol: str) -> IntradayPosition:
        return self.intraday.setdefault(symbol, IntradayPosition())

    # ---- fills ----

    def fill_delivery_buy(self, symbol: str, qty: int, price: int) -> None:
        self.cash -= qty * price
        holding = self.holding(symbol)
        holding.qty += qty
        holding.cost += qty * price

    def fill_delivery_sell(self, symbol: str, qty: int, price: int) -> None:
        holding = self.holding(symbol)
        cost_removed = holding.cost * qty // holding.qty
        self.realised_pnl += qty * price - cost_removed
        holding.cost -= cost_removed
        holding.qty -= qty
        holding.blocked -= qty
        self.cash += qty * price

    def fill_intraday(self, symbol: str, side: str, qty: int, price: int) -> None:
        pos = self.position(symbol)
        sign = 1 if side == "BUY" else -1
        closing = min(qty, abs(pos.qty)) if pos.qty * sign < 0 else 0
        if closing:
            cost_removed = pos.cost * closing // abs(pos.qty)
            # Long: profit when sold above entry. Short: profit when bought back below entry.
            pnl = closing * price - cost_removed if pos.qty > 0 else cost_removed - closing * price
            self.cash += pnl
            self.realised_pnl += pnl
            pos.cost -= cost_removed
            pos.qty += sign * closing
        opening = qty - closing
        if opening:
            pos.qty += sign * opening
            pos.cost += opening * price

    def closable_qty(self, symbol: str, side: str) -> int:
        """How much of an intraday order on this side would only reduce an existing position."""
        pos = self.intraday.get(symbol)
        if pos is None:
            return 0
        sign = 1 if side == "BUY" else -1
        return abs(pos.qty) if pos.qty * sign < 0 else 0
