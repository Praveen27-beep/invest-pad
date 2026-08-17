"""XIRR and valuation -- ENGINE_SPEC sections 2 and 4."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.engine.errors import MissingPriceError
from app.engine.holdings import compute_holdings
from app.engine.types import Transaction, TxnType
from app.engine.valuation import total_market_value, value_holdings
from app.engine.xirr import (
    PERIOD_TOO_SHORT_WARNING,
    compute_period_xirr,
    compute_xirr,
    compute_xirr_holdings,
    period_warning,
)

ISIN_A = "INE0Q9301021"
ISIN_B = "INE153T01027"


def txn(txn_type: str, qty: str, price: str, day: str, isin: str = ISIN_A, **kw):
    return Transaction(
        isin=isin,
        txn_date=date.fromisoformat(day),
        txn_type=TxnType(txn_type),
        quantity=Decimal(qty),
        price=Decimal(price),
        charges=Decimal(kw.get("charges", "0")),
        dividend_amount=Decimal(kw.get("dividend_amount", "0")),
    )


# --- section 2, valuation ------------------------------------------------------


def test_valuation_derives_every_price_field() -> None:
    holdings = compute_holdings([txn("BUY", "10", "100", "2024-01-10")])
    (valued,) = value_holdings(holdings, {ISIN_A: Decimal("150")})

    assert valued.last_price == Decimal("150")
    assert valued.market_value == Decimal("1500")
    assert valued.unrealised == Decimal("500")
    assert valued.unrealised_pct == Decimal("0.5")
    assert valued.weight_pct == Decimal("1")


def test_weights_are_relative_to_the_whole_book() -> None:
    holdings = compute_holdings(
        [
            txn("BUY", "10", "100", "2024-01-10", isin=ISIN_A),
            txn("BUY", "10", "100", "2024-01-10", isin=ISIN_B),
        ]
    )
    valued = value_holdings(holdings, {ISIN_A: Decimal("300"), ISIN_B: Decimal("100")})
    weights = {h.isin: h.weight_pct for h in valued}
    assert weights[ISIN_A] == Decimal("0.75")
    assert weights[ISIN_B] == Decimal("0.25")


def test_missing_price_raises_and_names_every_offender() -> None:
    """One ISIN per attempt would waste the day of whoever has to find the prices."""
    holdings = compute_holdings(
        [
            txn("BUY", "10", "100", "2024-01-10", isin=ISIN_A),
            txn("BUY", "10", "100", "2024-01-10", isin=ISIN_B),
        ]
    )
    with pytest.raises(MissingPriceError) as excinfo:
        value_holdings(holdings, {})
    assert excinfo.value.isins == sorted([ISIN_A, ISIN_B])
    assert ISIN_A in str(excinfo.value) and ISIN_B in str(excinfo.value)


def test_missing_price_is_never_silently_zero() -> None:
    holdings = compute_holdings(
        [
            txn("BUY", "10", "100", "2024-01-10", isin=ISIN_A),
            txn("BUY", "10", "100", "2024-01-10", isin=ISIN_B),
        ]
    )
    with pytest.raises(MissingPriceError):
        total_market_value(holdings, {ISIN_A: Decimal("150")})


# --- section 4, XIRR -----------------------------------------------------------


def test_exactly_twenty_percent_over_two_years() -> None:
    """100000 in, worth 144000 two years later. 1.44 = (1+r)^2, so r = 20% exactly."""
    result = compute_xirr(
        [txn("BUY", "1000", "100", "2024-08-08")],
        {ISIN_A: Decimal("144")},
        date(2026, 8, 8),
    )
    assert abs(result - Decimal("0.2")) <= Decimal("0.0005")


def test_terminal_flow_is_what_a_tradebook_cannot_supply() -> None:
    """Same trades, different closing price, different answer."""
    rows = [txn("BUY", "1000", "100", "2024-08-08")]
    higher = compute_xirr(rows, {ISIN_A: Decimal("200")}, date(2026, 8, 8))
    lower = compute_xirr(rows, {ISIN_A: Decimal("110")}, date(2026, 8, 8))
    assert higher > lower


def test_dividends_count_as_inflow() -> None:
    rows = [txn("BUY", "1000", "100", "2024-08-08")]
    with_dividend = [*rows, txn("DIVIDEND", "0", "0", "2025-08-08", dividend_amount="5000")]
    assert compute_xirr(with_dividend, {ISIN_A: Decimal("144")}, date(2026, 8, 8)) > compute_xirr(
        rows, {ISIN_A: Decimal("144")}, date(2026, 8, 8)
    )


def test_corporate_actions_contribute_no_cash_flow() -> None:
    """Shares moved, not cash. A bonus must not register as a deposit or a return."""
    rows = [txn("BUY", "1000", "100", "2024-08-08")]
    with_bonus = [*rows, txn("BONUS", "1000", "0", "2025-08-08")]
    # Same money in, same money out: 2000 shares at 72 is the same 144000.
    assert compute_xirr(rows, {ISIN_A: Decimal("144")}, date(2026, 8, 8)) == compute_xirr(
        with_bonus, {ISIN_A: Decimal("72")}, date(2026, 8, 8)
    )


def test_returns_none_rather_than_zero_when_unanswerable() -> None:
    """Zero would be a lie the caller cannot tell apart from a real result."""
    assert compute_xirr([], {}, date(2026, 8, 8)) is None


def test_no_sign_change_returns_none() -> None:
    rows = [txn("BUY", "10", "100", "2024-08-08")]
    assert compute_xirr(rows, {ISIN_A: Decimal("0")}, date(2026, 8, 8)) is None


def test_holdings_variant_excludes_fully_exited_positions() -> None:
    """The gap between the two variants is the insight; they must not coincide here."""
    rows = [
        txn("BUY", "100", "100", "2024-08-08", isin=ISIN_A),
        txn("BUY", "100", "100", "2024-08-08", isin=ISIN_B),
        txn("SELL", "100", "400", "2025-08-08", isin=ISIN_B),
    ]
    prices = {ISIN_A: Decimal("50")}

    all_txns = compute_xirr(rows, {**prices, ISIN_B: Decimal("0")}, date(2026, 8, 8))
    held_only = compute_xirr_holdings(rows, prices, date(2026, 8, 8))

    # B tripled and was sold; A halved and is retained. The live book is worse.
    assert held_only < all_txns


def test_as_of_replays_history() -> None:
    rows = [
        txn("BUY", "1000", "100", "2024-08-08"),
        txn("BUY", "1000", "500", "2026-01-01"),
    ]
    early = compute_xirr(rows, {ISIN_A: Decimal("144")}, date(2026, 8, 8))
    assert early is not None
    # Truncating before the second buy must change the answer.
    truncated = compute_xirr(rows, {ISIN_A: Decimal("144")}, date(2025, 8, 8))
    assert truncated != early


# --- section 4, period XIRR ----------------------------------------------------


def test_mid_period_deposit_is_not_counted_as_growth() -> None:
    """The fixture case, asserted directly. Endpoints-only would give ~2.05."""
    result = compute_period_xirr(
        [txn("BUY", "10000", "200", "2026-08-10")],
        {ISIN_A: Decimal("305")},
        date(2025, 8, 11),
        Decimal("1000000"),
        date(2026, 8, 11),
    )
    assert abs(result - Decimal("0.05")) <= Decimal("0.02")
    assert result < Decimal("0.1"), "mid-period deposit was counted as return"


def test_transactions_on_the_start_date_are_not_double_counted() -> None:
    """opening_value already reflects a transaction dated exactly on start_date; it must
    not also appear as a fresh cash outflow, or the outflow is double-counted.

    Checked against a position built entirely BEFORE the period instead of an empty
    ledger: both end up holding the identical 100 shares at ``as_of``, so if the
    same-day buy were (wrongly) also counted as a flow, only the same-day-buy scenario
    would move -- the two must land on the same answer.
    """
    same_day = compute_period_xirr(
        [txn("BUY", "100", "100", "2025-08-11")],
        {ISIN_A: Decimal("150")}, date(2025, 8, 11), Decimal("10000"), date(2026, 8, 11),
    )
    pre_existing = compute_period_xirr(
        [txn("BUY", "100", "100", "2020-01-01")],
        {ISIN_A: Decimal("150")}, date(2025, 8, 11), Decimal("10000"), date(2026, 8, 11),
    )
    assert same_day == pre_existing


def test_a_position_untouched_during_the_period_still_counts_in_the_terminal_value() -> None:
    """A buy-and-hold position with no in-period transaction must not vanish from the
    closing value. The terminal flow is the current market value of EVERYTHING held at
    ``as_of`` (ENGINE_SPEC section 4), not only of positions traded during the window --
    a regression guard for a bug where the terminal replay used only post-``start_date``
    rows and so silently dropped every untouched position's contribution to zero."""
    rows = [txn("BUY", "100", "100", "2020-01-01")]
    result = compute_period_xirr(
        rows, {ISIN_A: Decimal("200")}, date(2025, 8, 11), Decimal("15000"), date(2026, 8, 11)
    )
    assert result is not None
    # 15000 -> 20000 over exactly one year: XIRR is exactly the simple return.
    assert abs(result - Decimal("0.33333")) <= Decimal("0.001")


def test_short_window_is_computed_but_flagged() -> None:
    """Annualising a six-day return is valid arithmetic and practical nonsense."""
    assert period_warning(date(2026, 8, 5), date(2026, 8, 11)) == PERIOD_TOO_SHORT_WARNING
    assert period_warning(date(2025, 8, 11), date(2026, 8, 11)) is None
