"""Pre-trade checks. Every order passes through here before it reaches the matching engine."""
from dataclasses import dataclass

from .accounts import Account
from .instruments import Instrument


@dataclass
class Reservation:
    cash: int = 0  # paise to block until the order fills or is cancelled
    shares: int = 0  # shares to block for a delivery sell


def check_order(account: Account, instrument: Instrument, side: str, order_type: str, product: str, qty: int,
                price: int | None, margin_divisor: int, max_order_qty: int) -> tuple[str | None, Reservation]:
    """Returns (reject reason or None, what to reserve)."""
    # Check 1: the order itself is valid for this stock.
    if qty <= 0:
        return "BAD_QUANTITY", Reservation()
    if qty > max_order_qty:
        return "ORDER_SIZE_EXCEEDED", Reservation()
    if order_type == "LIMIT":
        if price is None:
            return "PRICE_REQUIRED", Reservation()
        if price < instrument.lower_band or price > instrument.upper_band:
            return "OUTSIDE_PRICE_BAND", Reservation()
        if price % instrument.tick != 0:
            return "BAD_TICK", Reservation()

    # A market order has no price, so reserve for the worst case: the upper band.
    worst_price = price if order_type == "LIMIT" else instrument.upper_band

    if product == "CNC":
        if side == "BUY":
            # Check 2: enough cash for the full order value.
            needed = qty * worst_price
            if account.available(margin_divisor) < needed:
                return "INSUFFICIENT_FUNDS", Reservation()
            return None, Reservation(cash=needed)
        # Check 3: the seller owns the shares and they are not already promised to another order.
        holding = account.holdings.get(instrument.symbol)
        free = holding.qty - holding.blocked if holding else 0
        if free < qty:
            return "INSUFFICIENT_SHARES", Reservation()
        return None, Reservation(shares=qty)

    # Intraday: margin is needed only for the part that opens or adds to a position.
    opening = max(0, qty - account.closable_qty(instrument.symbol, side))
    needed = opening * worst_price // margin_divisor
    if account.available(margin_divisor) < needed:
        return "INSUFFICIENT_FUNDS", Reservation()
    return None, Reservation(cash=needed)
