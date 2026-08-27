"""compute_lots and compute_realised -- ENGINE_SPEC section 3."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.engine.errors import NegativeHoldingError
from app.engine.lots import DEFAULT_LONG_TERM_DAYS, compute_lots
from app.engine.realised import compute_realised, tax_cost, tax_proceeds
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
        stt=Decimal(kw.get("stt", "0")),
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


def test_buy_side_stt_is_tracked_but_does_not_move_realised_cost() -> None:
    """STT paid on the BUY leg must not move `cost` (Phase 1's real-cash figure), but
    must be excluded from `tax_cost` -- Income Tax Act Section 48."""
    (r,) = compute_realised(
        [
            txn("BUY", "10", "100", "2024-01-10", charges="15", stt="15"),
            txn("SELL", "10", "200", "2024-06-10"),
        ]
    )
    assert r.cost == Decimal("1015")
    assert r.cost_stt == Decimal("15")
    assert tax_cost(r) == Decimal("1000")


def test_buy_side_mixed_stt_and_non_stt_charges_split_is_additive() -> None:
    """Only the STT portion of `charges` is excluded from `tax_cost` -- brokerage stays
    deductible, proving the split is a real subtraction, not all-or-nothing."""
    (r,) = compute_realised(
        [
            txn("BUY", "10", "100", "2024-01-10", charges="25", stt="15"),
            txn("SELL", "10", "200", "2024-06-10"),
        ]
    )
    assert r.cost == Decimal("1025")
    assert r.cost_stt == Decimal("15")
    assert tax_cost(r) == Decimal("1010")


def test_sell_side_stt_populates_proceeds_stt_without_moving_proceeds() -> None:
    """STT paid on the SELL leg must not move `proceeds`, but must be added back into
    `tax_proceeds` -- Section 48 disallows netting it out of full value of
    consideration."""
    (r,) = compute_realised(
        [
            txn("BUY", "10", "100", "2024-01-10"),
            txn("SELL", "10", "200", "2024-06-10", charges="20", stt="20"),
        ]
    )
    assert r.proceeds == Decimal("1980")
    assert r.proceeds_stt == Decimal("20")
    assert tax_proceeds(r) == Decimal("2000")


def test_sell_side_stt_mixed_with_other_charges() -> None:
    """The non-STT portion of sale-side charges stays netted out of `tax_proceeds`."""
    (r,) = compute_realised(
        [
            txn("BUY", "10", "100", "2024-01-10"),
            txn("SELL", "10", "200", "2024-06-10", charges="35", stt="20"),
        ]
    )
    assert r.proceeds == Decimal("1965")
    assert r.proceeds_stt == Decimal("20")
    assert tax_proceeds(r) == Decimal("1985")


def test_stt_is_carried_per_lot_through_a_fifo_split() -> None:
    """`stt_per_unit` survives a FIFO split exactly parallel to `cost_per_unit` --
    ENGINE_SPEC's worked example (100@200 then 100@300, SELL 150), with STT added to
    each BUY."""
    buys_with_stt = [
        txn("BUY", "100", "200", "2024-01-10", stt="100"),
        txn("BUY", "100", "300", "2024-06-10", stt="50"),
    ]
    first, second = compute_realised(
        [*buys_with_stt, txn("SELL", "150", "400", "2025-03-01")]
    )
    assert first.cost_stt == Decimal("100")
    assert tax_cost(first) == Decimal("19900")
    assert second.cost_stt == Decimal("25")
    assert tax_cost(second) == Decimal("14975")


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


def test_same_date_tie_between_lots_breaks_on_insertion_order() -> None:
    """ENGINE_SPEC section 1: replay order is (txn_date, id). ``ledger.ordered`` uses a
    stable sort on txn_date alone, so same-day rows keep their input order -- that IS
    the `id` tiebreak in practice (see ledger.py). A same-day BONUS credit and a
    same-day top-up BUY must therefore queue in whichever order the caller supplied
    them, not by type or cost -- this is what docs/TAX_ENGINE.md's bonus-stripping
    paragraph relies on being predictable.
    """
    bonus_first = [
        txn("BUY", "100", "200", "2024-01-10"),
        txn("BONUS", "100", "0", "2024-06-10"),
        txn("BUY", "50", "300", "2024-06-10"),
    ]
    assert [(lot.open_date, lot.cost_per_unit) for lot in compute_lots(bonus_first)] == [
        (date(2024, 1, 10), Decimal("200")),
        (date(2024, 6, 10), Decimal("0")),
        (date(2024, 6, 10), Decimal("300")),
    ]

    buy_first = [
        txn("BUY", "100", "200", "2024-01-10"),
        txn("BUY", "50", "300", "2024-06-10"),
        txn("BONUS", "100", "0", "2024-06-10"),
    ]
    assert [(lot.open_date, lot.cost_per_unit) for lot in compute_lots(buy_first)] == [
        (date(2024, 1, 10), Decimal("200")),
        (date(2024, 6, 10), Decimal("300")),
        (date(2024, 6, 10), Decimal("0")),
    ]

    # A sale sized to run past the oldest lot into whichever same-day lot is second
    # proves the tiebreak actually drives consumption, not just the open-lot listing.
    sell = txn("SELL", "150", "400", "2025-01-01")
    bonus_first_realised = compute_realised([*bonus_first, sell])
    assert (bonus_first_realised[1].cost, bonus_first_realised[1].gain) == (
        Decimal("0"), Decimal("20000"),
    )

    buy_first_realised = compute_realised([*buy_first, sell])
    assert (buy_first_realised[1].cost, buy_first_realised[1].gain) == (
        Decimal("15000"), Decimal("5000"),
    )


def test_bonus_stripping_scenario_sells_original_at_a_loss_keeps_bonus_lot() -> None:
    """Hand-computed end to end: buy, receive a 1:1 bonus, then sell exactly the
    original-quantity shares at a loss. FIFO consumes the original lot first because it
    opened before the bonus lot, so the loss is booked while the zero-cost bonus lot
    survives untouched -- this is the bonus-stripping strategy docs/TAX_ENGINE.md's
    corporate-action paragraph says the cost-0 FIFO entry makes computable.
    """
    rows = [
        txn("BUY", "100", "200", "2024-01-10"),
        txn("BONUS", "100", "0", "2024-06-10"),
        txn("SELL", "100", "150", "2025-01-15"),
    ]

    realised = compute_realised(rows)
    assert len(realised) == 1
    loss = realised[0]
    assert (loss.quantity, loss.cost, loss.proceeds, loss.gain) == (
        Decimal("100"), Decimal("20000"), Decimal("15000"), Decimal("-5000"),
    )
    assert (loss.holding_days, loss.term) == (371, Term.LONG)

    (remaining,) = compute_lots(rows)
    assert (remaining.open_date, remaining.quantity_open, remaining.cost_per_unit) == (
        date(2024, 6, 10), Decimal("100"), Decimal("0"),
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
