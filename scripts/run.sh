#!/usr/bin/env bash
# Builds whatever is missing and starts the app: paper trading on live NSE prices.
# Open http://localhost:8000 once it says "Uvicorn running".
#
#   scripts/run.sh                   start on port 8000
#   PORT=9000 scripts/run.sh         start on another port
#   ORDERBOOK_LIVE=0 scripts/run.sh  start without live prices (no internet needed)
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"
# Private settings such as OPENROUTER_API_KEY live in .env, which git ignores.
if [ -f .env ]; then set -a; . ./.env; set +a; fi

echo "[1/4] Matching engine (C++)"
[ -f engine/build/build.ninja ] || [ -f engine/build/Makefile ] || cmake -S engine -B engine/build -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build engine/build --target ob_engine | tail -1

echo "[2/4] Backend and recommendation system dependencies (Python)"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -c "import fastapi, uvicorn, numpy, pandas, scipy, yfinance, websockets.asyncio.client, yfinance.pricing_pb2" 2>/dev/null ||
  .venv/bin/pip install --quiet -r backend/requirements.txt -r recomendation_system/requirements.txt

echo "[3/4] NSE's daily files: every stock, its price band and tick size"
python3 scripts/fetch_nse_data.py || {
  ls data/nse/sec_bhavdata_full_*.csv >/dev/null 2>&1 || { echo "No NSE data available. Connect to the internet and run again."; exit 1; }
  echo "Could not download; using the data already in data/nse."
}

echo "[4/4] Frontend (React)"
[ -d frontend/node_modules ] || (cd frontend && npm install --no-audit --no-fund)
if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src frontend/index.html -newer frontend/dist/index.html -print -quit)" ]; then
  (cd frontend && npm run build | tail -2)
fi

echo "Starting on http://localhost:${PORT} (live prices from Yahoo Finance; keep it on your own computer)"
exec .venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$PORT"
