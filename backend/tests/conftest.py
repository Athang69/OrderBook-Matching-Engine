"""The tests run without the internet: no live prices are fetched, and each test feeds in its own."""
import os

os.environ.setdefault("ORDERBOOK_LIVE", "0")
