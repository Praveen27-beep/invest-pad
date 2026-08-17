"""Shared ledger traversal.

Both the weighted-average replay (section 1) and the FIFO replay (section 3) walk the
same rows in the same order. That ordering is defined once, here, because two replays
that disagree about sequence would disagree about cost basis in ways that only surface
on a portfolio large enough to be painful to debug.
"""

from __future__ import annotations

from datetime import date

from app.engine.types import Transaction


def ordered(
    transactions: list[Transaction], as_of: date | None = None
) -> list[Transaction]:
    """Ledger rows in replay order, optionally truncated at ``as_of``.

    ENGINE_SPEC section 1 specifies ``(txn_date, id)``. Sorting on ``txn_date`` alone is
    equivalent here and more robust: Python's sort is stable, so rows sharing a date keep
    their input order, which IS insertion order. The golden fixture carries no ``id``
    field at all, and 67 of its date/ISIN groups hold more than one row, so a sort that
    demanded ``id`` would have to invent a tiebreak.

    Truncating at ``as_of`` is what makes historical replay work: the same functions,
    an earlier date, and prices from that date reproduce the portfolio as it stood.
    """
    rows = transactions if as_of is None else [t for t in transactions if t.txn_date <= as_of]
    return sorted(rows, key=lambda t: t.txn_date)
