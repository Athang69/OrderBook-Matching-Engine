"""Why a stock moved, analysed by Claude.

The evidence for the day is gathered first (explain.py): the stock's move split into the market's part and
its own, similar companies, its sector index, and the headlines about the company, similar companies, its
industry, the Indian market and world markets. To that is added the market scene of the day: the main
Indian indices and India VIX, and the Asian, US, oil, gold and rupee markets. All of it is numbered and
handed to Claude, which writes the analysis and cites the headline numbers it relies on.

The model is always a free one on OpenRouter, using OPENROUTER_API_KEY from the environment or the
git-ignored .env file that scripts/run.sh reads. (`ask_claude` is kept but not called.)
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request

from .explain import Explainer
from .session import IST
from . import indicators as _indicators

MODEL = os.environ.get("ORDERBOOK_CLAUDE_MODEL", "opus")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Free models, tried in this order: if one is busy or rate-limited, OpenRouter moves on to the next.
OPENROUTER_MODELS = os.environ.get(
    "ORDERBOOK_OPENROUTER_MODELS",
    "nvidia/nemotron-3-ultra-550b-a55b:free,google/gemma-4-31b-it:free,nvidia/nemotron-3-super-120b-a12b:free").split(",")
TIMEOUT_SECONDS = 240
CACHE_SECONDS = 1800
PER_SCOPE = 10

INDIA = [("^NSEI", "NIFTY 50"), ("^BSESN", "SENSEX"), ("^NSEBANK", "NIFTY BANK"), ("^CNXIT", "NIFTY IT"),
         ("^CNXAUTO", "NIFTY AUTO"), ("^CNXPHARMA", "NIFTY PHARMA"), ("^CNXFMCG", "NIFTY FMCG"),
         ("^CNXMETAL", "NIFTY METAL"), ("^CNXREALTY", "NIFTY REALTY"), ("^CNXENERGY", "NIFTY ENERGY"),
         ("NIFTY_MIDCAP_100.NS", "NIFTY MIDCAP 100"), ("^CNXSC", "NIFTY SMALLCAP 100"), ("^INDIAVIX", "INDIA VIX")]
# (ticker, name, same day?) Asian markets trade at the same time as India; the US session of the same date
# ends after India closes, so the US session before is the one that could move Indian stocks.
WORLD = [("^TWII", "Taiwan TAIEX", True), ("^KS11", "Korea KOSPI", True), ("^N225", "Japan Nikkei 225", True),
         ("^HSI", "Hong Kong Hang Seng", True), ("000001.SS", "China Shanghai Composite", True),
         ("^GSPC", "US S&P 500", False), ("^IXIC", "US Nasdaq", False), ("^SOX", "US semiconductor index (SOX)", False),
         ("BZ=F", "Brent crude oil", False), ("GC=F", "Gold", False), ("INR=X", "US dollar in rupees", True)]
SCOPE_NAMES = {"company": "about the company", "peers": "about similar companies", "industry": "about its industry",
               "market": "about the Indian market", "global": "about world markets and geopolitics"}

SYSTEM = """You are a senior equity research analyst covering Indian stocks on NSE, writing for a college
faculty member who wants to understand why a stock moved on a given day. You receive a complete evidence
pack: the stock's price move, how much of it the market explains (beta), similar companies and sector
indices, Indian and world markets that day, and numbered news headlines published around that day.

Rules:
- Base every claim on the evidence pack. Cite headline numbers like [3] for each driver.
- Quantify with the numbers given (percent moves, beta, the stock's own move against its typical day).
- Link world events to the stock where the evidence supports it: for example a fall in Taiwan's or Korea's
  chip stocks reaching an Indian electronics maker, crude oil reaching oil marketers, or a war scare hitting
  the whole market. Explain the mechanism in one plain sentence.
- If the headlines do not explain the move, say so, and give the most likely explanation clearly marked as
  an inference from the numbers.
- Write plain, confident Indian English. Use the rupee sign. No investment advice.
- Reply with one JSON object only, no markdown fences, in exactly this shape:
{"headline": "one sentence that answers why it moved",
 "verdict": "Market-wide" | "Industry-wide" | "Company-specific" | "Mixed",
 "drivers": [{"title": "short name of the cause", "explanation": "two or three sentences",
              "impact": "major" | "moderate" | "minor", "direction": "negative" | "positive",
              "evidence": [headline numbers]}],
 "market_context": "two or three sentences on the Indian and world market that day",
 "stock_specific": "one or two sentences on what was specific to this stock",
 "confidence": "high" | "medium" | "low",
 "confidence_reason": "one sentence",
 "watch": ["two or three things to watch next"],
 "technical_view": "one or two sentences on what the candlestick patterns and chart model suggest",
 "sr_view": "one or two sentences: where price closed relative to the pivot levels and what that implies for the next session (entry near support, breakout above resistance, etc.). Omit if pivot data was not provided."}
Give two to four drivers, the most important first.
Do NOT write any reasoning, analysis, or explanation before the JSON. Output the JSON object immediately as the very first character of your response."""


class AnalysisError(RuntimeError):
    pass


def number_headlines(explanation: dict) -> list[dict]:
    """The headlines in a fixed order, numbered from 1, so Claude and the page cite the same numbers."""
    out = []
    for scope in SCOPE_NAMES:
        for h in explanation["headlines"].get(scope, [])[:PER_SCOPE]:
            out.append({**h, "n": len(out) + 1})
    return out


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.2f}%"


def build_prompt(e: dict, name: str, evidence: list[dict], india: list[tuple], world: list[tuple]) -> str:
    day = dt.date.fromisoformat(e["date"])
    previous = dt.date.fromisoformat(e["previous_date"])
    profile = e["profile"]
    own = e["change"] - (e["market_part"] or 0.0)
    lines = [
        f"STOCK: {e['symbol']} ({name}), listed on NSE.",
        f"Sector and industry (Yahoo): {profile.get('sector') or 'n/a'} / {profile.get('industry') or 'n/a'}.",
        f"Business: {(profile.get('summary') or 'n/a')[:600]}",
        "",
        f"DAY TO EXPLAIN: {day:%A %d %B %Y} (previous trading day {previous:%A %d %B}).",
        f"Move: {_pct(e['change'])}, from Rs {e['prev_close'] / 100:,.2f} to Rs {e['price'] / 100:,.2f}.",
        f"Beta against NIFTY 50 over the past year: {e['beta'] if e['beta'] is not None else 'n/a'}. "
        f"Part explained by the market (beta x NIFTY 50 move): {_pct(e['market_part'])}. Stock's own move: {_pct(own)}.",
        f"Typical daily own move: {_pct(e['typical_move'])} (so this own move was "
        f"{abs(own) / e['typical_move']:.1f} times a typical day)." if e["typical_move"] else "Typical daily move: n/a.",
        f"Rule-based first reading: {e['verdict']}.",
        "",
        "SIMILAR COMPANIES THAT DAY: " + (", ".join(f"{p['symbol']} {_pct(p['change'])}" for p in e["peers"]) or "none found"),
        f"SECTOR INDEX: {e['sector']['name']} {_pct(e['sector']['change'])}" if e["sector"] else "SECTOR INDEX: none mapped",
        "",
        "INDIAN MARKET THAT DAY: " + ", ".join(f"{n} {_pct(c)}" for n, c in india),
        "WORLD MARKETS (Asia same day; US, oil and gold their previous session): "
        + ", ".join(f"{n} {_pct(c)} ({d})" for n, c, d in world),
        "",
        "BIGGEST OWN MOVES OF THE STOCK IN THE LAST THREE MONTHS: "
        + ", ".join(f"{b['date']} {_pct(b['change'])}" for b in e["big_days"]),
        "",
        f"HEADLINES published from the previous close ({previous:%d %b} 3:30 pm) to the end of {day:%d %b}, numbered:",
    ]
    for h in evidence:
        when = dt.datetime.fromtimestamp(h["published"], IST).strftime("%d %b %H:%M")
        sent = h.get("sentiment")
        sent_tag = f" [FinBERT: {sent['label']}, score {sent['score']:+.2f}]" if sent else ""
        lines.append(f"[{h['n']}] ({SCOPE_NAMES[h['scope']]}) {when} | {h['title']}{sent_tag} | {h['source']}")
    if not evidence:
        lines.append("(no headlines found)")

    # Candlestick patterns
    patterns = e.get("candle_patterns", {})
    pat_today = patterns.get("today", [])
    pat_prev = patterns.get("previous", [])
    if pat_today or pat_prev:
        lines += ["", "CANDLESTICK PATTERNS (rule-based, from daily OHLC):"]
        for p in pat_today:
            lines.append(f"  {day:%d %b}: {p['name']} ({p['bias']}) — historical up rate {p['up_rate']:.0%}")
        for p in pat_prev:
            lines.append(f"  {previous:%d %b}: {p['name']} ({p['bias']}) — historical up rate {p['up_rate']:.0%}")

    # Chart CNN
    cnn = e.get("chart_cnn", {})
    cnn_today = cnn.get("today")
    cnn_prev = cnn.get("previous")
    if cnn_today or cnn_prev:
        lines += ["", "CHART CNN (20-day candlestick image model, Jiang-Kelly-Xiu 2023 method):"]
        if cnn_today and cnn_today.get("prob_up") is not None:
            lines.append(f"  Chart ending {day:%d %b}: P(up next 5 days) = {cnn_today['prob_up']:.1%}"
                         f"  (test accuracy {cnn_today['accuracy']:.1%}, baseline {cnn_today['baseline']:.1%})")
        if cnn_prev and cnn_prev.get("prob_up") is not None:
            lines.append(f"  Chart ending {previous:%d %b}: P(up next 5 days) = {cnn_prev['prob_up']:.1%}")

    # Classic Pivot Levels (additive block — does not change existing prompt structure)
    ohlc_bars = e.get("ohlc_bars", [])
    ohlc_by_date = {b["date"]: b for b in ohlc_bars}
    prev_bar = ohlc_by_date.get(e["previous_date"])
    if prev_bar and prev_bar.get("high") and prev_bar.get("low") and prev_bar.get("close"):
        from .pivot import compute_pivot as _cp, compute_entry_exit as _ce
        pv = _cp(int(prev_bar["high"]), int(prev_bar["low"]), int(prev_bar["close"]))
        if pv:
            def _r(p): return f"₹{p / 100:,.2f}"
            price_paise = int(e["price"])
            if price_paise > pv["r3"]:      pos = "above R3"
            elif price_paise > pv["r2"]:    pos = "between R2 and R3"
            elif price_paise > pv["r1"]:    pos = "between R1 and R2"
            elif price_paise > pv["pp"]:    pos = "between PP and R1"
            elif price_paise > pv["s1"]:    pos = "between PP and S1"
            elif price_paise > pv["s2"]:    pos = "between S1 and S2"
            elif price_paise > pv["s3"]:    pos = "between S2 and S3"
            else:                           pos = "below S3"
            inst = e.get("_tick")  # injected by Analyst._run when available
            tick = inst if isinstance(inst, int) and inst > 0 else 5
            entry_sug = _ce(pv, price_paise, tick)
            lines += [
                "",
                f"CLASSIC PIVOT LEVELS (from {previous:%d %b} H {_r(prev_bar['high'])} "
                f"/ L {_r(prev_bar['low'])} / C {_r(prev_bar['close'])}):",
                f"  PP {_r(pv['pp'])}  R1 {_r(pv['r1'])}  R2 {_r(pv['r2'])}  R3 {_r(pv['r3'])}",
                f"  S1 {_r(pv['s1'])}  S2 {_r(pv['s2'])}  S3 {_r(pv['s3'])}",
                f"  Close on {day:%d %b} ({_r(price_paise)}) was {pos}.",
                f"  Entry/exit suggestion: {entry_sug['reason']}",
            ]

    # Technical indicators (additive block — does not change existing prompt structure)
    indicators = e.get("indicators")
    if indicators:
        ind_lines = ["", "TECHNICAL INDICATORS (daily, as of previous close):"]
        rsi = indicators.get("rsi") or {}
        if "value" in rsi:
            ind_lines.append(f"  RSI(14): {rsi['value']} — {rsi['verdict']} — {rsi['reason']}")
        macd = indicators.get("macd") or {}
        if "macd" in macd:
            ind_lines.append(f"  MACD(12,26,9): MACD {macd['macd']}, Signal {macd['signal']}, "
                             f"Histogram {macd['histogram']} — {macd['verdict']} — {macd['reason']}")
        fib = indicators.get("fibonacci") or {}
        if "levels" in fib:
            nearest_b = (f"{fib['nearest_ratio_below']*100:.1f}% (₹{fib['nearest_below']:.2f})"
                         if fib.get("nearest_below") is not None else "none")
            nearest_a = (f"{fib['nearest_ratio_above']*100:.1f}% (₹{fib['nearest_above']:.2f})"
                         if fib.get("nearest_above") is not None else "none")
            ind_lines.append(f"  Fibonacci ({fib['trend']}, {_indicators.FIB_LOOKBACK}-day swing "
                             f"₹{fib['swing_low']:.2f}–₹{fib['swing_high']:.2f}): "
                             f"support {nearest_b}, resistance {nearest_a}")
        beta = indicators.get("beta") or {}
        if "value" in beta:
            ind_lines.append(f"  Beta vs {beta['benchmark']} ({beta['window_days']} days): "
                             f"{beta['value']} — {beta['verdict']} — {beta['reason']}")
        if len(ind_lines) > 1:
            lines += ind_lines

    lines += ["", f"Explain why {e['symbol']} moved {_pct(e['change'])} on {day:%d %B %Y}. "
              f"Include a technical_view field about the candlestick patterns and chart model, "
              f"and an sr_view field about the pivot level position and entry/exit implication. "
              f"Reply with the JSON object only."]
    return "\n".join(lines)


def read_answer(text: str) -> dict | None:
    """The JSON object in a model's reply, ignoring any reasoning or code fences around it."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Find the last { ... } block — models sometimes write reasoning before the JSON
    last = None
    for m in re.finditer(r"\{.*\}", text, re.DOTALL):
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, dict):
                last = parsed
        except json.JSONDecodeError:
            pass
    return last


def ask_model(prompt: str) -> dict:
    """OpenRouter's free models only; Claude is never used, so no paid credits are spent."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise AnalysisError("No OpenRouter key: put OPENROUTER_API_KEY=... in the .env file and restart scripts/run.sh.")
    return ask_openrouter(prompt, key)


def ask_openrouter(prompt: str, key: str) -> dict:
    started = time.time()
    body = {"models": OPENROUTER_MODELS, "temperature": 0.3, "max_tokens": 6000,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
    request = urllib.request.Request(OPENROUTER_URL, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000", "X-Title": "OrderBook"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.load(response)
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")[:300]
        raise AnalysisError(f"OpenRouter refused the request ({err.code}): {detail}") from None
    except (urllib.error.URLError, TimeoutError) as err:
        raise AnalysisError(f"Could not reach OpenRouter ({err}).") from None
    if data.get("error"):
        raise AnalysisError(f"OpenRouter: {data['error'].get('message', data['error'])}")
    text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    answer = read_answer(text)
    return {"answer": answer, "text": None if answer else text, "model": data.get("model") or OPENROUTER_MODELS[0],
            "seconds": round(time.time() - started, 1)}


def ask_claude(prompt: str, model: str = MODEL) -> dict:
    """Runs `claude -p` with the evidence on stdin and returns the parsed JSON answer with timing."""
    binary = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    if not os.path.exists(binary):
        raise AnalysisError("The Claude command-line tool is not installed on this computer.")
    started = time.time()
    with tempfile.TemporaryDirectory() as empty:  # an empty folder: Claude has no files to look at
        done = subprocess.run(
            [binary, "-p", "--model", model, "--output-format", "json", "--no-session-persistence",
             "--strict-mcp-config", "--system-prompt", SYSTEM, "--disallowedTools", "Bash", "Edit", "Write", "Read",
             "Glob", "Grep", "WebFetch", "WebSearch", "Task", "NotebookEdit"],
            input=prompt, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, cwd=empty)
    try:
        outer = json.loads(done.stdout)
    except json.JSONDecodeError:
        raise AnalysisError(f"Claude did not answer ({(done.stderr or done.stdout)[:200].strip()}).") from None
    if outer.get("is_error"):
        raise AnalysisError(f"Claude reported an error: {str(outer.get('result'))[:200]}")
    text = outer.get("result") or ""
    answer = read_answer(text)
    models = list((outer.get("modelUsage") or {}).keys())
    return {"answer": answer, "text": None if answer else text, "model": models[0] if models else model,
            "seconds": round(time.time() - started, 1)}


class Analyst:
    def __init__(self, explainer: Explainer, names, get_indicators=None):
        self._explainer = explainer
        self._names = names  # symbol -> company name
        self._get_indicators = get_indicators  # optional callable: symbol -> indicator dict
        self._lock = threading.Lock()
        self._cache: dict[tuple, tuple[float, dict]] = {}
        self._running: dict[tuple, threading.Event] = {}

    def analyse(self, symbol: str, day: dt.date | None) -> dict:
        explanation = self._explainer.explain(symbol, day)
        key = (symbol, explanation["date"])
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < CACHE_SECONDS:
                return hit[1]
            waiting = self._running.get(key)
            if waiting is None:
                self._running[key] = threading.Event()
        if waiting is not None:  # the same analysis is already being written; wait for it
            waiting.wait(TIMEOUT_SECONDS + 30)
            with self._lock:
                hit = self._cache.get(key)
            if hit:
                return hit[1]
            raise AnalysisError("The analysis is taking longer than expected. Try again.")
        try:
            result = self._run(symbol, explanation)
            with self._lock:
                self._cache[key] = (time.time(), result)
            return result
        finally:
            with self._lock:
                self._running.pop(key).set()

    def _run(self, symbol: str, explanation: dict) -> dict:
        day = dt.date.fromisoformat(explanation["date"])
        pool = self._explainer.pool()
        india_jobs = [(name, pool.submit(self._explainer.day_change, t, day)) for t, name in INDIA]
        world_jobs = [(name, pool.submit(self._explainer.day_change, t, day, not same_day)) for t, name, same_day in WORLD]
        india = [(n, j.result()[1]) for n, j in india_jobs if j.result()]
        world = [(n, j.result()[1], j.result()[0]) for n, j in world_jobs if j.result()]
        evidence = number_headlines(explanation)
        # Inject indicators into the explanation so build_prompt can include them
        if self._get_indicators is not None:
            try:
                explanation = {**explanation, "indicators": self._get_indicators(symbol)}
            except Exception:
                pass  # indicators are additive — never block the analysis
        prompt = build_prompt(explanation, self._names(symbol), evidence, india, world)
        reply = ask_model(prompt)

        # Deterministic S/R levels and entry/exit — computed from explanation data, not from LLM output
        sr_levels = None
        sr_entry = None
        ohlc_bars = explanation.get("ohlc_bars", [])
        prev_bar = {b["date"]: b for b in ohlc_bars}.get(explanation["previous_date"])
        if prev_bar and prev_bar.get("high") and prev_bar.get("low") and prev_bar.get("close"):
            from .pivot import compute_pivot as _cp2, compute_entry_exit as _ce2
            pv = _cp2(int(prev_bar["high"]), int(prev_bar["low"]), int(prev_bar["close"]))
            if pv:
                trading_day = explanation["date"]
                sr_levels = {"symbol": symbol, "trading_day": trading_day, **pv, "error": None}
                tick = explanation.get("_tick")
                tick = tick if isinstance(tick, int) and tick > 0 else 5
                sr_entry = _ce2(pv, int(explanation["price"]), tick)

        return {"symbol": symbol, "date": explanation["date"], "explanation": explanation, "evidence": evidence,
                "india": [{"name": n, "change": round(c, 5)} for n, c in india],
                "world": [{"name": n, "change": round(c, 5), "date": d} for n, c, d in world],
                "analysis": reply["answer"], "raw": reply["text"], "model": reply["model"], "seconds": reply["seconds"],
                "sr_levels": sr_levels, "sr_entry": sr_entry}
