"""GET /investors/{id}/performance, POST /ops/prices/refresh, POST /ops/snapshots/run.

``absolute_return`` is computed via ``compute_net_invested``/``compute_absolute_return``
(app/engine/returns.py), per the ``net_invested`` definition in ENGINE_SPEC section 5:
net lifetime cash contributed (BUY/IPO_ALLOT outflows minus SELL/BUYBACK inflows, across
the whole ledger). It is ``None`` when ``net_invested <= 0`` -- heavy net withdrawals, or
even a full exit at a profit, can drive lifetime contributions to zero or negative.

``cagr`` stays ``None`` permanently, by decision, not by omission: section 5 scopes CAGR
to per-holding only (its lump-sum assumption breaks for a portfolio's staggered dated
contributions), and there is no portfolio-level case that is both valid and not already
covered by ``xirr_all``.

``benchmark`` (section 6) is computed only when the ``benchmark`` query param is
supplied -- never by default, given the extra external-data dependency. MVP supports
``NIFTY50_TRI`` only (``app.prices.index_sources``); ``SENSEX_TRI`` is a valid contract
enum value with no reliable free, machine-fetchable source behind it yet, so it is
rejected with an explicit 400 rather than silently returning null or a guessed number --
see ``_benchmark``.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app import securities
from app.auth.dependencies import get_current_user, require_owned_investor
from app.config import Settings, get_settings
from app.database import get_conn, money, rate
from app.db import snapshots
from app.db.index_levels import get_index_levels
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
from app.engine.benchmark import compute_benchmark, required_index_dates
from app.engine.contribution import compute_contribution
from app.engine.errors import MissingIndexLevelError, MissingPriceError, NegativeHoldingError
from app.engine.holdings import MAX_PRICE_STALENESS_DAYS, compute_holdings
from app.engine.returns import compute_absolute_return, compute_net_invested
from app.engine.snapshot import compute_snapshot
from app.engine.twrr import compute_twrr
from app.engine.types import ZERO, Snapshot, Transaction
from app.engine.xirr import (
    compute_period_xirr,
    compute_xirr,
    compute_xirr_holdings,
    financial_year_start,
    period_warning,
    years_before,
)
from app.prices.alerts import Notifier, get_notifier
from app.prices.index_sources import (
    NIFTY_TRI_INDEX_NAME,
    IndexSourceFetchFailed,
    IndexSourceFormatError,
    fetch_and_store,
)
from app.prices.pipe import NSE_BHAVCOPY_EARLIEST, backfill_days, fetch_day, trading_days
from app.schemas.analytical import (
    ContributionResponse,
    PerformanceResponse,
    PriceRefreshResponse,
    SnapshotOut,
    SnapshotRunResponse,
)

#: The only benchmark names the contract declares (contracts/openapi.yaml). Kept as a
#: literal here so FastAPI 422s on anything else before ``performance`` even runs --
#: SENSEX_TRI still reaches the handler (it IS a valid enum member), where it gets a
#: deliberate 400 rather than the generic validation error.
BenchmarkName = Literal["NIFTY50_TRI", "SENSEX_TRI"]

logger = logging.getLogger("app")

router = APIRouter(tags=["derived", "ops"])


def _window_xirr(
    request: Request,
    connection: Any,
    investor_id: str,
    transactions: list[Transaction],
    prices: dict[str, Decimal],
    label: str,
    target_start: date,
    earliest_txn: date | None,
    as_of: date,
    advised_only: bool,
) -> tuple[Decimal | None, date | None]:
    """Shared opening-value resolution for every trailing/period XIRR window --
    ``fy_xirr``, ``xirr_1y``, ``xirr_3y``, ``xirr_5y``, and the adviser-onboarding
    ``period_xirr`` all call this with a different ``target_start``. Generalizes what
    used to be two near-identical private helpers (``_fy_xirr``/``_period_xirr``).

    Returns ``(xirr, actual_start_used)``. ``actual_start_used`` is the date the opening
    value actually came from -- almost always ``target_start`` itself, but occasionally
    a few days earlier when a persisted snapshot stood in for it (see step 2). Callers
    that disclose their window's start date (``period_xirr``'s ``period_start``) should
    use it; callers that don't (``fy_xirr`` and the three new fixed-calendar windows,
    matching ``fy_xirr``'s existing precedent of never disclosing its own 1-April anchor)
    simply discard it.

    Step 1 -- history guard. If the investor's earliest transaction postdates
    ``target_start`` (or there are no transactions at all), the window predates the
    portfolio's own history: ``compute_holdings`` at ``target_start`` would legitimately
    be empty, ``opening_value`` would legitimately be 0, and ``compute_period_xirr``
    would then fold in *every* transaction the investor has ever made -- numerically
    ``xirr_all``, silently mislabeled with this window's name. Blank the window instead
    of computing a number under the wrong label -- the same "never guess a start date"
    discipline this function's opening-value resolution applies below, just applied to
    whether the window applies at all.

    Step 2 -- a persisted snapshot on or before ``target_start``
    (``app.db.snapshots.get_snapshot_on_or_before``, Phase 2 Session 1's table) is the
    fast path, skipping live recomputation entirely. Its own ``as_of`` -- not
    ``target_start`` -- becomes ``compute_period_xirr``'s ``start_date``: using
    ``target_start`` as the label while the value actually came from a few days earlier
    would silently drop every transaction dated in that gap from both the opening value
    and the flow list, the same failure class ``compute_period_xirr``'s docstring
    documents for mid-period deposits (inflates on a BUY in the gap, deflates on a
    SELL), just scoped to the gap instead of the whole period. A snapshot older than
    ``MAX_PRICE_STALENESS_DAYS`` (``app.engine.holdings`` -- the codebase's existing
    answer to "how old can a substituted value be and still count as current," reused
    here rather than inventing a new tolerance) is treated as a miss: a sparse backfill
    gap should fall through to a precise live value, not silently widen the window.

    Step 3 -- on a miss, the live fallback this function has always used: build holdings
    and prices AT ``target_start``, ``compute_snapshot`` there. ``MissingPriceError`` is
    caught HERE ONLY, never re-raised, so the rest of the ``/performance`` response
    stays valid -- logged with structured context, turned into ``(None, None)``.
    """
    if earliest_txn is None or earliest_txn > target_start:
        return None, None

    persisted = snapshots.get_snapshot_on_or_before(
        connection, investor_id, target_start, advised_only
    )
    if persisted is not None and (target_start - persisted.as_of).days <= MAX_PRICE_STALENESS_DAYS:
        actual_start = persisted.as_of
        opening_value = persisted.market_value
    else:
        window_isins = [h.isin for h in compute_holdings(transactions, target_start)]
        window_prices = latest_prices(connection, window_isins, target_start)
        try:
            opening_snapshot = compute_snapshot(transactions, window_prices, target_start)
        except MissingPriceError as exc:
            logger.warning(
                "%s omitted: no usable price on/before %s for %s "
                "(investor_id=%s request_id=%s)",
                label, target_start, exc.isins, investor_id,
                getattr(getattr(request, "state", None), "request_id", None),
                exc_info=True,
            )
            return None, None
        actual_start = target_start
        opening_value = opening_snapshot.market_value

    xirr = compute_period_xirr(transactions, prices, actual_start, opening_value, as_of)
    return xirr, actual_start


def _window_twrr(
    connection: Any,
    investor_id: str,
    transactions: list[Transaction],
    target_start: date,
    earliest_txn: date | None,
    as_of: date,
    advised_only: bool,
    closing_snapshot: Snapshot,
) -> Decimal | None:
    """Shared snapshot-chain resolution for every TWRR window -- ``fy_twrr``,
    ``twrr_1y``, ``twrr_3y``, ``twrr_5y`` all call this with a different
    ``target_start``. Mirrors ``_window_xirr``'s opening-value resolution, but TWRR
    needs the FULL sub-period snapshot series between the window's start and ``as_of``,
    not just the two endpoints -- ``app.engine.twrr.compute_twrr`` chains between
    consecutive rows (docs/ENGINE_SPEC.md section 5).

    Step 1 -- the same history guard ``_window_xirr`` uses: a window that predates the
    investor's earliest transaction blanks to ``None`` rather than silently computing a
    chain over an empty portfolio.

    Step 2 -- the anchor snapshot: the nearest persisted row on or before
    ``target_start`` (``get_snapshot_on_or_before``), same ``MAX_PRICE_STALENESS_DAYS``
    tolerance ``_window_xirr``'s opening-value resolution uses, for the same reason -- a
    sparse backfill gap should blank the window rather than silently widen it. Unlike
    ``_window_xirr``, there is no live fallback here: a missing anchor means there is
    nothing to chain FROM, and a single live ``compute_snapshot`` at ``target_start``
    would be one point, not a series.

    Step 3 -- the chain: every persisted row from the anchor's own ``as_of`` through
    ``as_of`` (``list_snapshots_range``). If the series doesn't already reach exactly
    ``as_of`` (the common case -- today's daily snapshot job hasn't run yet), the
    caller's already-computed LIVE ``closing_snapshot`` is appended, so TWRR stays "as
    of today" like every other figure on this response rather than silently trailing by
    however many days the backfill lags. ``compute_twrr`` consumes whatever consecutive
    rows result, chaining across any interior gap as one wider sub-period rather than
    filling or interpolating it (see that function's own docstring).
    """
    if earliest_txn is None or earliest_txn > target_start:
        return None

    anchor = snapshots.get_snapshot_on_or_before(
        connection, investor_id, target_start, advised_only
    )
    if anchor is None or (target_start - anchor.as_of).days > MAX_PRICE_STALENESS_DAYS:
        return None

    chain = snapshots.list_snapshots_range(
        connection, investor_id, advised_only, anchor.as_of, as_of
    )
    if not chain or chain[-1].as_of != as_of:
        chain = [*chain, closing_snapshot]

    return compute_twrr(chain, transactions)


def _benchmark(
    request: Request,
    connection: Any,
    investor_id: str,
    transactions: list[Transaction],
    name: BenchmarkName,
    as_of: date,
) -> dict[str, Any] | None:
    """``benchmark``'s value, or ``None`` -- section 6's cash-flow replication, computed
    only when a caller asked for it (the ``benchmark`` query param).

    ``SENSEX_TRI`` is a valid contract enum member with no reliable free, machine-
    fetchable source behind it (confirmed in Plan Mode -- BSE's own archive is a JS-only
    page, Asia Index has no documented API, third-party aggregators are unfit as a
    system-of-record source). Rejected here with an explicit 400, BEFORE any database
    access, rather than this function ever guessing at a number or silently returning
    null for it -- a caller asking for a benchmark that does not exist yet needs to be
    told that plainly, unlike a caller who asked for nothing (the ``None`` early return
    in ``performance`` below) or one whose data genuinely has a gap (the
    ``MissingIndexLevelError`` catch below, which DOES degrade to null, because in that
    case the rest of the response is still valid and the gap is a data problem, not a
    "this isn't built" problem).

    On a cache miss, one live ``fetch_and_store`` covers the whole date range needed in
    a single call (the source answers a range, not one day at a time) -- then the same
    read is retried. Both ``MissingIndexLevelError`` (a genuine data gap) and a live
    fetch failure (``IndexSourceFetchFailed``/``IndexSourceFormatError`` -- the external
    source unreachable, or its undocumented response shape having changed) are caught
    HERE ONLY, exactly like ``_window_xirr`` catches ``MissingPriceError``:
    logged with structured context, turned into ``None`` so the rest of the performance
    response stays valid. An optional field's external dependency hiccupping must never
    500 the whole request.
    """
    if name == "SENSEX_TRI":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "SENSEX_TRI is not yet available: no reliable public TRI data source exists",
        )

    request_id = getattr(getattr(request, "state", None), "request_id", None)
    dates_needed = required_index_dates(transactions, as_of)
    levels = get_index_levels(connection, NIFTY_TRI_INDEX_NAME, dates_needed)
    if any(d not in levels for d in dates_needed):
        try:
            fetch_and_store(connection, min(dates_needed), max(dates_needed))
        except (IndexSourceFetchFailed, IndexSourceFormatError) as exc:
            logger.warning(
                "benchmark omitted: %s fetch failed for %s (investor_id=%s "
                "request_id=%s): %s",
                name, dates_needed, investor_id, request_id, exc,
                exc_info=True,
            )
            return None
        levels = get_index_levels(connection, NIFTY_TRI_INDEX_NAME, dates_needed)

    try:
        result = compute_benchmark(transactions, levels, as_of, name)
    except MissingIndexLevelError as exc:
        logger.warning(
            "benchmark omitted: no usable %s level for %s "
            "(investor_id=%s request_id=%s)",
            name, exc.dates, investor_id, request_id,
            exc_info=True,
        )
        return None

    return {
        "name": result.name,
        "xirr": rate(result.xirr),
        "terminal_value": money(result.terminal_value),
    }


@router.get(
    "/investors/{investor_id}/performance",
    response_model=PerformanceResponse,
    dependencies=[Depends(require_owned_investor)],
)
def performance(
    request: Request,
    investor_id: str,
    as_of: date | None = None,
    advised_only: bool = False,
    benchmark: BenchmarkName | None = None,
    connection: Any = Depends(get_conn),
) -> dict[str, Any]:
    """Both XIRR variants, always together -- CLAUDE.md: reporting one alone leaves a
    choice about which number flatters the portfolio, and that choice should not exist.
    Four fixed-calendar trailing windows sit beside them -- ``fy_xirr`` (financial-year-
    to-date), ``xirr_1y``, ``xirr_3y``, ``xirr_5y`` -- each independently omittable when
    the portfolio's history doesn't reach back that far or no usable opening price
    exists; see ``_window_xirr``. ``period_xirr`` sits beside those, scoped to the
    investor's stored ``onboarding_date`` (the adviser-onboarding case) -- same
    resolution, different start date.

    ``fy_twrr``/``twrr_1y``/``twrr_3y``/``twrr_5y`` (docs/ENGINE_SPEC.md section 5) sit
    beside their xirr counterparts, same target_start dates, never shown alone: TWRR
    chains the persisted daily snapshot series to measure the adviser (strips out when
    money moved), where XIRR measures the client's actual experience -- see
    ``_window_twrr``.

    ``advised_only`` restricts the ledger to accounts flagged ``is_advised`` (docs/
    DATA_MODEL.md, contracts/openapi.yaml), so a SEBI-registered adviser can report on
    the mandated account only.

    ``benchmark`` (section 6) is ``None`` unless a caller asks for it -- see
    ``_benchmark`` for the cash-flow replication and why ``SENSEX_TRI`` 400s.
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

    # Fixed-calendar trailing windows -- FY-to-date plus 1/3/5 calendar years back.
    # years_before is real date arithmetic (Feb-29-aware), not days=365*n, which would
    # drift by a day every leap year. earliest_txn is computed once and shared across
    # all five _window_xirr calls below (including period_xirr) rather than recomputed
    # per window.
    earliest_txn = min((t.txn_date for t in transactions), default=None)
    fy_xirr, _ = _window_xirr(
        request, connection, investor_id, transactions, prices,
        "fy_xirr", financial_year_start(resolved_as_of), earliest_txn,
        resolved_as_of, advised_only,
    )
    xirr_1y, _ = _window_xirr(
        request, connection, investor_id, transactions, prices,
        "xirr_1y", years_before(resolved_as_of, 1), earliest_txn,
        resolved_as_of, advised_only,
    )
    xirr_3y, _ = _window_xirr(
        request, connection, investor_id, transactions, prices,
        "xirr_3y", years_before(resolved_as_of, 3), earliest_txn,
        resolved_as_of, advised_only,
    )
    xirr_5y, _ = _window_xirr(
        request, connection, investor_id, transactions, prices,
        "xirr_5y", years_before(resolved_as_of, 5), earliest_txn,
        resolved_as_of, advised_only,
    )

    # TWRR windows (docs/ENGINE_SPEC.md section 5) -- the adviser-skill companion to the
    # four XIRR windows above, same target_start dates, never shown alone.
    fy_twrr = _window_twrr(
        connection, investor_id, transactions, financial_year_start(resolved_as_of),
        earliest_txn, resolved_as_of, advised_only, snapshot,
    )
    twrr_1y = _window_twrr(
        connection, investor_id, transactions, years_before(resolved_as_of, 1),
        earliest_txn, resolved_as_of, advised_only, snapshot,
    )
    twrr_3y = _window_twrr(
        connection, investor_id, transactions, years_before(resolved_as_of, 3),
        earliest_txn, resolved_as_of, advised_only, snapshot,
    )
    twrr_5y = _window_twrr(
        connection, investor_id, transactions, years_before(resolved_as_of, 5),
        earliest_txn, resolved_as_of, advised_only, snapshot,
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
    # shown. period_start echoes _window_xirr's actual_start_used -- almost always
    # onboarding_date itself, occasionally a few days earlier when only a nearby
    # persisted snapshot existed, always the honest date the opening value came from.
    onboarding_date = get_investor_onboarding_date(connection, investor_id)
    period_xirr_value: Decimal | None = None
    period_start: date | None = None
    period_warn: str | None = None
    if onboarding_date is not None and onboarding_date <= resolved_as_of:
        period_xirr_value, actual_start = _window_xirr(
            request, connection, investor_id, transactions, prices,
            "period_xirr", onboarding_date, earliest_txn, resolved_as_of, advised_only,
        )
        if period_xirr_value is not None:
            period_start = actual_start
            period_warn = period_warning(period_start, resolved_as_of)

    # benchmark (section 6): computed only when asked for -- see _benchmark's docstring
    # for why SENSEX_TRI 400s here rather than degrading to null like a genuine data gap.
    benchmark_out: dict[str, Any] | None = None
    if benchmark is not None:
        benchmark_out = _benchmark(
            request, connection, investor_id, transactions, benchmark, resolved_as_of
        )

    return {
        "as_of": resolved_as_of,
        "xirr_all": rate(xirr_all),
        "xirr_holdings": rate(xirr_holdings),
        "fy_xirr": rate(fy_xirr),
        "xirr_1y": rate(xirr_1y),
        "xirr_3y": rate(xirr_3y),
        "xirr_5y": rate(xirr_5y),
        "fy_twrr": rate(fy_twrr),
        "twrr_1y": rate(twrr_1y),
        "twrr_3y": rate(twrr_3y),
        "twrr_5y": rate(twrr_5y),
        "period_xirr": rate(period_xirr_value),
        "period_start": period_start,
        "cagr": None,  # permanent, by decision -- see module docstring, section 5
        "absolute_return": rate(absolute_return),
        "invested": money(snapshot.invested),
        "market_value": money(snapshot.market_value),
        "unrealised": money(snapshot.unrealised),
        "realised_to_date": money(snapshot.realised_to_date),
        "benchmark": benchmark_out,
        "warning": period_warn,
    }


def _snapshot_row(snapshot: Snapshot) -> dict[str, Any]:
    """One persisted row as JSON. Pure shaping, no computation -- the same split
    ``holdings.py``'s ``_row``/``_totals`` and ``reconcile.py``'s ``_discrepancy_row``
    use, so it is testable without a database."""
    return {
        "as_of": snapshot.as_of,
        "invested": money(snapshot.invested),
        "market_value": money(snapshot.market_value),
        "unrealised": money(snapshot.unrealised),
        "realised_to_date": money(snapshot.realised_to_date),
    }


@router.get(
    "/investors/{investor_id}/snapshots",
    response_model=list[SnapshotOut],
    dependencies=[Depends(require_owned_investor)],
)
def list_snapshots(
    investor_id: str,
    start: date,
    end: date,
    advised_only: bool = False,
    connection: Any = Depends(get_conn),
) -> list[dict[str, Any]]:
    """Persisted ``portfolio_snapshot`` rows for ``[start, end]`` -- a plain read
    against ``app.db.snapshots.list_snapshots_range``, never a live
    ``compute_snapshot()`` replay across the range (docs/ENGINE_SPEC.md section 8; the
    entire reason the table exists is to make this endpoint cheap). Powers the
    Dashboard's historical-value chart (docs/trackr_plus_phase2_overview.md section 6).

    A date with no persisted row -- before backfill's earliest reachable date, or a gap
    from a run that hit ``MissingPriceError`` -- is simply absent from the returned
    array. Never filled, never interpolated: the caller renders that as an honest gap,
    the same convention ``UnpricedBanner``/``MissingPriceNotice`` use on the frontend.

    ``advised_only`` selects the same independent series ``/performance`` and
    ``/ops/snapshots/run`` use -- accounts flagged ``is_advised`` were snapshotted as a
    genuinely different ledger, not filtered after the fact.
    """
    if start > end:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "start must be on or before end"
        )
    rows = snapshots.list_snapshots_range(connection, investor_id, advised_only, start, end)
    return [_snapshot_row(row) for row in rows]


@router.get(
    "/investors/{investor_id}/contribution",
    response_model=ContributionResponse,
    dependencies=[Depends(require_owned_investor)],
)
def contribution(
    investor_id: str,
    period_start: date,
    as_of: date | None = None,
    advised_only: bool = False,
    connection: Any = Depends(get_conn),
) -> dict[str, Any]:
    """Per-ISIN rupee attribution of the portfolio's gain over
    ``(period_start, as_of]`` -- docs/ENGINE_SPEC.md section 10, the first
    Intelligence-layer feature per ``docs/PRODUCT_VISION.md``.

    Unlike the XIRR/TWRR windows above, there is no persisted-snapshot fast path here
    (``_window_xirr``'s step 2): ``portfolio_snapshot`` carries only portfolio-level
    totals, not a per-ISIN breakdown, and this needs the latter at BOTH ``period_start``
    and ``as_of``. So both ends are always resolved live, the same way
    ``_window_xirr``'s step 3 fallback works -- ``compute_holdings`` at that date against
    prices looked up for it -- via ``compute_contribution`` itself, which raises
    ``MissingPriceError`` (caught by the global handler, 409) naming any held ISIN
    missing a price at either end, never substituting zero.

    ``period_start`` has no default the way ``fy_xirr``'s 1-April anchor does: the
    caller states the window explicitly, same as ``/snapshots``' ``start``/``end``.
    """
    resolved_as_of = as_of or date.today()
    if period_start > resolved_as_of:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "period_start must be on or before as_of"
        )

    transactions = load_transactions(
        connection, investor_id=investor_id, advised_only=advised_only
    )

    start_isins = [h.isin for h in compute_holdings(transactions, period_start)]
    start_prices = latest_prices(connection, start_isins, period_start)
    end_isins = [h.isin for h in compute_holdings(transactions, resolved_as_of)]
    end_prices = latest_prices(connection, end_isins, resolved_as_of)

    results = compute_contribution(
        transactions, start_prices, end_prices, period_start, resolved_as_of
    )
    meta = securities.lookup(connection, [c.isin for c in results])
    total_gain = sum((c.gain for c in results), ZERO)

    return {
        "as_of": resolved_as_of,
        "period_start": period_start,
        "total_gain": money(total_gain),
        "contributions": sorted(
            (
                {
                    "isin": c.isin,
                    "symbol": securities.describe(meta, c.isin)["symbol"],
                    "start_value": money(c.start_value),
                    "end_value": money(c.end_value),
                    "net_flow": money(c.net_flow),
                    "gain": money(c.gain),
                    "pct_of_total": rate(c.pct_of_total),
                }
                for c in results
            ),
            key=lambda row: Decimal(row["gain"]),
            reverse=True,
        ),
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
    (docs/ENGINE_SPEC.md section 8) -- everywhere else, including ``_window_xirr``'s
    live fallback, only ever reads it.

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
       DATE, exactly like ``_window_xirr`` does today: logged, skipped, never aborts the
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
                try:
                    isins = [h.isin for h in compute_holdings(transactions, on_date)]
                    day_prices = latest_prices(connection, isins, on_date)
                    snap = compute_snapshot(transactions, day_prices, on_date)
                except (MissingPriceError, NegativeHoldingError) as exc:
                    logger.warning(
                        "snapshot omitted: %s on/before %s (investor_id=%s advised_only=%s)",
                        exc, on_date, investor_id, advised_only,
                        exc_info=True,
                    )
                    skipped.append(
                        {
                            "investor_id": investor_id,
                            "advised_only": advised_only,
                            "as_of": on_date,
                            "isins": getattr(exc, "isins", None) or [getattr(exc, "isin", None)],
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
