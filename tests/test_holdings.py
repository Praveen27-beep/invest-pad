"""compute_holdings -- ENGINE_SPEC section 1, beyond what the fixture cases cover."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.engine.errors import NegativeHoldingError
from app.engine.holdings import compute_holdings, compute_holdings_partitioned
from app.engine.types import Source, Transaction, TxnType


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


def test_invested_is_identical_whether_stt_is_populated_or_zero() -> None:
    """compute_holdings reads txn.charges only, never txn.stt -- STT is a subset of
    charges (already counted there), so a populated stt field must not change the
    weighted-average invested/avg_cost figure CLAUDE.md's golden-fixture numbers and
    the tax-facing fix (docs/TAX_ENGINE.md's Session 10 status note) both depend on
    staying isolated from each other."""
    with_stt = [
        txn("BUY", "10", "100", "2024-01-10", charges="25", stt="15"),
        txn("SELL", "4", "150", "2024-06-10", charges="10", stt="6"),
    ]
    without_stt = [
        txn("BUY", "10", "100", "2024-01-10", charges="25"),
        txn("SELL", "4", "150", "2024-06-10", charges="10"),
    ]
    assert compute_holdings(with_stt) == compute_holdings(without_stt)


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


def test_same_day_sell_before_buy_round_trip_does_not_raise() -> None:
    """A same-day intraday round trip -- the SELL listed first in the source file, the
    matching BUY later -- must not trip NegativeHoldingError when the day nets
    non-negative. NSE cash equity has no way to end a day genuinely short (an intraday
    SELL-before-BUY leg is squared off by the broker before close), and a contract note
    commonly lists its Sale table before its Purchase table -- file order alone must
    never manufacture a deficit that was never real. Regression for the exact shape of
    the 2023-01-27 ADANIGREEN case this was found against: 60 sold, 60 bought, same day,
    SELL rows first in the source file."""
    holdings = compute_holdings(
        [
            txn("SELL", "50", "1577", "2023-01-27"),
            txn("BUY", "50", "1486.25", "2023-01-27"),
        ]
    )
    assert holdings == []  # opened and closed the same day


def test_same_day_sell_before_buy_still_raises_when_the_day_nets_short() -> None:
    """The tiebreak only reorders same-day rows; it must not hide a real end-of-day
    deficit. This day's SELL still exceeds its BUY even after the reorder, so it must
    raise -- against the true end-of-day shortfall, not an artifact of file order."""
    with pytest.raises(NegativeHoldingError) as excinfo:
        compute_holdings(
            [
                txn("SELL", "50", "1577", "2023-01-27"),
                txn("BUY", "30", "1486.25", "2023-01-27"),
            ]
        )
    assert excinfo.value.quantity == Decimal("-20")


def test_transfer_out_before_transfer_in_is_not_reordered() -> None:
    """TRANSFER_OUT/TRANSFER_IN -- an account-to-account migration, not a market trade --
    keep file order. Unlike SELL/BUY, there is no structural guarantee the pair nets
    non-negative, and file order is the only record of which leg happened first;
    reordering it the way SELL/BUY is reordered would change cost basis for no
    correctness gain (see fixtures/golden_portfolio.json's INE0Q9301021 TRANSFER pair,
    which is exactly this shape and depends on staying in file order)."""
    with pytest.raises(NegativeHoldingError):
        compute_holdings(
            [
                txn("TRANSFER_OUT", "50", "0", "2023-01-27"),
                txn("TRANSFER_IN", "50", "1486.25", "2023-01-27"),
            ]
        )


def test_partitioned_excludes_only_the_broken_isin() -> None:
    """The done-when for compute_holdings_partitioned: one ISIN whose ledger doesn't
    reconcile must not take a clean, independent ISIN down with it."""
    holdings, skipped = compute_holdings_partitioned(
        [
            txn("BUY", "10", "200", "2024-01-10", isin="INE153T01027"),
            txn("SELL", "40", "250", "2024-06-10", isin="INE153T01027"),
            txn("BUY", "20", "100", "2024-01-10", isin="INE942C01029"),
        ]
    )
    assert [h.isin for h in holdings] == ["INE942C01029"]
    (s,) = skipped
    assert s.isin == "INE153T01027"
    assert s.deficit == Decimal("30")
    assert s.as_of == date(2024, 6, 10)
    assert "INE153T01027" in s.message


def test_partitioned_matches_compute_holdings_when_nothing_is_broken() -> None:
    """No exclusions -> byte-identical to compute_holdings, not just "close enough" --
    this is what makes reusing this for /holdings and /summary safe."""
    transactions = [
        txn("BUY", "10", "200", "2024-01-10", isin="INE153T01027"),
        txn("BUY", "20", "100", "2024-01-10", isin="INE942C01029"),
    ]
    holdings, skipped = compute_holdings_partitioned(transactions)
    assert skipped == []
    assert holdings == compute_holdings(transactions)


def test_partitioned_excludes_multiple_broken_isins_independently() -> None:
    holdings, skipped = compute_holdings_partitioned(
        [
            txn("SELL", "1", "250", "2024-06-10", isin="INE153T01027"),
            txn("SELL", "1", "250", "2024-06-10", isin="INE942C01029"),
            txn("BUY", "20", "100", "2024-01-10", isin="INE000000000"),
        ]
    )
    assert [h.isin for h in holdings] == ["INE000000000"]
    assert {s.isin for s in skipped} == {"INE153T01027", "INE942C01029"}


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
