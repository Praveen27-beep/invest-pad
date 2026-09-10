"""CasPdfAdapter staged and promoted against a real database.

Closes the loop the pure-text tests in tests/test_cas_pdf.py can't reach: that
``Source.CAS`` actually inserts into the real ``txn_source`` Postgres enum (i.e. that
app/db/migrations/018_cas_source.sql applied and the value is usable, not just that the
migration ran without error), that ``stage_batch``'s new ``doctype``/``content_type``
parameters land in the ``document`` row correctly, and that a CAS-declared holding
actually reaches ``holding_snapshot`` -- app.db.holdings.record_snapshot's real SQL
against the real table, not a mock.

Content is plain UTF-8 text, not a real PDF: CasPdfAdapter.parse() only calls
pdfplumber when the bytes start with ``%PDF-``, decoding anything else directly -- the
same shortcut tests/test_db_webhook.py takes for the contract-note adapter, for the
same reason (no password-protected PDF needs to live in the repository to exercise the
staging plumbing).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from app.db import imports
from app.engine.types import Source, TxnType
from app.ingest.cas_pdf import CasPdfAdapter
from app.storage.local import SIGNING_SECRET_ENV, LocalDocumentStore

pytestmark = pytest.mark.db

ACTOR = "33333333-3333-3333-3333-333333333333"

MARKER = "CONSOLIDATED ACCOUNT STATEMENT (CAS) FOR SECURITIES HELD IN DEMAT FORM\n"

DP_SUMMARY = (
    "ZERODHA BROKING LIMITED\n"
    "CDSL Demat Account 1 5,350.50\n"
    "DP Id: 12081600 Client Id :46203315\n"
)

AS_ON_LINE = "Portfolio Value ` 5,350.50 as on 31-07-2026\n"

SPLIT_ROW = (
    "BLS SPLIT PAYOUT-CR CM\n"
    "EQUITY SHARES M51766 TM/CP\n"
    "INE153T01027 28-07-2026 0.000 100.000 -- 100.000 0\n"
    "EQUITY SHARES OF RE 1/- 13906 SETT\n"
    "AFTER SPLIT 1211232026139\n"
)

HOLDINGS_TABLE = (
    "INE153T01027 BLS LIMITED - EQUITY SHARES 100.000 -- -- -- 100.000 53.5050 5,350.50\n"
)

CAS_TEXT = (MARKER + DP_SUMMARY + AS_ON_LINE + SPLIT_ROW + HOLDINGS_TABLE).encode()


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalDocumentStore:
    monkeypatch.setenv(SIGNING_SECRET_ENV, "test-signing-secret")
    return LocalDocumentStore(tmp_path / "objects")


def _document_row(db):
    with db.cursor() as cur:
        cur.execute("SELECT doctype, content_type FROM document ORDER BY stored_at DESC LIMIT 1")
        return cur.fetchone()


def _snapshot_rows(db, account_id: str):
    with db.cursor() as cur:
        cur.execute(
            "SELECT isin, quantity, source FROM holding_snapshot WHERE account_id = %s",
            (account_id,),
        )
        return cur.fetchall()


def test_staging_a_cas_records_the_right_document_metadata(db, investor, store) -> None:
    """Regression: stage_batch used to hardcode TRADEBOOK/text-csv for every adapter,
    including PDFs -- see app/db/imports.py's stage_batch docstring."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    adapter = CasPdfAdapter(broker_accounts={"zerodha": account_id})

    imports.stage_batch(
        db, adapter, CAS_TEXT, investor_id=investor, account_id=account_id,
        filename="cas.pdf", store=store, investor_code="C001",
        doctype="CAS", content_type="application/pdf",
    )
    doctype, content_type = _document_row(db)
    assert doctype == "CAS"
    assert content_type == "application/pdf"


def test_staging_a_cas_writes_a_holding_snapshot(db, investor, store) -> None:
    """The reconciliation seam app/db/migrations/001_core.sql describes but nothing
    wrote to before this adapter: app.db.holdings.record_snapshot, called from
    stage_batch when the adapter defines parse_declared_holdings."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    adapter = CasPdfAdapter(broker_accounts={"zerodha": account_id})

    result = imports.stage_batch(
        db, adapter, CAS_TEXT, investor_id=investor, account_id=account_id,
        filename="cas.pdf", store=store, investor_code="C001",
        doctype="CAS", content_type="application/pdf",
    )
    assert result["declared_holdings"] == 1

    (row,) = _snapshot_rows(db, account_id)
    isin, quantity, source = row
    assert isin == "INE153T01027"
    assert quantity == 100
    assert source == "CAS"


def test_a_promoted_cas_row_carries_the_cas_source_enum_value(db, investor, store) -> None:
    """The real point of app/db/migrations/018_cas_source.sql: Source.CAS must be a
    usable value in the real txn_source Postgres enum, not just an app-level string
    that happens not to error until it hits the database."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    adapter = CasPdfAdapter(broker_accounts={"zerodha": account_id})

    batch = imports.stage_batch(
        db, adapter, CAS_TEXT, investor_id=investor, account_id=account_id,
        filename="cas.pdf", store=store, investor_code="C001",
        doctype="CAS", content_type="application/pdf",
    )
    imports.promote_batch(db, batch["batch_id"], actor_uid=ACTOR)

    with db.cursor() as cur:
        cur.execute(
            "SELECT isin, txn_type, quantity, price, source::text FROM transaction "
            "WHERE account_id = %s",
            (account_id,),
        )
        (row,) = cur.fetchall()
    isin, txn_type, quantity, price, source = row
    assert isin == "INE153T01027"
    assert TxnType(txn_type) is TxnType.SPLIT_ADJ
    assert quantity == 100
    assert price == 0
    assert Source(source) is Source.CAS
