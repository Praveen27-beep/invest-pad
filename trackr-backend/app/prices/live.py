"""Orchestrates the intraday live-price cache: check it, refresh what's stale/missing from
yfinance, store, return. The role this plays relative to `app.db.live_prices` /
`app.prices.yfinance_live` mirrors `app.prices.pipe` relative to `app.db.prices` /
`app.prices.sources` -- source module fetches, db module persists, this module is the glue
a caller actually reaches for.

The one rule that makes the whole live-pricing feature safe, stated once here rather than
left implicit at every call site: this is consulted ONLY for `as_of == ist_today()`, and
ONLY to fill ISINs bhavcopy has no row for yet (see app/routers/holdings.py::_portfolio).
Every other date is bhavcopy-only, unconditionally -- this module has no opinion on, and no
path that could touch, a historical valuation.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from app import securities
from app.db.live_prices import get_fresh, upsert_live_prices
from app.prices.yfinance_live import fetch_live, resolve_ticker

IST = ZoneInfo("Asia/Kolkata")


def ist_now() -> datetime:
    return datetime.now(IST)


def ist_today() -> date:
    """NSE's trading day, not the server's. The app runs in UTC (Vercel); naive
    ``date.today()`` would be wrong for the ~5.5 hours a day IST and UTC disagree on the
    date."""
    return ist_now().date()


def refresh_and_get(conn: Any, isins: list[str]) -> dict[str, Decimal]:
    """Live prices for ``isins``, refreshing from yfinance whatever the cache doesn't
    already cover freshly enough. No market-hours gate: yfinance is reachable any time,
    this path is only ever invoked on demand (a dashboard load asking for as_of ==
    today), never polled by a background job, and the TTL in ``get_fresh`` already
    bounds call volume to once per DEFAULT_MAX_AGE_SECONDS per ISIN regardless of when
    it's called. Outside NSE hours this just re-confirms the day's last close -- the
    same number bhavcopy will settle with, harmlessly held under the `live` flag until
    it does. A ticker that fails to resolve, or a fetch that fails outright, simply
    leaves that ISIN out of the result; the caller (bhavcopy's staleness-window
    fallback, then the unpriced bucket) already handles "no price" without this
    module's help.
    """
    if not isins:
        return {}

    cached = get_fresh(conn, isins)
    still_missing = [isin for isin in isins if isin not in cached]
    if not still_missing:
        return cached

    meta = securities.lookup(conn, still_missing)
    tickers = {
        isin: resolve_ticker(row["symbol"], row["exchange"])
        for isin in still_missing
        if (row := meta.get(isin)) and row.get("symbol")
    }
    fetched = fetch_live(tickers)
    if fetched:
        upsert_live_prices(conn, fetched, ist_now())

    return {**cached, **fetched}
