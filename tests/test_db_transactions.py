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

import pytest
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


def test_all_ten_txn_types_are_accepted_and_written(db, consented_investor) -> None:
    rows = [row(txn_type=t, source_ref=f"ref-{t.value}") for t in TxnType]
    summary = create_transactions(consented_investor, rows, connection=db)
    assert summary == {"inserted": 10, "skipped_duplicates": 0, "rejected": []}
    assert txn_count(db) == 10


def test_a_batch_with_a_within_batch_duplicate_inserts_once(db, consented_investor) -> None:
    duplicate_pair = [row(source_ref="dup"), row(source_ref="dup")]
    summary = create_transactions(consented_investor, duplicate_pair, connection=db)
    assert summary == {"inserted": 1, "skipped_duplicates": 1, "rejected": []}
    assert txn_count(db) == 1


def test_an_unknown_account_id_is_refused_by_the_database(db, consented_investor) -> None:
    import psycopg

    bad = TransactionIn(
        account_id="00000000-0000-0000-0000-000000000000",
        isin="INE153T01027",
        txn_date=date(2024, 1, 10),
        txn_type="BUY",
        quantity="10",
        price="100",
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        create_transactions(consented_investor, [bad], connection=db)
    db.rollback()
