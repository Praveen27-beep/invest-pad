"""value_holdings -- ENGINE_SPEC section 2, plus per-holding CAGR (section 5).

CAGR's start_value/start_date for a multi-buy position is not written down anywhere in
ENGINE_SPEC.md or fixtures/engine_cases.json -- confirmed a genuine gap, not just an
unread corner, before writing this. The convention pinned here (start_value = the
weighted-average `invested` cost pool, start_date = `first_buy_date`, the earliest
acquisition) was a product decision, not an invented one: treat the whole current cost
pool as a single lump sum put in on the first buy date.
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

import pytest
from app.engine.holdings import compute_holdings
from app.engine.types import Transaction, TxnType
from app.engine.valuation import value_holdings

ISIN = "INE153T01027"


def txn(txn_type: str, qty: str, price: str, day: str, isin: str = ISIN, **kw):
    return Transaction(
        isin=isin,
        txn_date=date.fromisoformat(day),
        txn_type=TxnType(txn_type),
        quantity=Decimal(qty),
        price=Decimal(price),
        charges=Decimal(kw.get("charges", "0")),
    )


def test_cagr_is_none_without_an_as_of() -> None:
    """The engine never reads the clock (see compute_snapshot's docstring) -- so with
    no dated reference point, CAGR is undefined rather than silently using today."""
    holdings = compute_holdings([txn("BUY", "100", "100", "2024-01-10")])
    (valued,) = value_holdings(holdings, {ISIN: Decimal("150")})
    assert valued.market_value == Decimal("15000")
    assert valued.cagr is None


def test_cagr_single_buy_matches_hand_calculation() -> None:
    """BUY 100 @ 100 on 2020-01-01, priced 200 on 2025-01-01.

    invested = 10,000, market_value = 20,000. days = (date(2025,1,1) -
    date(2020,1,1)).days == 1827 -- five calendar years spanning two leap years
    (2020, 2024), confirmed independently below rather than assumed as 365*5.

    Expected value cross-checked via `math.pow` (plain float exponentiation, not the
    Decimal `**` the implementation uses) so a bug in Decimal's power operator would
    not slip past a test that used the exact same code path to build its own answer.
    """
    holdings = compute_holdings([txn("BUY", "100", "100", "2020-01-01")])
    as_of = date(2025, 1, 1)
    days = (as_of - date(2020, 1, 1)).days
    assert days == 1827

    (valued,) = value_holdings(holdings, {ISIN: Decimal("200")}, as_of=as_of)
    assert valued.invested == Decimal("10000")
    assert valued.market_value == Decimal("20000")
    assert valued.cagr is not None

    expected = math.pow(20000 / 10000, 365.25 / 1827) - 1
    assert float(valued.cagr) == pytest.approx(expected, rel=1e-9)


def test_cagr_multi_buy_uses_first_buy_date_and_blended_invested() -> None:
    """Two buys at different dates and prices -- the case ENGINE_SPEC is silent on.

    qty 200, pool 20,000 + 30,000 = 50,000, avg 250 (matches ENGINE_SPEC section 1's
    own two-buy worked example). start_date is the EARLIER of the two buy dates, not
    the later one and not some blended date -- confirmed against first_buy_date
    directly, which is its own separately-tested contract (test_holdings.py).
    """
    holdings = compute_holdings(
        [
            txn("BUY", "100", "200", "2020-01-10"),
            txn("BUY", "100", "300", "2023-06-10"),
        ]
    )
    (h,) = holdings
    assert h.first_buy_date == date(2020, 1, 10)
    assert h.invested == Decimal("50000")

    as_of = date(2025, 1, 10)
    (valued,) = value_holdings(holdings, {ISIN: Decimal("400")}, as_of=as_of)
    days = (as_of - date(2020, 1, 10)).days

    expected = math.pow(80000 / 50000, 365.25 / days) - 1
    assert float(valued.cagr) == pytest.approx(expected, rel=1e-9)


def test_cagr_is_none_when_bought_on_as_of_itself() -> None:
    """Zero holding days -- 365.25 / 0 is undefined, not an extreme rate."""
    holdings = compute_holdings([txn("BUY", "100", "100", "2024-06-01")])
    (valued,) = value_holdings(
        holdings, {ISIN: Decimal("110")}, as_of=date(2024, 6, 1)
    )
    assert valued.cagr is None


def test_cagr_is_none_when_cost_basis_is_not_positive() -> None:
    """Sell a position out completely, then reopen it via a bonus allotment: the
    pool stays at 0 (BONUS never moves the pool) even though `first_buy_date` still
    points at the original 2024-01-01 buy -- `first_buy` is sticky across the whole
    replay, per engine/holdings.py. A zero cost basis is not a free lump sum; there is
    no `start_value` to raise to a power, so CAGR is None rather than +inf or 0."""
    holdings = compute_holdings(
        [
            txn("BUY", "100", "100", "2024-01-01"),
            txn("SELL", "100", "150", "2024-02-01"),
            txn("BONUS", "50", "0", "2024-03-01"),
        ]
    )
    (h,) = holdings
    assert h.invested == Decimal("0")
    assert h.first_buy_date == date(2024, 1, 1)

    (valued,) = value_holdings(
        holdings, {ISIN: Decimal("10")}, as_of=date(2025, 1, 1)
    )
    assert valued.cagr is None


def test_cagr_is_none_when_position_has_no_acquisition_to_anchor_a_start_date() -> None:
    """A position that entered the ledger purely via a corporate action (a demerger
    allotment with no corresponding BUY for this ISIN) has no acquisition date at
    all -- `first_buy_date` is None, so there is no start date to annualise from, and
    guessing one would be inventing financial logic ENGINE_SPEC does not state."""
    holdings = compute_holdings([txn("DEMERGER_IN", "50", "0", "2024-03-01")])
    (h,) = holdings
    assert h.first_buy_date is None
    assert h.invested == Decimal("0")

    (valued,) = value_holdings(
        holdings, {ISIN: Decimal("10")}, as_of=date(2025, 1, 1)
    )
    assert valued.cagr is None


def test_missing_price_still_raises_regardless_of_as_of() -> None:
    from app.engine.errors import MissingPriceError

    holdings = compute_holdings([txn("BUY", "100", "100", "2024-01-10")])
    with pytest.raises(MissingPriceError):
        value_holdings(holdings, {}, as_of=date(2024, 6, 1))
