"""demerger_cost_split -- docs/ENGINE_SPEC.md section 11.

Hand-computed per CLAUDE.md's "tests are the specification" rule, using the section's
own worked example: a 70:30 scheme-document cost ratio (Company A retains 70%, demerged
Company B receives 30%).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.engine.demerger import demerger_cost_split
from app.engine.errors import DemergerAdjustmentError
from app.engine.holdings import compute_holdings
from app.engine.lots import compute_lots
from app.engine.types import Source, Transaction, TxnType

ISIN_A = "INE001A01036"  # original (post-demerger) security
ISIN_B = "INE002B01044"  # new demerged-in security
EX_DATE = date(2024, 6, 1)


def _buy(isin: str, qty: str, price: str, day: str) -> Transaction:
    return Transaction(
        isin=isin,
        txn_date=date.fromisoformat(day),
        txn_type=TxnType.BUY,
        quantity=Decimal(qty),
        price=Decimal(price),
    )


def _demerger_in(qty: str) -> Transaction:
    return Transaction(
        isin=ISIN_B,
        txn_date=EX_DATE,
        txn_type=TxnType.DEMERGER_IN,
        quantity=Decimal(qty),
        price=Decimal("0"),
        source=Source.CORP_ACTION,
    )


def test_cost_transfer_is_the_scheme_documents_30_percent() -> None:
    """pool 100,000, A retains 70% -> cost_transfer = 100,000 x 0.30 = 30,000."""
    cost_out, cost_in = demerger_cost_split(
        original_isin=ISIN_A,
        new_isin=ISIN_B,
        txn_date=EX_DATE,
        original_cost_basis=Decimal("100000"),
        cost_ratio_retained=Decimal("0.70"),
        source_ref="SCHEME-2024-001",
    )
    assert cost_out.cost_transfer == Decimal("30000")
    assert cost_in.cost_transfer == Decimal("30000")


def test_returned_transactions_have_the_right_shape() -> None:
    cost_out, cost_in = demerger_cost_split(
        original_isin=ISIN_A,
        new_isin=ISIN_B,
        txn_date=EX_DATE,
        original_cost_basis=Decimal("100000"),
        cost_ratio_retained=Decimal("0.70"),
        source_ref="SCHEME-2024-001",
    )

    assert cost_out.isin == ISIN_A
    assert cost_out.txn_type == TxnType.DEMERGER_COST_OUT
    assert cost_out.txn_date == EX_DATE
    assert cost_out.quantity == Decimal("0")
    assert cost_out.price == Decimal("0")
    assert cost_out.source == Source.CORP_ACTION
    assert cost_out.source_ref == "SCHEME-2024-001"

    assert cost_in.isin == ISIN_B
    assert cost_in.txn_type == TxnType.DEMERGER_COST_IN
    assert cost_in.txn_date == EX_DATE
    assert cost_in.quantity == Decimal("0")
    assert cost_in.price == Decimal("0")


def test_ratio_not_strictly_between_zero_and_one_raises() -> None:
    with pytest.raises(ValueError):
        demerger_cost_split(ISIN_A, ISIN_B, EX_DATE, Decimal("100000"), Decimal("1"))
    with pytest.raises(ValueError):
        demerger_cost_split(ISIN_A, ISIN_B, EX_DATE, Decimal("100000"), Decimal("0"))
    with pytest.raises(ValueError):
        demerger_cost_split(ISIN_A, ISIN_B, EX_DATE, Decimal("100000"), Decimal("1.1"))


def test_holdings_cost_bases_sum_back_to_the_original_pool() -> None:
    """The section 11 worked example, run through the real engine: A's 70,000 and B's
    30,000 must sum back to the original 100,000 -- no cost is created or destroyed, it
    only moves."""
    original_buy = _buy(ISIN_A, "1000", "100", "2023-01-15")
    demerger_in = _demerger_in("500")

    cost_out, cost_in = demerger_cost_split(
        original_isin=ISIN_A,
        new_isin=ISIN_B,
        txn_date=EX_DATE,
        original_cost_basis=Decimal("100000"),
        cost_ratio_retained=Decimal("0.70"),
        source_ref="SCHEME-2024-001",
    )

    # DEMERGER_COST_IN inserted after DEMERGER_IN, per the ordering note in
    # ENGINE_SPEC section 11 and the docstring of demerger_cost_split.
    transactions = [original_buy, demerger_in, cost_out, cost_in]

    holdings = {h.isin: h for h in compute_holdings(transactions)}

    assert holdings[ISIN_A].invested == Decimal("70000")
    assert holdings[ISIN_A].avg_cost == Decimal("70.0000")
    assert holdings[ISIN_A].quantity == Decimal("1000")

    assert holdings[ISIN_B].invested == Decimal("30000")
    assert holdings[ISIN_B].avg_cost == Decimal("60.0000")
    assert holdings[ISIN_B].quantity == Decimal("500")

    assert holdings[ISIN_A].invested + holdings[ISIN_B].invested == Decimal("100000")


def test_original_buy_transaction_is_never_mutated() -> None:
    """docs/TAX_ENGINE.md's 'Never mutate history': the split is new rows, and the
    original BUY's own fields are untouched by constructing or replaying them."""
    original_buy = _buy(ISIN_A, "1000", "100", "2023-01-15")
    before = (original_buy.isin, original_buy.quantity, original_buy.price, original_buy.txn_type)

    demerger_in = _demerger_in("500")
    cost_out, cost_in = demerger_cost_split(
        original_isin=ISIN_A,
        new_isin=ISIN_B,
        txn_date=EX_DATE,
        original_cost_basis=Decimal("100000"),
        cost_ratio_retained=Decimal("0.70"),
    )
    compute_holdings([original_buy, demerger_in, cost_out, cost_in])

    after = (original_buy.isin, original_buy.quantity, original_buy.price, original_buy.txn_type)
    assert before == after
    # Frozen dataclass: mutation would raise, not silently fail, but the assertion above
    # is the actual invariant the task cares about -- replaying never touches the row.


def test_fifo_spread_is_proportional_by_quantity_across_two_open_lots() -> None:
    """Two open lots on A (600 @ 100, 400 @ 100), same 100,000 pool. A per-unit shift of
    -30 (= -30,000 / 1000) lands both lots at cost_per_unit 70, per ENGINE_SPEC section
    11's second worked example."""
    lot1 = _buy(ISIN_A, "600", "100", "2023-01-15")
    lot2 = _buy(ISIN_A, "400", "100", "2023-03-01")
    demerger_in = _demerger_in("500")

    cost_out, cost_in = demerger_cost_split(
        original_isin=ISIN_A,
        new_isin=ISIN_B,
        txn_date=EX_DATE,
        original_cost_basis=Decimal("100000"),
        cost_ratio_retained=Decimal("0.70"),
    )

    lots = compute_lots([lot1, lot2, demerger_in, cost_out, cost_in])
    a_lots = sorted((lot for lot in lots if lot.isin == ISIN_A), key=lambda lot: lot.open_date)

    assert [lot.quantity_open for lot in a_lots] == [Decimal("600"), Decimal("400")]
    assert [lot.cost_per_unit for lot in a_lots] == [Decimal("70"), Decimal("70")]

    b_lot = next(lot for lot in lots if lot.isin == ISIN_B)
    assert b_lot.quantity_open == Decimal("500")
    assert b_lot.cost_per_unit == Decimal("60")


def test_cost_out_against_isin_with_no_open_position_raises() -> None:
    """No BUY/DEMERGER_IN history for the ISIN at all -- the adjustment has nothing to
    attach to, which must raise rather than silently drop the cost transfer."""
    cost_out, cost_in = demerger_cost_split(
        original_isin=ISIN_A,
        new_isin=ISIN_B,
        txn_date=EX_DATE,
        original_cost_basis=Decimal("100000"),
        cost_ratio_retained=Decimal("0.70"),
    )

    with pytest.raises(DemergerAdjustmentError):
        compute_holdings([cost_out, cost_in])

    with pytest.raises(DemergerAdjustmentError):
        compute_lots([cost_out, cost_in])
