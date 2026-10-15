"""The live market data: reading Yahoo's replies, building trades and bars from the stream, and the
market clock. No network is used."""
import datetime as dt

from backend.app.instruments import make_instrument
from backend.app.market_data import MarketData
from backend.app.session import IST, session_status
from backend.app.yahoo import from_yahoo, parse_chart, parse_quote, parse_tick, to_yahoo

T0 = 1_792_036_800.0  # 15 Oct 2026, 09:30 IST (a Thursday)


def market():
    return MarketData({"RELIANCE": make_instrument("RELIANCE", close=1174_60, band_pct=10, data_date="2026-10-14")})


def test_tickers():
    assert to_yahoo("RELIANCE") == "RELIANCE.NS" and to_yahoo("^NSEI") == "^NSEI"
    assert from_yahoo("M&M.NS") == "M&M" and from_yahoo("^NSEI") == "^NSEI"


def test_quote_is_read_in_paise():
    q = parse_quote({"regularMarketPrice": 1181.0, "regularMarketPreviousClose": 1174.6, "bid": 1180.7, "ask": 0.0,
                     "regularMarketVolume": 1913807, "regularMarketTime": 1792037993, "longName": "Reliance Industries Limited",
                     "marketCap": 15981850132480, "trailingPE": 21.244827, "marketState": "REGULAR"})
    assert (q["ltp"], q["prev_close"], q["bid"], q["ask"]) == (1181_00, 1174_60, 1180_70, None)  # 0 means not known
    assert q["volume"] == 1913807 and q["pe"] == 21.24 and q["name"] == "Reliance Industries Limited"
    assert q["market_state"] == "REGULAR" and q["week52_high"] is None


def test_chart_skips_minutes_without_trades():
    chart = parse_chart({"timestamp": [1, 61, 121], "meta": {"chartPreviousClose": 1174.6},
                         "indicators": {"quote": [{"open": [1, None, 3], "high": [1, None, 3], "low": [1, None, 3],
                                                   "close": [1.5, None, 3.25], "volume": [10, None, 30]}]}})
    assert chart["bars"] == [[1, 100, 100, 100, 150, 10], [121, 300, 300, 300, 325, 30]]
    assert chart["prev_close"] == 1174_60


def test_stream_message():
    tick = parse_tick({"id": "TCS.NS", "price": 2363.0, "time": "1792037753000", "day_volume": "2173108"})
    assert tick == {"ticker": "TCS.NS", "price": 2363_00, "time": 1792037753.0, "day_volume": 2173108}
    assert parse_tick({"id": "TCS.NS"}) is None


def test_trades_come_from_the_rise_in_day_volume_and_the_tick_test():
    m = market()
    assert m.on_tick("RELIANCE", 1180_00, 1_000_000, T0) == 0  # the first message only sets the volume so far
    assert m.on_tick("RELIANCE", 1180_50, 1_000_400, T0 + 1) == 400
    assert m.on_tick("RELIANCE", 1180_20, 1_000_500, T0 + 2) == 100
    assert m.on_tick("RELIANCE", 1180_20, 1_000_500, T0 + 3) == 0  # no new volume: no trade
    tape = m.tape("RELIANCE", 10)
    assert [(t["price"], t["qty"], t["side"]) for t in tape] == [(1180_20, 100, "SELL"), (1180_50, 400, "BUY")]
    q = m.snapshot("RELIANCE")
    assert q["ltp"] == 1180_20 and q["volume"] == 1_000_500 and q["high"] == 1180_50 and q["low"] == 1180_00
    assert q["vwap"] == round((1180_50 * 400 + 1180_20 * 100) / 500)


def test_bars_from_yahoo_are_extended_by_the_stream():
    m = market()
    start = int(T0) - 600
    m.set_bars("RELIANCE", [[start + 60 * i, 1180_00 + i, 1181_00 + i, 1179_00 + i, 1180_00 + i, 1000] for i in range(10)])
    assert m.snapshot("RELIANCE")["vwap"] is not None
    m.on_tick("RELIANCE", 1190_00, 50_000, T0)
    m.on_tick("RELIANCE", 1191_00, 50_200, T0 + 30)
    bars = m.bars("RELIANCE")
    assert len(bars) == 11 and bars[-1] == [int(T0), 1190_00, 1191_00, 1190_00, 1191_00, 200]


def test_an_older_quote_does_not_undo_a_newer_trade():
    m = market()
    m.on_tick("RELIANCE", 1185_00, 1_000, T0 + 10)
    m.on_quote("RELIANCE", {"ltp": 1180_00, "quote_time": int(T0), "bid": 1184_90, "ask": 1185_10, "high": 1182_00,
                            "low": 1179_00, "volume": 900})
    q = m.snapshot("RELIANCE")
    assert q["ltp"] == 1185_00 and q["bid"] == 1184_90 and q["high"] == 1185_00 and q["low"] == 1179_00


def at(day: int, hour: int, minute: int) -> float:
    return dt.datetime(2026, 10, day, hour, minute, tzinfo=IST).timestamp()


def test_market_clock():
    assert session_status(at(15, 9, 5))["state"] == "PRE_OPEN"
    open_ = session_status(at(15, 10, 0))
    assert open_["state"] == "OPEN" and open_["intraday_open"]
    late = session_status(at(15, 15, 25))
    assert late["state"] == "OPEN" and not late["intraday_open"]  # after the 3:20 pm square-off
    evening = session_status(at(15, 16, 0))
    assert evening["state"] == "CLOSED" and evening["opens_at"] == at(16, 9, 15)
    saturday = session_status(at(17, 11, 0))
    assert saturday["state"] == "CLOSED" and saturday["opens_at"] == at(19, 9, 15)  # Monday
    assert session_status(at(15, 8, 0))["opens_at"] == at(15, 9, 15)


def test_a_holiday_is_recognised_from_yahoo():
    now = at(15, 11, 0)
    holiday = session_status(now, "CLOSED", now - 10)
    assert holiday["state"] == "CLOSED" and "holiday" in holiday["label"]
    assert session_status(now, "REGULAR", now - 10)["state"] == "OPEN"
    assert session_status(now, "CLOSED", now - 3600)["state"] == "OPEN"  # too old to trust
