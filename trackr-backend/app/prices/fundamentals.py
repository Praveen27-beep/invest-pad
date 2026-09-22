"""Orchestrates the fundamentals cache: pick what is stalest, fetch it, store it.

Sits to ``app.prices.yfinance_fundamentals`` / ``app.db.fundamentals`` exactly as
``app.prices.live`` sits to its own source and store: the source fetches, the db module
persists, and this is the module a caller actually reaches for.

The rule that makes the analytics endpoint fast, stated here once: **the read path never
calls this.** Only the cron does. A dashboard load reads whatever the cache holds and
reports its staleness; it never waits on a rate-limited third-party endpoint, and Yahoo
being slow or blocked can degrade coverage but can never hang or break the page.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Any

from app.db.fundamentals import Fundamentals, stalest_isins, upsert
from app.prices.yfinance_fundamentals import FundamentalsRow, fetch_many
from app.prices.yfinance_live import resolve_ticker

logger = logging.getLogger("prices.fundamentals")

#: How many scrips one cron run will fetch. `Ticker.info` is one request per scrip (plus
#: two for statements), so this is the request budget per run. With ~120 tracked ISINs a
#: limit of 60 refreshes everything roughly every other day, which is far more often than
#: a quarterly filing changes.
DEFAULT_BATCH_LIMIT = 60


def _to_record(isin: str, row: FundamentalsRow, as_of: date) -> Fundamentals:
    fields = asdict(row)
    fields.pop("symbol", None)
    return Fundamentals(
        isin=isin,
        as_of=as_of,
        source="YFINANCE",
        fetched_at=datetime.now(UTC),
        **fields,
    )


def refresh_stale(
    conn: Any,
    candidates: list[str],
    symbols: dict[str, str],
    exchanges: dict[str, str | None] | None = None,
    limit: int = DEFAULT_BATCH_LIMIT,
    as_of: date | None = None,
    ticker_factory: Any = None,
) -> dict[str, Any]:
    """Refresh the ``limit`` stalest of ``candidates``. Never raises.

    ``symbols`` is ISIN -> trading symbol, which the caller reads from ``security`` -- kept
    CURRENT by ``app.db.symbols.refresh_symbols``, without which this would cheerfully
    fetch a renamed scrip's dead ticker and store an empty row as if it were an answer.

    Each row is persisted as it arrives, so a rate-limited run keeps what it got.
    """
    on = as_of or date.today()
    wanted = stalest_isins(conn, candidates, limit)
    if not wanted:
        return {"requested": 0, "stored": 0, "with_data": 0, "as_of": on}

    exchanges = exchanges or {}
    tickers = {
        isin: resolve_ticker(symbols[isin], exchanges.get(isin))
        for isin in wanted
        if symbols.get(isin)
    }

    stored = 0
    with_data = 0

    def persist(isin: str, row: FundamentalsRow) -> None:
        nonlocal stored, with_data
        record = _to_record(isin, row, on)
        try:
            upsert(conn, [record])
            stored += 1
            if record.pe is not None or record.roe is not None or record.pb is not None:
                with_data += 1
        except Exception:
            # One bad row must not end the run; the rest of the batch is still worth having.
            logger.warning("could not store fundamentals for %s", isin, exc_info=True)

    try:
        fetch_many(tickers, ticker_factory=ticker_factory, on_row=persist)
    except Exception:
        logger.warning("fundamentals batch ended early", exc_info=True)

    logger.info(
        "fundamentals refresh: requested=%d stored=%d with_data=%d", len(tickers), stored, with_data
    )
    return {
        "requested": len(tickers),
        "stored": stored,
        "with_data": with_data,
        "as_of": on,
        "skipped_no_symbol": sorted(set(wanted) - set(tickers)),
    }
