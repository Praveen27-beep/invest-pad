"""POST/GET /investors/{id}/consent[/withdraw] -- app.routers.consent -- and the
``require_consent()`` gate wired into POST /investors/{id}/transactions and
POST /ingest/csv, against a real database.

Calls the route handlers directly with the ``db`` fixture's connection, the same
pattern tests/test_db_investors.py and tests/test_db_transactions.py use: a FastAPI
route decorator returns the plain function underneath, so no HTTP client is needed to
exercise it against a real Postgres cluster. ``current_user`` is passed by hand below,
standing in for what a real ``Depends(get_current_user)`` would have resolved from a
bearer token -- the same convention tests/test_db_grievance_router.py uses; that file's
own docstring explains why this does not prove an unauthenticated request is refused
(the plain function bypasses FastAPI's dependency injection entirely).

The email-ingestion path's gate is proven separately in tests/test_db_webhook.py, over
a real HTTP round trip via TestClient -- see
test_a_consent_less_investor_is_refused_and_nothing_is_staged there.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pytest
from app.config import Settings
from app.db.consent import ConsentMissingError
from app.routers.consent import consent_status, grant_consent, withdraw_consent
from app.routers.ingest import ingest_csv
from app.routers.transactions import create_transactions
from app.schemas.consent import ConsentGrantIn
from app.schemas.transactions import TransactionIn
from fastapi import UploadFile

pytestmark = pytest.mark.db

STAFF = {"id": "11111111-1111-1111-1111-111111111111", "email": "adviser@example.com"}

CSV_ROW = (
    "symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,"
    "trade_id,order_id,order_execution_time\n"
    "BLS,INE153T01027,2024-01-10,NSE,EQ,EQ,buy,false,100.000000,200.500000,"
    "12345,99001,2024-01-10T10:15:00\n"
)


def ingest_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        debug=True,
        database_url="postgresql://unused/for-this-suite",
        portfolio_encryption_key="unused-in-this-suite",
        portfolio_pan_pepper="unused-in-this-suite",
        jwt_secret="test-jwt-secret-not-for-production",
        storage_backend="local",
        local_storage_root=str(tmp_path / "objects"),
    )


def grant(db, investor, notice_version="v1", evidence_ref="msg-1") -> dict:
    return grant_consent(
        investor,
        ConsentGrantIn(notice_version=notice_version, evidence_ref=evidence_ref),
        conn=db,
        current_user=STAFF,
    )


# --- the router's own endpoints ------------------------------------------------------


def test_grant_records_a_consent_and_is_audited(db, investor) -> None:
    result = grant(db, investor)
    assert result["investor_id"] == investor
    assert result["notice_version"] == "v1"
    assert result["purpose"] == "PORTFOLIO_TRACKING"
    assert result["lawful_basis"] == "CONSENT"

    with db.cursor() as cur:
        cur.execute(
            "SELECT action, actor_uid FROM audit_log WHERE entity_id = %s", (result["id"],)
        )
        action, actor_uid = cur.fetchone()
    assert action == "CONSENT_GIVEN"
    assert str(actor_uid) == STAFF["id"]


def test_withdraw_takes_effect_and_reports_count(db, investor) -> None:
    grant(db, investor)
    result = withdraw_consent(investor, conn=db, current_user=STAFF)
    assert result == {"withdrawn_count": 1}


def test_status_reflects_grant_and_withdrawal(db, investor) -> None:
    assert consent_status(investor, conn=db) == {"has_live_consent": False}
    grant(db, investor)
    assert consent_status(investor, conn=db) == {"has_live_consent": True}
    withdraw_consent(investor, conn=db, current_user=STAFF)
    assert consent_status(investor, conn=db) == {"has_live_consent": False}


def test_a_regrant_after_withdrawal_is_a_new_row(db, investor) -> None:
    """The evidentiary history must survive -- app.db.consent.record_consent's own
    docstring. Proven here through the router, not just the db layer directly (already
    covered by tests/test_db_compliance.py)."""
    grant(db, investor, notice_version="v1")
    withdraw_consent(investor, conn=db, current_user=STAFF)
    grant(db, investor, notice_version="v2")

    with db.cursor() as cur:
        cur.execute(
            "SELECT notice_version, withdrawn_at FROM client_consent "
            "WHERE investor_id = %s ORDER BY consent_given_at",
            (investor,),
        )
        rows = cur.fetchall()
    assert [r[0] for r in rows] == ["v1", "v2"]
    assert rows[0][1] is not None and rows[1][1] is None


# --- the gate on POST /investors/{id}/transactions ------------------------------------


def transaction_row() -> TransactionIn:
    import os

    return TransactionIn(
        account_id=os.environ["_TEST_ACCOUNT_ID"],
        isin="INE153T01027",
        txn_date=date(2024, 1, 10),
        txn_type="BUY",
        quantity="10",
        price="100",
        source="MANUAL",
        source_ref="T1",
    )


def test_transactions_endpoint_refuses_without_a_consent_grant(db, investor) -> None:
    with pytest.raises(ConsentMissingError):
        create_transactions(investor, [transaction_row()], connection=db)
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM transaction")
        assert cur.fetchone()[0] == 0, "nothing must be written when consent is missing"


def test_transactions_endpoint_succeeds_once_consent_is_granted(db, investor) -> None:
    grant(db, investor)
    summary = create_transactions(investor, [transaction_row()], connection=db)
    assert summary == {"inserted": 1, "skipped_duplicates": 0, "rejected": []}


# --- the gate on POST /ingest/csv ------------------------------------------------------


def test_ingest_csv_refuses_without_a_consent_grant(db, investor, tmp_path) -> None:
    import os

    upload = UploadFile(file=io.BytesIO(CSV_ROW.encode()), filename="tradebook.csv")
    with pytest.raises(ConsentMissingError):
        import asyncio

        asyncio.run(
            ingest_csv(
                investor_id=investor,
                account_id=os.environ["_TEST_ACCOUNT_ID"],
                adapter="zerodha_tradebook",
                files=[upload],
                conn=db,
                settings=ingest_settings(tmp_path),
            )
        )
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM import_batch")
        assert cur.fetchone()[0] == 0, "nothing must be staged when consent is missing"


def test_ingest_csv_succeeds_once_consent_is_granted(db, investor, tmp_path) -> None:
    import asyncio
    import os

    grant(db, investor)
    upload = UploadFile(file=io.BytesIO(CSV_ROW.encode()), filename="tradebook.csv")
    (result,) = asyncio.run(
        ingest_csv(
            investor_id=investor,
            account_id=os.environ["_TEST_ACCOUNT_ID"],
            adapter="zerodha_tradebook",
            files=[upload],
            conn=db,
            settings=ingest_settings(tmp_path),
        )
    )
    assert result["parsed"] == 1
