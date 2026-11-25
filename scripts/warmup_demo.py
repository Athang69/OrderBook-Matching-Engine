"""Before a demo: loads every feature once for the stocks you will show, so nothing waits on stage.

    .venv/bin/python scripts/warmup_demo.py                    # default stocks
    .venv/bin/python scripts/warmup_demo.py RELIANCE TCS INFY  # your own list

Run it with the app already started (scripts/run.sh). The AI analysis takes 30 to 70 seconds per stock on
OpenRouter's free models; once a trading day has closed, its analysis is saved in data/analysis/ and comes
back instantly, even after a restart. The free tier allows about 50 analyses a day.
"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
STOCKS = sys.argv[1:] or ["RELIANCE", "TCS", "HDFCBANK", "INFY"]


def get(path: str, timeout: float = 300, body: dict | None = None):
    started = time.time()
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response), time.time() - started, None
    except Exception as err:  # noqa: BLE001 — report every failure the same way
        detail = getattr(err, "read", lambda: b"")().decode(errors="replace")[:200]
        return None, time.time() - started, f"{err} {detail}".strip()


def report(name: str, seconds: float, error: str | None, note: str = "") -> bool:
    print(f"  {'OK  ' if not error else 'FAIL'} {name:<22} {seconds:5.1f}s  {error or note}", flush=True)
    return not error


ok = True
status, _, err = get("/v1/health", 5)
if err:
    sys.exit("The app is not running. Start it with scripts/run.sh first.")
print(f"App up. {status['session']['label']}. Data date {status['data_date']}.\n")

for symbol in STOCKS:
    print(symbol)
    _, s, e = get(f"/v1/market/chart/{symbol}?range=1y&interval=1d")
    ok &= report("chart", s, e)
    _, s, e = get(f"/v1/market/indicators/{symbol}")
    ok &= report("indicators", s, e)
    ex, s, e = get(f"/v1/explain/{symbol}")
    cnn = ((ex or {}).get("chart_cnn") or {}).get("today") or {}
    ok &= report("why it moved + CNN", s, e, f"P(up) {cnn.get('prob_up')}, FinBERT on "
                 f"{sum(len(v) for v in (ex or {}).get('headlines', {}).values())} headlines")
    an, s, e = get(f"/v1/analysis/{symbol}")
    ok &= report("AI analysis", s, e or (None if (an or {}).get("analysis") else "the model's reply could not be read"),
                 f"{(an or {}).get('model')}")

print("\nRecommenders")
_, s, e = get("/v1/recommendations", body={"symbols": STOCKS, "confidences": {}, "budget": 10_000_000})
ok &= report("delivery", s, e)
_, s, e = get("/v1/recommendations/intraday", body={"symbols": STOCKS, "confidences": {}, "budget": 5_000_000})
ok &= report("intraday", s, e)

print("\nAll ready." if ok else "\nSomething failed: see FAIL above.")
sys.exit(0 if ok else 1)
