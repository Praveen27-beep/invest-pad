"""POST/GET /ops/dividends/* -- the automated declared-dividend feed and yfinance
discovery, wired the same way as ``app.routers.corporate_actions.ops_router`` wires
BONUS/SPLIT: one private worker, an ``X-Ops-Key`` POST for a human or a non-Vercel
scheduler, a ``CRON_SECRET`` GET for Vercel Cron specifically.

WHY THIS FILE EXISTS AT ALL. ``app.db.dividend_events.refresh_dividend_feed`` and
``discover_dividends_from_yfinance`` were correct and fully tested from the day they
were written, and neither was EVER REACHABLE from outside a test file: no endpoint, no
cron entry, nothing called them. The dividend_event table was therefore empty in any
real, running deployment -- not because the ingestion was wrong, but because nothing
had ever invoked it. See docs/INGESTION.md's Adapter 6b for the write-up of this gap
and why it is fixed here rather than left as a known limitation: an ingestion path that
is correct but never runs produces the identical symptom, from a user's chair, as one
that does not exist.

Gated by the same shared secrets as every other ``/ops/*`` route (never a user login):
this mutates reference data shared across every investor, exactly like the
corporate-action feed it sits beside.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.auth.ops import require_cron_secret, require_ops_key
from app.database import get_conn
from app.db import dividend_events as de
from app.schemas.transactions import DiscoverDividendsYfinanceOut, RefreshDividendFeedOut

ops_router = APIRouter(prefix="/ops/dividends", tags=["ops"])

#: The full set of outcome keys `refresh_dividend_feed`/`discover_dividends_from_yfinance`
#: can produce -- see app.db.dividend_events.OUTCOME_*. Used to normalise their dynamic
#: dict (only outcomes that actually occurred are present) into the schemas' fixed,
#: always-present fields, rather than leaving a caller to guess which keys might be
#: missing from a given run.
_OUTCOME_KEYS = (
    de.OUTCOME_INSERTED, de.OUTCOME_CORROBORATED, "classified",
    de.OUTCOME_CONFLICT, de.OUTCOME_AMBIGUOUS, de.OUTCOME_UNCHANGED, "failed",
)


def _normalise(counts: dict[str, Any]) -> dict[str, Any]:
    return {key: counts.get(key, 0) for key in _OUTCOME_KEYS}


def _refresh_dividends(conn: Any, start: date, end: date) -> dict[str, Any]:
    result = de.refresh_dividend_feed(conn, start, end, actor_uid=None)
    return {
        "fetched": result.get("fetched", 0),
        "error": result.get("error"),
        **_normalise(result),
    }


@ops_router.post(
    "/refresh",
    response_model=RefreshDividendFeedOut,
    dependencies=[Depends(require_ops_key)],
)
def refresh_dividends(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    conn: Any = Depends(get_conn),
) -> dict[str, Any]:
    """``X-Ops-Key``-gated -- a human or a non-Vercel scheduler triggering a fetch
    directly, same posture as ``refresh_corporate_actions``. Defaults to a 2-day window
    ending today, overridable for a backfill."""
    today = date.today()
    return _refresh_dividends(conn, start or today - timedelta(days=1), end or today)


@ops_router.get(
    "/refresh-cron",
    response_model=RefreshDividendFeedOut,
    dependencies=[Depends(require_cron_secret)],
)
def refresh_dividends_cron(conn: Any = Depends(get_conn)) -> dict[str, Any]:
    """Same job, reachable by Vercel Cron: GET, gated by ``CRON_SECRET`` rather than
    ``X-Ops-Key``, since that is the only credential Vercel's scheduler sends. See
    docs/DEPLOYMENT.md."""
    today = date.today()
    return _refresh_dividends(conn, today - timedelta(days=1), today)


@ops_router.post(
    "/discover-yfinance",
    response_model=DiscoverDividendsYfinanceOut,
    dependencies=[Depends(require_ops_key)],
)
def discover_dividends_yfinance(
    isin: list[str] | None = Query(default=None),
    conn: Any = Depends(get_conn),
) -> dict[str, Any]:
    """``X-Ops-Key``-gated, same posture as ``discover_yfinance`` for corporate actions.
    Occasional -- a ticker's whole dividend history comes back in one call and does not
    change day to day. Defaults to every ISIN this system has ever held; pass one or
    more ``isin`` query params to target specific securities instead of paying for the
    full sweep. **The one path with real historical depth** -- run this once against
    your own held ISINs to backfill dividend declarations the live NSE feed's rolling
    window structurally cannot reach."""
    result = de.discover_dividends_from_yfinance(conn, isins=isin)
    return {**_normalise(result), "errors": result.get("errors", {})}
