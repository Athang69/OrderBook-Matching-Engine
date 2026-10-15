"""Daily closing prices for NSE stocks, from Yahoo Finance via yfinance (as in the original script).

Prices are cached in data/history/ and fetched at most once a day. Only completed days are used:
the download stops before today. If the download fails, yesterday's cache is used and the result
is marked stale.
"""
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "history"
SOURCE = "Yahoo Finance (yfinance), daily closes adjusted for dividends and splits"


class PriceDataError(RuntimeError):
    pass


@dataclass
class PriceHistory:
    dates: list[str]
    prices: np.ndarray  # one row per day, one column per symbol, in rupees
    source: str
    stale: bool = False


def yahoo_ticker(symbol: str) -> str:
    return f"{symbol}.NS"  # NSE listings on Yahoo Finance


def load_prices(symbols: list[str], start: str, cache_dir: Path = CACHE_DIR) -> PriceHistory:
    today = dt.date.today()
    series: dict[str, pd.Series] = {}
    to_fetch = []
    for symbol in symbols:
        cached = _read_cache(cache_dir, symbol)
        if cached is not None and _fetched_on(cache_dir, symbol) == today:
            series[symbol] = cached
        else:
            to_fetch.append(symbol)

    stale = False
    if to_fetch:
        try:
            fetched = _download(to_fetch, start, today)
        except Exception as err:  # network errors, Yahoo refusing requests, empty responses
            fetched = {}
            reason = str(err) or type(err).__name__
        else:
            reason = "no data returned"
        for symbol in to_fetch:
            if symbol in fetched:
                series[symbol] = fetched[symbol]
                _write_cache(cache_dir, symbol, fetched[symbol])
            else:
                cached = _read_cache(cache_dir, symbol)
                if cached is None:
                    raise PriceDataError(f"Could not download price history for {symbol} ({reason}). "
                                         "Check the internet connection and try again.")
                series[symbol] = cached
                stale = True

    frame = pd.DataFrame(series)[symbols]
    frame = frame[frame.index >= pd.Timestamp(start)].dropna()  # only days every stock traded
    return PriceHistory(dates=[d.strftime("%Y-%m-%d") for d in frame.index], prices=frame.to_numpy(dtype=float),
                        source=SOURCE, stale=stale)


def _download(symbols: list[str], start: str, end: dt.date) -> dict[str, pd.Series]:
    import yfinance as yf  # imported here so the rest of the package works without it

    tickers = [yahoo_ticker(s) for s in symbols]
    raw = yf.download(tickers, start=start, end=end.isoformat(), auto_adjust=True, progress=False, threads=False)
    if raw is None or raw.empty:
        return {}
    close = raw["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    result = {}
    for symbol, ticker in zip(symbols, tickers):
        if ticker in close.columns:
            column = close[ticker].dropna()
            if not column.empty:
                column.index = pd.to_datetime(column.index).tz_localize(None).normalize()
                result[symbol] = column.astype(float)
    return result


def _cache_file(cache_dir: Path, symbol: str) -> Path:
    return cache_dir / f"{symbol}.csv"


def _fetched_on(cache_dir: Path, symbol: str) -> dt.date | None:
    path = _cache_file(cache_dir, symbol)
    return dt.date.fromtimestamp(path.stat().st_mtime) if path.exists() else None


def _read_cache(cache_dir: Path, symbol: str) -> pd.Series | None:
    path = _cache_file(cache_dir, symbol)
    if not path.exists():
        return None
    frame = pd.read_csv(path, parse_dates=["date"], index_col="date")
    return frame["close"].astype(float)


def _write_cache(cache_dir: Path, symbol: str, series: pd.Series) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    series.rename("close").rename_axis("date").to_csv(_cache_file(cache_dir, symbol))
