"""GET /investors/{id}/analytics -- the portfolio analytics surface.

READ-ONLY AND CACHE-BACKED. This endpoint never fetches from a third party. Prices come
from the bhavcopy pipe, fundamentals from whatever the cron has already stored, and
staleness is REPORTED rather than waited on. That is what keeps the page fast regardless
of what Yahoo is doing, and it is the difference between "analytics" and "a proxy".

Layering, which the lint rules enforce:
    app.engine      -- holdings, cost basis, XIRR. Decimal. Never recomputed here.
    app.analytics   -- statistics. float. Pure functions over materialised data.
    this module     -- reads the db, calls both, converts once at the edge.

Money is Decimal from the engine to the wire, where it becomes a string. Statistics are
floats and never become money: the rupee VaR below is the one crossing point, and it goes
through Decimal(str(ratio)) explicitly.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query

from app import securities
from app.analytics import composition, factors, risk, series, verdict
from app.analytics import fundamentals as fagg
from app.auth.dependencies import require_owned_investor
from app.auth.ops import require_cron_secret, require_ops_key
from app.config import Settings, get_settings
from app.database import get_conn
from app.db.fundamentals import latest as latest_fundamentals
from app.db.index_levels import get_index_levels
from app.db.prices import held_isins, latest_prices, price_series
from app.db.repository import load_transactions
from app.db.universe import DEFAULT_UNIVERSE, current_universe_isins
from app.engine.holdings import compute_holdings_partitioned
from app.prices.fundamentals import DEFAULT_BATCH_LIMIT, refresh_stale
from app.prices.index_sources import NIFTY_TRI_INDEX_NAME
from app.schemas.analytics import AnalyticsResponse, FundamentalsRefreshResponse

logger = logging.getLogger("routers.analytics")

router = APIRouter(tags=["analytics"])

#: How far back the price series is pulled. Five years plus a margin, because the 12-1
#: momentum construction needs a full year BEFORE the window it reports on.
_LOOKBACK_DAYS = 366 * 6

_FACTOR_KEYS = ("momentum", "value", "quality", "low_volatility")


def _money(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _num(value: Decimal | None) -> float | None:
    """A stored ratio -> a JSON number. Ratios are not money; see the module docstring."""
    return None if value is None else float(value)


def _pct(part: Decimal, whole: Decimal) -> float:
    return float(part / whole * 100) if whole else 0.0


@router.get(
    "/investors/{investor_id}/analytics",
    response_model=AnalyticsResponse,
    dependencies=[Depends(require_owned_investor)],
)
def analytics(
    investor_id: str,
    as_of: date | None = None,
    benchmark: str = NIFTY_TRI_INDEX_NAME,
    advised_only: bool = False,
    universe: str = DEFAULT_UNIVERSE,
    connection: Any = Depends(get_conn),
) -> dict[str, Any]:
    """Everything the analytics screen renders, from one replay of the ledger."""
    on = as_of or date.today()
    transactions = load_transactions(connection, investor_id, advised_only=advised_only)

    # Partitioned, not raw: a segment that does not reconcile is carried out as a named
    # exception rather than silently producing a negative holding.
    holdings, skipped = compute_holdings_partitioned(transactions, on)
    holdings = [h for h in holdings if h.quantity > 0]
    isins = [h.isin for h in holdings]
    meta = securities.lookup(connection, isins) if isins else {}

    prices = latest_prices(connection, isins, on) if isins else {}
    start = on - timedelta(days=_LOOKBACK_DAYS)
    history = price_series(connection, isins, start, on) if isins else {}
    fundamentals = latest_fundamentals(connection, isins, on) if isins else {}

    # --- positions, and the unpriced exception -----------------------------------------
    positions: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    total_value = Decimal(0)
    total_invested = Decimal(0)

    for holding in holdings:
        info = meta.get(holding.isin, {})
        price = prices.get(holding.isin)
        if price is None:
            # CLAUDE.md rule 4: never valued at zero. Carried out of every denominator.
            unresolved.append(
                {
                    "isin": holding.isin,
                    "symbol": info.get("symbol"),
                    "name": info.get("name"),
                    "quantity": str(holding.quantity),
                    "invested": str(holding.invested),
                    "reason": "No price on or before this date within the staleness window.",
                }
            )
            continue
        value = (holding.quantity * price).quantize(Decimal("0.01"))
        total_value += value
        total_invested += holding.invested
        positions.append(
            {
                "isin": holding.isin,
                "symbol": info.get("symbol"),
                "name": info.get("name") or info.get("symbol"),
                "quantity": str(holding.quantity),
                "invested": str(holding.invested),
                "avg_cost": str(holding.avg_cost),
                "last_price": str(price),
                "market_value": value,
                "unrealised": value - holding.invested,
                "sector": info.get("sector"),
                "market_cap_bucket": info.get("market_cap_bucket"),
                "_holding": holding,
            }
        )

    for position in positions:
        position["weight"] = _pct(position["market_value"], total_value)
        invested = Decimal(position["invested"])
        position["unrealised_pct"] = (
            float(position["unrealised"] / invested * 100) if invested else None
        )

    weights = {p["isin"]: p["weight"] for p in positions}
    labels = {p["isin"]: (p["symbol"] or p["isin"]) for p in positions}

    # --- price series, aligned ----------------------------------------------------------
    #
    # The benchmark is intersected rather than required outright. The TRI feed routinely
    # lags the bhavcopy by days, and dropping the comparison entirely for that -- which an
    # all-or-nothing rule does -- loses beta, relative return and a fifth of the health
    # grade over a gap that self-heals. Intersecting keeps BOTH SIDES ON EXACTLY THE SAME
    # DATES, which is the property that actually matters; the window just ends earlier, and
    # `observations` reports how many sessions it really covers.
    shared_dates, aligned = series.align(history, [p["isin"] for p in positions])
    bench_by_date = _benchmark_levels(connection, benchmark, shared_dates)
    if bench_by_date:
        comparable = [d for d in shared_dates if d in bench_by_date]
        if len(comparable) >= 30:
            shared_dates = comparable
            _, aligned = series.align(
                {i: [(d, c) for d, c in rows if d in bench_by_date] for i, rows in history.items()},
                [p["isin"] for p in positions],
            )
    bench_levels = [float(bench_by_date[d]) for d in shared_dates] if bench_by_date else None

    portfolio_levels = series.portfolio_series(aligned, weights) if aligned else []
    risk_windows = (
        risk.windows(portfolio_levels, bench_levels) if len(portfolio_levels) > 2 else {}
    )

    # --- capital state, trend, per-holding returns ---------------------------------------
    buckets = dict.fromkeys(("STRONG", "WEAKENING", "CAUTION", "RECOVERY"), Decimal(0))
    for position in positions:
        values = [float(c) for _, c in history.get(position["isin"], [])]
        dma50 = composition.moving_average(values, 50) if values else None
        direction = composition.trend(float(position["last_price"]), dma50)
        state = composition.capital_state(position["unrealised"] >= 0, direction)
        position["trend"] = direction
        position["capital_state"] = state
        buckets[state] += position["market_value"]
        position["returns"] = {
            label: _window_return(values, days)
            for label, days in (
                ("1w", 5), ("1m", 21), ("3m", 63),
                ("1y", 252), ("3y", 756), ("5y", 1260),
            )
        }

    # --- fundamentals on to positions ---------------------------------------------------
    for position in positions:
        row = fundamentals.get(position["isin"])
        if row is None:
            continue
        for field in (
            "pe", "pb", "roe", "net_margin", "debt_to_equity",
            "interest_cover", "dividend_yield", "sales_growth_1y", "profit_growth_1y",
        ):
            position[field] = _num(getattr(row, field))
        position["roe_basis"] = row.roe_basis
        position["fundamentals_as_of"] = row.as_of

    factor_scores = _factor_scores(connection, positions, weights, universe, on, history)
    for position in positions:
        position["factors"] = {
            key: factor_scores["holdings"].get(key, {}).get(position["isin"])
            for key in _FACTOR_KEYS
        }

    # --- aggregates ---------------------------------------------------------------------
    pe_agg = fagg.harmonic_mean([(p["weight"], p.get("pe")) for p in positions])
    pb_agg = fagg.harmonic_mean([(p["weight"], p.get("pb")) for p in positions])
    dy_agg = fagg.weighted_mean([(p["weight"], p.get("dividend_yield")) for p in positions])

    one_year = risk_windows.get("1y")
    relative_pp = None
    if one_year and one_year.cum_return is not None and one_year.bench_cum_return is not None:
        relative_pp = (one_year.cum_return - one_year.bench_cum_return) * 100

    bs_pairs = [
        (p["weight"], verdict.balance_sheet_score(p.get("debt_to_equity"), p.get("interest_cover")))
        for p in positions
    ]
    bs_used = [(w, s) for w, s in bs_pairs if s is not None]
    bs_weight = sum(w for w, _ in bs_used)
    balance_sheet = (
        sum(w * s for w, s in bs_used) / bs_weight if bs_weight else None
    )

    # Computed ONCE, here. It feeds both the health grade and the `derived` block, and the
    # frontend reads it rather than recomputing its own -- see DerivedOut.
    effective_n = composition.effective_holdings([p["weight"] for p in positions])

    health = verdict.compute_health(
        factor_scores=[factor_scores["portfolio"][k].score for k in _FACTOR_KEYS],
        effective_n=effective_n,
        balance_sheet=balance_sheet,
        balance_sheet_coverage=bs_weight,
        relative_1y_pp=relative_pp,
    )

    sector_alloc = composition.allocation([(p.get("sector"), p["market_value"]) for p in positions])
    cap_alloc = composition.allocation(
        [(p.get("market_cap_bucket"), p["market_value"]) for p in positions]
    )

    gains = sorted(
        (p for p in positions if p["unrealised"] > 0), key=lambda p: -p["unrealised"]
    )
    total_gain = sum(p["unrealised"] for p in gains)
    gain_share = (
        float(sum(p["unrealised"] for p in gains[:2]) / total_gain * 100)
        if total_gain > 0 and len(gains) >= 2
        else None
    )

    insights = verdict.build_insights(
        top_weights=[
            (labels[p["isin"]], p["weight"])
            for p in sorted(positions, key=lambda p: -p["weight"])
        ],
        gain_share_top2=gain_share,
        relative_1y_pp=relative_pp,
        beta=one_year.beta if one_year else None,
        quality_leaders=[labels[p["isin"]] for p in positions if (p.get("roe") or 0) > 0.30],
        top_sector=(sector_alloc[0]["label"], sector_alloc[0]["pct"]) if sector_alloc else None,
    )

    day_change, day_change_pct = _day_change(connection, positions, on)

    # --- derived scalars ----------------------------------------------------------------
    #
    # Everything below was previously recomputed by the browser from the fields already in
    # this payload. The two implementations agreed -- see DerivedOut, which says so
    # precisely -- but they agreed because of a precondition neither one stated. Computing
    # it once here is what stops that being load-bearing.
    growth = _growth_payload(shared_dates, portfolio_levels, bench_levels)
    growth_delta = None
    if growth and growth.get("benchmark"):
        growth_delta = _money(
            Decimal(growth["portfolio"][-1]) - Decimal(growth["benchmark"][-1])
        )

    # `bench_volatility` is falsy-checked rather than None-checked on purpose: a zero
    # benchmark volatility is not a 1.0 ratio, it is an unusable denominator.
    vol_ratio = None
    if one_year and one_year.volatility is not None and one_year.bench_volatility:
        vol_ratio = round(one_year.volatility / one_year.bench_volatility, 4)

    return {
        "as_of": on,
        "generated_at": datetime.now(UTC),
        "benchmark": benchmark,
        "coverage": _coverage(positions, total_value, history, shared_dates),
        "sources": {
            "quantity_and_cost": "Trackr+ ledger, replayed by app.engine.holdings (FIFO)",
            "prices": "NSE/BSE bhavcopy via app.prices.pipe",
            "fundamentals": "Yahoo Finance via yfinance (unofficial endpoint), cached",
            "market_cap_bucket": "AMFI half-yearly categorisation, ISIN-keyed",
            "sector": "NSE industry classification, ISIN-keyed",
            "benchmark": f"{benchmark} total-return index",
            "risk_free_rate": "91-day T-Bill, ASSUMED 6.48% -- not yet sourced",
        },
        "kpi": {
            "invested": _money(total_invested),
            "market_value": _money(total_value),
            "unrealised": _money(total_value - total_invested),
            "unrealised_pct": (
                _pct(total_value - total_invested, total_invested) if total_invested else None
            ),
            "day_change": _money(day_change),
            "day_change_pct": day_change_pct,
        },
        "health": {
            "score": health.score,
            "grade": health.grade,
            "components": [
                {
                    "key": c.key, "label": c.label, "weight": c.weight,
                    "score": c.score, "points": c.points, "evidence": c.evidence,
                }
                for c in health.components
            ],
            "drivers": health.drivers,
            "bands": [list(b) for b in health.bands],
            "rule_version": health.rule_version,
        },
        "factors": {
            key: {
                "score": factor_scores["portfolio"][key].score,
                "universe": factor_scores["portfolio"][key].universe,
                "universe_size": factor_scores["portfolio"][key].universe_size,
                "coverage_pct": factor_scores["portfolio"][key].coverage_pct,
            }
            for key in _FACTOR_KEYS
        },
        "risk": {
            label: {
                **asdict(window),
                "var_1d_95_value": _money(
                    (total_value * Decimal(str(window.var_1d_95))).quantize(Decimal("0.01"))
                )
                if window.var_1d_95 is not None
                else None,
            }
            for label, window in risk_windows.items()
        },
        "allocation": {
            "sector": [{**r, "value": _money(r["value"])} for r in sector_alloc],
            "market_cap": [{**r, "value": _money(r["value"])} for r in cap_alloc],
        },
        "correlation": _correlation_payload(aligned, labels),
        "fundamentals": {
            "pe": {"value": pe_agg.value, "excluded_weight_pct": pe_agg.excluded_weight_pct},
            "pb": {"value": pb_agg.value, "excluded_weight_pct": pb_agg.excluded_weight_pct},
            "dividend_yield": {
                "value": dy_agg.value,
                "excluded_weight_pct": dy_agg.excluded_weight_pct,
            },
            "benchmark": {},
            "benchmark_source": (
                "Index P/E, P/B and yield are published by NSE and are NOT in this "
                "system yet -- the price feed carries index LEVELS only."
            ),
        },
        "capital_state": {k: _money(v) for k, v in buckets.items()},
        "derived": {
            "effective_holdings": effective_n,
            "concentration_target": verdict.CONCENTRATION_TARGET,
            "position_count": len(positions),
            "vol_ratio_1y": vol_ratio,
            "growth_delta_vs_benchmark": growth_delta,
            "capital_state_pct": {k: _pct(v, total_value) for k, v in buckets.items()},
            "capital_state_total": _money(sum(buckets.values(), Decimal(0))),
            "lenses": _lens_payload(positions),
        },
        "growth_of_100k": growth,
        "positions": [_position_payload(p) for p in sorted(positions, key=lambda p: -p["weight"])],
        "insights": [asdict(i) for i in insights],
        "unresolved": unresolved + [
            {
                "isin": s.isin,
                "symbol": meta.get(s.isin, {}).get("symbol"),
                "name": meta.get(s.isin, {}).get("name"),
                "quantity": "0",
                "invested": "0",
                "reason": s.message,
            }
            for s in skipped
        ],
    }


def _lens_payload(positions: list[dict[str, Any]]) -> dict[str, Any]:
    """Every Valuation Map lens, scored against the portfolio's own averages.

    ``lens_averages`` and ``lens_status`` already existed and were already right. What was
    missing was anything on this side calling them: the screen recomputed both, which meant
    the "Attractive / Fair / Expensive" split on the page was produced by a second
    implementation of a rule this module owns.
    """
    out: dict[str, Any] = {}
    for key, lens in fagg.LENSES.items():
        averages = fagg.lens_averages(positions, key)
        x_field, _, _ = lens["x"]
        y_field, _, _ = lens["y"]
        statuses = lens["statuses"]
        counts = dict.fromkeys(statuses, 0)
        plotted = 0
        for position in positions:
            index = fagg.lens_status(position, key, averages)
            if index is not None:
                counts[statuses[index]] += 1
            # Plottable is a STRICTER test than scorable: lens_status grades on one axis
            # when only one is known, but a scatter point needs both.
            if position.get(x_field) is not None and position.get(y_field) is not None:
                plotted += 1
        out[key] = {
            "label": lens["label"],
            "x_field": x_field,
            "y_field": y_field,
            "x_average": averages.get(x_field),
            "y_average": averages.get(y_field),
            "status_counts": counts,
            "plotted": plotted,
            "plottable_pct": (
                round(100.0 * plotted / len(positions), 1) if positions else 0.0
            ),
        }
    return out


def _position_payload(position: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in position.items() if not k.startswith("_")}
    for field in ("market_value", "unrealised"):
        out[field] = _money(out.get(field))
    return out


def _window_return(values: list[float], days: int) -> float | None:
    if len(values) <= days or values[-1 - days] <= 0:
        return None
    return (values[-1] / values[-1 - days] - 1.0) * 100.0


def _benchmark_levels(connection: Any, benchmark: str, dates: list[date]) -> dict[date, Any] | None:
    """Whatever index levels exist for ``dates``. The CALLER intersects.

    Returns the mapping rather than a list so the caller can restrict the portfolio series
    to the same dates. Never carries a level forward into a gap: an index level invented
    for a missing day would put a fabricated benchmark return into a beta.
    """
    if not dates:
        return None
    try:
        levels = get_index_levels(connection, benchmark, dates)
    except Exception:
        logger.info("benchmark levels unavailable for %s", benchmark, exc_info=True)
        return None
    return levels or None


def _correlation_payload(aligned: dict[str, list[float]], labels: dict[str, str]) -> dict[str, Any]:
    if len(aligned) < 2:
        return {"symbols": [], "matrix": [], "average": None, "tightest": None, "loosest": None}
    matrix = composition.correlation_matrix(aligned, labels)
    return {
        "symbols": matrix.symbols,
        "matrix": matrix.matrix,
        "average": matrix.average,
        "tightest": list(matrix.tightest) if matrix.tightest else None,
        "loosest": list(matrix.loosest) if matrix.loosest else None,
    }


def _growth_payload(
    dates: list[date], levels: list[float], bench: list[float] | None
) -> dict[str, Any] | None:
    """Growth of Rs 1,00,000 over the trailing year, as strings."""
    if len(levels) < 30 or len(dates) != len(levels):
        return None
    window = min(len(levels), 253)
    tail_dates = dates[-window:]
    tail = levels[-window:]
    base = tail[0] or 1.0
    portfolio = [str(Decimal(str(100000 * v / base)).quantize(Decimal("0.01"))) for v in tail]
    benchmark = None
    if bench and len(bench) >= window:
        bt = bench[-window:]
        bbase = bt[0] or 1.0
        benchmark = [str(Decimal(str(100000 * v / bbase)).quantize(Decimal("0.01"))) for v in bt]
    return {
        "dates": tail_dates,
        "portfolio": portfolio,
        "benchmark": benchmark,
        "basis": "fixed_weight_backtest",
    }


def _day_change(
    connection: Any, positions: list[dict[str, Any]], on: date
) -> tuple[Decimal | None, float | None]:
    """Today's move, from the previous stored close. None when there is no previous close."""
    if not positions:
        return None, None
    isins = [p["isin"] for p in positions]
    # The day BEFORE the one the current prices actually came from -- not `on` minus a
    # calendar day. On a holiday, a weekend, or before the day's bhavcopy settles, `on`
    # and `on - 1` both resolve to the same stored close and the move reads as a flat
    # zero, which is a different claim from "the market did not move".
    latest_stored = _latest_price_date(connection, isins, on)
    if latest_stored is None:
        return None, None
    previous = latest_prices(connection, isins, latest_stored - timedelta(days=1))
    change = Decimal(0)
    base = Decimal(0)
    for position in positions:
        prior = previous.get(position["isin"])
        if prior is None:
            continue
        quantity = Decimal(position["quantity"])
        change += (Decimal(position["last_price"]) - prior) * quantity
        base += prior * quantity
    if base <= 0:
        return None, None
    return change.quantize(Decimal("0.01")), float(change / base * 100)


def _latest_price_date(connection: Any, isins: list[str], on: date) -> date | None:
    """The newest date on or before ``on`` that any of ``isins`` has a stored close for."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT max(price_date) FROM price WHERE isin = ANY(%s) AND price_date <= %s",
            (list(isins), on),
        )
        row = cur.fetchone()
    return row[0] if row else None


def _coverage(
    positions: list[dict[str, Any]],
    total_value: Decimal,
    history: dict[str, Any],
    shared_dates: list[date],
) -> dict[str, float]:
    def weight_with(field: str) -> float:
        return round(sum(p["weight"] for p in positions if p.get(field) is not None), 1)

    derived = round(
        sum(p["weight"] for p in positions if p.get("roe_basis") == "derived_statements"), 1
    )
    with_history = round(
        sum(p["weight"] for p in positions if history.get(p["isin"])), 1
    )
    return {
        "priced_pct": 100.0 if positions else 0.0,
        "pe_pct": weight_with("pe"),
        "pb_pct": weight_with("pb"),
        "roe_pct": weight_with("roe"),
        "debt_to_equity_pct": weight_with("debt_to_equity"),
        "interest_cover_pct": weight_with("interest_cover"),
        "sector_pct": weight_with("sector"),
        "roe_derived_weight_pct": derived,
        "price_history_pct": with_history,
    }


def _factor_scores(
    connection: Any,
    positions: list[dict[str, Any]],
    weights: dict[str, float],
    universe: str,
    on: date,
    history: dict[str, Any],
) -> dict[str, Any]:
    """Rank holdings against the stored universe, falling back to the holdings themselves.

    The fallback is NOT silent: ``universe`` in the response says which population was
    used, so a score ranked against fifteen holdings cannot be mistaken for a market
    percentile.
    """
    members = current_universe_isins(connection, universe)
    population = sorted({*members, *(p["isin"] for p in positions)})
    label = universe if members else f"HOLDINGS_{len(population)}"

    start = on - timedelta(days=_LOOKBACK_DAYS)
    pop_history = (
        price_series(connection, population, start, on) if population else {}
    )
    pop_history = {**pop_history, **history}
    pop_fundamentals = latest_fundamentals(connection, population, on) if population else {}

    momentum_raw: dict[str, float] = {}
    lowvol_raw: dict[str, float] = {}
    for isin in population:
        values = [float(c) for _, c in pop_history.get(isin, [])]
        if len(values) < 60:
            continue
        mom = factors.risk_adjusted_momentum(values)
        if mom is not None:
            momentum_raw[isin] = mom
        sd = series.stdev(series.daily_returns(values))
        if sd:
            lowvol_raw[isin] = -sd

    earnings_yield: dict[str, float] = {}
    book_to_price: dict[str, float] = {}
    roe_map: dict[str, float] = {}
    margin_map: dict[str, float] = {}
    leverage_map: dict[str, float] = {}
    for isin, row in pop_fundamentals.items():
        if row.pe and row.pe > 0:
            earnings_yield[isin] = 1.0 / float(row.pe)
        if row.pb and row.pb > 0:
            book_to_price[isin] = 1.0 / float(row.pb)
        if row.roe is not None:
            roe_map[isin] = float(row.roe)
        if row.net_margin is not None:
            margin_map[isin] = float(row.net_margin)
        if row.debt_to_equity is not None:
            leverage_map[isin] = -float(row.debt_to_equity)

    holding_scores = {
        "momentum": factors.percentile_rank(momentum_raw),
        "value": factors.percentile_rank(
            factors.combine(factors.zscore(earnings_yield), factors.zscore(book_to_price))
        ),
        "quality": factors.percentile_rank(
            factors.combine(
                factors.zscore(roe_map), factors.zscore(margin_map), factors.zscore(leverage_map)
            )
        ),
        "low_volatility": factors.percentile_rank(lowvol_raw),
    }
    portfolio = {
        key: factors.score_portfolio(scores, weights, label, len(population))
        for key, scores in holding_scores.items()
    }
    return {"holdings": holding_scores, "portfolio": portfolio}


# --- ops ---------------------------------------------------------------------------------


def _refresh_fundamentals(connection: Any, limit: int) -> dict[str, Any]:
    """Refresh the stalest slice of held + universe ISINs. Never raises."""
    candidates = sorted({*held_isins(connection), *current_universe_isins(connection)})
    meta = securities.lookup(connection, candidates) if candidates else {}
    symbols = {i: m.get("symbol") for i, m in meta.items() if m.get("symbol")}
    exchanges = {i: m.get("exchange") for i, m in meta.items()}
    return refresh_stale(connection, candidates, symbols, exchanges, limit=limit)


@router.post(
    "/ops/fundamentals/refresh",
    response_model=FundamentalsRefreshResponse,
    dependencies=[Depends(require_ops_key)],
)
def refresh_fundamentals(
    limit: int = Query(DEFAULT_BATCH_LIMIT, ge=1, le=500),
    connection: Any = Depends(get_conn),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Gated by ``X-Ops-Key``: this mutates shared reference data, not one caller's view."""
    return _refresh_fundamentals(connection, limit)


@router.get(
    "/ops/cron/fundamentals-refresh",
    response_model=FundamentalsRefreshResponse,
    dependencies=[Depends(require_cron_secret)],
)
def refresh_fundamentals_cron(
    connection: Any = Depends(get_conn),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """The Vercel-Cron counterpart: GET, no query params, fixed batch size."""
    return _refresh_fundamentals(connection, DEFAULT_BATCH_LIMIT)
