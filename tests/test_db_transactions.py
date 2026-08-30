"""POST /investors/{id}/transactions -- app.routers.transactions.create_transactions,
against a real database. See docs/FULL_VISION_BACKEND_ROADMAP.md section A1.

Calls the route handler directly with the ``db`` fixture's connection, the same pattern
tests/test_db_imports.py uses for ``imports.stage_batch``/``promote_batch``: a FastAPI
route decorator returns the plain function underneath, so no HTTP client is needed to
exercise it against a real Postgres cluster.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest
from app.db.repository import load_transactions
from app.engine.types import TxnType
from app.routers.transactions import create_transactions
from app.schemas.transactions import TransactionIn

pytestmark = pytest.mark.db

#: Per docs/DATA_MODEL.md's txn_type table: quantity/price for everything except
#: DIVIDEND (0/0, amount carried separately); DIVIDEND itself carries no quantity/price.
_SAMPLE_FIELDS = {
    TxnType.DIVIDEND: {"quantity": "0", "price": "0", "dividend_amount": "500"},
}


def row(txn_type: TxnType = TxnType.BUY, source_ref: str = "T1") -> TransactionIn:
    fields = {
        "account_id": os.environ["_TEST_ACCOUNT_ID"],
        "isin": "INE153T01027",
        "txn_date": date(2024, 1, 10),
        "txn_type": txn_type.value,
        "quantity": "10",
        "price": "100",
        "source": "MANUAL",
        "source_ref": source_ref,
    }
    fields.update(_SAMPLE_FIELDS.get(txn_type, {}))
    return TransactionIn(**fields)


def txn_count(db) -> int:
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM transaction")
        return cur.fetchone()[0]


def test_posting_inserts_a_transaction(db, consented_investor) -> None:
    summary = create_transactions(consented_investor, [row()], connection=db)
    assert summary == {"inserted": 1, "skipped_duplicates": 0, "rejected": []}
    assert txn_count(db) == 1


def test_reposting_the_same_row_is_idempotent(db, consented_investor) -> None:
    """Re-importing a file must be a no-op -- CLAUDE.md rule 3."""
    create_transactions(consented_investor, [row()], connection=db)
    summary = create_transactions(consented_investor, [row()], connection=db)
    assert summary == {"inserted": 0, "skipped_duplicates": 1, "rejected": []}
    assert txn_count(db) == 1


def test_every_txn_type_is_accepted_and_written(db, consented_investor) -> None:
    """Every TxnType, not a hardcoded count -- DEMERGER_COST_OUT/DEMERGER_COST_IN
    (migration 017) grew this enum from 10 to 12 after this test was first written with
    a literal ``10``, which silently stopped meaning "every type" the moment a new one
    was added. len(TxnType) can't go stale the same way."""
    rows = [row(txn_type=t, source_ref=f"ref-{t.value}") for t in TxnType]
    summary = create_transactions(consented_investor, rows, connection=db)
    assert summary == {
        "inserted": len(TxnType),
        "skipped_duplicates": 0,
        "rejected": [],
    }
    assert txn_count(db) == len(TxnType)


def test_a_batch_with_a_within_batch_duplicate_inserts_once(db, consented_investor) -> None:
    duplicate_pair = [row(source_ref="dup"), row(source_ref="dup")]
    summary = create_transactions(consented_investor, duplicate_pair, connection=db)
    assert summary == {"inserted": 1, "skipped_duplicates": 1, "rejected": []}
    assert txn_count(db) == 1


def test_an_isin_never_seen_before_is_accepted_not_a_foreign_key_violation(
    db, consented_investor
) -> None:
    """PHASE1_FIELD_TEST_REPORT.md Finding 1: manual entry referencing a brand-new ISIN
    (the normal case for any new investor -- every ISIN is new) used to fail with an
    unhandled ForeignKeyViolation because nothing on this path created the `security` row
    first, unlike app.db.imports's CSV path. `INE153T01027` (this file's `row()` default)
    is pre-seeded by the `investor` fixture, which is exactly why no existing test here
    caught this -- this one deliberately uses an ISIN nothing has inserted yet."""
    never_seen = TransactionIn(
        account_id=os.environ["_TEST_ACCOUNT_ID"],
        isin="INE040A01034",
        txn_date=date(2024, 1, 10),
        txn_type="BUY",
        quantity="10",
        price="100",
        source="MANUAL",
        source_ref="new-isin",
    )
    summary = create_transactions(consented_investor, [never_seen], connection=db)
    assert summary == {"inserted": 1, "skipped_duplicates": 0, "rejected": []}
    with db.cursor() as cur:
        cur.execute("SELECT isin FROM security WHERE isin = 'INE040A01034'")
        assert cur.fetchone() is not None


def test_cost_transfer_survives_a_save_and_load_round_trip(db, consented_investor) -> None:
    """docs/trackr_plus_phase3_overview.md section 7: a DEMERGER_COST_OUT/IN pair used to
    write every field except cost_transfer -- the one field that makes the correction
    meaningful -- and reload as a silent no-op. Pins the fix at the same layer the bug
    lived in: save_transactions -> load_transactions, not just the pure engine function."""
    demerger_out = TransactionIn(
        account_id=os.environ["_TEST_ACCOUNT_ID"],
        isin="INE153T01027",
        txn_date=date(2024, 6, 1),
        txn_type="DEMERGER_COST_OUT",
        quantity="0",
        price="0",
        cost_transfer="1234.567890",
        source="MANUAL",
        source_ref="demerger-out",
    )
    create_transactions(consented_investor, [demerger_out], connection=db)
    loaded = load_transactions(db, investor_id=consented_investor)
    reloaded = next(t for t in loaded if t.source_ref == "demerger-out")
    assert reloaded.cost_transfer == Decimal("1234.567890")


def test_an_unknown_account_id_is_refused_before_it_reaches_the_database(
    db, consented_investor
) -> None:
    """Pre-deployment audit (2026-08-30): this used to be refused by a raw
    ForeignKeyViolation bubbling up as an unhandled 500 -- correct for "doesn't exist",
    but the same unvalidated path also let an authenticated caller who owns
    ``consented_investor`` write rows against an account_id belonging to a DIFFERENT
    investor (and thus a different account owner), since a valid FK proves the account
    exists, not that this investor owns it. ``create_transactions`` now checks
    ``account_belongs_to`` up front -- see test below for the cross-investor case."""
    from fastapi import HTTPException

    bad = TransactionIn(
        account_id="00000000-0000-0000-0000-000000000000",
        isin="INE153T01027",
        txn_date=date(2024, 1, 10),
        txn_type="BUY",
        quantity="10",
        price="100",
    )
    with pytest.raises(HTTPException) as exc_info:
        create_transactions(consented_investor, [bad], connection=db)
    assert exc_info.value.status_code == 404


def test_an_account_belonging_to_another_investor_is_refused(
    db, consented_investor, another_consented_investor
) -> None:
    """The account exists and passes its FK -- it just belongs to a different investor
    than the one named in the URL. Without the ``account_belongs_to`` check this would
    silently append a transaction to a stranger's ledger."""
    from fastapi import HTTPException

    foreign = TransactionIn(
        account_id=os.environ["_TEST_ANOTHER_ACCOUNT_ID"],
        isin="INE153T01027",
        txn_date=date(2024, 1, 10),
        txn_type="BUY",
        quantity="10",
        price="100",
    )
    with pytest.raises(HTTPException) as exc_info:
        create_transactions(consented_investor, [foreign], connection=db)
    assert exc_info.value.status_code == 404
    assert txn_count(db) == 0
    db.rollback()
