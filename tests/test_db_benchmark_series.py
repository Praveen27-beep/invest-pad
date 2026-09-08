"""GET /investors/{id}/benchmark-series -- the Dashboard value chart's benchmark line,
against a real database.

Same pattern as tests/test_db_analytical.py: the route handler is called directly with the
``db`` fixture's connection. What is under test here is the seam this endpoint owns --
which dates get plotted, which index gets fetched, and what happens when the external
source is unavailable -- not the replication arithmetic itself, which is pinned without a
database in tests/test_benchmark.py.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest
from app.db.index_levels import upsert_index_levels
from app.db.snapshots import upsert_snapshot
from app.engine.types import Snapshot
from app.prices.index_sources import IndexLevelRow, IndexSourceFetchFailed
from app.routers.analytical import benchmark_series_endpoint
from app.routers.transactions import create_transactions
from app.schemas.transactions import TransactionIn
from starlette.requests import Request

from tests.test_db_analytical import add_security

pytestmark = pytest.mark.db

ISIN = "INE153T01027"
BUY_DATE = date(2024, 4, 1)
SNAP_A = date(2024, 6, 3)
SNAP_B = date(2024, 9, 30)


@pytest.fixture(autouse=True)
def _consent(db, investor) -> None:
    from app.db import consent

    consent.record_consent(db, investor, notice_version="v1", evidence_ref="test-fixture")


def fake_request() -> Request:
    return Request({"type": "http", "headers": []})


def seed_ledger(db, investor_id: str) -> None:
    add_security(db, ISIN, "TESTCO")
    create_transactions(
        investor_id,
        [
            TransactionIn(
                account_id=os.environ["_TEST_ACCOUNT_ID"],
                isin=ISIN,
                txn_date=BUY_DATE,
                txn_type="BUY",
                quantity="100",
                price="200",
                source="MANUAL",
                source_ref="T1",
            )
        ],
        connection=db,
    )


def seed_snapshots(db, investor_id: str, *days: date) -> None:
    for day in days:
        upsert_snapshot(
            db,
            investor_id,
            False,
            Snapshot(
                as_of=day,
                invested=Decimal("20000"),
                market_value=Decimal("21000"),
                unrealised=Decimal("1000"),
                realised_to_date=Decimal("0"),
            ),
        )


def seed_levels(db, index_name: str, levels: dict[date, str]) -> None:
    upsert_index_levels(
        db,
        [
            IndexLevelRow(
                index_name=index_name,
                level_date=day,
                close=Decimal(close),
                source="NIFTYINDICES_TRI",
            )
            for day, close in levels.items()
        ],
    )


def call(db, investor_id: str, **kwargs):
    return benchmark_series_endpoint(
        fake_request(), investor_id, start=BUY_DATE, end=SNAP_B, connection=db, **kwargs
    )


def test_points_land_on_snapshot_dates_and_nowhere_else(db, investor) -> None:
    """The line is drawn beside market value, so it must share market value's x-positions.
    A point on a date with no snapshot would sit over empty chart."""
    seed_ledger(db, investor)
    seed_snapshots(db, investor, SNAP_A, SNAP_B)
    seed_levels(
        db, "NIFTY500_TRI", {BUY_DATE: "20000", SNAP_A: "22000", SNAP_B: "24000"}
    )

    result = call(db, investor)

    assert result["name"] == "NIFTY500_TRI"
    assert [p["as_of"] for p in result["points"]] == [SNAP_A, SNAP_B]
    assert Decimal(result["points"][0]["value"]) == Decimal("22000")


def test_nifty_500_is_the_default_and_nifty_50_levels_are_not_borrowed(db, investor) -> None:
    """A stored NIFTY 50 series must not satisfy a NIFTY 500 request. The two indices share
    a table and a source module; only the name keeps them apart."""
    seed_ledger(db, investor)
    seed_snapshots(db, investor, SNAP_A)
    seed_levels(db, "NIFTY50_TRI", {BUY_DATE: "20000", SNAP_A: "22000"})

    def fail_if_fetched(*args: object, **kwargs: object) -> int:
        raise IndexSourceFetchFailed("no network in tests")

    import app.routers.analytical as analytical

    original = analytical.fetch_and_store
    analytical.fetch_and_store = fail_if_fetched
    try:
        result = call(db, investor)
    finally:
        analytical.fetch_and_store = original

    assert result["points"] == []


def test_an_unreachable_source_returns_an_empty_line_not_an_error(db, investor) -> None:
    """The benchmark is a decoration on a chart whose real subject -- the portfolio's own
    value -- comes from /snapshots and is already drawn. It must never take the chart down
    with it."""
    seed_ledger(db, investor)
    seed_snapshots(db, investor, SNAP_A)

    import app.routers.analytical as analytical

    original = analytical.fetch_and_store

    def fail(*args: object, **kwargs: object) -> int:
        raise IndexSourceFetchFailed("connection reset")

    analytical.fetch_and_store = fail
    try:
        result = call(db, investor)
    finally:
        analytical.fetch_and_store = original

    assert result == {"name": "NIFTY500_TRI", "points": []}


def test_a_range_with_no_snapshots_returns_no_points_and_fetches_nothing(db, investor) -> None:
    seed_ledger(db, investor)

    import app.routers.analytical as analytical

    original = analytical.fetch_and_store

    def fail_if_called(*args: object, **kwargs: object) -> int:
        raise AssertionError("nothing to plot: the index source must not be reached")

    analytical.fetch_and_store = fail_if_called
    try:
        result = call(db, investor)
    finally:
        analytical.fetch_and_store = original

    assert result["points"] == []


def test_sensex_is_refused_rather_than_guessed_at(db, investor) -> None:
    from fastapi import HTTPException

    seed_ledger(db, investor)
    seed_snapshots(db, investor, SNAP_A)

    with pytest.raises(HTTPException) as exc:
        call(db, investor, name="SENSEX_TRI")
    assert exc.value.status_code == 400


def test_start_after_end_is_a_400(db, investor) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        benchmark_series_endpoint(
            fake_request(), investor, start=SNAP_B, end=BUY_DATE, connection=db
        )
    assert exc.value.status_code == 400
