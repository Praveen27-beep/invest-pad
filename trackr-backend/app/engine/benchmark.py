"""Benchmark comparison -- docs/ENGINE_SPEC.md section 6.

A separate module from ``xirr.py`` on purpose: this is a distinct calculation -- what
would the SAME cash flows have returned in an index -- not a variant of portfolio XIRR.
It reuses ``xirr.py``'s cash-flow construction and solver rather than reimplementing
either, because the cash-flow universe is deliberately identical (docs/ENGINE_SPEC.md
section 4's BUY/IPO_ALLOT negative, SELL/BUYBACK/DIVIDEND positive convention).

MVP benchmarks: NIFTY 50 TRI only. TRI (total-return), never a price index -- a price
index excludes dividends and understates the benchmark. This module has no opinion about
where an index level came from; it is app.prices.index_sources' job to guarantee the
levels it fetches are genuinely TRI, and this module's caller (app.routers.analytical)
is what enforces which benchmark names are actually supported.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.engine.errors import MissingIndexLevelError
from app.engine.ledger import ordered
from app.engine.types import ZERO, Benchmark, Transaction
from app.engine.xirr import _solve, _transaction_flows


def required_index_dates(transactions: list[Transaction], as_of: date) -> list[date]:
    """Every date the replication needs an index level for.

    Exactly the dates ``_transaction_flows`` produces a cash flow for, plus ``as_of``
    (the terminal-value date) -- lets a caller (the router) resolve or fetch the levels
    it needs BEFORE calling ``compute_benchmark``, keeping this module free of I/O.

    Mirrors ``compute_benchmark``'s own no-flows short-circuit: an empty transaction
    list needs no index levels at all, not even ``as_of`` -- there would be nothing to
    terminal-value. Keeping the two in sync matters because the router calls this
    FIRST to decide what to fetch; if it disagreed with ``compute_benchmark`` here, the
    router would fetch/read a level that then goes unused.
    """
    rows = ordered(transactions, as_of)
    flows = _transaction_flows(rows)
    if not flows:
        return []
    dates = {d for d, _ in flows}
    dates.add(as_of)
    return sorted(dates)


def compute_benchmark(
    transactions: list[Transaction],
    index_levels: dict[date, Decimal],
    as_of: date,
    name: str,
) -> Benchmark:
    """Replicate the portfolio's own cash flows into an index -- "what if I had bought
    the index on exactly the days I bought stocks".

    ::

        for each portfolio cash flow (date, amount):
              units = amount / index_level(date)
              accumulate units
        benchmark_terminal = total_units * index_level(as_of)
        benchmark_xirr     = xirr(same dates, same amounts, benchmark_terminal)

    The cash flows reused here are ``_transaction_flows``'s own signed convention (BUY
    negative, SELL/DIVIDEND positive -- section 4). Units accumulate with that sign
    FLIPPED: money that left the portfolio to buy stock buys index units; money that
    came back from a sale OR a dividend redeems units. Dividends redeeming rather than
    adding units is correct specifically because a TRI level already has dividends
    reinvested into it -- taking cash out as a real dividend is economically a
    redemption from the hypothetical index position, same as a sale. Reading the spec's
    ``units = amount / index_level(date)`` literally against the unflipped sign
    convention would make ``total_units`` (and therefore the terminal flow) negative for
    any net-bought portfolio, which breaks the XIRR solve outright (no sign change) --
    the flip is what makes the formula produce a sensible answer at all.

    The FINAL xirr solve reuses the original, UNflipped flows (same dates, same signed
    amounts as ``compute_xirr`` itself would see) with ``benchmark_terminal`` appended as
    the terminal flow -- exactly parallel to how ``xirr.py``'s ``_series`` appends the
    real portfolio's terminal market value.

    Raises:
        MissingIndexLevelError: any date ``required_index_dates`` would have named is
            absent from ``index_levels``. Never defaulted to the nearest available level
            -- see the docstring on the exception itself.
    """
    rows = ordered(transactions, as_of)
    flows = _transaction_flows(rows)
    if not flows:
        return Benchmark(name=name, xirr=None, terminal_value=None)

    needed = {d for d, _ in flows}
    needed.add(as_of)
    missing = sorted(d for d in needed if d not in index_levels)
    if missing:
        raise MissingIndexLevelError(name, missing)

    total_units = ZERO
    for flow_date, amount in flows:
        total_units += -amount / index_levels[flow_date]

    terminal = total_units * index_levels[as_of]

    final_flows = list(flows)
    if terminal != ZERO:
        final_flows.append((as_of, terminal))

    return Benchmark(name=name, xirr=_solve(final_flows), terminal_value=terminal)


__all__ = ["compute_benchmark", "required_index_dates"]
