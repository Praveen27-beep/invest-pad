"""Dividend summaries -- docs/DATA_MODEL.md's DIVIDEND txn_type, ENGINE_SPEC.md section 4.

DIVIDEND is already a correct, first-class ledger row (qty=0, price=0, the amount lives
in ``dividend_amount``) and already flows into ``compute_xirr`` as a positive cash flow
(``app.engine.xirr._transaction_flows``) and into ``compute_twrr`` as a signed
sub-period outflow. This module adds nothing to that calculation -- it is the missing
aggregation over the same rows: how much a holding has actually paid, per ISIN and per
financial year, for display.

A holding with no ``DIVIDEND`` rows simply has no entry in the output. That is a true,
known zero -- it never declared one -- not the CLAUDE.md rule-4 "missing price defaulted
to zero" case, which is about substituting a value nobody has for one that is required.
Nothing here needs a substitute; there is nothing missing.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.engine.types import ZERO, DividendSummary, DividendYear, Transaction, TxnType
from app.engine.xirr import financial_year_start


def _fy_label(fy_start: date) -> str:
    """1 April YYYY -> ``"YYYY-YY+1"``, e.g. 2025-04-01 -> ``"2025-26"``.

    The inverse of ``app.routers.transactions._financial_year_bounds``, which already
    parses this exact label back into a date range for the ``/realised?fy=`` filter --
    same convention, opposite direction.
    """
    year = fy_start.year
    return f"{year}-{(year + 1) % 100:02d}"


def compute_dividends(transactions: list[Transaction]) -> list[DividendSummary]:
    """Sum ``DIVIDEND.dividend_amount`` per ISIN, and per financial year within each ISIN.

    FY boundaries reuse ``app.engine.xirr.financial_year_start`` (1 April -> 31 March)
    rather than reimplementing that rule a second time.

    Only ISINs with at least one ``DIVIDEND`` row appear, sorted by ISIN; each entry's
    ``by_year`` is sorted ascending by FY start. Mirrors ``compute_lots``/
    ``compute_realised``, which likewise omit an ISIN with nothing to report rather than
    emitting a zero-valued row for it.
    """
    totals: dict[str, Decimal] = {}
    by_year: dict[str, dict[str, Decimal]] = {}

    for txn in transactions:
        if txn.txn_type is not TxnType.DIVIDEND:
            continue
        fy = _fy_label(financial_year_start(txn.txn_date))
        totals[txn.isin] = totals.get(txn.isin, ZERO) + txn.dividend_amount
        year_totals = by_year.setdefault(txn.isin, {})
        year_totals[fy] = year_totals.get(fy, ZERO) + txn.dividend_amount

    return [
        DividendSummary(
            isin=isin,
            total=totals[isin],
            by_year=[
                DividendYear(fy=fy, amount=by_year[isin][fy])
                for fy in sorted(by_year[isin])
            ],
        )
        for isin in sorted(totals)
    ]


__all__ = ["compute_dividends"]
