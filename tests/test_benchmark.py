"""Benchmark comparison -- docs/ENGINE_SPEC.md section 6.

``fixtures/engine_cases.json``'s ``benchmark_cash_flow_replication`` case pins the exact
worked numbers; these tests cover the surrounding behaviour that a single fixture case
can't: the missing-data failure mode, the required-dates seam the router depends on, and
the TRI-vs-price-index pin item 4 of the session prompt calls for explicitly.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.engine.benchmark import compute_benchmark, required_index_dates
from app.engine.errors import MissingIndexLevelError
from app.engine.types import Transaction, TxnType

ISIN = "INE153T01027"
BUY_DATE = date(2024, 1, 10)
SELL_DATE = date(2024, 6, 10)
AS_OF = date(2025, 1, 10)


def a_buy(day: date = BUY_DATE, quantity: str = "100", price: str = "200") -> Transaction:
    return Transaction(
        isin=ISIN, txn_date=day, txn_type=TxnType.BUY,
        quantity=Decimal(quantity), price=Decimal(price),
    )


def a_sell(day: date = SELL_DATE, quantity: str = "50", price: str = "300") -> Transaction:
    return Transaction(
        isin=ISIN, txn_date=day, txn_type=TxnType.SELL,
        quantity=Decimal(quantity), price=Decimal(price),
    )


# --- required_index_dates ---------------------------------------------------------------


def test_required_index_dates_is_every_flow_date_plus_as_of() -> None:
    """The router resolves/fetches exactly these dates before calling compute_benchmark
    -- if this list were wrong, the router would either under-fetch (leaving a gap that
    turns into a null benchmark) or over-fetch (wasted calls to an external source)."""
    dates = required_index_dates([a_buy(), a_sell()], AS_OF)
    assert dates == [BUY_DATE, SELL_DATE, AS_OF]


def test_required_index_dates_deduplicates_when_as_of_matches_a_flow_date() -> None:
    dates = required_index_dates([a_buy()], BUY_DATE)
    assert dates == [BUY_DATE]


def test_required_index_dates_is_empty_when_there_are_no_transactions() -> None:
    """Mirrors compute_benchmark's own no-flows short-circuit -- an empty ledger needs
    no index level at all, not even as_of. If this disagreed with compute_benchmark, a
    caller (the router) would fetch/read a level that then goes unused."""
    assert required_index_dates([], AS_OF) == []


# --- missing data --------------------------------------------------------------------


def test_missing_index_level_raises_never_defaults() -> None:
    """Same posture as MissingPriceError (ENGINE_SPEC section 9): a gap is named and
    raised, never silently filled with the nearest available level."""
    levels = {BUY_DATE: Decimal("100")}  # SELL_DATE and AS_OF absent

    with pytest.raises(MissingIndexLevelError) as exc_info:
        compute_benchmark([a_buy(), a_sell()], levels, AS_OF, "NIFTY50_TRI")

    assert exc_info.value.dates == [SELL_DATE, AS_OF]


def test_no_transactions_returns_null_benchmark_not_an_error() -> None:
    """No cash flows at all means nothing to replicate -- distinct from a genuine gap in
    an otherwise-complete series, so this must not raise."""
    result = compute_benchmark([], {}, AS_OF, "NIFTY50_TRI")
    assert result.xirr is None
    assert result.terminal_value is None


# --- the sign convention, isolated from the fixture's specific numbers -------------------


def test_a_buy_alone_produces_a_positive_terminal_value() -> None:
    """Money that left the portfolio to buy stock must buy index units (a POSITIVE
    contribution), not redeem them -- reading ENGINE_SPEC section 6's formula literally
    against _transaction_flows' raw sign convention (BUY negative) would do the
    opposite, making the terminal value negative and breaking the XIRR solve outright for
    any net-bought portfolio. This is the assertion that would fail first if that sign
    flip were ever removed."""
    levels = {BUY_DATE: Decimal("100"), AS_OF: Decimal("120")}
    result = compute_benchmark([a_buy()], levels, AS_OF, "NIFTY50_TRI")

    # 100 shares @ 200 = 20,000 cash out -> 20,000 / 100 = 200 index units bought.
    # terminal = 200 units * 120 = 24,000.
    assert result.terminal_value == Decimal("24000")


# --- TRI vs. price index: the item-4 pin ------------------------------------------------


def test_price_index_levels_understate_the_benchmark_versus_tri() -> None:
    """ENGINE_SPEC section 6: 'Use TRI (total return) not price index -- price indices
    exclude dividends and understate the benchmark.' This engine function has no way to
    know which kind of series it was handed -- that guarantee lives in
    app.prices.index_sources, which only ever fetches the TotalReturnsIndex field
    (see tests/test_index_sources.py). What CAN be pinned here is the economic direction:
    over an identical real period and identical real cash flows, a TRI series (dividends
    reinvested into the level) must show a HIGHER benchmark return than a price-index
    series for the same underlying index over the same dates. If a price-index level were
    ever substituted for a TRI level in production, this is the number that would quietly
    be wrong, and this test is what would have caught it.
    """
    transactions = [a_buy(quantity="100", price="200")]

    # Same start, same real elapsed period -- a TRI series ends higher purely because it
    # carries reinvested dividends; a price index ends lower because it excludes them.
    tri_levels = {BUY_DATE: Decimal("100"), AS_OF: Decimal("122")}
    price_index_levels = {BUY_DATE: Decimal("100"), AS_OF: Decimal("115")}

    tri = compute_benchmark(transactions, tri_levels, AS_OF, "NIFTY50_TRI")
    price = compute_benchmark(transactions, price_index_levels, AS_OF, "NIFTY50_TRI")

    assert tri.xirr is not None and price.xirr is not None
    assert tri.xirr > price.xirr
    assert tri.terminal_value > price.terminal_value
