"""Why did a stock move? An explanation built only from evidence: the market, similar companies and
the news of that day. No language model writes it, so every sentence can be traced to a number or a
headline, and nothing is claimed that the evidence does not show.

1. The move is split in two with the market model used in event studies (MacKinlay, 1997): the part
   the whole market explains, which is the stock's beta times the NIFTY 50's move that day, and the
   stock's own part. The own part is compared with a typical day (the spread of the stock's own parts
   over the past year), which says whether the move was ordinary or unusual.
2. Similar companies (Yahoo's list) and the matching NIFTY sector index show whether the move was
   shared across the industry.
3. Headlines from that day are collected at four levels: the company, the similar companies, its
   industry in India and abroad, and the whole market. Each is tagged with its likely cause by keyword
   lists (results, broker ratings, geopolitical tension, interest rates, oil, fund flows and so on) and
   given a tone from positive and negative words.
4. Headlines that point the same way as the move, and are closest to the company, are offered as the
   likely reasons.
"""
import datetime as dt
import re
import statistics
import threading
import time
import urllib.parse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from .news import FEED_URL, fetch_feed, mentions_any, parse_items
from .session import IST
from .yahoo import from_yahoo, to_yahoo
from . import finbert as _finbert
from .candles import detect_patterns as _detect_patterns
from . import chart_cnn as _chart_cnn

MARKET_TICKER, MARKET_NAME = "^NSEI", "NIFTY 50"
LOOKBACK_DAYS = 250  # trading days behind beta and the typical move
MIN_DAYS = 30  # fewer than this and the market split is not attempted
BIG_DAYS = 6  # biggest recent moves offered as shortcuts
BIG_DAYS_WINDOW = 63  # about three months of trading days
MAX_PEERS = 5
CLOSE = dt.time(15, 30)
RECENT_TTL, PAST_TTL, PROFILE_TTL = 120, 6 * 3600, 24 * 3600  # seconds

# Yahoo's sector or industry (a pattern) -> the NIFTY sector index that tracks it (or None) and words for
# the industry's news. The first match wins, so the specific industries come before broad sectors.
THEMES: list[tuple[str, tuple[str, str] | None, list[str]]] = [
    (r"Banks", ("^NSEBANK", "NIFTY BANK"), ["bank stocks", "banking stocks", "PSU banks"]),
    (r"Capital Markets|Financial Data|Asset Management", ("NIFTY_CAPITAL_MKT.NS", "NIFTY CAPITAL MARKETS"),
     ["capital market stocks", "broking stocks", "AMC stocks"]),
    (r"Insurance", ("NIFTY_FIN_SERVICE.NS", "NIFTY FINANCIAL SERVICES"), ["insurance stocks", "insurers"]),
    (r"Credit Services|Mortgage|Financial", ("NIFTY_FIN_SERVICE.NS", "NIFTY FINANCIAL SERVICES"),
     ["NBFC stocks", "financial stocks"]),
    (r"Information Technology|Software", ("^CNXIT", "NIFTY IT"), ["IT stocks", "Nasdaq", "tech stocks"]),
    (r"Semiconductor|Electronic|Computer Hardware|Communication Equipment|Scientific & Technical", None,
     ["electronics stocks", "EMS stocks", "semiconductor", "chip stocks", "electronics manufacturing"]),
    (r"Auto", ("^CNXAUTO", "NIFTY AUTO"), ["auto stocks", "auto sales", "automobile"]),
    (r"Drug|Pharmaceutical|Biotechnology", ("^CNXPHARMA", "NIFTY PHARMA"), ["pharma stocks", "USFDA"]),
    (r"Healthcare|Medical|Diagnostics", ("NIFTY_HEALTHCARE.NS", "NIFTY HEALTHCARE"),
     ["hospital stocks", "healthcare stocks"]),
    (r"Steel|Aluminum|Copper|Metals|Mining|Gold|Silver", ("^CNXMETAL", "NIFTY METAL"),
     ["metal stocks", "steel prices", "LME"]),
    (r"Chemicals|Agricultural Inputs", ("NIFTY_CHEMICALS.NS", "NIFTY CHEMICALS"), ["chemical stocks", "agrochemical"]),
    (r"Oil & Gas|Oil and Gas", ("NIFTY_OIL_AND_GAS.NS", "NIFTY OIL & GAS"), ["crude oil", "oil stocks", "OMC stocks"]),
    (r"Utilities|Energy|Renewable|Solar|Coal", ("^CNXENERGY", "NIFTY ENERGY"),
     ["power stocks", "energy stocks", "renewable energy stocks"]),
    (r"Real Estate", ("^CNXREALTY", "NIFTY REALTY"), ["realty stocks", "real estate stocks"]),
    (r"Telecom", ("NIFTY_IND_DIGITAL.NS", "NIFTY INDIA DIGITAL"), ["telecom stocks", "tariff hike"]),
    (r"Entertainment|Broadcasting|Publishing|Advertising", ("^CNXMEDIA", "NIFTY MEDIA"), ["media stocks"]),
    (r"Aerospace|Defense", ("NIFTY_IND_DEFENCE.NS", "NIFTY INDIA DEFENCE"), ["defence stocks", "defense stocks"]),
    (r"Engineering & Construction|Infrastructure|Building Materials|Cement", ("^CNXINFRA", "NIFTY INFRASTRUCTURE"),
     ["infra stocks", "cement stocks", "construction stocks"]),
    (r"Consumer Defensive|Packaged Foods|Household|Tobacco|Beverages|Personal Products|Confectioners",
     ("^CNXFMCG", "NIFTY FMCG"), ["FMCG stocks"]),
    (r"Furnishings|Appliances|Consumer Electronics|Luxury|Apparel|Footwear|Leisure|Restaurants|Lodging|Retail",
     ("^CNXCONSUM", "NIFTY CONSUMPTION"), ["consumer stocks", "retail stocks"]),
    (r"Industrials|Machinery|Electrical Equipment|Tools", ("NIFTY_INDIA_MFG.NS", "NIFTY INDIA MANUFACTURING"),
     ["capital goods stocks", "industrial stocks"]),
]

# Likely causes, found by keywords in a headline. A headline can have several; the first is its main one.
REASONS: list[tuple[str, str]] = [
    ("Profit booking", r"\bprofit[- ](booking|taking)\b"),
    ("Quarterly results", r"\bq[1-4]\b|q[1-4]fy|\bquarter(ly)?\b|\bresults?\b|\bearnings\b|\bprofit\b(?![- ](booking|taking))|\bnet loss\b|\brevenue\b|\bebitda\b|\bmargins?\b|\bpat\b"),
    ("ESG or credit rating", r"\besg\b|\bcredit rating\b|\bcrisil\b|\bicra\b|\bcare ratings\b|\bind-?ra\b"),
    ("Broker rating or target price", r"\bdowngrade[sd]?\b|\bupgrade[sd]?\b|\btarget( price)?\b|\bprice target\b|\brating\b|\binitiates? coverage\b|\bbuy call\b|\bupside\b|\bdownside\b|\boverweight\b|\bunderweight\b"),
    ("Orders and contracts", r"\border (win|worth|from|book)\b|\bbags?\b|\bwins?\b.*\border\b|\bsecures?\b|\bcontract\b|\btender\b|\bl1 bidder\b"),
    ("Deals and stake changes", r"\bacqui(re|res|red|sition)\b|\bmerger\b|\bdemerger\b|\bstake\b|\bblock deal\b|\bbulk deal\b|\bofs\b|\boffer for sale\b|\bpromoters?\b|\bpledge\b|\bqip\b|\bfund ?rais\w*|\bipo\b"),
    ("Dividend, bonus, split or buyback", r"\bdividend\b|\bbonus\b|\bstock split\b|\bsplit\b|\bbuyback\b|\brecord date\b"),
    ("Regulator or legal action", r"\birdai\b|\brbi (curbs?|norms|rules|action|proposal|bans?|penalty)\b|\bregulat(or|ory)\b|\bsebi\b|\bpenalty\b|\bprobe\b|\braids?\b|\bfraud\b|\blawsuit\b|\bcourt\b|\bbanned?\b|\bshow[- ]cause\b|\btax demand\b|\bgst (demand|notice)\b|\binsolvency\b"),
    ("Management change", r"\bceo\b|\bmanaging director\b|\bcfo\b|\bchairman\b|\bresign\w*|\bsteps down\b|\bappoint\w*"),
    ("Product, plant or approval", r"\blaunch\w*|\busfda\b|\bfda\b|\bapprov\w*|\bpatent\b|\bplant\b|\bfacility\b|\bcapacity\b|\bexpansion\b"),
    ("Geopolitical tension", r"\bwars?\b|\bconflict\b|\btensions?\b|\bmissiles?\b|\bmilitary\b|\battacks?\b|\bair ?strikes?\b|\bsanctions?\b|\btaiwan\b|\bisrael\b|\biran\b|\bgaza\b|\bukraine\b|\brussia\b|\bmiddle east\b|\bgeopolitic\w*|\binvasion\b"),
    ("Interest rates and inflation", r"\brepo\b|\brate (cut|hike)s?\b|\binterest rates?\b|\binflation\b|\bcpi\b|\bwpi\b|\bfomc\b|\bfed (rate|meeting|chair|policy)\b|\bbond yields?\b|\bmonetary policy\b|\brbi policy\b"),
    ("Oil, rupee and commodities", r"\bcrude\b|\boil prices?\b|\bbrent\b|\brupee\b|\bdollar\b|\bgold prices?\b|\bcommodit\w*|\bmetal prices?\b|\blme\b"),
    ("Trade policy and tariffs", r"\btariffs?\b|\btrade (war|deal|talks)\b|\bimport dut\w*|\bexport (curbs?|ban)\b|\bpli\b|\banti-dumping\b"),
    ("Foreign and fund flows", r"\bfiis?\b|\bfpis?\b|\bforeign (investors?|funds?|selling|buying|outflows?|inflows?)\b|\bdiis?\b|\boutflows?\b|\binflows?\b|\bmsci\b|\bftse\b|\brebalanc\w*"),
    ("Global markets", r"\bwall street\b|\bnasdaq\b|\bdow\b|\bs&p 500\b|\basian markets?\b|\bglobal (markets?|cues|sell-?off|rout)\b|\bus markets?\b|\bchina\b|\bjapan\b|\bnikkei\b|\bkospi\b|\bhang seng\b|\bkorea\b|\bsamsung\b|\bsk hynix\b|\btsmc\b|\bnvidia\b"),
    ("Economy and policy", r"\bgdp\b|\bbudget\b|\bgovernment\b|\bpolicy\b|\breforms?\b|\bmonsoon\b|\belections?\b|\bgst\b"),
    ("Price move", r"52-week (high|low)|\b(upper|lower) circuit\b|\bintraday (high|low)\b|\bhits? (record|fresh|new) (high|low)\b|\bvolumes?\b"),
]
_REASONS = [(label, re.compile(pattern, re.IGNORECASE)) for label, pattern in REASONS]

# Tone: positive and negative words; the strongest words count twice.
_POSITIVE = re.compile(r"\b(rise[sn]?|rose|gain(s|ed)?|jump(s|ed)?|up|higher|beats?|strong(er)?|upgrade[sd]?|wins?|bags?|"
                       r"secure[sd]?|approv\w*|boost(s|ed)?|rebound(s|ed)?|recover\w*|outperform\w*|bullish|record high|"
                       r"inflows?|upside|buy|growth|grows?|expan\w*|in (the )?green)\b", re.IGNORECASE)
_NEGATIVE = re.compile(r"\b(fall(s|ing)?|fell|drop(s|ped)?|declin\w*|slips?|slipped|slide|slid|sinks?|sank|sheds?|down|"
                       r"lower|loss(es)?|weak(er|ness)?|miss(es|ed)?|cuts?|downgrade[sd]?|concerns?|fears?|worr\w*|"
                       r"sell-?off|selling|pressure|slowdown|probe|penalty|fraud|default|wars?|tensions?|outflows?|"
                       r"bearish|crisis|halt(s|ed)?|bann?ed|lawsuit|resign\w*|downside|reduce|sell|in (the )?red)\b", re.IGNORECASE)
_STRONG = re.compile(r"\b(crash(es|ed)?|plunge[sd]?|slump(s|ed)?|tumble[sd]?|tank(s|ed)?|nosedive[sd]?|rout|"
                     r"surge[sd]?|soar(s|ed)?|skyrocket\w*|zoom(s|ed)?|rall(y|ies|ied))\b", re.IGNORECASE)
_STRONG_UP = re.compile(r"\b(surge[sd]?|soar(s|ed)?|skyrocket\w*|zoom(s|ed)?|rall(y|ies|ied))\b", re.IGNORECASE)

MARKET_WORDS = ["Sensex", "Nifty", "Dalal Street", "stock market", "share market", "markets"]
SCOPE_WEIGHT = {"company": 3.0, "peers": 2.0, "industry": 1.5, "market": 1.0, "global": 0.8}
SCOPE_TEXT = {"company": "news about {symbol}", "peers": "news about similar companies",
              "industry": "news about its industry", "market": "news about the whole market",
              "global": "news about world markets"}
GLOBAL_WORDS = ["Asian markets", "Asia", "Wall Street", "global", "geopolitical", "war", "crude", "Taiwan", "China",
                "Korea", "Japan", "Nasdaq", "Fed", "tariff", "tariffs", "Iran", "Israel", "Russia", "Ukraine", "oil"]


class ExplainError(ValueError):
    """A problem worded for the user, such as a date the stock did not trade."""


@dataclass
class Headline:
    title: str
    source: str
    url: str
    published: int
    scope: str  # company | peers | industry | market
    tone: float  # -1 negative to +1 positive
    reasons: list[str] = field(default_factory=list)


def classify(sector: str | None, industry: str | None) -> dict:
    """The NIFTY sector index and the industry news words for a company's Yahoo sector and industry."""
    text = f"{industry or ''} | {sector or ''}"
    for pattern, index, words in THEMES:
        if re.search(pattern, text, re.IGNORECASE):
            return {"index": index, "words": words}
    return {"index": None, "words": []}


def tone(title: str) -> float:
    """From -1 (only negative words) to +1 (only positive words); 0 when neither or balanced."""
    strong = _STRONG.findall(title)
    strong_up = sum(1 for _ in _STRONG_UP.finditer(title))
    up = len(_POSITIVE.findall(title)) + 2 * strong_up
    down = len(_NEGATIVE.findall(title)) + 2 * (len(strong) - strong_up)
    return 0.0 if up + down == 0 else (up - down) / (up + down)


def reasons_in(title: str) -> list[str]:
    return [label for label, pattern in _REASONS if pattern.search(title)]


def is_english(title: str) -> bool:
    letters = [c for c in title if c.isalpha()]
    return bool(letters) and sum(c.isascii() for c in letters) / len(letters) > 0.9


def closes_by_day(bars: list[list[int]]) -> dict[dt.date, int]:
    """Daily bars [time, open, high, low, close, volume] as {Indian date: close}."""
    return {dt.datetime.fromtimestamp(b[0], IST).date(): b[4] for b in bars if b[4]}


def ohlcv_by_day(bars: list[list[int]]) -> dict[dt.date, tuple[int, int, int, int, int]]:
    """Daily bars as {Indian date: (open, high, low, close, volume)}."""
    return {dt.datetime.fromtimestamp(b[0], IST).date(): (b[1], b[2], b[3], b[4], b[5])
            for b in bars if b[4]}


def daily_returns(closes: dict[dt.date, int]) -> dict[dt.date, float]:
    """Each day's change from the previous trading day, as a fraction."""
    days = sorted(closes)
    return {b: closes[b] / closes[a] - 1 for a, b in zip(days, days[1:])}


def market_model(stock: dict[dt.date, float], market: dict[dt.date, float], before: dt.date,
                 lookback: int = LOOKBACK_DAYS) -> dict | None:
    """Beta and the typical daily move (whole and own part) from the `lookback` days before `before`."""
    days = sorted(d for d in stock if d in market and d < before)[-lookback:]
    if len(days) < MIN_DAYS:
        return None
    s = [stock[d] for d in days]
    m = [market[d] for d in days]
    ms, mm = statistics.fmean(s), statistics.fmean(m)
    variance = sum((x - mm) ** 2 for x in m)
    beta = sum((x - mm) * (y - ms) for x, y in zip(m, s)) / variance if variance else 1.0
    beta = min(max(beta, 0.0), 3.0)  # keep it sensible for the explanation
    own = [y - beta * x for x, y in zip(m, s)]
    return {"beta": beta, "typical": statistics.stdev(s), "typical_own": statistics.stdev(own), "days": len(days)}


# Causes that belong to one company: news of this kind about a similar company does not explain this one.
OWN_COMPANY_CAUSES = {"Management change", "Dividend, bonus, split or buyback", "Deals and stake changes",
                      "Regulator or legal action", "Product, plant or approval", "ESG or credit rating"}
MARKET_EXCLUDED = OWN_COMPANY_CAUSES - {"Regulator or legal action"}  # a regulator can move a whole market
# Tags that describe the trading more than they explain it, and so count for less.
WEAK_CAUSES = {"Price move": 0.4, "Profit booking": 0.6, "ESG or credit rating": 0.5}
# Yahoo files similar businesses under neighbouring sectors (an electronics maker can be "Technology" or
# "Industrials"), so a similar company counts if its sector is in the same group.
SECTOR_GROUPS = [{"Technology", "Industrials", "Communication Services"}, {"Financial Services", "Real Estate"},
                 {"Consumer Cyclical", "Consumer Defensive"}, {"Energy", "Utilities", "Basic Materials"},
                 {"Healthcare"}]


def related_sectors(a: str | None, b: str | None) -> bool:
    return bool(a and b) and (a == b or any(a in g and b in g for g in SECTOR_GROUPS))


def likely_reasons(headlines: list[Headline], direction: int, market_led: bool, industry_led: bool | None,
                   own_unusual: bool | None = None, limit: int = 4) -> list[dict]:
    """The causes the headlines point to, best first, with up to two headlines each.

    A headline counts for more when it is about the company itself, when its tone matches the move, and
    when it names a cause rather than only describing the price. News about similar companies and the
    industry counts fully only when they moved the same way (`industry_led`; None when unknown), news about
    the whole market only when the market moved the same way (`market_led`), and news about the company
    itself less when its own move was ordinary (`own_unusual` False)."""
    scored = []
    for h in headlines:
        # A similar company's or the market's news counts only for causes that can spread beyond one company.
        excluded = (OWN_COMPANY_CAUSES if h.scope == "peers" else MARKET_EXCLUDED if h.scope in ("market", "global")
                    else set())
        tags = [t for t in h.reasons if t not in excluded]
        if h.scope == "peers" and h.reasons and not tags:
            continue
        main = tags[0] if tags else None
        weight = SCOPE_WEIGHT[h.scope]
        if h.scope == "company" and own_unusual is False:
            weight *= 0.6
        elif h.scope == "market":
            weight *= 2.5 if market_led else 0.6
        elif h.scope == "peers":  # if the similar companies did not move with the stock, their news hardly explains it
            weight *= 1.0 if industry_led else 0.8 if industry_led is None else 0.25
        elif h.scope == "industry":  # industry news abroad can still reach one company even if its peers held up
            weight *= 1.0 if industry_led else 0.8 if industry_led is None else 0.5
        agreement = h.tone * direction
        fit = 1.0 if direction == 0 or agreement > 0 else 0.5 if h.tone == 0 else 0.15
        cause = WEAK_CAUSES.get(main, 1.0) if main else 0.6
        scored.append((weight * fit * cause, main, h))
    groups: dict[tuple[str, str], list[tuple[float, Headline]]] = {}
    for score, main, h in sorted(scored, key=lambda t: (-t[0], -t[2].published)):
        groups.setdefault((main or "Other news", h.scope), []).append((score, h))
    out = []
    for (label, scope), items in sorted(groups.items(), key=lambda kv: -kv[1][0][0]):
        best = items[0][0]
        if best < 0.25 or (label == "Other news" and out):
            continue
        shown = [h for _, h in items[:2]]
        total = sum(h.tone for h in shown)
        out.append({"label": label, "scope": scope, "score": round(best, 2),
                    "tone": "negative" if total < 0 else "positive" if total > 0 else "mixed",
                    "headlines": [asdict(h) for h in shown]})
        if len(out) == limit:
            break
    return out


def industry_move(peers: list[tuple[str, float | None]], sector: tuple[str, float] | None) -> float | None:
    """How the industry moved: the middle of the similar companies' moves, or else the sector index."""
    moves = [c for _, c in peers if c is not None]
    if len(moves) >= 2:
        return statistics.median(moves)
    return sector[1] if sector else None


def same_way(part: float | None, whole: float, share: float = 0.4) -> bool | None:
    """Whether `part` moved the same way as `whole` and by at least `share` of it; None if unknown."""
    if part is None:
        return None
    return part * whole > 0 and abs(part) >= share * abs(whole)


def _pct(x: float) -> str:
    return f"{abs(x) * 100:.2f}%"


def _signed(x: float) -> str:
    return ("+" if x > 0 else "−" if x < 0 else "") + _pct(x)


def _verb(x: float, past: bool = True) -> str:
    if abs(x) < 0.001:
        return "was almost unchanged"
    return ("rose" if x > 0 else "fell") if past else ("rise" if x > 0 else "fall")


def summarise(f: dict) -> tuple[str, list[str]]:
    """A verdict and plain sentences from the facts of a move. `f` holds: symbol, when ("today" or "on
    Thu 15 Oct"), change, price, prev_close, market (change or None), model (from market_model or None),
    sector ((name, change) or None), peers [(symbol, change)], reasons (from likely_reasons)."""
    sym, r = f["symbol"], f["change"]
    sentences = [f"{sym} {_verb(r)} {_pct(r) + ' ' if abs(r) >= 0.001 else ''}{f['when']} "
                 f"(₹{f['prev_close'] / 100:,.2f} to ₹{f['price'] / 100:,.2f})."]
    model, rm = f["model"], f["market"]
    market_part = model["beta"] * rm if model and rm is not None else 0.0
    if rm is not None:
        if abs(rm) < 0.0025:
            sentences.append(f"The market was nearly flat ({MARKET_NAME} {_signed(rm)}), so it does not explain the move.")
        elif rm * r > 0:
            sentences.append(f"The whole market {_verb(rm)} as well ({MARKET_NAME} {_signed(rm)})." + (
                f" {sym} usually moves about {model['beta']:.1f} times as much as the market, so about "
                f"{_signed(market_part)} of its move came from the market." if model else ""))
        else:
            sentences.append(f"The market went the other way ({MARKET_NAME} {_signed(rm)}), so the market did not "
                             f"cause this {'fall' if r < 0 else 'rise'}.")
    if f["sector"]:
        name, change = f["sector"]
        sentences.append(f"Its sector index, {name}, {_verb(change)} {_pct(change)}.")
    peers = [(s, c) for s, c in f["peers"] if c is not None]
    if len(peers) >= 2:
        listed = ", ".join(f"{s} {_signed(c)}" for s, c in sorted(peers, key=lambda p: p[1]))
        sentences.append(f"Similar companies that day: {listed}.")
    industry = industry_move(peers, f["sector"])
    if industry is not None and abs(r) >= 0.001:
        measure = "the middle of similar companies" if len(peers) >= 2 else "its sector index"
        if same_way(industry, r):
            sentences.append(f"Its industry moved the same way ({measure} {_signed(industry)}), so the move was "
                             "largely shared across the industry.")
        elif industry * r > 0 and abs(industry) >= 0.25 * abs(r):
            sentences.append(f"Its industry moved the same way but less ({measure} {_signed(industry)}), so part of "
                             f"the move was industry-wide and part was {sym}'s own.")
        elif industry * r > 0:
            sentences.append(f"Its industry {_verb(industry)} only slightly ({measure} {_signed(industry)}), so the "
                             f"move was mostly {sym}'s own.")
        else:
            sentences.append(f"Its industry went the other way ({measure} {_signed(industry)}), so the move was "
                             f"{sym}'s own.")
    own = r - market_part
    z = abs(own) / model["typical_own"] if model and model["typical_own"] else None
    if z is not None and abs(r) >= 0.001:
        lead = f"Leaving out the market, {sym}'s own move was {_signed(own)}"
        if z >= 2:
            sentences.append(f"{lead}, {z:.1f} times its typical day: an unusual move, usually tied to news.")
        elif z < 1:
            sentences.append(f"{lead}, within its typical daily range (about {_pct(model['typical_own'])}), "
                             "so it may not have a single cause.")
        else:
            sentences.append(f"{lead}, {z:.1f} times its typical day.")
    causes = [g for g in f["reasons"] if g["label"] not in WEAK_CAUSES and g["label"] != "Other news"]
    if causes:
        parts = [f"{_lower(g['label'])} ({SCOPE_TEXT[g['scope']].format(symbol=sym)})" for g in causes[:3]]
        sentences.append("The news that day points mainly to " + _join(parts) + ".")
    if abs(r) >= 0.001 and z is not None and z >= 1.5 and not any(g["scope"] == "company" for g in causes):
        sentences.append(f"No news about {sym} itself that day explains its own move"
                         + ("; the causes above are possible outside ones." if causes else "."))
    if not causes:
        sentences.append(f"No news that day about {sym}, similar companies, its industry or the market explains it; "
                         "moves like this can come from ordinary buying and selling.")

    if rm is not None and model and market_part * r > 0 and abs(market_part) >= 0.6 * abs(r):
        verdict = "Market-wide move"
    elif same_way(industry, r):
        verdict = "Industry-wide move"
    elif z is not None and z >= 2:
        verdict = "Company-specific move"
    else:
        verdict = "Ordinary day"
    return verdict, sentences


def _lower(label: str) -> str:
    """"Quarterly results" -> "quarterly results", but "ESG or credit rating" keeps its capitals."""
    return label if label[:2].isupper() else label[0].lower() + label[1:]


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


class Explainer:
    """Gathers the evidence for one stock and one day, with caches so a repeat costs nothing.

    `terms(symbol)` gives (name to search the news for, words a headline must contain); `fetch(url)`
    downloads a news feed. The Yahoo calls and news searches block, so call `explain` from a worker thread.
    """

    def __init__(self, yahoo, symbols: Callable[[], set[str]], terms: Callable[[str], tuple[str, list[str]]],
                 fetch: Callable[[str], bytes] | None = None, clock: Callable[[], float] = time.time):
        self._yahoo = yahoo
        self._symbols = symbols
        self._terms = terms
        self._fetch = fetch
        self._clock = clock
        self._lock = threading.Lock()
        self._cache: dict[tuple, tuple[float, object]] = {}
        self._pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="explain")

    def explain(self, symbol: str, day: dt.date | None = None) -> dict:
        today = dt.datetime.fromtimestamp(self._clock(), IST).date()
        recent = day is None or (today - day).days <= 1
        key = ("result", symbol, day)
        cached = self._cached(key, RECENT_TTL if recent else PAST_TTL)
        if cached is not None:
            return cached
        started = time.perf_counter()

        profile = self._profile(symbol)
        theme = classify(profile["sector"], profile["industry"])
        index = theme["index"]
        tickers = [to_yahoo(symbol), MARKET_TICKER] + ([index[0]] if index else []) + [to_yahoo(p) for p in profile["peers"]]
        bars = dict(zip(tickers, self._pool.map(lambda t: self._bars(t, recent), tickers)))
        closes = bars[to_yahoo(symbol)]
        if len(closes) < 2:
            raise ExplainError(f"There is not enough price history for {symbol} yet.")
        latest = max(closes)
        day = day or latest
        if day not in closes:
            raise ExplainError(f"{symbol} did not trade on {day:%a %d %b %Y}. Choose a trading day.")
        previous = max((d for d in closes if d < day), default=None)
        if previous is None:
            raise ExplainError(f"{day:%d %b %Y} is {symbol}'s first day in the price history, so there is no move to explain.")

        stock_r = daily_returns(closes)
        market_r = daily_returns(bars[MARKET_TICKER])
        model = market_model(stock_r, market_r, day)
        change = stock_r[day]
        sector = None
        if index and day in daily_returns(bars[index[0]]):
            sector = (index[1], daily_returns(bars[index[0]])[day])
        peers = [(p, daily_returns(bars[to_yahoo(p)]).get(day)) for p in profile["peers"]]

        window = self._window(previous, day, today)
        headlines = self._headlines(symbol, profile["peers"], theme["words"], window)
        direction = 1 if change > 0.001 else -1 if change < -0.001 else 0
        market = market_r.get(day)
        market_led = bool(model and market is not None and same_way(model["beta"] * market, change, 0.6))
        industry_led = same_way(industry_move(peers, sector), change)
        own = change - (model["beta"] * market if model and market is not None else 0.0)
        own_unusual = abs(own) >= 1.5 * model["typical_own"] if model and model["typical_own"] else None
        reasons = likely_reasons(headlines, direction, market_led, industry_led, own_unusual)
        when = "today" if day == today else f"on {day:%a %d %b}" if day.year == today.year else f"on {day:%d %b %Y}"
        facts = {"symbol": symbol, "when": when, "change": change, "price": closes[day], "prev_close": closes[previous],
                 "market": market, "model": model, "sector": sector, "peers": peers, "reasons": reasons}
        verdict, sentences = summarise(facts)

        result = {
            "symbol": symbol, "date": day.isoformat(), "previous_date": previous.isoformat(), "latest_date": latest.isoformat(),
            "change": round(change, 5), "price": closes[day], "prev_close": closes[previous],
            "verdict": verdict, "summary": sentences,
            "market": {"name": MARKET_NAME, "change": None if market is None else round(market, 5)},
            "beta": round(model["beta"], 2) if model else None,
            "market_part": round(model["beta"] * market, 5) if model and market is not None else None,
            "typical_move": round(model["typical_own"], 5) if model else None,
            "sector": {"name": sector[0], "change": round(sector[1], 5)} if sector else None,
            "peers": [{"symbol": p, "change": None if c is None else round(c, 5)} for p, c in peers],
            "profile": profile,
            "reasons": reasons,
            "headlines": {scope: [asdict(h) for h in headlines if h.scope == scope][:12] for scope in SCOPE_WEIGHT},
            "big_days": self._big_days(stock_r, market_r, model, latest),
            "runtime_ms": int((time.perf_counter() - started) * 1000),
        }

        # ---- FinBERT sentiment on headlines ----
        try:
            titles = [h.title for h in headlines]
            sentiments = _finbert.score_headlines(titles, timeout=15)
            for h, s in zip(headlines, sentiments):
                if s is not None:
                    h.tone = s.score  # replace keyword tone with FinBERT score
            # Rebuild headline dicts with FinBERT data
            def _h_dict(h, s):
                d = asdict(h)
                if s:
                    d["sentiment"] = {"label": s.label, "pos": s.pos, "neg": s.neg, "neu": s.neu, "score": s.score}
                return d
            result["headlines"] = {
                scope: [_h_dict(h, sentiments[i]) for i, h in enumerate(headlines) if h.scope == scope][:12]
                for scope in SCOPE_WEIGHT
            }
            # Scope totals
            scope_sent = {}
            for scope in SCOPE_WEIGHT:
                hs = [sentiments[i] for i, h in enumerate(headlines) if h.scope == scope and sentiments[i]]
                if hs:
                    avg = sum(s.score for s in hs) / len(hs)
                    scope_sent[scope] = {"avg_score": round(avg, 3), "count": len(hs),
                                         "positive": sum(1 for s in hs if s.label == "positive"),
                                         "negative": sum(1 for s in hs if s.label == "negative"),
                                         "neutral": sum(1 for s in hs if s.label == "neutral")}
            result["sentiment_totals"] = scope_sent
        except Exception:
            result["sentiment_totals"] = {}

        # ---- Candlestick patterns ----
        try:
            ohlcv = self._ohlcv(to_yahoo(symbol))
            sorted_days = sorted(d for d in ohlcv if d <= day)
            if len(sorted_days) >= 3:
                # Last 3 bars for pattern detection
                pattern_days = sorted_days[-3:]
                ohlc_window = [(ohlcv[d][0], ohlcv[d][1], ohlcv[d][2], ohlcv[d][3]) for d in pattern_days]
                # Context: 5-10 closes before the pattern window
                ctx_days = sorted_days[:-3][-10:]
                ctx_closes = [ohlcv[d][3] for d in ctx_days]
                patterns_today = _detect_patterns(ohlc_window, ctx_closes)
                # Also check the day before
                if len(sorted_days) >= 4:
                    prev_days = sorted_days[-4:-1]
                    ohlc_prev = [(ohlcv[d][0], ohlcv[d][1], ohlcv[d][2], ohlcv[d][3]) for d in prev_days]
                    ctx_prev = sorted_days[:-4][-10:]
                    patterns_prev = _detect_patterns(ohlc_prev, [ohlcv[d][3] for d in ctx_prev])
                else:
                    patterns_prev = []
                result["candle_patterns"] = {"today": patterns_today, "previous": patterns_prev}
                # OHLC bars for the frontend to render as candlesticks (last ~10 days around the explained day)
                render_days = sorted_days[-10:]
                result["ohlc_bars"] = [
                    {"date": d.isoformat(), "open": ohlcv[d][0], "high": ohlcv[d][1],
                     "low": ohlcv[d][2], "close": ohlcv[d][3], "volume": ohlcv[d][4]}
                    for d in render_days
                ]
            else:
                result["candle_patterns"] = {"today": [], "previous": []}
                result["ohlc_bars"] = []
        except Exception:
            result["candle_patterns"] = {"today": [], "previous": []}
            result["ohlc_bars"] = []

        # ---- Chart CNN ----
        try:
            ohlcv = self._ohlcv(to_yahoo(symbol))
            cnn_today = _chart_cnn.chart_for_day(closes, ohlcv, day)
            cnn_prev = _chart_cnn.chart_for_day(closes, ohlcv, previous) if previous else None
            result["chart_cnn"] = {"today": cnn_today, "previous": cnn_prev}
        except Exception:
            result["chart_cnn"] = {"today": None, "previous": None}

        self._store(key, result)
        return result

    def day_change(self, ticker: str, day: dt.date, before: bool = False) -> tuple[str, float] | None:
        """A ticker's change on `day` (or, with `before`, on its last session before `day`), with that date."""
        closes = self._bars(ticker, (dt.datetime.fromtimestamp(self._clock(), IST).date() - day).days <= 1)
        moves = daily_returns(closes)
        days = [d for d in moves if (d < day if before else d == day)]
        if not days:
            return None
        d = max(days)
        return d.isoformat(), moves[d]

    def pool(self) -> ThreadPoolExecutor:
        return self._pool

    # ---- evidence ----

    def _profile(self, symbol: str) -> dict:
        cached = self._cached(("profile", symbol), PROFILE_TTL)
        if cached is not None:
            return cached
        ticker = to_yahoo(symbol)
        info, similar = self._pool.map(lambda f: _quietly(f, ticker), (self._yahoo.profile, self._yahoo.similar))
        info = info or {"sector": None, "industry": None, "summary": None}
        known = self._symbols()
        candidates = [from_yahoo(t) for t in (similar or []) if t.endswith(".NS") and from_yahoo(t) in known
                      and from_yahoo(t) != symbol]
        # Yahoo's list mixes in stocks that people look at together; keep those in a related sector.
        sectors = list(self._pool.map(lambda p: (_quietly(self._yahoo.profile, to_yahoo(p)) or {}).get("sector"), candidates))
        peers = [p for p, sector in zip(candidates, sectors) if related_sectors(info["sector"], sector)][:MAX_PEERS]
        profile = {**info, "peers": peers}
        self._store(("profile", symbol), profile)
        return profile

    def _bars(self, ticker: str, recent: bool) -> dict[dt.date, int]:
        cached = self._cached(("bars", ticker), RECENT_TTL if recent else PAST_TTL)
        if cached is not None:
            return cached
        try:
            raw = self._yahoo.chart(ticker, "1y", "1d")["bars"]
            closes = closes_by_day(raw)
            self._store(("ohlcv", ticker), ohlcv_by_day(raw))
        except Exception:
            closes = {}
        self._store(("bars", ticker), closes)
        return closes

    def _ohlcv(self, ticker: str) -> dict[dt.date, tuple[int, int, int, int, int]]:
        """Full OHLCV data, available after _bars has been called for this ticker."""
        return self._cached(("ohlcv", ticker), PAST_TTL) or {}

    def _window(self, previous: dt.date, day: dt.date, today: dt.date) -> dict:
        """When headlines count for a day's move: from the previous close to the end of the day.

        Recent days are searched with Google's "within N days", which gives exact times; older days by
        date range, which gives only the date, so a headline dated the previous day counts only for the
        company (results are often announced after the close)."""
        start = dt.datetime.combine(previous, CLOSE, IST).timestamp()
        end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0, 0), IST).timestamp()
        if (today - day).days <= 1:
            return {"query": f"when:{(today - previous).days + 1}d", "start": start, "end": end, "exact": True}
        return {"query": f"after:{previous.isoformat()} before:{(day + dt.timedelta(days=1)).isoformat()}",
                "start": dt.datetime.combine(previous, dt.time(0, 0), IST).timestamp(), "end": end, "exact": False,
                "day_start": dt.datetime.combine(day, dt.time(0, 0), IST).timestamp()}

    def _headlines(self, symbol: str, peers: list[str], industry_words: list[str], window: dict) -> list[Headline]:
        name, aliases = self._terms(symbol)
        peer_terms = [self._terms(p) for p in peers]
        searches = [("company", f'"{name}"', aliases)]
        if peer_terms:
            searches.append(("peers", "(" + " OR ".join(f'"{n}"' for n, _ in peer_terms) + ")",
                             [a for _, al in peer_terms for a in al]))
        if industry_words:
            searches.append(("industry", "(" + " OR ".join(f'"{w}"' for w in industry_words) + ")",
                             [w.split()[0] for w in industry_words]))
        searches.append(("market", "(Sensex OR Nifty OR \"Dalal Street\")", MARKET_WORDS))
        searches.append(("global", '("Asian markets" OR "Wall Street" OR "global markets" OR geopolitical OR war '
                                   'OR "crude oil" OR Taiwan)', GLOBAL_WORDS))
        results = self._pool.map(lambda s: self._search(f"{s[1]} {window['query']}"), searches)

        out: list[Headline] = []
        seen: set[str] = set()
        company_words = mentions_any(aliases)
        for (scope, _, words), articles in zip(searches, results):
            pattern = mentions_any(words)
            for a in articles:
                if a.url in seen or not pattern.search(a.title) or not is_english(a.title):
                    continue
                if scope != "company" and company_words.search(a.title):
                    scope_here = "company"  # a peer or market story that names the company is about it
                else:
                    scope_here = scope
                start = window["start"] if window["exact"] or scope_here == "company" else window["day_start"]
                if not start <= a.published < window["end"]:
                    continue
                seen.add(a.url)
                out.append(Headline(a.title, a.source, a.url, a.published, scope_here, round(tone(a.title), 2),
                                    reasons_in(a.title)))
        return out

    def _search(self, query: str):
        cached = self._cached(("news", query), RECENT_TTL)
        if cached is not None:
            return cached
        url = FEED_URL + urllib.parse.urlencode({"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"})
        try:
            articles = parse_items((self._fetch or fetch_feed)(url))
        except Exception:
            return []  # one failed search should not stop the explanation; it is not cached
        self._store(("news", query), articles)
        return articles

    @staticmethod
    def _big_days(stock_r: dict, market_r: dict, model: dict | None, latest: dt.date) -> list[dict]:
        """The days with the largest own moves in about the last three months, newest first."""
        beta = model["beta"] if model else 1.0
        days = sorted(d for d in stock_r if d <= latest)[-BIG_DAYS_WINDOW:]
        moves = [(d, stock_r[d], stock_r[d] - beta * market_r.get(d, 0.0)) for d in days]
        top = sorted(moves, key=lambda m: -abs(m[2]))[:BIG_DAYS]
        return [{"date": d.isoformat(), "change": round(r, 5), "own": round(o, 5)} for d, r, o in sorted(top, reverse=True)]

    # ---- cache ----

    def _cached(self, key: tuple, ttl: float):
        with self._lock:
            entry = self._cache.get(key)
            return entry[1] if entry and self._clock() - entry[0] < ttl else None

    def _store(self, key: tuple, value) -> None:
        with self._lock:
            self._cache[key] = (self._clock(), value)
            if len(self._cache) > 2000:  # drop the oldest half; a long session stays small
                for k, _ in sorted(self._cache.items(), key=lambda kv: kv[1][0])[:1000]:
                    del self._cache[k]


def _quietly(call, *args):
    try:
        return call(*args)
    except Exception:
        return None


def to_date(text: str | None) -> dt.date | None:
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise ExplainError("Dates are written YYYY-MM-DD, for example 2026-10-15.") from None

