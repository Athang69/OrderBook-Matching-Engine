"""Order management tests. They run against the real C++ engine binary."""
import pytest

from backend.app import config
from backend.app.audit import AuditLog
from backend.app.engine_client import EngineClient
from backend.app.exchange import Exchange
from backend.app.instruments import make_instrument, price_band, tick_size
from backend.app.market_data import MarketData

RS = 100  # paise per rupee
START_CASH = 10_00_000 * RS


@pytest.fixture
def ex():
    # A Rs 100 stock: tick is 1 paise and the 10% band runs from Rs 90 to Rs 110.
    inst = make_instrument("TEST", prev_close=100 * RS, open_=100 * RS, high=101 * RS, low=99 * RS, close=100 * RS,
                           volume=1000, trades=10, band_pct=10, data_date="2026-01-01")
    engine = EngineClient(config.ENGINE_BIN)
    market = MarketData([inst])
    exchange = Exchange(engine, [inst], market, AuditLog(None), margin_divisor=5, max_order_qty=100_000, depth_levels=5)
    exchange.create_account("alice", START_CASH)
    exchange.create_account("bob", START_CASH, shares=1000)  # bob owns 1,000 shares bought at Rs 100
    exchange.market = market
    yield exchange
    engine.close()


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


def test_buy_order_blocks_cash_and_cancel_releases_it(ex):
    order = ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 100, 99 * RS)
    assert order.status == "OPEN"
    p = ex.portfolio("alice")
    assert p["blocked_for_orders"] == 100 * 99 * RS
    assert p["available"] == START_CASH - 100 * 99 * RS
    assert p["cash"] == START_CASH  # nothing is spent until the order trades

    cancelled = ex.cancel_order(order.id, "alice")
    assert cancelled.status == "CANCELLED"
    assert ex.portfolio("alice")["available"] == START_CASH
    assert ex.market.snapshot("TEST")["bids"] == []


def test_trade_moves_cash_and_shares_on_both_sides(ex):
    sell = ex.place_order("bob", "TEST", "SELL", "LIMIT", "CNC", 40, 100 * RS)
    buy = ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 40, 101 * RS)
    assert buy.status == "FILLED" and ex.get_order(sell.id).status == "FILLED"
    assert buy.fills[0]["price"] == 100 * RS  # trades at the waiting order's price, not the buyer's limit

    alice, bob = ex.portfolio("alice"), ex.portfolio("bob")
    assert alice["cash"] == START_CASH - 40 * 100 * RS
    assert alice["blocked_for_orders"] == 0  # the extra Rs 1 a share that was reserved is released
    assert alice["holdings"][0]["qty"] == 40
    assert bob["cash"] == START_CASH + 40 * 100 * RS
    assert bob["holdings"][0]["qty"] == 960
    assert ex.market.snapshot("TEST")["ltp"] == 100 * RS


def test_risk_checks_reject_bad_orders(ex):
    def reason(*args):
        order = ex.place_order(*args)
        assert order.status == "REJECTED"
        return order.reason

    assert reason("alice", "TEST", "BUY", "LIMIT", "CNC", 100_000, 105 * RS) == "INSUFFICIENT_FUNDS"
    assert reason("alice", "TEST", "SELL", "LIMIT", "CNC", 10, 100 * RS) == "INSUFFICIENT_SHARES"
    assert reason("alice", "TEST", "BUY", "LIMIT", "CNC", 10, 111 * RS) == "OUTSIDE_PRICE_BAND"
    assert reason("alice", "TEST", "BUY", "LIMIT", "CNC", 10, 89 * RS) == "OUTSIDE_PRICE_BAND"
    assert reason("alice", "TEST", "BUY", "LIMIT", "CNC", 100_001, 100 * RS) == "ORDER_SIZE_EXCEEDED"
    assert reason("alice", "NOPE", "BUY", "LIMIT", "CNC", 10, 100 * RS) == "UNKNOWN_SYMBOL"
    assert ex.portfolio("alice")["available"] == START_CASH  # rejected orders reserve nothing


def test_shares_promised_to_one_sell_order_cannot_back_another(ex):
    first = ex.place_order("bob", "TEST", "SELL", "LIMIT", "CNC", 800, 105 * RS)
    second = ex.place_order("bob", "TEST", "SELL", "LIMIT", "CNC", 300, 105 * RS)
    assert first.status == "OPEN"
    assert second.status == "REJECTED" and second.reason == "INSUFFICIENT_SHARES"


def test_partial_fill(ex):
    ex.place_order("bob", "TEST", "SELL", "LIMIT", "CNC", 60, 100 * RS)
    buy = ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 100, 100 * RS)
    assert buy.status == "PARTIALLY_FILLED" and buy.filled == 60 and buy.remaining == 40
    p = ex.portfolio("alice")
    assert p["cash"] == START_CASH - 60 * 100 * RS
    assert p["blocked_for_orders"] == 40 * 100 * RS  # still reserved for the part that is waiting
    assert ex.market.snapshot("TEST")["bids"] == [[100 * RS, 40, 1]]


def test_market_order_reserves_worst_case_then_releases(ex):
    ex.place_order("bob", "TEST", "SELL", "LIMIT", "CNC", 50, 100 * RS)
    buy = ex.place_order("alice", "TEST", "BUY", "MARKET", "CNC", 80)
    # Only 50 shares were on offer: 50 trade, the other 30 are cancelled.
    assert buy.status == "CANCELLED" and buy.reason == "NO_LIQUIDITY" and buy.filled == 50
    p = ex.portfolio("alice")
    assert p["cash"] == START_CASH - 50 * 100 * RS
    assert p["blocked_for_orders"] == 0


def test_price_time_priority_end_to_end(ex):
    a = ex.place_order("bob", "TEST", "SELL", "LIMIT", "CNC", 50, 100_00)
    c = ex.place_order("bob", "TEST", "SELL", "LIMIT", "CNC", 40, 100_05)
    b = ex.place_order("bob", "TEST", "SELL", "LIMIT", "CNC", 30, 100_00)
    buy = ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 70, 100_05)
    assert [(f["price"], f["qty"]) for f in buy.fills] == [(100_00, 50), (100_00, 20)]
    assert ex.get_order(a.id).status == "FILLED"
    assert ex.get_order(b.id).filled == 20 and ex.get_order(b.id).status == "PARTIALLY_FILLED"
    assert ex.get_order(c.id).filled == 0


def test_intraday_uses_margin_allows_short_selling_and_squares_off(ex):
    ex.place_order("bob", "TEST", "BUY", "LIMIT", "CNC", 500, 100 * RS)   # someone to sell to
    ex.place_order("bob", "TEST", "SELL", "LIMIT", "CNC", 500, 102 * RS)  # someone to buy back from

    # Alice owns no shares, but an intraday order may sell short.
    short = ex.place_order("alice", "TEST", "SELL", "MARKET", "MIS", 200)
    assert short.status == "FILLED"
    p = ex.portfolio("alice")
    assert p["intraday"][0]["qty"] == -200
    assert p["intraday_margin"] == 200 * 100 * RS // 5  # 20% of the position value
    assert p["cash"] == START_CASH  # no cash moves until the position is closed

    closing = ex.square_off("alice")
    assert len(closing) == 1 and closing[0].status == "FILLED"
    p = ex.portfolio("alice")
    assert p["intraday"] == [] and p["intraday_margin"] == 0
    # Sold at Rs 100, bought back at Rs 102: a loss of Rs 2 a share.
    assert p["realised_pnl"] == -200 * 2 * RS
    assert p["cash"] == START_CASH - 200 * 2 * RS


def test_intraday_buying_power_is_five_times_cash(ex):
    ex.place_order("bob", "TEST", "SELL", "LIMIT", "CNC", 1000, 100 * RS)
    # Rs 10,00,000 of cash cannot buy 40,000 shares at Rs 100 for delivery, but can intraday.
    assert ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 40_000, 100 * RS).reason == "INSUFFICIENT_FUNDS"
    intraday = ex.place_order("alice", "TEST", "BUY", "LIMIT", "MIS", 40_000, 100 * RS)
    assert intraday.status == "PARTIALLY_FILLED" and intraday.filled == 1000
    assert ex.place_order("alice", "TEST", "BUY", "LIMIT", "MIS", 20_000, 100 * RS).reason == "INSUFFICIENT_FUNDS"


def test_cancel_errors(ex):
    order = ex.place_order("alice", "TEST", "BUY", "LIMIT", "CNC", 10, 99 * RS)
    with pytest.raises(PermissionError):
        ex.cancel_order(order.id, "bob")
    ex.cancel_order(order.id, "alice")
    with pytest.raises(ValueError):
        ex.cancel_order(order.id, "alice")
    with pytest.raises(KeyError):
        ex.cancel_order(987654, "alice")
