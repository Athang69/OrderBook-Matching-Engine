"""Loads each stock's reference data from the previous day's free NSE files."""
import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Instrument:
    symbol: str
    prev_close: int  # all prices in paise
    open: int
    high: int
    low: int
    close: int
    volume: int
    trades: int
    tick: int
    band_pct: int
    lower_band: int
    upper_band: int
    data_date: str  # the trading day the figures come from, e.g. "2026-10-09"

    @property
    def avg_trade_qty(self) -> int:
        return max(1, self.volume // max(1, self.trades))

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "prev_close": self.prev_close,
            "tick": self.tick,
            "band_pct": self.band_pct,
            "lower_band": self.lower_band,
            "upper_band": self.upper_band,
            "day": {"open": self.open, "high": self.high, "low": self.low, "close": self.close, "volume": self.volume},
            "data_date": self.data_date,
        }


def tick_size(price: int) -> int:
    """NSE tick size (paise) for a share price (paise), from the price slabs in force since April 2025."""
    rupees = price / 100
    if rupees < 250:
        return 1
    if rupees <= 1000:
        return 5
    if rupees <= 5000:
        return 10
    if rupees <= 10000:
        return 50
    if rupees <= 20000:
        return 100
    return 500


def price_band(prev_close: int, band_pct: int, tick: int) -> tuple[int, int]:
    """Lowest and highest allowed price for the day, rounded inwards to the tick."""
    lower = prev_close * (100 - band_pct) // 100
    upper = prev_close * (100 + band_pct) // 100
    lower += (-lower) % tick  # round up to a tick multiple
    upper -= upper % tick  # round down to a tick multiple
    return lower, upper


def to_paise(text: str) -> int:
    return int(round(float(text.strip()) * 100))


def make_instrument(symbol: str, prev_close: int, open_: int, high: int, low: int, close: int, volume: int,
                    trades: int, band_pct: int, data_date: str) -> Instrument:
    tick = tick_size(prev_close)
    lower, upper = price_band(prev_close, band_pct, tick)
    return Instrument(symbol, prev_close, open_, high, low, close, volume, trades, tick, band_pct, lower, upper, data_date)


def latest_data_files(data_dir: Path) -> tuple[Path, Path]:
    """The newest bhavcopy that also has a price band list for the same day."""
    for bhav in sorted(data_dir.glob("sec_bhavdata_full_*.csv"), key=_file_date, reverse=True):
        bands = data_dir / bhav.name.replace("sec_bhavdata_full_", "sec_list_")
        if bands.exists():
            return bhav, bands
    raise FileNotFoundError(f"No NSE data in {data_dir}. Run: python3 scripts/fetch_nse_data.py")


def _file_date(path: Path) -> dt.date:
    stamp = path.stem.rsplit("_", 1)[-1]  # DDMMYYYY
    return dt.datetime.strptime(stamp, "%d%m%Y").date()


def load_instruments(data_dir: Path, symbols: list[str], default_band_pct: int) -> list[Instrument]:
    bhav_path, bands_path = latest_data_files(data_dir)
    data_date = _file_date(bhav_path).isoformat()

    bands: dict[str, int] = {}
    with bands_path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["Series"].strip() == "EQ":
                band = row["Band"].strip()
                bands[row["Symbol"].strip()] = int(band) if band.isdigit() else default_band_pct

    found: dict[str, Instrument] = {}
    with bhav_path.open(newline="") as fh:
        for row in csv.DictReader(fh, skipinitialspace=True):
            symbol = row["SYMBOL"].strip()
            if symbol in symbols and row["SERIES"].strip() == "EQ":
                found[symbol] = make_instrument(
                    symbol,
                    to_paise(row["PREV_CLOSE"]), to_paise(row["OPEN_PRICE"]), to_paise(row["HIGH_PRICE"]),
                    to_paise(row["LOW_PRICE"]), to_paise(row["CLOSE_PRICE"]),
                    int(row["TTL_TRD_QNTY"]), int(row["NO_OF_TRADES"]),
                    bands.get(symbol, default_band_pct), data_date,
                )
    missing = [s for s in symbols if s not in found]
    if missing:
        raise ValueError(f"Symbols not found in {bhav_path.name}: {', '.join(missing)}")
    return [found[s] for s in symbols]
