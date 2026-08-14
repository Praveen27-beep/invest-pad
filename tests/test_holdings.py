"""compute_holdings -- ENGINE_SPEC section 1, beyond what the fixture cases cover."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from engine.errors import NegativeHoldingError
from engine.holdings import compute_holdings
from engine.types import Source, Transaction, TxnType


def txn(txn_type: str, qty: str, price: str, day: str, isin: str = "INE153T01027", **kw):
    return Transaction(
        isin=isin,
        txn_date=date.fromisoformat(day),
        txn_type=TxnType(txn_type),
        quantity=Decimal(qty),
        price=Decimal(price),
        charges=Decimal(kw.get("charges", "0")),
    )


def test_the_session_gate_bonus_does_not_move_invested() -> None:
    """The done-when: quantity 400, invested UNCHANGED at 50000, avg_cost 125.

    If invested moves when free shares arrive, the cost-pool rule is wrong. This is the
    single assertion the whole session is measured on.
    """
    holdings = compute_holdings(
        [
            txn("BUY", "100", "200", "2024-01-10"),
            txn("BUY", "100", "300", "2024-06-10"),
            txn("BONUS", "200", "0", "2025-03-01"),
        ]
    )
    (h,) = holdings
    assert h.quantity == Decimal("400")
    assert h.invested == Decimal("50000")
    assert h.avg_cost == Decimal("125")


def test_disposal_removes_cost_proportionally() -> None:
    """Selling never moves the average -- it changes what you own, not what it cost."""
    holdings = compute_holdings(
        [
            txn("BUY", "100", "200", "2024-01-10"),
            txn("BUY", "100", "300", "2024-06-10"),
            txn("SELL", "100", "400", "2025-01-10"),
        ]
    )
    (h,) = holdings
    assert h.avg_cost == Decimal("250")
    assert h.invested == Decimal("25000")


def test_charges_join_the_cost_pool() -> None:
    holdings = compute_holdings([txn("BUY", "10", "100", "2024-01-10", charges="50")])
    (h,) = holdings
    assert h.invested == Decimal("1050")
    assert h.avg_cost == Decimal("105")


def test_closed_position_is_excluded() -> None:
    holdings = compute_holdings(
        [txn("BUY", "100", "200", "2024-01-10"), txn("SELL", "100", "250", "2024-06-10")]
    )
    assert holdings == []


def test_dividend_moves_neither_quantity_nor_pool() -> None:
    base = [txn("BUY", "100", "200", "2024-01-10")]
    before = compute_holdings(base)[0]
    after = compute_holdings([*base, txn("DIVIDEND", "0", "0", "2024-06-10")])[0]
    assert (after.quantity, after.invested) == (before.quantity, before.invested)


def test_as_of_truncates_the_replay() -> None:
    rows = [
        txn("BUY", "100", "200", "2024-01-10"),
        txn("BUY", "100", "300", "2025-06-10"),
    ]
    early = compute_holdings(rows, as_of=date(2024, 12, 31))[0]
    assert early.quantity == Decimal("100")
    assert early.invested == Decimal("20000")

    late = compute_holdings(rows, as_of=date(2025, 12, 31))[0]
    assert late.quantity == Decimal("200")


def test_disposal_exceeding_holding_raises() -> None:
    """Missing buy history, not a short position -- the tradebook date-filter symptom."""
    with pytest.raises(NegativeHoldingError) as excinfo:
        compute_holdings(
            [txn("BUY", "10", "200", "2024-01-10"), txn("SELL", "40", "250", "2024-06-10")]
        )
    assert "INE153T01027" in str(excinfo.value)


def test_disposal_against_nothing_raises() -> None:
    with pytest.raises(NegativeHoldingError):
        compute_holdings([txn("SELL", "1", "250", "2024-06-10")])


def test_positions_are_independent_and_sorted() -> None:
    holdings = compute_holdings(
        [
            txn("BUY", "10", "100", "2024-01-10", isin="INE942C01029"),
            txn("BUY", "20", "200", "2024-01-10", isin="INE153T01027"),
        ]
    )
    assert [h.isin for h in holdings] == ["INE153T01027", "INE942C01029"]
    assert [h.invested for h in holdings] == [Decimal("4000"), Decimal("1000")]


def test_first_buy_date_is_the_earliest_acquisition() -> None:
    h = compute_holdings(
        [
            txn("BUY", "10", "100", "2024-06-10"),
            txn("BUY", "10", "100", "2024-01-10"),
        ]
    )[0]
    assert h.first_buy_date == date(2024, 1, 10)


def test_price_fields_are_unset_without_a_price_pipe() -> None:
    """Valuation is section 2 and a separate concern; holdings alone cannot know value."""
    h = compute_holdings([txn("BUY", "10", "100", "2024-01-10")])[0]
    assert h.last_price is None
    assert h.market_value is None


def test_source_is_never_consulted() -> None:
    """The engine must not branch on which adapter produced a row."""
    manual = Transaction(
        isin="INE153T01027",
        txn_date=date(2024, 1, 10),
        txn_type=TxnType.BUY,
        quantity=Decimal("10"),
        price=Decimal("100"),
        source=Source.MANUAL,
    )
    tradebook = Transaction(
        isin="INE153T01027",
        txn_date=date(2024, 1, 10),
        txn_type=TxnType.BUY,
        quantity=Decimal("10"),
        price=Decimal("100"),
        source=Source.TRADEBOOK,
    )
    assert compute_holdings([manual])[0].invested == compute_holdings([tradebook])[0].invested
