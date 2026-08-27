"""Portfolio-snapshot persistence, against a real cluster -- docs/ENGINE_SPEC.md section 8."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest
from app.db import snapshots as dbsnapshots
from app.db.prices import upsert_prices
from app.db.repository import load_transactions
from app.engine.snapshot import compute_snapshot
from app.engine.types import Snapshot
from app.prices.pipe import MergedPrice
from app.routers.transactions import create_transactions
from app.schemas.transactions import TransactionIn

pytestmark = pytest.mark.db

ISIN = "INE153T01027"
AS_OF = date(2024, 9, 30)


@pytest.fixture(autouse=True)
def _consent(db, investor) -> None:
    """A couple of tests here seed through the real create_transactions, which
    require_consent now gates -- this file is about snapshot persistence, not the
    consent gate itself (that's tests/test_db_consent_router.py's job)."""
    from app.db import consent

    consent.record_consent(db, investor, notice_version="v1", evidence_ref="test-fixture")


def seed_price(db, isin: str, on: date, close: str) -> None:
    upsert_prices(
        db, [MergedPrice(isin=isin, price_date=on, close=Decimal(close), source="NSE_BHAVCOPY")]
    )


def buy(
    account_id: str, isin: str, day: date, quantity: str, price: str, ref: str
) -> TransactionIn:
    return TransactionIn(
        account_id=account_id, isin=isin, txn_date=day, txn_type="BUY",
        quantity=quantity, price=price, source="MANUAL", source_ref=ref,
    )


def a_snapshot(
    as_of: date = AS_OF,
    invested: str = "1000",
    market_value: str = "1200",
    unrealised: str = "200",
    realised_to_date: str = "0",
) -> Snapshot:
    return Snapshot(
        as_of=as_of,
        invested=Decimal(invested),
        market_value=Decimal(market_value),
        unrealised=Decimal(unrealised),
        realised_to_date=Decimal(realised_to_date),
    )


# --- upsert / point lookup ------------------------------------------------------------


def test_upsert_and_point_lookup_round_trip(db, investor) -> None:
    dbsnapshots.upsert_snapshot(db, investor, False, a_snapshot())
    assert dbsnapshots.get_snapshot(db, investor, AS_OF, False) == a_snapshot()


def test_a_missing_snapshot_is_none_not_an_error(db, investor) -> None:
    """A miss is the signal for the caller to fall back to a live compute_snapshot call,
    not a failure -- _window_xirr depends on this being a quiet None."""
    assert dbsnapshots.get_snapshot(db, investor, AS_OF, False) is None


def test_upsert_is_idempotent_and_a_rerun_corrects_the_stored_total(db, investor) -> None:
    """Same reasoning as app.db.prices.upsert_prices: a rerun (after a price correction)
    should carry the better number through, not be a no-op forever."""
    dbsnapshots.upsert_snapshot(db, investor, False, a_snapshot(market_value="1200"))
    dbsnapshots.upsert_snapshot(db, investor, False, a_snapshot(market_value="1500"))

    got = dbsnapshots.get_snapshot(db, investor, AS_OF, False)
    assert got.market_value == Decimal("1500")
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM portfolio_snapshot")
        assert cur.fetchone()[0] == 1


def test_advised_only_is_an_independent_series(db, investor) -> None:
    """The whole point of carrying advised_only in the grain: the unfiltered and
    advised-only views for the SAME investor and SAME date can legitimately differ."""
    dbsnapshots.upsert_snapshot(db, investor, False, a_snapshot(market_value="1200"))
    dbsnapshots.upsert_snapshot(db, investor, True, a_snapshot(market_value="900"))

    assert dbsnapshots.get_snapshot(db, investor, AS_OF, False).market_value == Decimal("1200")
    assert dbsnapshots.get_snapshot(db, investor, AS_OF, True).market_value == Decimal("900")


# --- nearest-before lookup (Phase 2 Session 3: 1Y/3Y/5Y trailing windows) -------------


def test_get_snapshot_on_or_before_returns_the_exact_row_when_one_exists(db, investor) -> None:
    """Subsumes get_snapshot's exact-match case -- when a row exists exactly on the
    requested date, it is necessarily the latest qualifying row."""
    dbsnapshots.upsert_snapshot(db, investor, False, a_snapshot(market_value="1200"))
    got = dbsnapshots.get_snapshot_on_or_before(db, investor, AS_OF, False)
    assert got.as_of == AS_OF
    assert got.market_value == Decimal("1200")


def test_get_snapshot_on_or_before_returns_the_nearest_earlier_row_when_no_exact_match(
    db, investor
) -> None:
    dbsnapshots.upsert_snapshot(
        db, investor, False, a_snapshot(as_of=date(2024, 8, 9), market_value="1100")
    )
    dbsnapshots.upsert_snapshot(
        db, investor, False, a_snapshot(as_of=date(2024, 8, 12), market_value="1400")
    )

    got = dbsnapshots.get_snapshot_on_or_before(db, investor, date(2024, 8, 11), False)

    assert got.as_of == date(2024, 8, 9)
    assert got.market_value == Decimal("1100")


def test_get_snapshot_on_or_before_ignores_later_rows_and_returns_none_with_nothing_earlier(
    db, investor
) -> None:
    """A row exists, just not on or before the requested date -- honest None, not the
    later row silently borrowed from the future."""
    dbsnapshots.upsert_snapshot(
        db, investor, False, a_snapshot(as_of=date(2024, 9, 1), market_value="1500")
    )
    got = dbsnapshots.get_snapshot_on_or_before(db, investor, date(2024, 8, 1), False)
    assert got is None


def test_get_snapshot_on_or_before_is_scoped_to_its_own_advised_only_series(
    db, investor
) -> None:
    dbsnapshots.upsert_snapshot(db, investor, False, a_snapshot(market_value="1200"))
    got = dbsnapshots.get_snapshot_on_or_before(db, investor, AS_OF, True)
    assert got is None


# --- the section 8 invariant: always recomputable from the ledger ---------------------


def test_persisted_snapshot_matches_live_compute_snapshot(db, investor) -> None:
    """A persisted row must be field-for-field identical to what compute_snapshot()
    produces live for the same ledger and prices -- ENGINE_SPEC section 8's "cache of a
    derivation, always recomputable" invariant, pinned directly rather than assumed."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    create_transactions(
        investor,
        [buy(account_id, ISIN, date(2023, 1, 10), "100", "200", "T1")],
        connection=db,
    )
    seed_price(db, ISIN, AS_OF, "250")

    transactions = load_transactions(db, investor_id=investor)
    live = compute_snapshot(transactions, {ISIN: Decimal("250")}, AS_OF)

    dbsnapshots.upsert_snapshot(db, investor, False, live)
    persisted = dbsnapshots.get_snapshot(db, investor, AS_OF, False)

    assert persisted == live


# --- backfill support -------------------------------------------------------------------


def test_snapshot_dates_present_for_resumable_backfill(db, investor) -> None:
    dbsnapshots.upsert_snapshot(db, investor, False, a_snapshot(as_of=date(2024, 8, 10)))
    dbsnapshots.upsert_snapshot(db, investor, False, a_snapshot(as_of=date(2024, 8, 11)))

    present = dbsnapshots.snapshot_dates_present(
        db, investor, False, date(2024, 8, 1), date(2024, 8, 31)
    )
    assert present == {date(2024, 8, 10), date(2024, 8, 11)}


def test_snapshot_dates_present_is_scoped_to_its_own_advised_only_series(db, investor) -> None:
    dbsnapshots.upsert_snapshot(db, investor, False, a_snapshot(as_of=date(2024, 8, 10)))

    present = dbsnapshots.snapshot_dates_present(
        db, investor, True, date(2024, 8, 1), date(2024, 8, 31)
    )
    assert present == set()


# --- the gate ---------------------------------------------------------------------------


def test_as_of_cannot_be_in_the_future(db, investor) -> None:
    import psycopg

    with pytest.raises(psycopg.errors.CheckViolation):
        dbsnapshots.upsert_snapshot(db, investor, False, a_snapshot(as_of=date(2999, 1, 1)))
    db.rollback()


# --- range read (Phase 2 Session 2: the historical-value chart) -----------------------


def test_list_snapshots_range_returns_rows_in_date_order(db, investor) -> None:
    """Inserted out of order -- the read must sort, not echo insertion order."""
    dbsnapshots.upsert_snapshot(
        db, investor, False, a_snapshot(as_of=date(2024, 8, 12), market_value="1300")
    )
    dbsnapshots.upsert_snapshot(
        db, investor, False, a_snapshot(as_of=date(2024, 8, 10), market_value="1200")
    )
    dbsnapshots.upsert_snapshot(
        db, investor, False, a_snapshot(as_of=date(2024, 8, 11), market_value="1250")
    )

    rows = dbsnapshots.list_snapshots_range(
        db, investor, False, date(2024, 8, 1), date(2024, 8, 31)
    )

    assert [r.as_of for r in rows] == [date(2024, 8, 10), date(2024, 8, 11), date(2024, 8, 12)]
    assert [r.market_value for r in rows] == [
        Decimal("1200"),
        Decimal("1250"),
        Decimal("1300"),
    ]


def test_list_snapshots_range_excludes_dates_outside_bounds(db, investor) -> None:
    dbsnapshots.upsert_snapshot(db, investor, False, a_snapshot(as_of=date(2024, 8, 5)))
    dbsnapshots.upsert_snapshot(db, investor, False, a_snapshot(as_of=date(2024, 8, 15)))

    rows = dbsnapshots.list_snapshots_range(
        db, investor, False, date(2024, 8, 10), date(2024, 8, 20)
    )
    assert [r.as_of for r in rows] == [date(2024, 8, 15)]


def test_list_snapshots_range_is_scoped_to_its_own_advised_only_series(db, investor) -> None:
    dbsnapshots.upsert_snapshot(db, investor, False, a_snapshot(as_of=date(2024, 8, 10)))
    dbsnapshots.upsert_snapshot(db, investor, True, a_snapshot(as_of=date(2024, 8, 11)))

    rows = dbsnapshots.list_snapshots_range(
        db, investor, False, date(2024, 8, 1), date(2024, 8, 31)
    )
    assert [r.as_of for r in rows] == [date(2024, 8, 10)]


def test_list_snapshots_range_with_nothing_persisted_is_an_empty_list_not_an_error(
    db, investor
) -> None:
    """Before backfill's earliest reachable date, or an investor onboarded after the
    requested range: an honest empty result, never a fabricated row and never an
    exception -- the same non-error-miss convention as ``get_snapshot``."""
    rows = dbsnapshots.list_snapshots_range(
        db, investor, False, date(2024, 1, 1), date(2024, 1, 31)
    )
    assert rows == []


def test_list_snapshots_range_does_not_fill_a_gap_between_two_real_rows(db, investor) -> None:
    """A missing middle day (a backfill run that hit MissingPriceError) must not appear
    at all -- no interpolated or repeated value standing in for it. Exactly two rows
    back, for the two real days, nothing for the day in between."""
    dbsnapshots.upsert_snapshot(
        db, investor, False, a_snapshot(as_of=date(2024, 8, 1), market_value="1000")
    )
    dbsnapshots.upsert_snapshot(
        db, investor, False, a_snapshot(as_of=date(2024, 8, 3), market_value="1100")
    )

    rows = dbsnapshots.list_snapshots_range(
        db, investor, False, date(2024, 8, 1), date(2024, 8, 3)
    )
    assert [r.as_of for r in rows] == [date(2024, 8, 1), date(2024, 8, 3)]
