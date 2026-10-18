"""Latest news headlines for a stock, from Google News search (an RSS feed, no key needed).

For each stock the search asks for the past week's news about the company. Headlines that do
not name the company, quote pages and repeats are dropped, and the most recent few are kept.
Results are cached for a few minutes; if a refresh fails, the last good headlines are returned
with a note saying so.
"""
import email.utils
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from defusedxml import ElementTree  # the feed comes from the internet, so parse it safely

SOURCE = "Google News"
FEED_URL = "https://news.google.com/rss/search?"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
TIMEOUT_SECONDS = 8

# Listings and quote pages that are not news.
NOT_NEWS = re.compile(r"share price (today|live)|stock price (today|live|&|chart)|stock price, news|quote and history"
                      r"|^news by |price chart|live nse|share price$", re.IGNORECASE)


@dataclass
class Article:
    title: str
    source: str
    url: str
    published: int  # Unix time, seconds


def search_url(company: str) -> str:
    query = f'"{company}" share when:7d'  # this week's news that mentions the company
    return FEED_URL + urllib.parse.urlencode({"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"})


def fetch_feed(url: str) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read()


def parse_items(feed: bytes) -> list[Article]:
    """Every headline in a feed, newest first: publisher name taken off the title, quote pages,
    unsafe links and repeats of the same story dropped."""
    root = ElementTree.fromstring(feed)
    articles: list[Article] = []
    seen: set[str] = set()
    for item in root.iterfind("./channel/item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        source_element = item.find("source")
        source = (source_element.text or "").strip() if source_element is not None else ""
        if source and title.endswith(f" - {source}"):
            title = title[: -len(f" - {source}")].strip()  # Google appends the publisher to the title
        if not title or not url.startswith(("https://", "http://")) or NOT_NEWS.search(title):
            continue
        key = re.sub(r"\W+", " ", title.lower()).strip()[:70]  # the same story from different feeds
        if key in seen:
            continue
        seen.add(key)
        try:
            published = int(email.utils.parsedate_to_datetime(item.findtext("pubDate") or "").timestamp())
        except (TypeError, ValueError):
            continue
        articles.append(Article(title=title, source=source, url=url, published=published))
    articles.sort(key=lambda a: a.published, reverse=True)
    return articles


def mentions_any(words: list[str]) -> re.Pattern:
    """Matches any of `words` as a whole word, ignoring case."""
    return re.compile("|".join(rf"(?<!\w){re.escape(w)}(?!\w)" for w in words), re.IGNORECASE)


def parse_feed(feed: bytes, aliases: list[str], count: int) -> list[Article]:
    """The `count` most recent headlines that name the company."""
    mentions = mentions_any(aliases)
    return [a for a in parse_items(feed) if mentions.search(a.title)][:count]


SUFFIX = re.compile(r"[\s,.]+(limited|ltd\.?)\s*$", re.IGNORECASE)


def company_terms(symbol: str, name: str | None, overrides: dict[str, tuple[str, list[str]]]) -> tuple[str, list[str]]:
    """The name to search the news for, and the words a headline must contain to be about the stock.

    "TATA MOTORS LIMITED" gives ("Tata Motors", ["Tata Motors", "TATAMOTORS"]). A name of three or more
    words also accepts its first two, and one of four or more is searched by those two ("Adani Ports and
    Special Economic Zone" is searched as "Adani Ports"). A symbol of three or more letters is accepted
    too. `overrides` holds hand-written terms for stocks where this goes wrong.
    """
    if symbol in overrides:
        return overrides[symbol]
    clean = SUFFIX.sub("", (name or symbol).strip()).strip()
    if clean.isupper():
        clean = " ".join(w if len(w) <= 3 and w.isalpha() and w not in ("AND", "THE", "OF") else w.title()
                         for w in clean.split()).replace(" And ", " and ").replace(" Of ", " of ")
    words = clean.split()
    aliases = [clean]
    search = clean
    if len(words) >= 3:
        short = " ".join(words[1:3] if words[0].lower() == "the" else words[:2])
        aliases.append(short)
        if len(words) >= 4:
            search = short
    if symbol.isalpha() and len(symbol) >= 3:
        aliases.append(symbol)
    return search, aliases


class NewsService:
    """`companies` maps a symbol to (name to search for, words a headline must contain): a dict, or a
    function for stocks looked up on demand."""

    def __init__(self, companies, per_stock: int, cache_seconds: int, fetch=None, clock=time.time):
        self._company = companies if callable(companies) else companies.__getitem__
        self._per_stock = per_stock
        self._cache_seconds = cache_seconds
        self._fetch = fetch  # None means the real fetch_feed, looked up at call time so tests can replace it
        self._clock = clock
        self._lock = threading.Lock()
        self._cache: dict[str, dict] = {}  # symbol -> {"articles", "fetched_at", "error"}

    def latest(self, symbols: list[str]) -> dict[str, dict]:
        now = self._clock()
        with self._lock:
            stale = [s for s in symbols if s not in self._cache or now - self._cache[s]["fetched_at"] >= self._cache_seconds]
        if stale:
            with ThreadPoolExecutor(max_workers=min(4, len(stale))) as pool:
                for symbol, entry in zip(stale, pool.map(self._refresh, stale)):
                    with self._lock:
                        self._cache[symbol] = entry
        with self._lock:
            return {s: {"symbol": s, "company": self._company(s)[0], **self._cache[s]} for s in symbols}

    def _refresh(self, symbol: str) -> dict:
        company, aliases = self._company(symbol)
        fetch = self._fetch or fetch_feed
        try:
            articles = parse_feed(fetch(search_url(company)), aliases, self._per_stock)
            return {"articles": [asdict(a) for a in articles], "fetched_at": self._clock(), "error": None}
        except Exception as err:  # no internet, Google refusing, a broken feed
            with self._lock:
                previous = self._cache.get(symbol)
            message = f"Could not refresh the news ({type(err).__name__})."
            if previous and previous["articles"]:
                return {**previous, "error": message + " Showing the last headlines we had."}
            # Try again on the next request instead of caching the failure for the full period.
            return {"articles": [], "fetched_at": self._clock() - self._cache_seconds, "error": message}
