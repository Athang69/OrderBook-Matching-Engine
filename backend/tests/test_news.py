"""News headlines: parsing the feed, filtering, caching and the API. No network is used."""
from xml.sax.saxutils import escape

import pytest
from fastapi.testclient import TestClient

from backend.app import config, news
from backend.app.main import app
from backend.app.news import NewsService, company_terms, parse_feed

ALIASES = ["Reliance", "RIL"]


def feed(*items: tuple[str, str, str, str]) -> bytes:
    """items: (title, source, link, pubDate)."""
    body = "".join(
        f"<item><title>{escape(t)} - {escape(s)}</title><link>{escape(l)}</link><pubDate>{d}</pubDate>"
        f"<source url='https://x'>{escape(s)}</source></item>"
        for t, s, l, d in items)
    return f"<?xml version='1.0'?><rss><channel><title>t</title>{body}</channel></rss>".encode()


SAMPLE = feed(
    ("Reliance shares rise after Jio IPO news", "Livemint", "https://news.example/1", "Wed, 14 Oct 2026 12:00:00 GMT"),
    ("RIL board meets on Friday", "ET", "https://news.example/2", "Wed, 14 Oct 2026 15:00:00 GMT"),
    ("Market wrap: Nifty ends flat", "ET", "https://news.example/3", "Wed, 14 Oct 2026 16:00:00 GMT"),
    ("Reliance Industries Share Price Today - Live", "Some site", "https://news.example/4", "Wed, 14 Oct 2026 17:00:00 GMT"),
    ("Reliance shares rise after Jio IPO news!", "Other paper", "https://news.example/5", "Wed, 14 Oct 2026 11:00:00 GMT"),
    ("Reliance to invest in solar", "BS", "javascript:alert(1)", "Wed, 14 Oct 2026 13:00:00 GMT"),
    ("Reliance Retail opens 100 stores", "BS", "https://news.example/7", "Tue, 13 Oct 2026 09:00:00 GMT"),
    ("Reliance Capital update", "BS", "https://news.example/8", "Mon, 12 Oct 2026 09:00:00 GMT"),
    ("Unreliance is not a word", "BS", "https://news.example/9", "Wed, 14 Oct 2026 18:00:00 GMT"),
    ("Reliance Share Price", "Upstox", "https://news.example/10", "Wed, 14 Oct 2026 19:00:00 GMT"),
    ("Reliance Industries Limited (RELIANCE) stock price, news, quote and history", "Yahoo", "https://news.example/11", "Wed, 14 Oct 2026 19:30:00 GMT"),
)


def test_keeps_the_most_recent_headlines_about_the_company():
    articles = parse_feed(SAMPLE, ALIASES, 3)
    assert [a.title for a in articles] == [
        "RIL board meets on Friday",                  # 15:00
        "Reliance shares rise after Jio IPO news",    # 12:00; the 11:00 repeat is dropped
        "Reliance Retail opens 100 stores",           # 13 Oct
    ]
    assert articles[0].source == "ET"  # the publisher is taken off the end of the title
    assert articles[0].url == "https://news.example/2"
    assert articles[0].published > articles[1].published > articles[2].published


def test_drops_unrelated_quote_pages_and_unsafe_links():
    titles = [a.title for a in parse_feed(SAMPLE, ALIASES, 10)]
    assert "Market wrap: Nifty ends flat" not in titles  # does not name the company
    assert not any("Share Price" in t or "quote and history" in t for t in titles)  # quote pages, not news
    assert "Reliance to invest in solar" not in titles  # link is not http(s)
    assert "Unreliance is not a word" not in titles  # whole words only


def test_aliases_with_symbols_match():
    lt = feed(("L&T wins Rs 5,000 crore order", "ET", "https://n/1", "Wed, 14 Oct 2026 12:00:00 GMT"),
              ("SALT prices fall", "ET", "https://n/2", "Wed, 14 Oct 2026 13:00:00 GMT"))
    assert [a.title for a in parse_feed(lt, ["Larsen", "L&T"], 3)] == ["L&T wins Rs 5,000 crore order"]


def test_broken_feed_raises():
    with pytest.raises(Exception):
        parse_feed(b"<rss><channel><item>", ALIASES, 3)


class FakeClock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


def make_service(fetch, clock):
    return NewsService({"RELIANCE": ("Reliance Industries", ALIASES)}, 3, 600, fetch=fetch, clock=clock)


def test_results_are_cached_for_the_cache_period():
    calls = []
    clock = FakeClock()
    service = make_service(lambda url: calls.append(url) or SAMPLE, clock)
    first = service.latest(["RELIANCE"])["RELIANCE"]
    assert len(first["articles"]) == 3 and first["error"] is None and first["company"] == "Reliance Industries"
    clock.now += 599
    service.latest(["RELIANCE"])
    assert len(calls) == 1  # still fresh
    clock.now += 2
    service.latest(["RELIANCE"])
    assert len(calls) == 2  # refreshed after 10 minutes
    assert "Reliance+Industries" in calls[0] or "Reliance%20Industries" in calls[0]


def test_failed_refresh_keeps_the_last_headlines():
    clock = FakeClock()
    answers = [SAMPLE]

    def fetch(url):
        if answers:
            return answers.pop()
        raise OSError("offline")

    service = make_service(fetch, clock)
    service.latest(["RELIANCE"])
    clock.now += 601
    entry = service.latest(["RELIANCE"])["RELIANCE"]
    assert len(entry["articles"]) == 3
    assert "Showing the last headlines" in entry["error"]


def test_failure_with_nothing_cached_is_reported_and_retried():
    clock = FakeClock()
    calls = []

    def fetch(url):
        calls.append(url)
        raise OSError("offline")

    service = make_service(fetch, clock)
    entry = service.latest(["RELIANCE"])["RELIANCE"]
    assert entry["articles"] == [] and "Could not refresh" in entry["error"]
    service.latest(["RELIANCE"])
    assert len(calls) == 2  # a failure is not cached


pytestmark_api = pytest.mark.skipif(not any(config.NSE_DATA_DIR.glob("sec_bhavdata_full_*.csv")),
                                    reason="NSE data not downloaded")


@pytest.fixture(scope="module")
def client():
    patch = pytest.MonkeyPatch()
    patch.setattr(news, "fetch_feed", lambda url: SAMPLE)
    with TestClient(app) as test_client:
        yield test_client
    patch.undo()


@pytestmark_api
def test_news_api(client):
    body = client.get("/v1/news", params={"symbols": ["RELIANCE", "reliance", "TCS"]}).json()
    assert body["source"] == "Google News" and body["per_stock"] == 3
    assert list(body["stocks"]) == ["RELIANCE", "TCS"]  # repeats removed, order kept
    assert body["stocks"]["RELIANCE"]["articles"][0]["title"] == "RIL board meets on Friday"
    assert body["stocks"]["TCS"]["company"] == "Tata Consultancy Services"
    assert body["stocks"]["TCS"]["articles"] == []  # the sample feed has nothing that names TCS


@pytestmark_api
def test_news_api_validation(client):
    assert client.get("/v1/news").status_code == 422
    assert client.get("/v1/news", params={"symbols": ["NOPE"]}).status_code == 422
    too_many = config.DEFAULT_WATCHLIST + ["WIPRO", "NTPC", "ONGC"]
    assert len(too_many) > config.MAX_NEWS_SYMBOLS
    assert client.get("/v1/news", params={"symbols": too_many}).status_code == 422


def test_search_terms_for_any_stock():
    assert company_terms("TMCV", "TATA MOTORS LIMITED", {}) == ("Tata Motors", ["Tata Motors", "TMCV"])
    search, aliases = company_terms("ADANIPORTS", "Adani Ports and Special Economic Zone Limited", {})
    assert search == "Adani Ports" and "Adani Ports" in aliases
    assert company_terms("INDHOTEL", "THE INDIAN HOTELS COMPANY LIMITED", {})[1][1] == "Indian Hotels"
    assert company_terms("TCS", "anything", config.COMPANIES) == config.COMPANIES["TCS"]
