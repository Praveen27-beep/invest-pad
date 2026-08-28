"""app/db/holdings.py::record_snapshot -- holding_snapshot writes, against a real
database.

Pinning a real bug found against a real statement: holding_snapshot.isin is a foreign
key into security (001_core.sql), but nothing ensured that row existed before this was
fixed. promote_batch (app/db/imports.py) satisfies the identical constraint for
transaction.isin by inserting a bare security row first -- record_snapshot needed the
same treatment, for the same reason: an import is how a new holding is first
discovered, and a CAS's Holdings table lists fund-in-demat ISINs that will never
appear in a promoted transaction (mutual funds are out of Phase 1 scope), so without
this such an ISIN could never get a security row any other way.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from app.db import holdings

pytestmark = pytest.mark.db


@dataclass(frozen=True, slots=True)
class FakeHolding:
    """Same shape record_snapshot actually needs -- isin/account_id/quantity/
    snap_date -- without importing app.ingest.cas_pdf.DeclaredHolding, which this
    module doesn't otherwise depend on."""

    isin: str
    account_id: str
    quantity: Decimal
    snap_date: date


def _account_id() -> str:
    return os.environ["_TEST_ACCOUNT_ID"]


def test_a_holding_whose_security_does_not_exist_yet_still_writes(db, investor) -> None:
    """The real bug: a fund-in-demat ISIN a CAS declares but that has never been part
    of a promoted transaction had no security row, and the insert failed with
    ForeignKeyViolation. INF247L01BQ9 is the real ISIN that surfaced this."""
    account_id = _account_id()
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM security WHERE isin = 'INF247L01BQ9'")
        assert cur.fetchone()[0] == 0

    written = holdings.record_snapshot(
        db,
        [FakeHolding(isin="INF247L01BQ9", account_id=account_id,
                     quantity=Decimal("10"), snap_date=date(2026, 6, 30))],
    )
    assert written == 1

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM security WHERE isin = 'INF247L01BQ9'")
        assert cur.fetchone()[0] == 1
        cur.execute(
            "SELECT quantity FROM holding_snapshot WHERE account_id = %s AND isin = %s",
            (account_id, "INF247L01BQ9"),
        )
        assert cur.fetchone()[0] == Decimal("10")


def test_an_existing_security_row_is_left_alone(db, investor) -> None:
    """ON CONFLICT DO NOTHING -- record_snapshot must never overwrite a symbol or
    other detail an earlier promoted transaction already established."""
    account_id = _account_id()
    with db.cursor() as cur:
        cur.execute("SELECT symbol FROM security WHERE isin = 'INE153T01027'")
        (symbol_before,) = cur.fetchone()

    holdings.record_snapshot(
        db,
        [FakeHolding(isin="INE153T01027", account_id=account_id,
                     quantity=Decimal("5"), snap_date=date(2026, 6, 30))],
    )

    with db.cursor() as cur:
        cur.execute("SELECT symbol FROM security WHERE isin = 'INE153T01027'")
        (symbol_after,) = cur.fetchone()
    assert symbol_after == symbol_before


def test_upsert_on_the_same_account_isin_date_overwrites_the_quantity(db, investor) -> None:
    """Re-processing the same statement period must overwrite, not duplicate --
    docs/INGESTION.md's "assume every message may arrive twice"."""
    account_id = _account_id()
    snap_date = date(2026, 6, 30)
    holdings.record_snapshot(
        db, [FakeHolding(isin="INE153T01027", account_id=account_id,
                          quantity=Decimal("5"), snap_date=snap_date)]
    )
    holdings.record_snapshot(
        db, [FakeHolding(isin="INE153T01027", account_id=account_id,
                          quantity=Decimal("9"), snap_date=snap_date)]
    )

    with db.cursor() as cur:
        cur.execute(
            "SELECT count(*), max(quantity) FROM holding_snapshot "
            "WHERE account_id = %s AND isin = %s AND snap_date = %s",
            (account_id, "INE153T01027", snap_date),
        )
        count, quantity = cur.fetchone()
    assert count == 1
    assert quantity == Decimal("9")


def test_a_holding_with_no_account_id_is_skipped_not_written_with_a_null(db, investor) -> None:
    written = holdings.record_snapshot(
        db,
        [FakeHolding(isin="INE153T01027", account_id="", quantity=Decimal("5"),
                     snap_date=date(2026, 6, 30))],
    )
    assert written == 0
