"""GET /investors/{id}/performance, POST /ops/prices/refresh.

``absolute_return`` is computed via ``compute_net_invested``/``compute_absolute_return``
(app/engine/returns.py), per the ``net_invested`` definition in ENGINE_SPEC section 5:
net lifetime cash contributed (BUY/IPO_ALLOT outflows minus SELL/BUYBACK inflows, across
the whole ledger). It is ``None`` when ``net_invested <= 0`` -- heavy net withdrawals, or
even a full exit at a profit, can drive lifetime contributions to zero or negative.

``cagr`` stays ``None`` permanently, by decision, not by omission: section 5 scopes CAGR
to per-holding only (its lump-sum assumption breaks for a portfolio's staggered dated
contributions), and there is no portfolio-level case that is both valid and not already
covered by ``xirr_all``. Benchmark comparison (section 6) needs an index-level feed this
system does not have, so it is left unwired rather than faked.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.auth.dependencies import get_current_user
from app.config import Settings, get_settings
from app.database import get_conn, money, rate
from app.db import snapshots
from app.db.prices import (
    held_isins,
    latest_prices,
    missing_prices,
    price_dates_present,
    upsert_prices,
)
from app.db.repository import (
    get_investor_onboarding_date,
    list_investor_ids,
    load_transactions,
)
from app.engine.errors import MissingPriceError
from app.engine.holdings import compute_holdings
from app.engine.returns import compute_absolute_return, compute_net_invested
from app.engine.snapshot import compute_snapshot
from app.engine.types import Transaction
from app.engine.xirr import (
    compute_fy_xirr,
    compute_period_xirr,
    compute_xirr,
    compute_xirr_holdings,
    financial_year_start,
    period_warning,
)
from app.prices.alerts import Notifier, get_notifier
from app.prices.pipe import NSE_BHAVCOPY_EARLIEST, backfill_days, trading_days, fetch_day
from app.schemas.analytical import (
    PerformanceResponse,
    PriceRefreshResponse,
    SnapshotRunResponse,
)

logger = logging.getLogger("app")

router = APIRouter(tags=["derived", "ops"])


def _fy_xirr(
    request: Request,
    connection: Any,
    investor_id: str,
    transactions: list[Transaction],
    prices: dict[str, Decimal],
    as_of: date,
    advised_only: bool,
) -> Decimal | None:
    """``fy_xirr``'s opening_value: a persisted 1-April snapshot first, a live
    ``compute_snapshot`` call only when none exists -- never a stand-in either way.

    ``compute_fy_xirr``'s docstring: ``opening_value`` must be the market value ON 1
    APRIL, from a stored ``Snapshot`` or ``compute_snapshot`` against that date's prices;
    where neither exists, the honest move is to omit the metric. ``app.db.snapshots`` is
    that store now (Phase 2 Session 1) -- a hit means the on-the-fly recomputation this
    function used to do on every request is skipped entirely. A miss falls through to the
    exact live path this function has always used, unchanged: when a held-at-1-April ISIN
    has no usable price that far back, ``MissingPriceError`` is caught HERE ONLY, not
    re-raised, so the rest of the response (xirr_all, xirr_holdings, invested/market_value)
    is still valid and must still be returned. Substituting today's price, the nearest
    available date, or any other stand-in would count this year's entire gain as if it
    already existed on day one -- exactly what the docstring forbids. The condition is
    logged, not swallowed.
    """
    fy_start = financial_year_start(as_of)
    persisted = snapshots.get_snapshot(connection, investor_id, fy_start, advised_only)
    if persisted is not None:
        return compute_fy_xirr(transactions, prices, persisted.market_value, as_of)

    fy_isins = [h.isin for h in compute_holdings(transactions, fy_start)]
    fy_prices = latest_prices(connection, fy_isins, fy_start)
    try:
        opening_snapshot = compute_snapshot(transactions, fy_prices, fy_start)
    except MissingPriceError as exc:
        logger.warning(
            "fy_xirr omitted: no usable price on/before %s for %s "
            "(investor_id=%s request_id=%s)",
            fy_start, exc.isins, investor_id,
            getattr(getattr(request, "state", None), "request_id", None),
            exc_info=True,
        )
        return None
    return compute_fy_xirr(transactions, prices, opening_snapshot.market_value, as_of)


def _period_xirr(
    request: Request,
    connection: Any,
    investor_id: str,
    transactions: list[Transaction],
    prices: dict[str, Decimal],
    start_date: date,
    as_of: date,
    advised_only: bool,
) -> Decimal | None:
    """``period_xirr``'s opening_value: a persisted onboarding-date snapshot first, a
    live ``compute_snapshot`` call only when none exists -- never a stand-in either way.
    Identical shape to ``_fy_xirr``: a persisted-row hit skips recomputation outright; on
    a miss, ``MissingPriceError`` is caught HERE ONLY, logged, and turned into ``None`` so
    the rest of the response stays valid. ``start_date`` is the investor's stored
    ``onboarding_date`` (docs/DATA_MODEL.md) rather than ``financial_year_start(as_of)``
    -- the caller (``performance``) only invokes this when ``start_date <= as_of``.
    """
    persisted = snapshots.get_snapshot(connection, investor_id, start_date, advised_only)
    if persisted is not None:
        return compute_period_xirr(
            transactions, prices, start_date, persisted.market_value, as_of
        )

    period_isins = [h.isin for h in compute_holdings(transactions, start_date)]
    period_prices = latest_prices(connection, period_isins, start_date)
    try:
        opening_snapshot = compute_snapshot(transactions, period_prices, start_date)
    except MissingPriceError as exc:
        logger.warning(
            "period_xirr omitted: no usable price on/before %s for %s "
            "(investor_id=%s request_id=%s)",
            start_date, exc.isins, investor_id,
            getattr(getattr(request, "state", None), "request_id", None),
            exc_info=True,
        )
        return None
    return compute_period_xirr(
        transactions, prices, start_date, opening_snapshot.market_value, as_of
    )


@router.get("/investors/{investor_id}/performance", response_model=PerformanceResponse)
def performance(
    request: Request,
    investor_id: str,
    as_of: date | None = None,
    advised_only: bool = False,
    connection: Any = Depends(get_conn),
) -> dict[str, Any]:
    """Both XIRR variants, always together -- CLAUDE.md: reporting one alone leaves a
    choice about which number flatters the portfolio, and that choice should not exist.
    ``fy_xirr`` sits beside them, scoped to the financial year to date; see ``_fy_xirr``
    for why it can legitimately come back null. ``period_xirr`` sits beside those,
    scoped to the investor's stored ``onboarding_date`` (the adviser-onboarding case);
    see ``_period_xirr``.

    ``advised_only`` restricts the ledger to accounts flagged ``is_advised`` (docs/
    DATA_MODEL.md, contracts/openapi.yaml), so a SEBI-registered adviser can report on
    the mandated account only.
    """
    resolved_as_of = as_of or date.today()
    transactions = load_transactions(
        connection, investor_id=investor_id, advised_only=advised_only
    )

    isins = [h.isin for h in compute_holdings(transactions, resolved_as_of)]
    prices = latest_prices(connection, isins, resolved_as_of)

    snapshot = compute_snapshot(transactions, prices, resolved_as_of)
    xirr_all = compute_xirr(transactions, prices, resolved_as_of)
    xirr_holdings = compute_xirr_holdings(transactions, prices, resolved_as_of)
    fy_xirr = _fy_xirr(
        request, connection, investor_id, transactions, prices, resolved_as_of, advised_only
    )
    net_invested = compute_net_invested(transactions, resolved_as_of)
    absolute_return = compute_absolute_return(
        net_invested, snapshot.market_value, snapshot.realised_to_date
    )

    # period_xirr (adviser onboarding). onboarding_date is stored independently of any
    # given request's as_of (a free query param, usable for historical replay) -- unlike
    # financial_year_start(as_of), it is not guaranteed <= as_of, so that has to be
    # checked here rather than assumed. period_start and warning stay tied to
    # period_xirr's non-null-ness: no partial state where a date is known but nothing is
    # shown.
    onboarding_date = get_investor_onboarding_date(connection, investor_id)
    period_xirr_value: Decimal | None = None
    period_start: date | None = None
    period_warn: str | None = None
    if onboarding_date is not None and onboarding_date <= resolved_as_of:
        period_xirr_value = _period_xirr(
            request, connection, investor_id, transactions, prices,
            onboarding_date, resolved_as_of, advised_only,
        )
        if period_xirr_value is not None:
            period_start = onboarding_date
            period_warn = period_warning(onboarding_date, resolved_as_of)

    return {
        "as_of": resolved_as_of,
        "xirr_all": rate(xirr_all),
        "xirr_holdings": rate(xirr_holdings),
        "fy_xirr": rate(fy_xirr),
        "period_xirr": rate(period_xirr_value),
        "period_start": period_start,
        "absolute_return": rate(absolute_return),
        "invested": money(snapshot.invested),
        "market_value": money(snapshot.market_value),
        "unrealised": money(snapshot.unrealised),
        "realised_to_date": money(snapshot.realised_to_date),
        "warning": period_warn,
    }


@router.post("/ops/prices/refresh", response_model=PriceRefreshResponse)
def refresh_prices(
    connection: Any = Depends(get_conn),
    _current_user: dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Fetch NSE + BSE bhavcopy and upsert prices for every ISIN the ledger holds.

    Mirrors ``app.prices.pipe.main()``'s logic exactly (both exchanges mandatory, stores
    only ISINs already in the ledger, and the same ``get_notifier`` selection so a
    failure reaches a human here too) as a callable endpoint rather than a cron
    entry point. Requires auth: this mutates stored prices for every investor, not just
    the caller's own view of one.
    """
    price_date = date.today()
    result = fetch_day(price_date, notifier=get_notifier(settings))
    wanted = set(held_isins(connection))
    stored = upsert_prices(connection, [p for p in result.prices if p.isin in wanted])
    missing = missing_prices(connection, sorted(wanted), price_date)

    return {
        "prices_stored": stored,
        "missing_isins": missing,
        "price_date": price_date,
    }


def _run_snapshots(
    connection: Any, start: date, end: date, notifier: Notifier
) -> dict[str, Any]:
    """The rebuild job. The ONLY code path allowed to write ``portfolio_snapshot``
    (docs/ENGINE_SPEC.md section 8) -- everywhere else, including ``_fy_xirr`` and
    ``_period_xirr``'s live fallback, only ever reads it.

    Two steps, both resumable so a timeout mid-backfill does not mean starting over:

    1. Price step -- mirrors ``refresh_prices``'s body, looped over ``[start, end]``
       via ``backfill_days`` (which itself clamps to ``NSE_BHAVCOPY_EARLIEST``, the
       archive's real floor) rather than the ledger's. ``price_dates_present`` skips
       dates already stored.
    2. Snapshot step -- for every investor, for BOTH ``advised_only`` values (docs/
       ENGINE_SPEC.md section 8 / this table's own comment: the two are genuinely
       different ledgers, not a display filter), compute and upsert one snapshot per
       trading day the investor could have held something on. Per-investor start is
       clamped again to that investor's own earliest transaction -- a client onboarded
       in 2025 gets no rows manufactured for 2024. ``MissingPriceError`` is caught PER
       DATE, exactly like ``_fy_xirr`` does today: logged, skipped, never aborts the
       rest of the run.
    """
    already_priced = price_dates_present(connection, start, end)
    price_results = backfill_days(
        start, end, already_present=already_priced, notifier=notifier
    )
    wanted = set(held_isins(connection))
    price_dates_fetched = 0
    for result in price_results:
        stored = upsert_prices(connection, [p for p in result.prices if p.isin in wanted])
        if stored:
            price_dates_fetched += 1

    snapshots_written = 0
    skipped: list[dict[str, Any]] = []
    for investor_id in list_investor_ids(connection):
        for advised_only in (False, True):
            transactions = load_transactions(
                connection, investor_id=investor_id, advised_only=advised_only
            )
            if not transactions:
                continue
            earliest_txn = min(t.txn_date for t in transactions)
            investor_start = max(start, NSE_BHAVCOPY_EARLIEST, earliest_txn)
            if investor_start > end:
                continue

            already_snapped = snapshots.snapshot_dates_present(
                connection, investor_id, advised_only, investor_start, end
            )
            for on_date in trading_days(investor_start, end):
                if on_date in already_snapped:
                    continue
                isins = [h.isin for h in compute_holdings(transactions, on_date)]
                day_prices = latest_prices(connection, isins, on_date)
                try:
                    snap = compute_snapshot(transactions, day_prices, on_date)
                except MissingPriceError as exc:
                    logger.warning(
                        "snapshot omitted: no usable price on/before %s for %s "
                        "(investor_id=%s advised_only=%s)",
                        on_date, exc.isins, investor_id, advised_only,
                        exc_info=True,
                    )
                    skipped.append(
                        {
                            "investor_id": investor_id,
                            "advised_only": advised_only,
                            "as_of": on_date,
                            "isins": exc.isins,
                        }
                    )
                    continue
                snapshots.upsert_snapshot(connection, investor_id, advised_only, snap)
                snapshots_written += 1

    return {
        "snapshots_written": snapshots_written,
        "price_dates_fetched": price_dates_fetched,
        "skipped_missing_price": skipped,
    }


@router.post("/ops/snapshots/run", response_model=SnapshotRunResponse)
def run_snapshots(
    start: date | None = None,
    end: date | None = None,
    connection: Any = Depends(get_conn),
    _current_user: dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Persist ``portfolio_snapshot`` rows via ``_run_snapshots``.

    No ``start``/``end`` -> both default to today: the cheap daily catch-up, run
    alongside ``/ops/prices/refresh``. A wider range is a resumable historical backfill,
    fetching any bhavcopy it needs first. Auth-gated like ``/ops/prices/refresh``: this
    writes stored totals for every investor, not just the caller's own view of one.
    """
    resolved_start = start or date.today()
    resolved_end = end or date.today()
    return _run_snapshots(
        connection, resolved_start, resolved_end, get_notifier(settings)
    )
