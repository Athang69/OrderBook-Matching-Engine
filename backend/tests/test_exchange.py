"""Paper trading against the market. The tests feed in quotes and trades as the live feed would, and
run against the real C++ engine binary."""
import time

import pytest

from backend.app import charges, config
from backend.app.audit import AuditLog
from backend.app.engine_client import EngineClient
from backend.app.exchange import Exchange
from backend.app.instruments import make_instrument, price_band, tick_size
from backend.app.market_data import MarketData

RS = 100  # paise per rupee
START_CASH = 10_00_000 * RS


class Session:
    """The market session, set by each test."""

    def __init__(self):
        self.state = "OPEN"
        self.intraday_open = True
        self.day = "2026-10-15"

    def __call__(self):
        return {"state": self.state, "intraday_open": self.state == "OPEN" and self.intraday_open,
                "trading_day": self.day, "label": self.state.title()}


class Feed:
    """Quotes and trades for the stock TEST, as the live feed sends them."""

    def __init__(self, ex):
        self.ex = ex
        self.volume = 10_000
        ex.market.on_tick("TEST", 100 * RS, self.volume, time.time())  # the day's volume so far

    def quote(self, ltp, bid=None, ask=None, age=0.0):
        self.ex.market.on_quote("TEST", {"ltp": ltp, "bid": bid, "ask": ask, "quote_time": int(time.time()) + 1,
                                         "prev_close": 100 * RS, "volume": self.volume}, received=time.time() - age)

    def trade(self, price, qty):
        self.volume += qty
        traded = self.ex.market.on_tick("TEST", price, self.volume, time.time())
        self.ex.on_market_trade("TEST", price, traded)


@pytest.fixture
def ex():
    # A Rs 100 stock: tick is 1 paisa and the 10% band runs from Rs 90 to Rs 110.
    instruments = {"TEST": make_instrument("TEST", close=100 * RS, band_pct=10, data_date="2026-10-14"),
                   "TTF": make_instrument("TTF", close=100 * RS, band_pct=5, data_date="2026-10-14", series="BE")}
    engine = EngineClient(config.ENGINE_BIN)
    market = MarketData(instruments)
    session = Session()
    exchange = Exchange(engine, instruments, market, AuditLog(None), session, margin_divisor=5,
                        max_order_qty=100_000, depth_levels=5)
    exchange.create_account("alice", START_CASH)
    exchange.create_account("bob", START_CASH)
    exchange.market, exchange.session = market, session
    exchange.feed = Feed(exchange)
    yield exchange
    engine.close()


def fees(product, side, value):
    return charges.for_fill(product, side, value).total


def test_tick_size_slabs():
    assert tick_size(249_99) == 1
    assert tick_size(250_00) == 5
    assert tick_size(1000_00) == 5
    assert tick_size(1178_00) == 10
    assert tick_size(5000_01) == 50
    assert tick_size(15000_00) == 100
    assert tick_size(25000_00) == 500


def test_price_band_is_rounded_inwards_to_the_tick():
    lower, upper = price_band(692_25, 10, 5)  # 10% of Rs 692.25 is not on a 5 paise grid
    assert (lower, upper) == (623_05, 761_45)
    assert lower % 5 == 0 and upper % 5 == 0


def test_market_buy_fills_at_the_real_best_offer_and_pays_charges(ex):
    ex.feed.quote(100_00, bid=99_95, ask=100_05)
    order = ex.place_order("alice", "TEST", "BUY", "MARKET", "CNC", 10)
    assert order.status == "FILLED" and order.fills[0]["price"] == 100_05
    p = ex.portfolio("alice")
    paid = fees("CNC", "BUY", 10 * 100_05)
    assert order.charges.total == paid and order.charges.stt == round(10 * 100_05 * 0.001)
    assert p["cash"] == START_CASH - 10 * 100_05 - paid
    assert p["blocked_for_orders"] == 0  # the worst-case reservation is released
    assert p["holdings"][0]["qty"] == 10 and p["charges"]["total"] == paid


def test_old_or_odd_best_offer_falls_back_to_the_last_price(ex):
    ex.feed.quote(100_00, bid=99_95, ask=100_05, age=30)  # 30 seconds old
    assert ex.place_order("alice", "TEST", "BUY", "MARKET", "CNC", 1).fills[0]["price"] == 100_00
    ex.feed.quote(100_00, bid=99_00, ask=101_50)  # more than 0.5% from the last price
    assert ex.place_order("alice", "TEST", "BUY", "MARKET", "CNC", 1).fills[0]["price"] == 100_00


def test_limit_above_the_offer_trades_at_the_better_real_price(ex):
    ex.feed.quote(100_00, bid=99_95, ask=100_05)
    order = ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 10, 101_00)
    assert order.status == "FILLED" and order.fills[0]["price"] == 100_05


def test_waiting_order_fills_only_on_real_trades_and_only_their_volume(ex):
    ex.feed.quote(100_00, bid=99_95, ask=100_05)
    order = ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 100, 99_50)
    assert order.status == "OPEN"
    assert ex.portfolio("alice")["blocked_for_orders"] == 100 * 99_50 + fees("CNC", "BUY", 100 * 99_50)
    assert ex.own_book("TEST")[0] == [[99_50, 100, 1]]

    ex.feed.trade(99_80, 500)  # above the limit: no fill
    assert order.filled == 0
    ex.feed.trade(99_50, 30)  # at the limit, but only 30 shares traded
    assert order.status == "PARTIALLY_FILLED" and order.filled == 30
    ex.feed.trade(99_40, 1_000)  # through the limit: the rest fills, at the limit price
    assert order.status == "FILLED" and [f["price"] for f in order.fills] == [99_50, 99_50]
    assert ex.portfolio("alice")["blocked_for_orders"] == 0
    assert ex.own_book("TEST") == ([], [])


def test_price_then_time_priority_among_waiting_orders(ex):
    ex.feed.quote(100_00, bid=99_95, ask=100_05)
    first = ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 50, 99_50)
    second = ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 50, 99_50)
    better = ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 30, 99_60)
    ex.feed.trade(99_50, 60)
    assert better.filled == 30 and better.fills[0]["price"] == 99_60  # best price first
    assert first.filled == 30 and second.filled == 0  # then the earlier order at the same price


def test_sell_order_fills_when_the_market_trades_up(ex):
    ex.feed.quote(100_00, bid=99_95, ask=100_05)
    ex.place_order("alice", "TEST", "BUY", "MARKET", "CNC", 20)
    sell = ex.place_order("alice", "TEST", "SELL", "LIMIT", "CNC", 20, 100_50)
    assert sell.status == "OPEN"
    ex.feed.trade(100_40, 100)
    assert sell.filled == 0
    ex.feed.trade(100_60, 100)
    assert sell.status == "FILLED" and sell.fills[0]["price"] == 100_50
    p = ex.portfolio("alice")
    assert p["holdings"] == [] and p["realised_pnl"] == 20 * (100_50 - 100_05)


def test_risk_checks_reject_bad_orders(ex):
    ex.feed.quote(100_00, bid=99_95, ask=100_05)

    def reason(*args):
        order = ex.place_order(*args)
        assert order.status == "REJECTED"
        return order.reason

    assert reason("alice", "TEST", "BUY", "LIMIT", "CNC", 10_000, 105 * RS) == "INSUFFICIENT_FUNDS"
    assert reason("alice", "TEST", "SELL", "LIMIT", "CNC", 10, 100 * RS) == "INSUFFICIENT_SHARES"
    assert reason("alice", "TEST", "BUY", "LIMIT", "CNC", 10, 111 * RS) == "OUTSIDE_PRICE_BAND"
    assert reason("alice", "TEST", "BUY", "LIMIT", "CNC", 10, 89 * RS) == "OUTSIDE_PRICE_BAND"
    assert reason("alice", "TEST", "BUY", "LIMIT", "CNC", 100_001, 100 * RS) == "ORDER_SIZE_EXCEEDED"
    assert reason("alice", "NOPE", "BUY", "LIMIT", "CNC", 10, 100 * RS) == "UNKNOWN_SYMBOL"
    assert reason("alice", "TTF", "BUY", "MARKET", "MIS", 10) == "INTRADAY_NOT_ALLOWED"  # BE: delivery only
    assert reason("alice", "TTF", "BUY", "MARKET", "CNC", 10) == "NO_LIVE_PRICE"  # no price has arrived
    assert ex.portfolio("alice")["available"] == START_CASH  # rejected orders reserve nothing


def test_shares_promised_to_one_sell_order_cannot_back_another(ex):
    ex.feed.quote(100_00, bid=99_95, ask=100_05)
    ex.place_order("alice", "TEST", "BUY", "MARKET", "CNC", 100)
    assert ex.place_order("alice", "TEST", "SELL", "LIMIT", "CNC", 80, 105 * RS).status == "OPEN"
    second = ex.place_order("alice", "TEST", "SELL", "LIMIT", "CNC", 30, 105 * RS)
    assert second.status == "REJECTED" and second.reason == "INSUFFICIENT_SHARES"


def test_an_order_may_not_trade_with_your_own(ex):
    ex.feed.quote(100_00, bid=99_80, ask=100_20)
    assert ex.place_order("alice", "TEST", "BUY", "LIMIT", "MIS", 10, 99_90).status == "OPEN"  # inside the spread
    crossing = ex.place_order("alice", "TEST", "SELL", "LIMIT", "MIS", 10, 99_90)
    assert crossing.status == "REJECTED" and crossing.reason == "SELF_TRADE"
    assert ex.place_order("alice", "TEST", "SELL", "MARKET", "MIS", 10).reason == "SELF_TRADE"
    assert ex.place_order("alice", "TEST", "SELL", "LIMIT", "MIS", 10, 100_50).status == "OPEN"


def test_intraday_short_uses_margin_and_squares_off_at_the_real_offer(ex):
    ex.feed.quote(100_00, bid=99_95, ask=100_05)
    short = ex.place_order("alice", "TEST", "SELL", "MARKET", "MIS", 200)  # owns no shares: a short sale
    assert short.status == "FILLED" and short.fills[0]["price"] == 99_95
    p = ex.portfolio("alice")
    assert p["intraday"][0]["qty"] == -200
    assert p["intraday_margin"] == 200 * 99_95 // 5  # 20% of the position value

    ex.feed.quote(101_00, bid=100_95, ask=101_05)
    closing = ex.square_off("alice")
    assert len(closing) == 1 and closing[0].fills[0]["price"] == 101_05
    p = ex.portfolio("alice")
    assert p["intraday"] == [] and p["intraday_margin"] == 0
    loss = 200 * (101_05 - 99_95)
    assert p["realised_pnl"] == -loss
    assert p["cash"] == START_CASH - loss - p["charges"]["total"]
    assert p["charges"]["brokerage"] == short.charges.brokerage + closing[0].charges.brokerage > 0


def test_intraday_buying_power_is_five_times_cash(ex):
    ex.feed.quote(100_00, bid=99_95, ask=100_05)
    # Rs 10,00,000 of cash cannot buy 40,000 shares at Rs 99 for delivery, but can intraday.
    assert ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 40_000, 99 * RS).reason == "INSUFFICIENT_FUNDS"
    assert ex.place_order("alice", "TEST", "BUY", "LIMIT", "MIS", 40_000, 99 * RS).status == "OPEN"
    assert ex.place_order("alice", "TEST", "BUY", "LIMIT", "MIS", 20_000, 99 * RS).reason == "INSUFFICIENT_FUNDS"


def test_after_market_orders_wait_for_the_next_session(ex):
    ex.session.state = "CLOSED"
    ex.feed.quote(100_00, bid=99_95, ask=100_05)
    limit = ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 10, 100 * RS)
    market = ex.place_order("alice", "TEST", "BUY", "MARKET", "CNC", 5)
    assert limit.status == market.status == "OPEN" and limit.amo and market.amo
    assert ex.place_order("alice", "TEST", "BUY", "MARKET", "MIS", 5).reason == "INTRADAY_CLOSED"
    ex.feed.trade(98_00, 500)  # trades are ignored while the market is closed
    assert limit.filled == 0 and ex.own_book("TEST") == ([], [])

    ex.session.state = "OPEN"
    ex.feed.trade(99_00, 500)  # the first trade of the new session
    assert limit.status == "FILLED" and limit.fills[0]["price"] == 99_00
    assert market.status == "FILLED" and market.fills[0]["price"] == 99_00


def test_open_orders_expire_at_the_close(ex):
    ex.feed.quote(100_00, bid=99_95, ask=100_05)
    order = ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 10, 95 * RS)
    ex.on_clock()
    ex.session.state = "CLOSED"
    ex.on_clock()
    assert order.status == "CANCELLED" and order.reason == "EXPIRED"
    assert ex.portfolio("alice")["available"] == START_CASH


def test_intraday_positions_are_squared_off_at_3_20(ex):
    ex.feed.quote(100_00, bid=99_95, ask=100_05)
    ex.place_order("alice", "TEST", "BUY", "MARKET", "MIS", 100)
    ex.session.intraday_open = False  # 3:20 pm
    assert ex.place_order("alice", "TEST", "BUY", "MARKET", "MIS", 10).reason == "INTRADAY_CLOSED"
    ex.on_clock()
    assert ex.portfolio("alice")["intraday"] == []
    closing = ex.list_orders("alice")[0]
    assert closing["tag"] == "AUTO_SQUARE_OFF" and closing["status"] == "FILLED" and closing["side"] == "SELL"


def test_new_day_gives_an_empty_book_its_new_band(ex):
    ex.feed.quote(100_00, bid=99_95, ask=100_05)
    ex.place_order("alice", "TEST", "BUY", "MARKET", "CNC", 1)  # the stock now has a book in the engine
    instruments = {"TEST": make_instrument("TEST", close=120 * RS, band_pct=10, data_date="2026-10-15")}
    ex.set_instruments(instruments)
    ex.feed.quote(120_00, bid=119_95, ask=120_05)
    assert ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 1, 115 * RS).status == "OPEN"  # above the old band


def test_cancel_errors(ex):
    ex.feed.quote(100_00, bid=99_95, ask=100_05)
    order = ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 10, 99 * RS)
    with pytest.raises(PermissionError):
        ex.cancel_order(order.id, "bob")
    ex.cancel_order(order.id, "alice")
    with pytest.raises(ValueError):
        ex.cancel_order(order.id, "alice")
    with pytest.raises(KeyError):
        ex.cancel_order(987654, "alice")


def test_charges_follow_the_published_rates():
    delivery = charges.for_fill("CNC", "BUY", 1_00_000 * RS)  # Rs 1 lakh
    assert (delivery.brokerage, delivery.stt, delivery.stamp) == (0, 100_00, 15_00)
    assert delivery.exchange == round(1_00_000 * RS * 0.0000297) and delivery.sebi == 10
    assert delivery.gst == round((delivery.exchange + delivery.sebi) * 0.18)
    sell = charges.for_fill("MIS", "SELL", 1_00_000 * RS)
    assert sell.brokerage == 20_00 and sell.stt == 25_00 and sell.stamp == 0  # 0.03% would be Rs 30: capped at Rs 20
    second_fill = charges.for_fill("MIS", "SELL", 1_00_000 * RS, brokerage_so_far=20_00)
    assert second_fill.brokerage == 0  # one order never pays more than Rs 20
