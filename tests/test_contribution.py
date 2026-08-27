"""compute_contribution -- docs/ENGINE_SPEC.md section 10.

The worked example from the spec, also pinned as
fixtures/engine_cases.json's contribution_mid_period_buy_sell_and_dividend case (see
tests/test_engine_cases.py::check_contribution for the fixture-driven run). This file
exercises the same scenario with explicit assertions per open question the spec had to
resolve, so a regression names exactly which rule broke.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.engine.contribution import compute_contribution
from app.engine.errors import MissingPriceError
from app.engine.types import Transaction, TxnType

ISIN_A = "INE100A01016"  # held throughout, pays a dividend mid-period
ISIN_B = "INE200B01023"  # bought mid-period, still held
ISIN_C = "INE300C01030"  # held at start, fully exited mid-period

PERIOD_START = date(2025, 1, 1)
AS_OF = date(2025, 12, 31)

TRANSACTIONS = [
    Transaction(
        isin=ISIN_A,
        txn_date=date(2024, 1, 15),
        txn_type=TxnType.BUY,
        quantity=Decimal("100"),
        price=Decimal("900"),
    ),
    Transaction(
        isin=ISIN_A,
        txn_date=date(2025, 6, 15),
        txn_type=TxnType.DIVIDEND,
        quantity=Decimal("0"),
        price=Decimal("0"),
        dividend_amount=Decimal("4000"),
    ),
    Transaction(
        isin=ISIN_B,
        txn_date=date(2025, 4, 1),
        txn_type=TxnType.BUY,
        quantity=Decimal("50"),
        price=Decimal("2000"),
    ),
    Transaction(
        isin=ISIN_C,
        txn_date=date(2024, 3, 1),
        txn_type=TxnType.BUY,
        quantity=Decimal("100"),
        price=Decimal("400"),
    ),
    Transaction(
        isin=ISIN_C,
        txn_date=date(2025, 7, 1),
        txn_type=TxnType.SELL,
        quantity=Decimal("100"),
        price=Decimal("450"),
    ),
]

START_PRICES = {ISIN_A: Decimal("1000"), ISIN_C: Decimal("500")}
END_PRICES = {ISIN_A: Decimal("1300"), ISIN_B: Decimal("2400")}


def _compute() -> dict[str, object]:
    result = compute_contribution(
        TRANSACTIONS, START_PRICES, END_PRICES, PERIOD_START, AS_OF
    )
    return {c.isin: c for c in result}


def test_holding_bought_mid_period_counts_gain_only_since_purchase() -> None:
    """ISIN B: not held at period_start, so start_value=0 and net_flow absorbs the
    purchase cost -- gain is the appreciation since the buy, not inflated by the cost
    of acquiring the position."""
    by_isin = _compute()
    b = by_isin[ISIN_B]

    assert b.start_value == Decimal("0")
    assert b.end_value == Decimal("120000")
    assert b.net_flow == Decimal("100000")
    assert b.gain == Decimal("20000")


def test_holding_fully_exited_mid_period_excludes_pre_period_gain() -> None:
    """ISIN C: held before period_start at 50,000, sold mid-period for 45,000 proceeds.
    gain must be -5,000 (the loss from period_start's value to the sale) -- NOT the
    position's full realised gain, which would reach back to its 2024 purchase cost of
    40,000 and double-count a prior period's gain into this one."""
    by_isin = _compute()
    c = by_isin[ISIN_C]

    assert c.start_value == Decimal("50000")
    assert c.end_value == Decimal("0")
    assert c.net_flow == Decimal("-45000")
    assert c.gain == Decimal("-5000")


def test_dividends_count_toward_contribution() -> None:
    """ISIN A: no BUY/SELL in the window, only a 4,000 dividend. If dividends were
    excluded, gain would be flat 30,000 (pure price appreciation); with dividends
    counted as return (matching section 5's TWRR Candidate B), it is 34,000."""
    by_isin = _compute()
    a = by_isin[ISIN_A]

    assert a.net_flow == Decimal("-4000")
    assert a.gain == Decimal("34000")


def test_exited_position_appears_in_results() -> None:
    """A fully-sold ISIN must still appear -- docs/PRODUCT_VISION.md's 'which
    investments destroyed value?' needs exactly this row, not a silently shrunk list."""
    by_isin = _compute()
    assert ISIN_C in by_isin


def test_percentages_sum_to_one_and_are_shown_uncapped() -> None:
    """pct_of_total is gain / total_gain for every holding, never capped -- ISIN C's
    negative contribution and ISIN A/B's combined >100% share are both shown as-is."""
    by_isin = _compute()
    total = sum((c.gain for c in by_isin.values()), Decimal("0"))
    assert total == Decimal("49000")

    pct_sum = sum((c.pct_of_total for c in by_isin.values()), Decimal("0"))
    assert abs(pct_sum - Decimal("1")) <= Decimal("0.000001")

    assert by_isin[ISIN_C].pct_of_total is not None
    assert by_isin[ISIN_C].pct_of_total < 0


def test_missing_start_price_for_a_held_isin_raises() -> None:
    """A missing price at period_start must raise MissingPriceError, never be
    substituted with zero -- ENGINE_SPEC section 2's rule applies at both ends of the
    window, not only at as_of."""
    with pytest.raises(MissingPriceError):
        compute_contribution(TRANSACTIONS, {}, END_PRICES, PERIOD_START, AS_OF)


def test_missing_end_price_for_a_held_isin_raises() -> None:
    with pytest.raises(MissingPriceError):
        compute_contribution(TRANSACTIONS, START_PRICES, {}, PERIOD_START, AS_OF)
