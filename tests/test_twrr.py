"""TWRR -- docs/ENGINE_SPEC.md section 5.

``fixtures/engine_cases.json``'s ``twrr_dividend_and_contribution_sub_periods`` case pins
the exact worked numbers; these tests cover the surrounding behaviour that a single
fixture case can't: the sign convention isolated from the fixture's specific numbers, the
"fewer than two snapshots" / "zero opening value" / "non-positive elapsed span" guards,
and gap handling across a missed backfill day.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.engine.twrr import compute_twrr
from app.engine.types import Snapshot, Transaction, TxnType

ISIN = "INE153T01027"


def a_snapshot(day: date, market_value: str, invested: str | None = None) -> Snapshot:
    return Snapshot(
        as_of=day,
        invested=Decimal(invested if invested is not None else market_value),
        market_value=Decimal(market_value),
    )


def a_buy(day: date, quantity: str = "50", price: str = "200") -> Transaction:
    return Transaction(
        isin=ISIN, txn_date=day, txn_type=TxnType.BUY,
        quantity=Decimal(quantity), price=Decimal(price),
    )


def a_sell(day: date, quantity: str = "50", price: str = "200") -> Transaction:
    return Transaction(
        isin=ISIN, txn_date=day, txn_type=TxnType.SELL,
        quantity=Decimal(quantity), price=Decimal(price),
    )


def a_dividend(day: date, amount: str) -> Transaction:
    return Transaction(
        isin=ISIN, txn_date=day, txn_type=TxnType.DIVIDEND,
        quantity=Decimal("0"), price=Decimal("0"), dividend_amount=Decimal(amount),
    )


# --- guards: cannot support an answer -----------------------------------------------


def test_fewer_than_two_snapshots_returns_none() -> None:
    result = compute_twrr([a_snapshot(date(2024, 1, 1), "100000")], [])
    assert result is None


def test_empty_series_returns_none() -> None:
    assert compute_twrr([], []) is None


def test_zero_opening_value_returns_none() -> None:
    """A sub-period that opens at zero (the account held nothing yet) has an undefined
    return-from-zero ratio -- None, never a divide-by-zero, never a fabricated rate."""
    series = [
        a_snapshot(date(2024, 1, 1), "0"),
        a_snapshot(date(2024, 7, 1), "50000"),
    ]
    assert compute_twrr(series, [a_buy(date(2024, 1, 1))]) is None


def test_same_day_series_returns_none() -> None:
    """Zero elapsed span between the first and last snapshot has no well-defined
    annualised rate."""
    series = [
        a_snapshot(date(2024, 1, 1), "100000"),
        a_snapshot(date(2024, 1, 1), "100000"),
    ]
    assert compute_twrr(series, []) is None


def test_total_wipeout_returns_none() -> None:
    """A chained product that reaches zero or below has no well-defined annualised rate
    -- same reasoning app.engine.valuation._cagr uses for a non-positive base."""
    series = [
        a_snapshot(date(2024, 1, 1), "100000"),
        a_snapshot(date(2024, 7, 1), "0"),
    ]
    assert compute_twrr(series, []) is None


# --- the sign convention, isolated from the fixture's specific numbers ---------------


def test_no_flows_is_pure_price_return() -> None:
    """No transactions between two snapshots: the sub-period return is exactly the
    price change, no flow adjustment involved."""
    series = [
        a_snapshot(date(2024, 1, 1), "100000"),
        a_snapshot(date(2025, 1, 1), "110000"),
    ]
    result = compute_twrr(series, [])
    assert result is not None
    # 366-day span (2024 is a leap year); cumulative return is exactly 10%.
    expected = Decimal("1.10") ** (Decimal("365.25") / Decimal("366")) - 1
    assert abs(result - expected) <= Decimal("0.000001")


def test_a_buy_is_backed_out_as_an_inflow() -> None:
    """A BUY funded mid-period must not be counted as portfolio growth -- backing it out
    of the sub-period's flow is what keeps a contribution from inflating the return the
    same way section 4's mid-period-deposit XIRR case guards against."""
    series = [
        a_snapshot(date(2024, 1, 1), "100000"),
        a_snapshot(date(2024, 7, 1), "118000"),
    ]
    # 50 @ 200 = 10,000 contributed mid-period. Pure return: (118000-10000)/100000-1 = 8%.
    result = compute_twrr(series, [a_buy(date(2024, 3, 1))])
    assert result is not None
    total_days = (date(2024, 7, 1) - date(2024, 1, 1)).days
    expected = Decimal("1.08") ** (Decimal("365.25") / Decimal(total_days)) - 1
    assert abs(result - expected) <= Decimal("0.000001")


def test_dividend_is_credited_back_as_return_not_excluded() -> None:
    """The confirmed convention (ENGINE_SPEC section 5, Candidate B): a dividend is
    signed as a portfolio outflow, which is mathematically equivalent to crediting it
    back into the sub-period's return -- so a portfolio with flat market value but a
    dividend payout shows a POSITIVE return, not zero."""
    series = [
        a_snapshot(date(2024, 1, 1), "100000"),
        a_snapshot(date(2024, 7, 1), "100000"),  # market value unchanged
    ]
    result = compute_twrr(series, [a_dividend(date(2024, 4, 1), "2000")])
    assert result is not None and result > 0, (
        "a dividend must show up as positive return, not vanish the way excluding it "
        "from flows entirely would make it"
    )


def test_a_sell_is_backed_out_the_same_way_as_a_dividend() -> None:
    """SELL and DIVIDEND share a sign (both leave the tracked portfolio) -- two series
    with the same net portfolio-side cash removal must produce the same return."""
    series_sell = [
        a_snapshot(date(2024, 1, 1), "100000"),
        a_snapshot(date(2024, 7, 1), "88000"),
    ]
    series_dividend = [
        a_snapshot(date(2024, 1, 1), "100000"),
        a_snapshot(date(2024, 7, 1), "88000"),
    ]
    sell_result = compute_twrr(series_sell, [a_sell(date(2024, 4, 1), quantity="50", price="200")])
    dividend_result = compute_twrr(series_dividend, [a_dividend(date(2024, 4, 1), "10000")])
    assert sell_result is not None and dividend_result is not None
    assert abs(sell_result - dividend_result) <= Decimal("0.000000001")


# --- gap handling ---------------------------------------------------------------------


def test_gap_between_persisted_snapshots_widens_that_sub_period() -> None:
    """A missed backfill day is not filled or interpolated -- the chain simply treats
    the two rows either side of the gap as one wider sub-period, folding in every flow
    dated inside the gap."""
    series = [
        a_snapshot(date(2024, 1, 1), "100000"),
        # 2024-04-01 never persisted (a missed backfill day).
        a_snapshot(date(2024, 7, 1), "118000"),
    ]
    result = compute_twrr(series, [a_buy(date(2024, 3, 1))])
    assert result is not None
    total_days = (date(2024, 7, 1) - date(2024, 1, 1)).days
    expected = Decimal("1.08") ** (Decimal("365.25") / Decimal(total_days)) - 1
    assert abs(result - expected) <= Decimal("0.000001")


def test_unsorted_input_is_chained_in_date_order() -> None:
    """The series is sorted defensively -- a caller passing rows out of order must not
    silently chain them backwards."""
    in_order = [
        a_snapshot(date(2024, 1, 1), "100000"),
        a_snapshot(date(2024, 7, 1), "110000"),
    ]
    reversed_order = list(reversed(in_order))
    assert compute_twrr(in_order, []) == compute_twrr(reversed_order, [])
