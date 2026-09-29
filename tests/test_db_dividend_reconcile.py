"""The second-pass dividend reconciler: leftovers only, identity proven by NSE's bhavcopy."""

from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal

import pytest
from app.db import dividend_events as de
from app.db import repository
from app.db.dividend_reconcile import reconcile_pending_dividends
from app.engine.corporate_actions import Verification
from app.engine.dividend_events import DividendEvent, DividendKind
from app.engine.types import Source, Transaction, TxnType

pytestmark = pytest.mark.db

ISIN = "INE153T01027"  # seeded by the ``investor`` fixture (symbol BLS)
STALE = "INE153T01019"  # what NSE's corporate-actions feed still prints for BLS
EX = date(2025, 9, 8)


class _Feed:
    def __init__(self, *rows: dict):
        self.rows, self.calls = list(rows), 0

    def fetch(self, start: date, end: date) -> bytes:
        self.calls += 1
        return json.dumps(self.rows).encode()


class _NoFetch:
    def fetch(self, on: date) -> bytes:
        raise AssertionError("bhavcopy is seeded; nothing should be fetched")


def _nse_row(isin=STALE, symbol="BLS", subject="Dividend - Re 1 Per Share", ex="08-Sep-2025"):
    return {"isin": isin, "symbol": symbol, "exDate": ex, "recDate": ex, "subject": subject}


def _seed_bhavcopy(db, isin=ISIN, symbol="BLS", on=EX) -> None:
    db.execute(
        "INSERT INTO reference_bhavcopy_day VALUES (%s,%s,%s,now())",
        (on, "https://nsearchives.nseindia.com/test.csv.zip", "0" * 64),
    )
    db.execute(
        "INSERT INTO reference_bhavcopy_security VALUES (%s,%s,%s,'EQ',100)", (on, isin, symbol)
    )


def _yf_event(db, amount="1", ex=EX, isin=ISIN) -> None:
    de.add_dividend_event(
        db,
        DividendEvent(
            isin=isin,
            ex_date=ex,
            amount_per_share=Decimal(amount),
            kind=DividendKind.UNSPECIFIED,
            source="Yahoo Finance (yfinance)",
            source_url="https://finance.yahoo.com/quote/BLS.NS/history",
            verification=Verification.DRAFT,
        ),
    )


def _hold(db, on=date(2025, 1, 2)) -> None:
    repository.save_transactions(
        db,
        [
            Transaction(
                isin=ISIN,
                txn_date=on,
                txn_type=TxnType.BUY,
                quantity=Decimal("10"),
                price=Decimal("100"),
                source=Source.TRADEBOOK,
                account_id=os.environ["_TEST_ACCOUNT_ID"],
            )
        ],
    )


def _state(db) -> Verification:
    return de.list_dividend_events(db, isins=[ISIN])[0].verification


def test_a_stale_nse_isin_proven_by_the_bhavcopy_verifies_the_leftover(db, investor) -> None:
    _hold(db)
    _yf_event(db)
    _seed_bhavcopy(db)
    db.commit()
    result = reconcile_pending_dividends(db, _Feed(_nse_row()), _NoFetch())
    assert result["verified"] == 1
    event = de.list_dividend_events(db, isins=[ISIN])[0]
    assert event.verification is Verification.VERIFIED
    assert STALE in event.corroborated_by and event.corroborated_url.startswith("https://")


def test_the_bhavcopy_naming_another_isin_leaves_it_draft(db, investor) -> None:
    _hold(db)
    _yf_event(db)
    _seed_bhavcopy(db, isin="INE153T01035")  # the symbol traded under a different ISIN
    db.commit()
    result = reconcile_pending_dividends(db, _Feed(_nse_row()), _NoFetch())
    assert result["identity_unproven"] == 1
    assert _state(db) is Verification.DRAFT


def test_a_different_issuer_prefix_is_never_considered(db, investor) -> None:
    _hold(db)
    _yf_event(db)
    _seed_bhavcopy(db)
    db.commit()
    result = reconcile_pending_dividends(db, _Feed(_nse_row(isin="INE009A01021")), _NoFetch())
    assert result["no_nse_row"] == 1
    assert _state(db) is Verification.DRAFT


def test_a_disagreeing_amount_disputes_rather_than_verifies(db, investor) -> None:
    _hold(db)
    _yf_event(db, amount="0.50")
    _seed_bhavcopy(db)
    db.commit()
    result = reconcile_pending_dividends(db, _Feed(_nse_row()), _NoFetch())
    assert result["disputed"] == 1
    assert _state(db) is Verification.DISPUTED


def test_two_nse_rows_on_one_date_are_ambiguous(db, investor) -> None:
    _hold(db)
    _yf_event(db)
    _seed_bhavcopy(db)
    db.commit()
    feed = _Feed(_nse_row(), _nse_row(subject="Special Dividend - Rs 2 Per Share"))
    assert reconcile_pending_dividends(db, feed, _NoFetch())["ambiguous"] == 1
    assert _state(db) is Verification.DRAFT


def test_only_leftovers_a_holder_was_eligible_for_are_processed(db, investor) -> None:
    """Held from 2026 only: a 2025 dividend is not pending work -- no fetch is spent on it."""
    _hold(db, on=date(2026, 1, 2))
    _yf_event(db)
    db.commit()
    feed = _Feed(_nse_row())
    assert reconcile_pending_dividends(db, feed, _NoFetch())["pending"] == 0
    assert feed.calls == 0
    assert _state(db) is Verification.DRAFT


def test_the_reconcile_cron_route_is_scheduled() -> None:
    from pathlib import Path

    config = json.loads(
        (Path(__file__).resolve().parents[1] / "trackr-backend" / "vercel.json").read_text()
    )
    assert "/ops/dividends/reconcile-cron" in {entry["path"] for entry in config["crons"]}
