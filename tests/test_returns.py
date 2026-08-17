"""Other return measures -- ENGINE_SPEC section 5.

fixtures/engine_cases.json pins the two hand-computed spec cases (net_invested and the
zero/negative guard). These tests cover the surrounding edges: which txn_types count,
charges, as_of truncation, and the exact boundary of the guard.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.engine.returns import compute_absolute_return, compute_net_invested
from app.engine.types import ZERO, Transaction, TxnType

ISIN_A = "INE0Q9301021"


def txn(txn_type: str, qty: str, price: str, day: str, isin: str = ISIN_A, **kw):
    return Transaction(
        isin=isin,
        txn_date=date.fromisoformat(day),
        txn_type=TxnType(txn_type),
        quantity=Decimal(qty),
        price=Decimal(price),
        charges=Decimal(kw.get("charges", "0")),
        dividend_amount=Decimal(kw.get("dividend_amount", "0")),
    )


def test_dividends_are_not_capital_contributed() -> None:
    transactions = [
        txn("BUY", "100", "100", "2024-01-10"),
        txn("DIVIDEND", "0", "0", "2024-06-10", dividend_amount="500"),
    ]
    assert compute_net_invested(transactions, date(2024, 12, 31)) == Decimal("10000")


def test_transfers_have_no_cash_effect() -> None:
    """TRANSFER_IN/TRANSFER_OUT move shares, not cash -- see xirr.py's CASH_OUT_TYPES
    comment. A BUY alongside them should be the only thing that moves net_invested."""
    transactions = [
        txn("BUY", "100", "100", "2024-01-10"),
        txn("TRANSFER_IN", "50", "100", "2024-03-10"),
        txn("TRANSFER_OUT", "20", "100", "2024-04-10"),
    ]
    assert compute_net_invested(transactions, date(2024, 12, 31)) == Decimal("10000")


def test_charges_add_to_outflow_and_subtract_from_inflow() -> None:
    transactions = [
        txn("BUY", "100", "100", "2024-01-10", charges="50"),
        txn("SELL", "50", "100", "2024-06-10", charges="20"),
    ]
    # outflow 10000 + 50 = 10050; inflow 5000 - 20 = 4980; net = 10050 - 4980 = 5070
    assert compute_net_invested(transactions, date(2024, 12, 31)) == Decimal("5070")


def test_ipo_allot_and_buyback_use_the_same_convention_as_buy_and_sell() -> None:
    transactions = [
        txn("IPO_ALLOT", "100", "100", "2024-01-10"),
        txn("BUYBACK", "40", "150", "2024-06-10"),
    ]
    # outflow 10000; inflow 6000; net = 4000
    assert compute_net_invested(transactions, date(2024, 12, 31)) == Decimal("4000")


def test_as_of_truncates_transactions_after_the_cutoff() -> None:
    transactions = [
        txn("BUY", "100", "100", "2024-01-10"),
        txn("BUY", "100", "200", "2025-01-10"),
    ]
    assert compute_net_invested(transactions, date(2024, 6, 1)) == Decimal("10000")


def test_empty_ledger_has_zero_net_invested() -> None:
    assert compute_net_invested([], date(2024, 12, 31)) == ZERO


def test_absolute_return_undefined_on_empty_ledger() -> None:
    assert compute_absolute_return(ZERO, ZERO, ZERO) is None


def test_absolute_return_undefined_when_net_invested_is_exactly_zero() -> None:
    """A full exit at cost, no gain or loss: net_invested nets to exactly zero. This is
    the guard's boundary, not just the negative case -- must not raise or divide."""
    assert compute_absolute_return(ZERO, ZERO, Decimal("0")) is None


def test_absolute_return_computes_the_plain_ratio() -> None:
    net_invested = Decimal("10000")
    market_value = Decimal("15000")
    realised_to_date = ZERO
    result = compute_absolute_return(net_invested, market_value, realised_to_date)
    assert result == Decimal("0.5")
