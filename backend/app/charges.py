"""The charges on every trade, as an Indian discount broker's contract note shows them.

Rates are those published for NSE equity in 2025 (brokerage as at a typical discount broker).
They change from time to time, and brokers differ, so check a current contract note before relying
on them. All amounts are in paise and rounded to the nearest paisa.

                      Delivery (CNC)           Intraday (MIS)
  Brokerage           none                     0.03% or Rs 20 an order, whichever is lower
  STT                 0.1% on buys and sells   0.025% on sells
  Exchange charges    0.00297% of the value    0.00297% of the value
  SEBI fee            Rs 10 a crore            Rs 10 a crore
  Stamp duty          0.015% on buys           0.003% on buys
  GST                 18% of brokerage, exchange charges and the SEBI fee
"""
from dataclasses import asdict, dataclass

BROKERAGE_RATE = 0.0003
BROKERAGE_CAP = 20_00  # Rs 20 per order
EXCHANGE_RATE = 0.0000297
SEBI_RATE = 0.000001
GST_RATE = 0.18
STT = {("CNC", "BUY"): 0.001, ("CNC", "SELL"): 0.001, ("MIS", "BUY"): 0.0, ("MIS", "SELL"): 0.00025}
STAMP = {("CNC", "BUY"): 0.00015, ("MIS", "BUY"): 0.00003}


@dataclass
class Charges:
    brokerage: int = 0
    stt: int = 0
    exchange: int = 0
    sebi: int = 0
    stamp: int = 0
    gst: int = 0

    @property
    def total(self) -> int:
        return self.brokerage + self.stt + self.exchange + self.sebi + self.stamp + self.gst

    def add(self, other: "Charges") -> None:
        for name, value in asdict(other).items():
            setattr(self, name, getattr(self, name) + value)

    def to_dict(self) -> dict:
        return {**asdict(self), "total": self.total}


def for_fill(product: str, side: str, value: int, brokerage_so_far: int = 0) -> Charges:
    """Charges on one fill worth `value` paise. `brokerage_so_far` is what the same order has already
    paid, so an intraday order never pays more than Rs 20 in brokerage however many fills it has."""
    brokerage = 0
    if product == "MIS":
        brokerage = min(round(value * BROKERAGE_RATE), max(0, BROKERAGE_CAP - brokerage_so_far))
    exchange = round(value * EXCHANGE_RATE)
    sebi = round(value * SEBI_RATE)
    return Charges(
        brokerage=brokerage,
        stt=round(value * STT[(product, side)]),
        exchange=exchange,
        sebi=sebi,
        stamp=round(value * STAMP.get((product, side), 0.0)),
        gst=round((brokerage + exchange + sebi) * GST_RATE),
    )


def estimate(product: str, side: str, value: int) -> int:
    """The most an order of this value can cost in charges; reserved with the order."""
    return for_fill(product, side, value).total
