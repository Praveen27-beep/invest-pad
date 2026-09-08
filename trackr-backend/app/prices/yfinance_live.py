"""Intraday quotes from Yahoo Finance (https://github.com/ranaroussi/yfinance), for
"today, before tonight's bhavcopy settles" only -- see app/prices/live.py for the gate
that enforces that boundary. This module knows nothing about dates, staleness, or the
ledger; it converts ISINs to tickers and tickers to prices, and stops.

yfinance is unofficial scraping of Yahoo's own endpoints, not a licensed API, and Yahoo's
rate limits tightened considerably through 2025-2026. The one rule that keeps this usable:
ALWAYS ONE BATCHED CALL for every ticker in a refresh, never a per-ISIN loop -- a loop is
exactly the pattern that gets an IP blocked. A failure here (429, network error, an empty
frame) is routine, not exceptional: it degrades to an empty result, and the caller falls
through to bhavcopy or the unpriced bucket, the same way a bad bhavcopy fetch does NOT
degrade (that one alerts -- see app/prices/sources.py). Intraday flakiness self-heals on
the next read or at the latest, tonight's bhavcopy; it is not worth paging anyone over.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger("prices.yfinance_live")

#: NSE/BSE equities trade in paisa ticks -- there is no such thing as a real market
#: price with more than 2 decimal places. Yahoo's own backend stores prices at float32
#: precision (confirmed: casting a returned Close down to float32 and back round-trips
#: exactly), so a value like 2320.10 routinely arrives as 2320.10009765625 -- a binary
#: artifact from Yahoo's side, not from anything this module does. Quantizing recovers
#: the real tradable price instead of faithfully preserving someone else's rounding
#: noise; ROUND_HALF_UP to match app/engine/holdings.py's own convention.
_PAISA = Decimal("0.01")


def resolve_ticker(symbol: str, exchange: str | None) -> str:
    """NSE trading symbol -> Yahoo ticker. ``.BO`` only when the security is BSE-only;
    ``.NS`` for NSE and for ``BOTH`` -- deeper liquidity, the same reason
    app.prices.pipe.SOURCE_PRIORITY has NSE win a bhavcopy conflict."""
    suffix = ".BO" if exchange == "BSE" else ".NS"
    return f"{symbol}{suffix}"


def _last_close(frame: Any, symbol: str) -> Decimal | None:
    """The most recent non-null Close for one ticker out of a yfinance download frame.
    ``None`` on anything short of a clean numeric value -- a delisted or mistyped ticker
    must degrade to "no live price", never a fabricated one."""
    try:
        # yfinance keeps a (Ticker, Field) MultiIndex on frame.columns whenever
        # group_by="ticker" is used -- confirmed empirically this holds even for a
        # single-symbol request, it does NOT flatten to bare field columns. Symbol
        # *count* is not a reliable proxy for this shape (an earlier version of this
        # function assumed it was, and silently dropped every single-ISIN live fetch
        # via a caught KeyError -- exactly the common case of one holding's bhavcopy
        # lagging while everything else is already priced).
        multi = getattr(frame.columns, "nlevels", 1) > 1
        series = frame[symbol]["Close"] if multi else frame["Close"]
        closes = series.dropna()
        if closes.empty:
            return None
        value = closes.iloc[-1]
    except (KeyError, IndexError, TypeError):
        return None
    try:
        # str() first, deliberately -- see CLAUDE.md rule 1. yfinance returns numpy
        # float64; Decimal(float) would smuggle in exactly the binary-approximation
        # error this codebase exists to avoid. Quantizing to paisa on top of that
        # cleans up Yahoo's own float32-precision noise -- see _PAISA above.
        return Decimal(str(value)).quantize(_PAISA, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def fetch_live(tickers: dict[str, str]) -> dict[str, Decimal]:
    """ISIN -> Yahoo ticker in, ISIN -> Decimal last price out.

    One yfinance call for every ticker requested, however many ISINs that is. Any ISIN
    whose ticker didn't resolve to a usable price -- ticker wrong, Yahoo has nothing for
    it, or the whole call failed -- is simply absent from the result. Never raises.
    """
    if not tickers:
        return {}

    isins_by_ticker: dict[str, list[str]] = {}
    for isin, ticker in tickers.items():
        isins_by_ticker.setdefault(ticker, []).append(isin)
    symbols = sorted(isins_by_ticker)

    try:
        import yfinance as yf

        frame = yf.download(
            symbols,
            period="1d",
            group_by="ticker",
            progress=False,
            threads=True,
            auto_adjust=False,
        )
    except Exception:
        logger.info("yfinance live fetch failed for %d ticker(s)", len(symbols), exc_info=True)
        return {}

    if frame is None or frame.empty:
        return {}

    out: dict[str, Decimal] = {}
    for symbol in symbols:
        price = _last_close(frame, symbol)
        if price is None:
            continue
        for isin in isins_by_ticker[symbol]:
            out[isin] = price
    return out
