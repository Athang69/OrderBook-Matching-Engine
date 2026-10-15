"""Whether NSE is open: the normal session is 9:15 am to 3:30 pm Indian time, Monday to Friday.

The clock alone does not know about exchange holidays, so Yahoo's own market state for the NIFTY 50
is also used when it is recent: on a holiday it does not say the market is trading.
"""
import datetime as dt

from . import config

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
YAHOO_STATE_MAX_AGE = 300  # seconds; an older reading is ignored and the clock alone decides


def _at(day: dt.date, hm: tuple[int, int]) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hm[0], hm[1], tzinfo=IST)


def _next_weekday(day: dt.date) -> dt.date:
    day += dt.timedelta(days=1)
    while day.weekday() >= 5:
        day += dt.timedelta(days=1)
    return day


def session_status(now: float, yahoo_state: str | None = None, yahoo_state_at: float | None = None) -> dict:
    """The session at Unix time `now`.

    state is OPEN, PRE_OPEN (9:00 to 9:15, when NSE collects orders for the opening price) or CLOSED.
    """
    t = dt.datetime.fromtimestamp(now, IST)
    today = t.date()
    weekday = today.weekday() < 5
    open_at, close_at = _at(today, config.MARKET_OPEN), _at(today, config.MARKET_CLOSE)
    recent = yahoo_state is not None and yahoo_state_at is not None and now - yahoo_state_at < YAHOO_STATE_MAX_AGE
    # Yahoo says REGULAR while NSE trades; anything else in the middle of the session means a holiday.
    holiday = recent and weekday and open_at + dt.timedelta(minutes=2) <= t < close_at and yahoo_state != "REGULAR"

    if weekday and not holiday and open_at <= t < close_at:
        state = "OPEN"
    elif weekday and not holiday and _at(today, config.PRE_OPEN) <= t < open_at:
        state = "PRE_OPEN"
    else:
        state = "CLOSED"

    if state != "CLOSED" or (weekday and not holiday and t < open_at):
        next_open = open_at
    else:
        next_open = _at(_next_weekday(today), config.MARKET_OPEN)
    square_off_at = _at(today, config.INTRADAY_SQUARE_OFF)
    labels = {"OPEN": "Market open", "PRE_OPEN": "Pre-open session", "CLOSED": "Market closed"}
    return {
        "state": state,
        "label": labels[state] + (" (exchange holiday)" if holiday else ""),
        "now": now,
        "trading_day": today.isoformat(),
        "opens_at": next_open.timestamp(),
        "closes_at": close_at.timestamp(),
        "intraday_open": state == "OPEN" and t < square_off_at,
        "square_off_at": square_off_at.timestamp(),
    }
