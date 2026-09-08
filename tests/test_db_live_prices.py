"""Live intraday prices (app.prices.live) merged into holdings valuation for today only --
against a real database. The live fetch itself is mocked throughout: what's under test is
the boundary drawn in app.routers.holdings._portfolio (which date, which ISINs, who wins),
not yfinance/network behaviour -- that's tests/test_yfinance_live.py's job.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.routers.holdings import holdings
from app.routers.transactions import create_transactions
from app.schemas.transactions import TransactionIn

from tests.test_db_holdings import add_security, seed_price

pytestmark = pytest.mark.db

ISIN = "INE153T01027"
TODAY = date(2024, 9, 30)
HISTORICAL = date(2023, 6, 15)


@pytest.fixture(autouse=True)
def _consent(db, investor) -> None:
    from app.db import consent

    consent.record_consent(db, investor, notice_version="v1", evidence_ref="test-fixture")


def _seed_holding(db, investor_id: str, isin: str = ISIN) -> None:
    add_security(db, isin, "TESTCO")
    create_transactions(
        investor_id,
        [
            TransactionIn(
                account_id=os.environ["_TEST_ACCOUNT_ID"],
                isin=isin,
                txn_date=date(2023, 1, 10),
                txn_type="BUY",
                quantity="100",
                price="100",
                source="MANUAL",
                source_ref="T1",
            )
        ],
        connection=db,
    )


def test_historical_as_of_never_calls_the_live_path(db, investor, monkeypatch) -> None:
    """A missing bhavcopy price for a PAST date must stay unpriced -- never filled from
    the live cache, even if the live path would happily return something."""
    _seed_holding(db, investor)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("live price path must not be consulted for a historical as_of")

    monkeypatch.setattr("app.routers.holdings.refresh_and_get", fail_if_called)

    result = holdings(investor, as_of=HISTORICAL, asset_class=None, connection=db)

    assert result["unpriced"]["count"] == 1
    assert result["holdings"] == []
    assert result["live_as_of"] is None


def test_todays_gap_is_filled_from_the_live_cache(db, investor, monkeypatch) -> None:
    """as_of == today, no bhavcopy row yet: the live cache fills it, and the holding
    comes back marked `live`."""
    _seed_holding(db, investor)
    monkeypatch.setattr("app.routers.holdings.ist_today", lambda: TODAY)
    monkeypatch.setattr(
        "app.routers.holdings.refresh_and_get", lambda conn, isins: {ISIN: Decimal("150")}
    )

    result = holdings(investor, as_of=TODAY, asset_class=None, connection=db)

    assert len(result["holdings"]) == 1
    row = result["holdings"][0]
    assert row["live"] is True
    assert Decimal(row["last_price"]) == Decimal("150")
    assert result["live_as_of"] is not None


def test_bhavcopy_wins_over_a_live_price_for_the_same_isin(db, investor, monkeypatch) -> None:
    """Bhavcopy landing for today must never be second-guessed by a live quote -- the live
    path is not even consulted once bhavcopy already covers every held ISIN."""
    _seed_holding(db, investor)
    seed_price(db, ISIN, TODAY, "200")
    monkeypatch.setattr("app.routers.holdings.ist_today", lambda: TODAY)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("bhavcopy already covers this ISIN; live must not be consulted")

    monkeypatch.setattr("app.routers.holdings.refresh_and_get", fail_if_called)

    result = holdings(investor, as_of=TODAY, asset_class=None, connection=db)

    row = result["holdings"][0]
    assert Decimal(row["last_price"]) == Decimal("200")
    assert row["live"] is False
    assert result["live_as_of"] is None


def test_both_sources_missing_still_lands_in_unpriced(db, investor, monkeypatch) -> None:
    """The live cache failing outright is not a new failure mode -- it's the same one
    MissingPriceError already names, one layer up in _portfolio's partition."""
    _seed_holding(db, investor)
    monkeypatch.setattr("app.routers.holdings.ist_today", lambda: TODAY)
    monkeypatch.setattr("app.routers.holdings.refresh_and_get", lambda conn, isins: {})

    result = holdings(investor, as_of=TODAY, asset_class=None, connection=db)

    assert result["unpriced"]["count"] == 1
    assert result["holdings"] == []
    assert result["live_as_of"] is None


def test_live_beats_a_carried_forward_close_for_today(db, investor, monkeypatch) -> None:
    """The case the whole feature exists for, and the one a naive "fill what bhavcopy is
    missing" rule silently skips.

    Bhavcopy is published after the close, so on any trading morning the newest stored row
    is YESTERDAY's -- and ``latest_prices`` carries it forward, leaving nothing "missing"
    to fall back for. Deciding on the exact date instead (``prices_on_date``) is what lets
    an intraday quote reach a portfolio that already has a usable, merely older, close.
    """
    _seed_holding(db, investor)
    seed_price(db, ISIN, TODAY - timedelta(days=1), "200")
    monkeypatch.setattr("app.routers.holdings.ist_today", lambda: TODAY)
    monkeypatch.setattr(
        "app.routers.holdings.refresh_and_get", lambda conn, isins: {ISIN: Decimal("150")}
    )

    result = holdings(investor, as_of=TODAY, asset_class=None, connection=db)

    row = result["holdings"][0]
    assert Decimal(row["last_price"]) == Decimal("150")
    assert row["live"] is True


def test_a_carried_forward_close_is_kept_when_the_live_fetch_returns_nothing(
    db, investor, monkeypatch
) -> None:
    """yfinance being unreachable degrades to yesterday's official close, NOT to unpriced.

    The distinction matters: yesterday's bhavcopy inside the staleness window is a real,
    reproducible number that ``latest_prices`` already sanctions for this ``as_of``. It is
    just not a live one, so the row must not claim to be.
    """
    _seed_holding(db, investor)
    seed_price(db, ISIN, TODAY - timedelta(days=1), "200")
    monkeypatch.setattr("app.routers.holdings.ist_today", lambda: TODAY)
    monkeypatch.setattr("app.routers.holdings.refresh_and_get", lambda conn, isins: {})

    result = holdings(investor, as_of=TODAY, asset_class=None, connection=db)

    row = result["holdings"][0]
    assert Decimal(row["last_price"]) == Decimal("200")
    assert row["live"] is False
    assert result["live_as_of"] is None


def test_todays_settled_bhavcopy_replaces_a_live_quote_already_cached(
    db, investor, monkeypatch
) -> None:
    """The seamless handover: tonight's bhavcopy lands, and the SAME read that would have
    served a live quote now serves the settled close instead. Nothing is deleted or
    migrated -- the live cache row is simply outranked from that read on.
    """
    _seed_holding(db, investor)
    monkeypatch.setattr("app.routers.holdings.ist_today", lambda: TODAY)
    monkeypatch.setattr(
        "app.routers.holdings.refresh_and_get", lambda conn, isins: {ISIN: Decimal("150")}
    )

    intraday = holdings(investor, as_of=TODAY, asset_class=None, connection=db)
    assert Decimal(intraday["holdings"][0]["last_price"]) == Decimal("150")

    seed_price(db, ISIN, TODAY, "162.40")
    settled = holdings(investor, as_of=TODAY, asset_class=None, connection=db)

    row = settled["holdings"][0]
    assert Decimal(row["last_price"]) == Decimal("162.40")
    assert row["live"] is False
    assert settled["live_as_of"] is None
