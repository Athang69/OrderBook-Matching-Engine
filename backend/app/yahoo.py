"""Live and historical NSE prices from Yahoo Finance, free and without an account.

Five services are used:
  quotes  one request returns the latest quote for up to 50 stocks: last price, best bid and best
          offer, the day's open, range and volume, the 52-week range, market value and P/E
  chart   price bars: one-minute bars for today, up to weekly bars for five years
  profile a company's sector, industry and business description
  similar the companies Yahoo considers most like a given one
  stream  a WebSocket that pushes each stock's last traded price and the day's volume as it trades,
          about once a second for busy stocks. Measured on 15 Oct 2026, prices reached us about two
          seconds after they traded on NSE.

Yahoo does not publish market depth (the quantities waiting at each price) or every single trade;
brokers' data feeds, which need an account with the broker, have those.

The yfinance library is used for the session cookie these services need and to decode the stream.
"""
import asyncio
import base64
import json
import logging
import threading
import time
from collections.abc import Callable, Iterable

log = logging.getLogger("orderbook.yahoo")

QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/"
PROFILE_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
SIMILAR_URL = "https://query2.finance.yahoo.com/v6/finance/recommendationsbysymbol/"
STREAM_URL = "wss://streamer.finance.yahoo.com/?version=2"
QUOTES_PER_REQUEST = 50
RESUBSCRIBE_SECONDS = 15  # the stream stops sending to clients that do not repeat their subscription

# Bar size for each chart range.
CHART_INTERVALS = {"1d": "1m", "5d": "5m", "1mo": "30m", "6mo": "1d", "1y": "1d", "5y": "1wk"}


def to_yahoo(symbol: str) -> str:
    """NSE symbol to Yahoo ticker: RELIANCE -> RELIANCE.NS. Index tickers (^NSEI) pass through."""
    return symbol if symbol.startswith("^") else f"{symbol}.NS"


def from_yahoo(ticker: str) -> str:
    return ticker[:-3] if ticker.endswith(".NS") else ticker


def paise(value) -> int | None:
    """Yahoo sends rupees as floats; zero or missing means not known."""
    if isinstance(value, (int, float)) and value > 0:
        return int(round(value * 100))
    return None


def parse_quote(q: dict) -> dict:
    """One Yahoo quote as the fields this app uses, prices in paise."""
    return {
        "ltp": paise(q.get("regularMarketPrice")),
        "prev_close": paise(q.get("regularMarketPreviousClose")),
        "open": paise(q.get("regularMarketOpen")),
        "high": paise(q.get("regularMarketDayHigh")),
        "low": paise(q.get("regularMarketDayLow")),
        "volume": int(q.get("regularMarketVolume") or 0),
        "bid": paise(q.get("bid")),
        "ask": paise(q.get("ask")),
        "quote_time": int(q.get("regularMarketTime") or 0) or None,
        "name": q.get("longName") or q.get("shortName"),
        "week52_high": paise(q.get("fiftyTwoWeekHigh")),
        "week52_low": paise(q.get("fiftyTwoWeekLow")),
        "market_cap": int(q["marketCap"]) if q.get("marketCap") else None,  # rupees
        "pe": round(float(q["trailingPE"]), 2) if q.get("trailingPE") else None,
        "eps": round(float(q["epsTrailingTwelveMonths"]), 2) if q.get("epsTrailingTwelveMonths") else None,
        "dividend_yield": round(float(q["dividendYield"]), 2) if q.get("dividendYield") else None,  # percent
        "price_to_book": round(float(q["priceToBook"]), 2) if q.get("priceToBook") else None,
        "avg_volume": int(q.get("averageDailyVolume3Month") or 0) or None,
        "market_state": q.get("marketState"),
    }


def parse_chart(result: dict) -> dict:
    """Chart bars as [time, open, high, low, close, volume] with prices in paise, oldest first."""
    times = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    bars = []
    for i, t in enumerate(times):
        o, h, l, c = (quote.get(k, [None] * len(times))[i] for k in ("open", "high", "low", "close"))
        if c is None or o is None:
            continue  # minutes with no trade
        v = (quote.get("volume") or [0] * len(times))[i] or 0
        bars.append([int(t), paise(o), paise(h), paise(l), paise(c), int(v)])
    meta = result.get("meta", {})
    return {"bars": bars, "prev_close": paise(meta.get("chartPreviousClose") or meta.get("previousClose")),
            "ltp": paise(meta.get("regularMarketPrice")), "quote_time": meta.get("regularMarketTime")}


def parse_tick(message: dict) -> dict | None:
    """A decoded stream message as {ticker, price, time, day_volume}; None if it has no price."""
    price = paise(message.get("price"))
    if price is None or "id" not in message:
        return None
    return {"ticker": message["id"], "price": price, "time": int(message.get("time", 0)) / 1000 or time.time(),
            "day_volume": int(message.get("day_volume", 0) or 0)}


class YahooClient:
    """Quotes and charts over HTTPS. The calls block, so run them in a worker thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()  # yfinance's session is shared; send one request at a time
        self._data = None

    def _get(self, url: str, params: dict) -> dict:
        from yfinance.data import YfData  # imported late: it is slow to import and not needed offline

        with self._lock:
            if self._data is None:
                self._data = YfData()
            return self._data.get_raw_json(url, params=params, timeout=10)

    def quotes(self, tickers: Iterable[str]) -> dict[str, dict]:
        tickers = list(dict.fromkeys(tickers))
        out: dict[str, dict] = {}
        for start in range(0, len(tickers), QUOTES_PER_REQUEST):
            chunk = tickers[start:start + QUOTES_PER_REQUEST]
            reply = self._get(QUOTE_URL, {"symbols": ",".join(chunk)})
            for q in (reply.get("quoteResponse") or {}).get("result") or []:
                out[q["symbol"]] = parse_quote(q)
        return out

    def chart(self, ticker: str, range_: str) -> dict:
        reply = self._get(CHART_URL + ticker, {"range": range_, "interval": CHART_INTERVALS[range_],
                                               "includePrePost": "false"})
        results = (reply.get("chart") or {}).get("result") or []
        if not results:
            raise LookupError(f"no chart data for {ticker}")
        return parse_chart(results[0])


    def profile(self, ticker: str) -> dict:
        """The company's sector, industry and a short description of its business."""
        reply = self._get(PROFILE_URL + ticker, {"modules": "assetProfile"})
        results = (reply.get("quoteSummary") or {}).get("result") or [{}]
        profile = results[0].get("assetProfile") or {}
        return {"sector": profile.get("sector"), "industry": profile.get("industry"),
                "summary": profile.get("longBusinessSummary")}

    def similar(self, ticker: str) -> list[str]:
        """Tickers of similar companies, as Yahoo suggests them (often four or five)."""
        reply = self._get(SIMILAR_URL + ticker, {})
        results = (reply.get("finance") or {}).get("result") or [{}]
        return [r["symbol"] for r in results[0].get("recommendedSymbols") or [] if r.get("symbol")]


class YahooStream:
    """Keeps one WebSocket open, subscribed to the tickers asked for, and passes each price on.

    Reconnects by itself, waiting longer after each failure (up to 30 seconds).
    """

    def __init__(self, on_tick: Callable[[dict], None]):
        self._on_tick = on_tick
        self._wanted: set[str] = set()
        self.connected = False
        self.last_message: float | None = None
        self.error: str | None = None

    def set_tickers(self, tickers: Iterable[str]) -> None:
        self._wanted = set(tickers)

    async def run(self) -> None:
        from google.protobuf.json_format import MessageToDict
        from websockets.asyncio.client import connect
        from yfinance.pricing_pb2 import PricingData

        def decode(raw: str | bytes) -> dict | None:
            encoded = json.loads(raw).get("message", "")
            data = PricingData()
            data.ParseFromString(base64.b64decode(encoded))
            return parse_tick(MessageToDict(data, preserving_proto_field_name=True))

        backoff = 1.0
        while True:
            try:
                async with connect(STREAM_URL, open_timeout=10, ping_interval=20, max_queue=1024) as socket:
                    self.connected, self.error, backoff = True, None, 1.0
                    sent: set[str] = set()
                    last_subscribe = 0.0
                    while True:
                        wanted = set(self._wanted)
                        if wanted != sent or time.monotonic() - last_subscribe > RESUBSCRIBE_SECONDS:
                            gone = sent - wanted
                            if gone:
                                await socket.send(json.dumps({"unsubscribe": sorted(gone)}))
                            if wanted:
                                await socket.send(json.dumps({"subscribe": sorted(wanted)}))
                            sent, last_subscribe = wanted, time.monotonic()
                        try:
                            raw = await asyncio.wait_for(socket.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue
                        try:
                            tick = decode(raw)
                        except Exception:  # one bad message should not drop the connection
                            log.debug("could not decode a stream message", exc_info=True)
                            continue
                        if tick is not None:
                            self.last_message = time.time()
                            self._on_tick(tick)
            except asyncio.CancelledError:
                self.connected = False
                raise
            except Exception as err:  # network down, Yahoo closing the connection, DNS failure
                self.connected = False
                self.error = f"{type(err).__name__}: {err}"[:200]
                log.warning("price stream disconnected (%s); retrying in %.0f s", self.error, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
