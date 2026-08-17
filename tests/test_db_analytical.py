"""GET /investors/{id}/performance -- app.routers.analytical.performance, against a real
database. See docs/FULL_VISION_BACKEND_ROADMAP.md sections A3 and A4.

Calls the route handler directly with the ``db`` fixture's connection, the same pattern
tests/test_db_reconcile.py uses for ``reconcile.reconcile_holdings``: a FastAPI route
decorator returns the plain function underneath, so no HTTP client is needed to exercise
it against a real Postgres cluster. Transactions are seeded through
``transactions.create_transactions`` rather than raw SQL, so the ledger this replays is
written the same way the real ingestion path writes it.

``performance`` now takes ``request: Request`` (for the request-id in the fy_xirr-omitted
log line) -- a minimal Starlette ``Request`` with no ASGI server behind it is enough,
since only ``request.state`` is ever read.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.db import prices as dbprices
from app.db.repository import load_transactions
from app.engine.snapshot import compute_snapshot
from app.engine.xirr import PERIOD_TOO_SHORT_WARNING, compute_fy_xirr, compute_period_xirr
from app.prices.pipe import MergedPrice
from app.routers.analytical import performance
from app.routers.transactions import create_transactions
from app.schemas.transactions import TransactionIn
from starlette.requests import Request

pytestmark = pytest.mark.db

ISIN_A = "INE153T01027"
ISIN_B = "INE242A01010"

#: A fixed FY window: 2024-04-01 is the FY start for any as_of in FY 2024-25.
FY_START = date(2024, 4, 1)
AS_OF = date(2024, 9, 30)


def fake_request() -> Request:
    """A minimal Starlette Request -- enough to exercise ``request.state`` without an
    ASGI server, the same as calling the handler directly needs no HTTP client."""
    return Request({"type": "http", "headers": []})


def seed_price(db, isin: str, on: date, close: str) -> None:
    dbprices.upsert_prices(
        db, [MergedPrice(isin=isin, price_date=on, close=Decimal(close), source="NSE_BHAVCOPY")]
    )


def buy(
    account_id: str, isin: str, day: date, quantity: str, price: str, ref: str
) -> TransactionIn:
    return TransactionIn(
        account_id=account_id,
        isin=isin,
        txn_date=day,
        txn_type="BUY",
        quantity=quantity,
        price=price,
        source="MANUAL",
        source_ref=ref,
    )


def sell(
    account_id: str, isin: str, day: date, quantity: str, price: str, ref: str
) -> TransactionIn:
    return TransactionIn(
        account_id=account_id,
        isin=isin,
        txn_date=day,
        txn_type="SELL",
        quantity=quantity,
        price=price,
        source="MANUAL",
        source_ref=ref,
    )


def add_unadvised_account(db, investor_id: str) -> str:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO account (investor_id, broker, is_advised) "
            "VALUES (%s, 'GROWW', false) RETURNING id",
            (investor_id,),
        )
        account_id = str(cur.fetchone()[0])
    db.commit()
    return account_id


def add_security(db, isin: str, symbol: str) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO security (isin, symbol, exchange) VALUES (%s, %s, 'NSE') "
            "ON CONFLICT DO NOTHING",
            (isin, symbol),
        )
    db.commit()


def set_onboarding_date(db, investor_id: str, on: date) -> None:
    with db.cursor() as cur:
        cur.execute(
            "UPDATE investor SET onboarding_date = %s WHERE id = %s", (on, investor_id)
        )
    db.commit()


# --- fy_xirr -----------------------------------------------------------------------


def test_fy_xirr_uses_the_real_1_april_market_value_as_opening_value(db, investor) -> None:
    """A buy-and-hold position, priced both on 1 April and at as_of. fy_xirr must match
    what compute_fy_xirr itself returns when fed the SAME 1-April snapshot -- pinning
    that the router derives opening_value from a real historical snapshot, not a
    shortcut, per compute_fy_xirr's docstring."""
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    create_transactions(
        investor,
        [buy(advised_account, ISIN_A, date(2023, 1, 10), "100", "100", "T1")],
        connection=db,
    )
    seed_price(db, ISIN_A, FY_START, "150")
    seed_price(db, ISIN_A, AS_OF, "200")

    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["fy_xirr"] is not None

    transactions = load_transactions(db, investor_id=investor)
    opening = compute_snapshot(transactions, {ISIN_A: Decimal("150")}, FY_START)
    expected = compute_fy_xirr(transactions, {ISIN_A: Decimal("200")}, opening.market_value, AS_OF)
    assert result["fy_xirr"] == pytest.approx(float(expected))


def test_fy_xirr_is_null_not_a_guess_when_no_1_april_price_exists(db, investor, caplog) -> None:
    """No price exists on or before 1 April for a held ISIN. fy_xirr must come back
    null -- never today's price, never the nearest available date -- and the omission
    must be logged, not silently swallowed. The rest of the response is unaffected: this
    is not a whole-request failure."""
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    create_transactions(
        investor,
        [buy(advised_account, ISIN_A, date(2023, 1, 10), "100", "100", "T1")],
        connection=db,
    )
    # Only a price at as_of -- nothing anywhere near 1 April.
    seed_price(db, ISIN_A, AS_OF, "200")

    with caplog.at_level(logging.WARNING, logger="app"):
        result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["fy_xirr"] is None
    assert result["xirr_holdings"] is not None
    assert result["market_value"] is not None
    assert "fy_xirr omitted" in caplog.text
    assert ISIN_A in caplog.text


def test_fy_xirr_is_null_when_no_holdings_are_priced_at_all(db, investor) -> None:
    """No transactions at all -- there is nothing held at 1 April, so opening_value is
    legitimately zero and fy_xirr is computed (or None from too few flows), never an
    error. Distinguishes 'nothing held' from 'a held ISIN has no price'."""
    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)
    assert result["xirr_all"] is None
    assert result["xirr_holdings"] is None
    assert result["fy_xirr"] is None


# --- period_xirr (adviser onboarding) -------------------------------------------------

ONBOARDING = date(2023, 6, 1)


def test_period_xirr_uses_the_real_onboarding_date_market_value_as_opening_value(
    db, investor
) -> None:
    """A buy-and-hold position, priced both on the onboarding_date and at as_of.
    period_xirr must match what compute_period_xirr itself returns when fed the SAME
    onboarding-date snapshot -- pinning that the router derives opening_value from a
    real historical snapshot, not a shortcut, per compute_period_xirr's docstring and
    the mid-period-deposit-not-inflated case in fixtures/engine_cases.json."""
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    set_onboarding_date(db, investor, ONBOARDING)
    create_transactions(
        investor,
        [buy(advised_account, ISIN_A, date(2023, 1, 10), "100", "100", "T1")],
        connection=db,
    )
    seed_price(db, ISIN_A, ONBOARDING, "150")
    seed_price(db, ISIN_A, AS_OF, "200")

    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["period_xirr"] is not None
    assert result["period_start"] == ONBOARDING

    transactions = load_transactions(db, investor_id=investor)
    opening = compute_snapshot(transactions, {ISIN_A: Decimal("150")}, ONBOARDING)
    expected = compute_period_xirr(
        transactions, {ISIN_A: Decimal("200")}, ONBOARDING, opening.market_value, AS_OF
    )
    assert result["period_xirr"] == pytest.approx(float(expected))


def test_period_xirr_is_null_not_a_guess_when_no_onboarding_date_price_exists(
    db, investor, caplog
) -> None:
    """No price exists on or before onboarding_date for a held ISIN. period_xirr must
    come back null -- never today's price, never the nearest available date -- and the
    omission must be logged, not silently swallowed."""
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    set_onboarding_date(db, investor, ONBOARDING)
    create_transactions(
        investor,
        [buy(advised_account, ISIN_A, date(2023, 1, 10), "100", "100", "T1")],
        connection=db,
    )
    # Only a price at as_of -- nothing anywhere near onboarding_date.
    seed_price(db, ISIN_A, AS_OF, "200")

    with caplog.at_level(logging.WARNING, logger="app"):
        result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["period_xirr"] is None
    assert result["period_start"] is None
    assert result["warning"] is None
    assert result["xirr_holdings"] is not None
    assert "period_xirr omitted" in caplog.text
    assert ISIN_A in caplog.text


def test_period_xirr_is_null_when_the_investor_has_no_onboarding_date(db, investor) -> None:
    """No onboarding_date is set at all -- the common case today. Omitted, not guessed;
    a case fy_xirr can't structurally have, since financial_year_start is always
    computable."""
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    create_transactions(
        investor,
        [buy(advised_account, ISIN_A, date(2023, 1, 10), "100", "100", "T1")],
        connection=db,
    )
    seed_price(db, ISIN_A, AS_OF, "200")

    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["period_xirr"] is None
    assert result["period_start"] is None
    assert result["warning"] is None


def test_period_xirr_is_null_when_onboarding_date_is_after_as_of(db, investor) -> None:
    """A historical replay dated before the investor's onboarding_date. onboarding_date
    is stored independently of any given request's as_of (a free query param), unlike
    financial_year_start(as_of) which is always <= as_of by construction -- so this has
    to be guarded explicitly rather than assumed, or period_warning would see a negative
    day span and wrongly fire 'period too short' on a metric that was never computed."""
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    set_onboarding_date(db, investor, AS_OF + timedelta(days=10))
    create_transactions(
        investor,
        [buy(advised_account, ISIN_A, date(2023, 1, 10), "100", "100", "T1")],
        connection=db,
    )
    seed_price(db, ISIN_A, AS_OF, "200")

    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["period_xirr"] is None
    assert result["period_start"] is None
    assert result["warning"] is None


def test_period_warning_fires_when_the_window_is_under_90_days(db, investor) -> None:
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    onboarding = AS_OF - timedelta(days=30)
    set_onboarding_date(db, investor, onboarding)
    create_transactions(
        investor,
        [buy(advised_account, ISIN_A, date(2023, 1, 10), "100", "100", "T1")],
        connection=db,
    )
    seed_price(db, ISIN_A, onboarding, "150")
    seed_price(db, ISIN_A, AS_OF, "160")

    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["period_xirr"] is not None
    assert result["warning"] == PERIOD_TOO_SHORT_WARNING


def test_period_warning_does_not_fire_when_the_window_is_90_days_or_more(db, investor) -> None:
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    onboarding = AS_OF - timedelta(days=200)
    set_onboarding_date(db, investor, onboarding)
    create_transactions(
        investor,
        [buy(advised_account, ISIN_A, date(2023, 1, 10), "100", "100", "T1")],
        connection=db,
    )
    seed_price(db, ISIN_A, onboarding, "150")
    seed_price(db, ISIN_A, AS_OF, "200")

    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["period_xirr"] is not None
    assert result["warning"] is None


# --- advised_only --------------------------------------------------------------------


def test_advised_only_restricts_performance_to_the_advised_account(db, investor) -> None:
    unadvised_account = add_unadvised_account(db, investor)
    add_security(db, ISIN_B, "SECB")
    create_transactions(
        investor,
        [
            buy(os.environ["_TEST_ACCOUNT_ID"], ISIN_A, date(2023, 1, 10), "100", "100", "ADV"),
            buy(unadvised_account, ISIN_B, date(2023, 1, 10), "50", "300", "UNADV"),
        ],
        connection=db,
    )
    seed_price(db, ISIN_A, AS_OF, "150")
    seed_price(db, ISIN_B, AS_OF, "400")

    everything = performance(fake_request(), investor, as_of=AS_OF, connection=db)
    advised_only = performance(
        fake_request(), investor, as_of=AS_OF, advised_only=True, connection=db
    )

    assert Decimal(advised_only["invested"]) == Decimal("10000")
    assert Decimal(everything["invested"]) == Decimal("25000")


def test_advised_only_defaults_to_false(db, investor) -> None:
    unadvised_account = add_unadvised_account(db, investor)
    add_security(db, ISIN_B, "SECB")
    create_transactions(
        investor,
        [
            buy(os.environ["_TEST_ACCOUNT_ID"], ISIN_A, date(2023, 1, 10), "100", "100", "ADV"),
            buy(unadvised_account, ISIN_B, date(2023, 1, 10), "50", "300", "UNADV"),
        ],
        connection=db,
    )
    seed_price(db, ISIN_A, AS_OF, "150")
    seed_price(db, ISIN_B, AS_OF, "400")

    default = performance(fake_request(), investor, as_of=AS_OF, connection=db)
    assert Decimal(default["invested"]) == Decimal("25000")


# --- absolute_return / cagr -- ENGINE_SPEC section 5 -----------------------------------


def test_absolute_return_uses_net_lifetime_cash_contributed(db, investor) -> None:
    """BUY 100@100 (outflow 10000), SELL 40@150 (inflow 6000): net_invested = 4000.
    Remaining 60 shares priced at 200 -> market_value 12000. realised_to_date (FIFO,
    40 of the original 100@100 lot) = 6000 - 4000 = 2000.
    absolute_return = (12000 + 2000 - 4000) / 4000 = 2.5.
    """
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    create_transactions(
        investor,
        [
            buy(advised_account, ISIN_A, date(2023, 1, 10), "100", "100", "T1"),
            sell(advised_account, ISIN_A, date(2024, 1, 10), "40", "150", "T2"),
        ],
        connection=db,
    )
    seed_price(db, ISIN_A, AS_OF, "200")

    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["absolute_return"] == pytest.approx(2.5)


def test_absolute_return_is_null_after_a_full_profitable_exit(db, investor) -> None:
    """BUY 100@100 (outflow 10000), SELL 100@300 (inflow 30000): net_invested = -20000,
    negative despite a real 20000 gain. absolute_return must be null at the HTTP layer
    too -- the guard has to survive the router boundary, not just the engine call."""
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    create_transactions(
        investor,
        [
            buy(advised_account, ISIN_A, date(2023, 1, 10), "100", "100", "T1"),
            sell(advised_account, ISIN_A, date(2023, 6, 10), "100", "300", "T2"),
        ],
        connection=db,
    )

    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["absolute_return"] is None


def test_cagr_is_always_null(db, investor) -> None:
    """Portfolio-level CAGR is permanently out of scope (ENGINE_SPEC section 5, decided
    2026-08-16) -- a regression lock so a future change doesn't silently reintroduce it."""
    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)
    assert result["cagr"] is None
