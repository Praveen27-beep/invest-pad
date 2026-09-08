"""Persistence for the intraday live-price cache -- app.db.live_prices, against a real
database. Unit-level behaviour of the source module (ticker resolution, Decimal
conversion, the never-raise contract) lives in tests/test_yfinance_live.py; this file is
about the cache contract itself: overwrite semantics and "a stale row is omitted, not
served" -- the same posture app.db.prices documents for bhavcopy, just on a
minutes-not-days clock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.db import live_prices

from tests.test_db_holdings import add_security

pytestmark = pytest.mark.db

ISIN = "INE153T01027"
OTHER_ISIN = "INE242A01010"


def test_upsert_then_get_fresh_returns_the_value(db) -> None:
    add_security(db, ISIN, "TESTCO")

    written = live_prices.upsert_live_prices(
        db, {ISIN: Decimal("150.25")}, datetime.now(UTC)
    )

    assert written == 1
    assert live_prices.get_fresh(db, [ISIN]) == {ISIN: Decimal("150.25")}


def test_upsert_overwrites_rather_than_accumulating_history(db) -> None:
    add_security(db, ISIN, "TESTCO")
    now = datetime.now(UTC)
    live_prices.upsert_live_prices(db, {ISIN: Decimal("100")}, now)

    live_prices.upsert_live_prices(db, {ISIN: Decimal("110")}, now)

    assert live_prices.get_fresh(db, [ISIN]) == {ISIN: Decimal("110")}


def test_a_stale_row_is_omitted_not_served(db) -> None:
    add_security(db, ISIN, "TESTCO")
    stale = datetime.now(UTC) - timedelta(seconds=999)
    live_prices.upsert_live_prices(db, {ISIN: Decimal("100")}, stale)

    assert live_prices.get_fresh(db, [ISIN], max_age_seconds=180) == {}


def test_a_row_just_inside_the_ttl_is_served(db) -> None:
    add_security(db, ISIN, "TESTCO")
    recent = datetime.now(UTC) - timedelta(seconds=10)
    live_prices.upsert_live_prices(db, {ISIN: Decimal("100")}, recent)

    assert live_prices.get_fresh(db, [ISIN], max_age_seconds=180) == {ISIN: Decimal("100")}


def test_get_fresh_with_no_isins_returns_empty(db) -> None:
    assert live_prices.get_fresh(db, []) == {}


def test_get_fresh_omits_isins_never_cached(db) -> None:
    add_security(db, ISIN, "TESTCO")

    assert live_prices.get_fresh(db, [ISIN]) == {}


def test_get_fresh_only_returns_the_requested_isins(db) -> None:
    add_security(db, ISIN, "TESTCO")
    add_security(db, OTHER_ISIN, "OTHERCO")
    now = datetime.now(UTC)
    live_prices.upsert_live_prices(db, {ISIN: Decimal("100"), OTHER_ISIN: Decimal("200")}, now)

    assert live_prices.get_fresh(db, [ISIN]) == {ISIN: Decimal("100")}


def test_upsert_with_empty_prices_is_a_noop(db) -> None:
    assert live_prices.upsert_live_prices(db, {}, datetime.now(UTC)) == 0
