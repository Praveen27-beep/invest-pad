"""Schema, migrations and the repository, against a real Postgres cluster.

The invariants here are the ones a substitute database would not reproduce: a unique
index that actually rejects, a trigger that actually raises, and NUMERIC that actually
keeps its digits.
"""

from __future__ import annotations

import os
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from db import audit, repository
from db.migrate import discover, migrate
from engine.dedupe import make_dedupe_key
from engine.types import Source, Transaction, TxnType

pytestmark = pytest.mark.db


def txn(qty: str = "100", price: str = "200", ref: str = "T1", **kw) -> Transaction:
    return Transaction(
        isin=kw.get("isin", "INE153T01027"),
        txn_date=kw.get("txn_date", date(2024, 1, 10)),
        txn_type=kw.get("txn_type", TxnType.BUY),
        quantity=Decimal(qty),
        price=Decimal(price),
        charges=Decimal(kw.get("charges", "0")),
        account_id=os.environ["_TEST_ACCOUNT_ID"],
        source=Source.TRADEBOOK,
        source_ref=ref,
    )


# --- migrations ----------------------------------------------------------------


def test_migrations_are_discovered_in_order() -> None:
    versions = [v for v, _ in discover()]
    assert versions == sorted(versions)
    assert versions[0] == 1


def test_migrations_are_idempotent(db) -> None:
    """Re-running must apply nothing. A runner that reapplies DDL is a runner that
    destroys data on the second deploy."""
    assert migrate(db) == []


def test_every_core_table_exists(db) -> None:
    with db.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = {r[0] for r in cur.fetchall()}
    assert {
        "investor", "account", "security", "transaction", "price", "holding_snapshot",
        "client_consent", "audit_log", "investor_secret", "retention_policy", "legal_hold",
    } <= tables


def test_there_is_no_holdings_table(db) -> None:
    """Holdings are computed on read. A holdings table means the architecture broke."""
    with db.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = {r[0] for r in cur.fetchall()}
    assert "holdings" not in tables
    assert "holding" not in tables


def test_no_column_matches_the_credential_ban(db) -> None:
    """The legal basis for operating without FIU registration is that these cannot exist.

    The banned names are read out of the Makefile rather than restated here. Two reasons:
    the list cannot drift from what `make lint` actually enforces, and writing the
    literals into this file would itself trip that rule -- a test for the ban must not be
    the thing that breaks it.
    """
    makefile = (Path(__file__).parent.parent / "Makefile").read_text()
    pattern = re.search(r'grep -rniE "([^"]+)"', makefile)
    assert pattern, "credential ban not found in Makefile"
    banned = set(pattern.group(1).split("|"))
    assert len(banned) >= 5, "the ban list looks truncated"

    with db.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public'"
        )
        columns = {r[0].lower() for r in cur.fetchall()}
    assert not (columns & banned)


# --- the unique index, which is the point --------------------------------------


def test_dedupe_key_is_unique_at_the_database_level(db, investor) -> None:
    """The single most important line in the schema."""
    import psycopg

    row = txn()
    key = make_dedupe_key(row)
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO transaction (account_id, isin, txn_date, txn_type, quantity, "
            "price, source, dedupe_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (row.account_id, row.isin, row.txn_date, "BUY", row.quantity, row.price,
             "TRADEBOOK", key),
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO transaction (account_id, isin, txn_date, txn_type, quantity, "
                "price, source, dedupe_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (row.account_id, row.isin, row.txn_date, "BUY", row.quantity, row.price,
                 "TRADEBOOK", key),
            )
    db.rollback()


def test_duplicate_import_is_a_noop_against_the_real_database(db, investor) -> None:
    """Case 9 where BUILD_PLAN says it must pass: against Postgres, not in memory."""
    rows = [txn()]
    first = repository.save_transactions(db, rows)
    assert (first.inserted, first.skipped_duplicates) == (1, 0)

    second = repository.save_transactions(db, rows)
    assert (second.inserted, second.skipped_duplicates) == (0, 1)

    assert len(repository.load_transactions(db, investor_id=investor)) == 1


def test_overlapping_imports_insert_each_trade_once(db, investor) -> None:
    """Five overlapping tradebook exports is the normal case, not the exception."""
    a = [txn(ref="T1"), txn(ref="T2")]
    b = [txn(ref="T2"), txn(ref="T3")]
    repository.save_transactions(db, a)
    summary = repository.save_transactions(db, b)
    assert (summary.inserted, summary.skipped_duplicates) == (1, 1)
    assert len(repository.load_transactions(db, investor_id=investor)) == 3


# --- append-only ---------------------------------------------------------------


def test_update_on_transaction_raises(db, investor) -> None:
    import psycopg

    repository.save_transactions(db, [txn()])
    with db.cursor() as cur, pytest.raises(psycopg.errors.RestrictViolation):
        cur.execute("UPDATE transaction SET quantity = 1")
    db.rollback()


def test_delete_on_transaction_raises(db, investor) -> None:
    import psycopg

    repository.save_transactions(db, [txn()])
    with db.cursor() as cur, pytest.raises(psycopg.errors.RestrictViolation):
        cur.execute("DELETE FROM transaction")
    db.rollback()


def test_erasure_flag_is_the_only_way_through(db, investor) -> None:
    repository.save_transactions(db, [txn()])
    with db.cursor() as cur:
        cur.execute("SET LOCAL app.erasure_authorised = 'on'")
        cur.execute("DELETE FROM transaction")
        assert cur.rowcount == 1
    db.rollback()


# --- precision -----------------------------------------------------------------


def test_numeric_round_trips_without_drift(db, investor) -> None:
    """NUMERIC(20,6). Six decimals of quantity, exactly, in and out."""
    repository.save_transactions(
        db, [txn(qty="0.012000", price="1234.567891", ref="FRACTIONAL")]
    )
    (loaded,) = repository.load_transactions(db, isin="INE153T01027")
    assert loaded.quantity == Decimal("0.012000")
    assert loaded.price == Decimal("1234.567891")
    assert isinstance(loaded.quantity, Decimal)


def test_loaded_rows_are_engine_objects(db, investor) -> None:
    """The boundary is enforced by what crosses it: Transactions, not rows."""
    repository.save_transactions(db, [txn()])
    (loaded,) = repository.load_transactions(db, investor_id=investor)
    assert isinstance(loaded, Transaction)
    assert loaded.txn_type is TxnType.BUY
    assert loaded.source is Source.TRADEBOOK


def test_quantity_must_be_positive(db, investor) -> None:
    """Direction comes from txn_type, never from a sign on quantity."""
    import psycopg

    with db.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO transaction (account_id, isin, txn_date, txn_type, quantity, "
            "price, source, dedupe_key) VALUES (%s,'INE153T01027','2024-01-10','SELL',"
            "-5,100,'MANUAL','neg')",
            (os.environ["_TEST_ACCOUNT_ID"],),
        )
    db.rollback()


def test_isin_format_is_enforced(db) -> None:
    import psycopg

    with db.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute("INSERT INTO security (isin) VALUES ('NOTANISIN')")
    db.rollback()


# --- audit ---------------------------------------------------------------------


def test_every_import_leaves_an_audit_row(db, investor) -> None:
    repository.save_transactions(db, [txn()], actor_uid=None)
    with db.cursor() as cur:
        cur.execute("SELECT action, diff_json FROM audit_log WHERE action = %s",
                    (audit.ACTION_IMPORT,))
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][1]["inserted"] == 1


def test_a_failed_audit_rolls_back_the_mutation(db, investor, monkeypatch) -> None:
    """An unaudited mutation must be impossible, not merely unlikely.

    The audit write shares the transaction, so if it cannot be written the data it would
    have described does not survive either.
    """
    def boom(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(audit, "record", boom)
    with pytest.raises(RuntimeError):
        repository.save_transactions(db, [txn()])
    db.rollback()

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM transaction")
        assert cur.fetchone()[0] == 0
