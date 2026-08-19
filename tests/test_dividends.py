"""compute_dividends -- DATA_MODEL.md's DIVIDEND txn_type, ENGINE_SPEC section 4.

DIVIDEND is already a correct, first-class ledger row (qty=0, price=0, amount in
dividend_amount) and already flows into XIRR as a positive cash flow
(app.engine.xirr._transaction_flows). This is the missing aggregation over those same
rows: per-ISIN, per-financial-year totals for display -- no new calculation rule, just
a sum grouped two ways.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.engine.dividends import compute_dividends
from app.engine.types import Transaction, TxnType

ISIN_A = "INE0Q9301021"
ISIN_B = "INE153T01027"


def txn(txn_type: str, day: str, isin: str = ISIN_A, dividend_amount: str = "0") -> Transaction:
    return Transaction(
        isin=isin,
        txn_date=date.fromisoformat(day),
        txn_type=TxnType(txn_type),
        quantity=Decimal("0") if txn_type == "DIVIDEND" else Decimal("1"),
        price=Decimal("0") if txn_type == "DIVIDEND" else Decimal("100"),
        dividend_amount=Decimal(dividend_amount),
    )


def dividend(day: str, amount: str, isin: str = ISIN_A) -> Transaction:
    return txn("DIVIDEND", day, isin=isin, dividend_amount=amount)


def test_sums_per_isin_and_splits_by_financial_year() -> None:
    """Straddles the 1-April FY boundary twice: a January and a June payment both land
    in FY 2023-24 (April-to-March), an April and the following March payment both land
    in FY 2024-25."""
    rows = [
        dividend("2023-06-10", "500"),
        dividend("2024-01-15", "300"),
        dividend("2024-04-05", "800"),
        dividend("2025-03-20", "200"),
    ]

    (summary,) = compute_dividends(rows)

    assert summary.isin == ISIN_A
    assert summary.total == Decimal("1800")
    assert [(y.fy, y.amount) for y in summary.by_year] == [
        ("2023-24", Decimal("800")),
        ("2024-25", Decimal("1000")),
    ]


def test_multiple_isins_are_independent_and_sorted() -> None:
    rows = [
        dividend("2024-05-01", "100", isin=ISIN_B),
        dividend("2024-05-01", "50", isin=ISIN_A),
    ]

    summaries = compute_dividends(rows)

    assert [s.isin for s in summaries] == sorted([ISIN_A, ISIN_B])
    by_isin = {s.isin: s.total for s in summaries}
    assert by_isin[ISIN_A] == Decimal("50")
    assert by_isin[ISIN_B] == Decimal("100")


def test_isin_with_no_dividend_rows_is_absent() -> None:
    """A holding that never declared a dividend does not appear at all -- a true,
    known zero (it never happened), not the CLAUDE.md rule-4 'missing price defaulted
    to zero' case (a value nobody has substituted for a required one). Absence is the
    honest representation here, same as compute_lots/compute_realised omitting an ISIN
    with nothing to report."""
    rows = [txn("BUY", "2024-01-10"), txn("SELL", "2024-02-10")]
    assert compute_dividends(rows) == []


def test_non_dividend_transactions_on_a_paying_isin_are_ignored() -> None:
    rows = [
        txn("BUY", "2024-01-10"),
        txn("SELL", "2024-02-10"),
        dividend("2024-05-01", "150"),
    ]

    (summary,) = compute_dividends(rows)

    assert summary.total == Decimal("150")
    assert [(y.fy, y.amount) for y in summary.by_year] == [("2024-25", Decimal("150"))]
