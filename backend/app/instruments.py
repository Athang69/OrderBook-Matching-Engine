"""Every NSE stock that can be traded, with its rules for the day, from NSE's free daily files.

The two files are the latest full bhavcopy (prices and volumes for each stock) and the price band
list (each stock's daily limit, and its name). The closing price in the bhavcopy is the reference
for the next session: the price band is worked out from it, and so is the tick size.
"""
import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str  # as NSE lists it, e.g. "RELIANCE INDUSTRIES LIMITED"
    series: str  # EQ, or BE for trade-for-trade stocks
    close: int  # the reference closing price, in paise, like every price here
    volume: int  # shares traded on that day
    trades: int
    tick: int
    band_pct: int
    lower_band: int
    upper_band: int
    data_date: str  # the trading day the closing price comes from, e.g. "2026-10-14"

    @property
    def avg_trade_qty(self) -> int:
        return max(1, self.volume // max(1, self.trades))

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "name": self.name, "series": self.series, "close": self.close,
            "tick": self.tick, "band_pct": self.band_pct, "lower_band": self.lower_band, "upper_band": self.upper_band,
            "volume": self.volume, "avg_trade_qty": self.avg_trade_qty, "data_date": self.data_date,
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


def price_band(reference: int, band_pct: int, tick: int) -> tuple[int, int]:
    """Lowest and highest allowed price for the day, rounded inwards to the tick."""
    lower = reference * (100 - band_pct) // 100
    upper = reference * (100 + band_pct) // 100
    lower += (-lower) % tick  # round up to a tick multiple
    upper -= upper % tick  # round down to a tick multiple
    return max(lower, tick), upper


def to_paise(text: str) -> int:
    return int(round(float(text.strip()) * 100))


def make_instrument(symbol: str, close: int, band_pct: int, data_date: str, name: str = "", series: str = "EQ",
                    volume: int = 0, trades: int = 0) -> Instrument:
    tick = tick_size(close)
    lower, upper = price_band(close, band_pct, tick)
    return Instrument(symbol, name or symbol, series, close, volume, trades, tick, band_pct, lower, upper, data_date)


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


def load_instruments(data_dir: Path, series: tuple[str, ...], default_band_pct: int) -> dict[str, Instrument]:
    """Every stock in the given series, by symbol, from the newest NSE files in `data_dir`."""
    bhav_path, bands_path = latest_data_files(data_dir)
    data_date = _file_date(bhav_path).isoformat()

    listed: dict[str, tuple[int, str]] = {}  # symbol -> (band %, name)
    with bands_path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["Series"].strip() in series:
                band = row["Band"].strip()
                listed[row["Symbol"].strip()] = (int(band) if band.isdigit() else default_band_pct,
                                                 row["Security Name"].strip())

    found: dict[str, Instrument] = {}
    with bhav_path.open(newline="") as fh:
        for row in csv.DictReader(fh, skipinitialspace=True):
            symbol, kind = row["SYMBOL"].strip(), row["SERIES"].strip()
            if kind not in series:
                continue
            try:
                close = to_paise(row["CLOSE_PRICE"])
            except ValueError:
                continue
            if close <= 0:
                continue
            band, name = listed.get(symbol, (default_band_pct, symbol))
            found[symbol] = make_instrument(symbol, close, band, data_date, name=name, series=kind,
                                            volume=int(row["TTL_TRD_QNTY"] or 0), trades=int(row["NO_OF_TRADES"] or 0))
    if not found:
        raise ValueError(f"No {'/'.join(series)} stocks in {bhav_path.name}")
    return found
