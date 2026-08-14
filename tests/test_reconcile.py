"""reconcile and compute_snapshot -- ENGINE_SPEC sections 7 and 8."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from engine.errors import MissingPriceError
from engine.reconcile import reconcile
from engine.snapshot import compute_snapshot
from engine.types import Transaction, TxnType

ISIN = "INE153T01027"
OTHER = "INE0Q9301021"


def txn(txn_type: str, qty: str, price: str, day: str, isin: str = ISIN):
    return Transaction(
        isin=isin,
        txn_date=date.fromisoformat(day),
        txn_type=TxnType(txn_type),
        quantity=Decimal(qty),
        price=Decimal(price),
    )


BOUGHT_200 = [txn("BUY", "200", "250", "2024-01-10")]


# --- section 7, reconciliation -------------------------------------------------


def test_matching_quantities_reconcile_clean() -> None:
    """A clean run is an empty list, not a list of zero-difference rows."""
    assert reconcile(BOUGHT_200, {ISIN: Decimal("200")}) == []


def test_doubled_quantity_reads_as_a_bonus() -> None:
    (d,) = reconcile(BOUGHT_200, {ISIN: Decimal("400")})
    assert d.computed_qty == Decimal("200")
    assert d.declared_qty == Decimal("400")
    assert d.difference == Decimal("200")
    assert d.ratio == Decimal("2")
    assert "bonus" in d.likely_cause.lower()


def test_tripled_quantity_reads_as_a_bonus_or_split() -> None:
    (d,) = reconcile(BOUGHT_200, {ISIN: Decimal("600")})
    assert d.ratio == Decimal("3")
    assert "bonus" in d.likely_cause.lower()


@pytest.mark.parametrize(("declared", "expected"), [("1000", "1:5 split"), ("2000", "1:10 split")])
def test_split_ratios(declared: str, expected: str) -> None:
    (d,) = reconcile(BOUGHT_200, {ISIN: Decimal(declared)})
    assert d.likely_cause == expected


def test_nothing_computed_reads_as_an_unrecorded_transfer_in() -> None:
    (d,) = reconcile([], {ISIN: Decimal("100")})
    assert d.computed_qty == Decimal("0")
    assert d.ratio is None, "ratio is undefined against a zero computed quantity"
    assert "transfer-in" in d.likely_cause.lower()


def test_nothing_declared_reads_as_a_full_exit() -> None:
    (d,) = reconcile(BOUGHT_200, {ISIN: Decimal("0")})
    assert "full exit" in d.likely_cause.lower()


def test_surplus_that_is_not_a_clean_ratio_reads_as_a_missed_buy() -> None:
    (d,) = reconcile(BOUGHT_200, {ISIN: Decimal("237")})
    assert "missed buy" in d.likely_cause.lower()


def test_shortfall_reads_as_a_missed_sell_or_transfer_out() -> None:
    (d,) = reconcile(BOUGHT_200, {ISIN: Decimal("150")})
    assert d.difference == Decimal("-50")
    assert "missed sell" in d.likely_cause.lower()


def test_near_ratios_are_not_diagnosed_as_corporate_actions() -> None:
    """2.0 and 2.5 mean different things; a loose match hands a human a wrong answer."""
    (d,) = reconcile(BOUGHT_200, {ISIN: Decimal("500")})
    assert "bonus" not in d.likely_cause.lower()
    assert "missed buy" in d.likely_cause.lower()


def test_only_disagreeing_isins_are_reported() -> None:
    rows = [*BOUGHT_200, txn("BUY", "50", "100", "2024-01-10", isin=OTHER)]
    found = reconcile(rows, {ISIN: Decimal("200"), OTHER: Decimal("100")})
    assert [d.isin for d in found] == [OTHER]


# --- section 8, snapshots ------------------------------------------------------


def test_snapshot_totals() -> None:
    snap = compute_snapshot(BOUGHT_200, {ISIN: Decimal("300")}, date(2024, 6, 30))
    assert snap.as_of == date(2024, 6, 30)
    assert snap.invested == Decimal("50000")
    assert snap.market_value == Decimal("60000")
    assert snap.unrealised == Decimal("10000")
    assert snap.realised_to_date == Decimal("0")


def test_snapshot_replays_history_at_the_given_date() -> None:
    """Same functions, an earlier date, historical prices."""
    rows = [*BOUGHT_200, txn("BUY", "100", "400", "2025-01-10")]
    early = compute_snapshot(rows, {ISIN: Decimal("300")}, date(2024, 6, 30))
    late = compute_snapshot(rows, {ISIN: Decimal("300")}, date(2025, 6, 30))
    assert early.invested == Decimal("50000")
    assert late.invested == Decimal("90000")


def test_snapshot_accumulates_realised_gains() -> None:
    rows = [*BOUGHT_200, txn("SELL", "100", "400", "2024-06-10")]
    snap = compute_snapshot(rows, {ISIN: Decimal("300")}, date(2024, 12, 31))
    assert snap.realised_to_date == Decimal("15000")
    assert snap.invested == Decimal("25000")


def test_snapshot_raises_on_a_missing_historical_price() -> None:
    """Backfilling needs prices for what was held THEN, not what is held now."""
    with pytest.raises(MissingPriceError):
        compute_snapshot(BOUGHT_200, {}, date(2024, 6, 30))
