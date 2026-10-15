#!/usr/bin/env python3
"""Download the free daily NSE files the app needs into data/nse/.

Two files are fetched for the most recent trading day that NSE has published (today's appear in
the evening, after the close):
  * the full bhavcopy (close, volume and trade count of every stock), whose closing prices are the
    reference for the next session's price bands
  * the price band list (each stock's name and daily price limit)

Only the standard library is used so this runs before the virtualenv exists.
The files belong to NSE: they are kept in data/ (git-ignored) and never committed.
"""
import argparse
import datetime as dt
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "nse"
BASE = "https://nsearchives.nseindia.com"
# NSE's servers ignore requests that do not look like a browser.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Referer": "https://www.nseindia.com/",
}


def download(url: str, dest: pathlib.Path) -> bool:
    """Fetch url into dest. Returns False when the file does not exist (holiday or weekend)."""
    if dest.exists() and dest.stat().st_size > 0:
        return True
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
    except urllib.error.HTTPError as err:
        if err.code in (403, 404):
            return False
        raise
    if len(body) < 1000:  # an error page, not a data file
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return True


def fetch_day(day: dt.date) -> bool:
    stamp = day.strftime("%d%m%Y")
    bhav = download(f"{BASE}/products/content/sec_bhavdata_full_{stamp}.csv", OUT / f"sec_bhavdata_full_{stamp}.csv")
    if not bhav:
        return False
    bands = download(f"{BASE}/content/equities/sec_list_{stamp}.csv", OUT / f"sec_list_{stamp}.csv")
    if not bands:
        print(f"  {day}: bhavcopy found but no price band list; skipping", file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lookback", type=int, default=10, help="how many calendar days to search backwards")
    args = parser.parse_args()

    day = dt.date.today()  # today's files exist only after the close; then it falls back a day
    for _ in range(args.lookback):
        if day.weekday() < 5:
            try:
                if fetch_day(day):
                    print(f"NSE data ready for {day:%d %b %Y} in {OUT}")
                    return 0
            except (urllib.error.URLError, TimeoutError) as err:
                print(f"  {day}: download failed ({err})", file=sys.stderr)
        day -= dt.timedelta(days=1)
    print("No NSE trading-day files could be downloaded. Check the internet connection.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
