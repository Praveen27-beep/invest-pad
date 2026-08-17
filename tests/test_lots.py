"""compute_lots and compute_realised -- ENGINE_SPEC section 3."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.engine.errors import NegativeHoldingError
from app.engine.lots import DEFAULT_LONG_TERM_DAYS, compute_lots
from app.engine.realised import compute_realised
from app.engine.types import Term, Transaction, TxnType

from tests.conftest import SCHEMA, load_json


def txn(txn_type: str, qty: str, price: str, day: str, isin: str = "INE153T01027", **kw):
    return Transaction(
        isin=isin,
        txn_date=date.fromisoformat(day),
        txn_type=TxnType(txn_type),
        quantity=Decimal(qty),
        price=Decimal(price),
        charges=Decimal(kw.get("charges", "0")),
    )


TWO_BUYS = [txn("BUY", "100", "200", "2024-01-10"), txn("BUY", "100", "300", "2024-06-10")]


def test_long_term_days_default_matches_asset_classes_json() -> None:
    """The threshold lives in data. The engine's default must not drift from it."""
    seeded = load_json(SCHEMA / "asset_classes.json")["asset_classes"]
    eq = next(entry for entry in seeded if entry["code"] == "EQ")
    assert eq["long_term_days"] == DEFAULT_LONG_TERM_DAYS


def test_acquisitions_push_lots_oldest_first() -> None:
    lots = compute_lots(TWO_BUYS)
    assert [lot.open_date for lot in lots] == [date(2024, 1, 10), date(2024, 6, 10)]
    assert [lot.cost_per_unit for lot in lots] == [Decimal("200"), Decimal("300")]


def test_charges_raise_lot_cost() -> None:
    (lot,) = compute_lots([txn("BUY", "10", "100", "2024-01-10", charges="50")])
    assert lot.cost_per_unit == Decimal("105")


def test_disposal_smaller_than_oldest_lot_splits_it() -> None:
    lots = compute_lots([*TWO_BUYS, txn("SELL", "40", "400", "2025-03-01")])
    assert [lot.quantity_open for lot in lots] == [Decimal("60"), Decimal("100")]
    assert lots[0].cost_per_unit == Decimal("200")


def test_disposal_consumes_whole_lots_in_order() -> None:
    """The surviving lot keeps its OWN cost, not the blended average."""
    lots = compute_lots([*TWO_BUYS, txn("SELL", "150", "400", "2025-03-01")])
    assert len(lots) == 1
    assert lots[0].quantity_open == Decimal("50")
    assert lots[0].cost_per_unit == Decimal("300")


def test_bonus_pushes_a_zero_cost_lot_at_the_action_date() -> None:
    """What makes bonus-stripping computable in a later phase."""
    lots = compute_lots([*TWO_BUYS, txn("BONUS", "200", "0", "2025-03-01")])
    bonus_lot = lots[-1]
    assert bonus_lot.cost_per_unit == Decimal("0")
    assert bonus_lot.open_date == date(2025, 3, 1)
    assert sum(lot.quantity_open for lot in lots) == Decimal("400")


def test_realised_splits_across_two_lots_with_separate_terms() -> None:
    """The spec's worked example: one sale, part long-term and part short."""
    realised = compute_realised([*TWO_BUYS, txn("SELL", "150", "400", "2025-03-01")])
    assert len(realised) == 2

    first, second = realised
    assert (first.quantity, first.cost, first.proceeds, first.gain) == (
        Decimal("100"), Decimal("20000"), Decimal("40000"), Decimal("20000"),
    )
    assert (first.holding_days, first.term) == (416, Term.LONG)

    assert (second.quantity, second.cost, second.proceeds, second.gain) == (
        Decimal("50"), Decimal("15000"), Decimal("20000"), Decimal("5000"),
    )
    assert (second.holding_days, second.term) == (264, Term.SHORT)


def test_term_boundary_is_strictly_greater_than_the_threshold() -> None:
    """LONG when holding_days EXCEEDS the threshold. Exactly 365 days is SHORT."""
    exactly_365 = compute_realised(
        [txn("BUY", "1", "100", "2024-01-10"), txn("SELL", "1", "150", "2025-01-09")]
    )
    assert exactly_365[0].holding_days == 365
    assert exactly_365[0].term is Term.SHORT

    one_more = compute_realised(
        [txn("BUY", "1", "100", "2024-01-10"), txn("SELL", "1", "150", "2025-01-10")]
    )
    assert one_more[0].holding_days == 366
    assert one_more[0].term is Term.LONG


def test_charges_reduce_proceeds() -> None:
    (r,) = compute_realised(
        [
            txn("BUY", "10", "100", "2024-01-10"),
            txn("SELL", "10", "200", "2024-06-10", charges="100"),
        ]
    )
    assert r.proceeds == Decimal("1900")
    assert r.gain == Decimal("900")


def test_no_realised_gain_without_a_disposal() -> None:
    assert compute_realised(TWO_BUYS) == []


def test_transfer_out_consumes_lots_without_realising() -> None:
    """DATA_MODEL gives TRANSFER_OUT a cash effect of 0, so it is not a realised gain."""
    rows = [txn("BUY", "100", "200", "2024-01-10"), txn("TRANSFER_OUT", "40", "0", "2024-06-10")]
    assert compute_realised(rows) == []
    assert sum(lot.quantity_open for lot in compute_lots(rows)) == Decimal("60")


def test_disposal_exceeding_open_lots_raises() -> None:
    with pytest.raises(NegativeHoldingError):
        compute_lots(
            [
                txn("BUY", "10", "200", "2024-01-10"),
                txn("SELL", "40", "250", "2024-06-10"),
            ]
        )


def test_lots_and_holdings_agree_on_quantity() -> None:
    """Two methods, one ledger. If total quantity disagrees, one replay is wrong."""
    from app.engine.holdings import compute_holdings

    rows = [
        *TWO_BUYS,
        txn("BONUS", "200", "0", "2025-03-01"),
        txn("SELL", "150", "400", "2025-06-01"),
    ]
    lot_total = sum(lot.quantity_open for lot in compute_lots(rows))
    holding_total = sum(h.quantity for h in compute_holdings(rows))
    assert lot_total == holding_total == Decimal("250")
