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
from app.db import snapshots as dbsnapshots
from app.db.repository import load_transactions
from app.engine.snapshot import compute_snapshot
from app.engine.types import Snapshot
from app.engine.xirr import (
    PERIOD_TOO_SHORT_WARNING,
    compute_fy_xirr,
    compute_period_xirr,
    years_before,
)
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


def test_fy_xirr_prefers_a_persisted_snapshot_over_live_recomputation(db, investor) -> None:
    """Phase 2 Session 1's actual payoff: when a portfolio_snapshot row already exists
    for 1 April, _fy_xirr must use it and skip the live compute_snapshot call entirely --
    proven by seeding a row with a market_value live computation would NOT produce (no
    1-April price is stored at all) and asserting the response matches the SEEDED value,
    not None and not a guess."""
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    create_transactions(
        investor,
        [buy(advised_account, ISIN_A, date(2023, 1, 10), "100", "100", "T1")],
        connection=db,
    )
    seed_price(db, ISIN_A, AS_OF, "200")
    # Deliberately NOT seeding a price on/near FY_START -- a live compute_snapshot call
    # would raise MissingPriceError and fy_xirr would come back None. The persisted row
    # below is the only way this test's fy_xirr can be non-null.
    dbsnapshots.upsert_snapshot(
        db, investor, False,
        Snapshot(
            as_of=FY_START, invested=Decimal("10000"), market_value=Decimal("15000"),
            unrealised=Decimal("5000"), realised_to_date=Decimal("0"),
        ),
    )

    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["fy_xirr"] is not None
    transactions = load_transactions(db, investor_id=investor)
    expected = compute_fy_xirr(transactions, {ISIN_A: Decimal("200")}, Decimal("15000"), AS_OF)
    assert result["fy_xirr"] == pytest.approx(float(expected))


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


def test_period_xirr_prefers_a_persisted_snapshot_over_live_recomputation(db, investor) -> None:
    """Same proof as fy_xirr's equivalent test: seed a portfolio_snapshot row for
    onboarding_date with no corresponding price stored anywhere near it, so a live
    compute_snapshot call would raise MissingPriceError and period_xirr would come back
    None. A non-null result here is only possible via the persisted row."""
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    set_onboarding_date(db, investor, ONBOARDING)
    create_transactions(
        investor,
        [buy(advised_account, ISIN_A, date(2023, 1, 10), "100", "100", "T1")],
        connection=db,
    )
    seed_price(db, ISIN_A, AS_OF, "200")
    dbsnapshots.upsert_snapshot(
        db, investor, False,
        Snapshot(
            as_of=ONBOARDING, invested=Decimal("10000"), market_value=Decimal("14000"),
            unrealised=Decimal("4000"), realised_to_date=Decimal("0"),
        ),
    )

    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["period_xirr"] is not None
    assert result["period_start"] == ONBOARDING
    transactions = load_transactions(db, investor_id=investor)
    expected = compute_period_xirr(
        transactions, {ISIN_A: Decimal("200")}, ONBOARDING, Decimal("14000"), AS_OF
    )
    assert result["period_xirr"] == pytest.approx(float(expected))


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


# --- xirr_1y / xirr_3y / xirr_5y (Phase 2 Session 3: trailing windows) ----------------


def test_xirr_5y_blanks_independently_while_fy_1y_3y_still_compute(db, investor) -> None:
    """~3.7 years of real history: fy_xirr/xirr_1y/xirr_3y compute normally while
    xirr_5y alone is None -- the per-window guard's independence, not an all-or-nothing
    outcome. Also the regression guard for the latent bug where a target predating the
    ledger degenerates into xirr_all silently mislabeled with the window's name: without
    the guard, compute_holdings at the 5Y target would be empty, opening_value would be
    0, and every transaction the investor ever made would fold into the flow list."""
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    earliest = date(2021, 1, 10)  # after the 5Y target (2019-09-30), before the 3Y one
    create_transactions(
        investor,
        [buy(advised_account, ISIN_A, earliest, "100", "100", "T1")],
        connection=db,
    )
    seed_price(db, ISIN_A, AS_OF, "200")
    for target in (FY_START, years_before(AS_OF, 1), years_before(AS_OF, 3)):
        dbsnapshots.upsert_snapshot(
            db, investor, False,
            Snapshot(
                as_of=target, invested=Decimal("10000"), market_value=Decimal("12000"),
                unrealised=Decimal("2000"), realised_to_date=Decimal("0"),
            ),
        )

    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["fy_xirr"] is not None
    assert result["xirr_1y"] is not None
    assert result["xirr_3y"] is not None
    assert result["xirr_5y"] is None


def test_xirr_1y_uses_the_snapshots_own_date_not_the_target_when_nearby(db, investor) -> None:
    """A persisted snapshot 5 days before the 1Y target (exactly at the
    MAX_PRICE_STALENESS_DAYS bound) stands in for it -- but the router must pass the
    SNAPSHOT's own as_of into compute_period_xirr, not the target date, or the
    transaction dated between the two would be silently dropped from both the opening
    value and the flow list. Same failure class as the documented mid-period-deposit
    bug, scoped to the gap instead of the whole period."""
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    target_1y = years_before(AS_OF, 1)
    snapshot_date = target_1y - timedelta(days=5)
    gap_txn_date = target_1y - timedelta(days=3)

    create_transactions(
        investor,
        [
            buy(advised_account, ISIN_A, date(2020, 1, 10), "100", "100", "T1"),
            buy(advised_account, ISIN_A, gap_txn_date, "50", "300", "T2"),
        ],
        connection=db,
    )
    seed_price(db, ISIN_A, AS_OF, "400")
    dbsnapshots.upsert_snapshot(
        db, investor, False,
        Snapshot(
            as_of=snapshot_date, invested=Decimal("10000"), market_value=Decimal("15000"),
            unrealised=Decimal("5000"), realised_to_date=Decimal("0"),
        ),
    )

    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["xirr_1y"] is not None
    transactions = load_transactions(db, investor_id=investor)
    expected = compute_period_xirr(
        transactions, {ISIN_A: Decimal("400")}, snapshot_date, Decimal("15000"), AS_OF
    )
    assert result["xirr_1y"] == pytest.approx(float(expected))

    # The buggy alternative: labelling the same opening value with target_1y instead of
    # the snapshot's real date silently drops the gap transaction from the flow list
    # entirely (txn_date > target_1y excludes it). Must not match what the router
    # actually returned.
    buggy = compute_period_xirr(
        transactions, {ISIN_A: Decimal("400")}, target_1y, Decimal("15000"), AS_OF
    )
    assert result["xirr_1y"] != pytest.approx(float(buggy))


def test_a_persisted_snapshot_older_than_the_staleness_bound_is_not_used(db, investor) -> None:
    """A persisted row exists but 10 days before the 1Y target -- beyond
    MAX_PRICE_STALENESS_DAYS (5). Using it directly would silently widen the window by
    that much; the router must treat it as a miss and fall through to the live path
    instead. No price exists anywhere near the target for that live path either, so
    xirr_1y must come back None -- proof the stale row was rejected, not silently
    accepted (if it had been used, xirr_1y would be non-null)."""
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    target_1y = years_before(AS_OF, 1)
    create_transactions(
        investor,
        [buy(advised_account, ISIN_A, date(2020, 1, 10), "100", "100", "T1")],
        connection=db,
    )
    seed_price(db, ISIN_A, AS_OF, "200")  # nothing anywhere near target_1y
    dbsnapshots.upsert_snapshot(
        db, investor, False,
        Snapshot(
            as_of=target_1y - timedelta(days=10), invested=Decimal("10000"),
            market_value=Decimal("15000"), unrealised=Decimal("5000"),
            realised_to_date=Decimal("0"),
        ),
    )

    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["xirr_1y"] is None


def test_fy_xirr_is_null_when_the_investors_only_transaction_postdates_fy_start(
    db, investor
) -> None:
    """Latent bug regression guard: without the earliest-transaction guard, a target
    predating the ledger makes compute_holdings(transactions, fy_start) legitimately
    empty, opening_value legitimately 0, and compute_period_xirr then folds in every
    transaction the investor has ever made -- numerically xirr_all, silently mislabeled
    'this FY'. fy_xirr must come back None instead of that mislabeled number."""
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    create_transactions(
        investor,
        [buy(advised_account, ISIN_A, FY_START + timedelta(days=30), "100", "100", "T1")],
        connection=db,
    )
    seed_price(db, ISIN_A, AS_OF, "200")

    result = performance(fake_request(), investor, as_of=AS_OF, connection=db)

    assert result["fy_xirr"] is None
    # xirr_all is NOT None -- proving fy_xirr's None came from the guard specifically,
    # not from some broader failure (e.g. too few flows for the solver) that would have
    # blanked xirr_all too.
    assert result["xirr_all"] is not None


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
