"""Document persistence and its compliance consequences, against a real cluster.

The assertion that matters most here is that erasure removes the FILES, not just the rows.
A statement that outlives the record of it is a leak with no index.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from app.db import audit, documents, privacy
from app.storage.local import SIGNING_SECRET_ENV, LocalDocumentStore

pytestmark = pytest.mark.db

PDF = b"%PDF-1.4 CAS for C001"
OTHER = b"%PDF-1.4 contract note"


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalDocumentStore:
    monkeypatch.setenv(SIGNING_SECRET_ENV, "test-signing-secret")
    return LocalDocumentStore(tmp_path / "objects")


def store_one(db, store, investor, content=PDF, doctype="CAS", filename="cas.pdf"):
    return documents.store_document(
        db,
        store,
        investor_id=investor,
        investor_code="C001",
        doctype=doctype,
        content=content,
        received=date(2026, 3, 31),
        filename=filename,
    )


def test_storing_records_the_pointer_and_writes_the_object(db, store, investor) -> None:
    result = store_one(db, store, investor)
    assert result["already_present"] is False
    assert store.get(result["storage_key"]) == PDF
    assert store.exists(result["storage_key"])


def test_storing_the_same_document_twice_inserts_one_row(db, store, investor) -> None:
    """Forwarding delivers the same statement more than once. That must be a no-op."""
    first = store_one(db, store, investor)
    second = store_one(db, store, investor, filename="cas (1).pdf")

    assert second["already_present"] is True
    assert str(second["id"]) == str(first["id"])
    assert len(documents.documents_for_investor(db, investor)) == 1


def test_different_documents_both_land(db, store, investor) -> None:
    store_one(db, store, investor, content=PDF)
    store_one(db, store, investor, content=OTHER, doctype="CONTRACT_NOTE")
    assert len(documents.documents_for_investor(db, investor)) == 2


def test_sha256_is_unique_at_the_database_level(db, store, investor) -> None:
    import psycopg

    result = store_one(db, store, investor)
    with db.cursor() as cur, pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO document (investor_id, doctype, storage_key, sha256, byte_size, "
            "received_at) VALUES (%s,'CAS','other/key.pdf',%s,10,'2026-03-31')",
            (investor, result["sha256"]),
        )
    db.rollback()


def test_storing_is_audited(db, store, investor) -> None:
    store_one(db, store, investor)
    with db.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM audit_log WHERE action = %s", (audit.ACTION_DOCUMENT_STORED,)
        )
        assert cur.fetchone()[0] == 1


def test_issuing_a_signed_url_is_audited(db, store, investor) -> None:
    """Access is granted at issuance. Following the URL happens at the provider, which
    this system may never hear about."""
    result = store_one(db, store, investor)
    url = documents.signed_url_for(db, store, result["id"], ttl_seconds=60)
    assert "signature=" in url

    with db.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM audit_log WHERE action = %s", (audit.ACTION_DOCUMENT_ACCESSED,)
        )
        assert cur.fetchone()[0] == 1


# --- the assertion this whole session exists for -------------------------------


def test_erasure_removes_the_files_not_just_the_rows(db, store, investor) -> None:
    result = store_one(db, store, investor)
    key = result["storage_key"]
    assert store.exists(key)

    erased = privacy.erase_investor(db, investor, store=store)

    assert erased["documents"] == 1
    assert not store.exists(key), "the PDF outlived the record of it"
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM document")
        assert cur.fetchone()[0] == 0


def test_erasure_refuses_when_documents_exist_but_no_store_is_given(db, store, investor) -> None:
    """Better to refuse than to delete the rows and silently strand the files."""
    result = store_one(db, store, investor)
    with pytest.raises(ValueError, match="no store was given"):
        privacy.erase_investor(db, investor)
    db.rollback()
    assert store.exists(result["storage_key"])


def test_erasure_without_documents_needs_no_store(db, investor) -> None:
    assert privacy.erase_investor(db, investor)["documents"] == 0


def test_legal_hold_still_protects_documents(db, store, investor) -> None:
    result = store_one(db, store, investor)
    privacy.place_legal_hold(db, investor, reason="SEBI complaint")

    with pytest.raises(privacy.LegalHoldError):
        privacy.erase_investor(db, investor, store=store)

    assert store.exists(result["storage_key"]), "held documents must survive"
    assert len(documents.documents_for_investor(db, investor)) == 1


def test_erasure_does_not_touch_another_investors_documents(db, store, investor) -> None:
    store_one(db, store, investor)
    with db.cursor() as cur:
        cur.execute("INSERT INTO investor (code, display_name) VALUES ('C002','Two') RETURNING id")
        other = str(cur.fetchone()[0])
    documents.store_document(
        db,
        store,
        investor_id=other,
        investor_code="C002",
        doctype="CAS",
        content=OTHER,
        received=date(2026, 3, 31),
        filename="cas.pdf",
    )

    privacy.erase_investor(db, investor, store=store)
    survivors = documents.documents_for_investor(db, other)
    assert len(survivors) == 1
    assert store.exists(survivors[0]["storage_key"])


# --- export --------------------------------------------------------------------


def test_export_lists_documents_without_embedding_bytes(db, store, investor) -> None:
    """A portability export carrying megabytes of PDF is a second copy of the most
    sensitive thing here, in a file that then travels by email."""
    store_one(db, store, investor)
    export = privacy.export_investor(db, investor)

    assert len(export["documents"]) == 1
    serialised = repr(export)
    assert "%PDF" not in serialised
    assert export["documents"][0]["sha256"]


# --- key rotation groundwork from migration 003 --------------------------------


def test_pan_hash_cannot_be_stored_without_its_ciphertext(db, investor, crypto_env) -> None:
    """A hash without the PAN behind it can never be re-peppered. See docs/KEY_ROTATION.md."""
    import psycopg
    from app.db import crypto

    with db.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO investor_secret (investor_id, pan_hash) VALUES (%s,%s)",
            (investor, crypto.hash_pan("AAAPZ1234C")),
        )
    db.rollback()


def test_versioning_columns_exist_for_rotation(db) -> None:
    with db.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'investor_secret'"
        )
        columns = {r[0] for r in cur.fetchall()}
    assert {"key_version", "pepper_version", "pan_hash_next"} <= columns


def _other_investor(db: object, code: str = "C002") -> str:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO investor (code, display_name) VALUES (%s,'Two') RETURNING id", (code,)
        )
        return str(cur.fetchone()[0])


def test_the_same_document_stores_independently_for_another_investor(db, store, investor) -> None:
    """Regression: document.sha256 was UNIQUE across the whole table, so the second
    investor to send identical bytes was handed the FIRST investor's row -- someone
    else's document id, someone else's storage key, already_present=True. Their own
    upload was never recorded at all. A content hash identifies bytes, not a tenant."""
    other = _other_investor(db)

    mine = store_one(db, store, investor)
    theirs = documents.store_document(
        db,
        store,
        investor_id=other,
        investor_code="C002",
        doctype="CAS",
        content=PDF,
        received=date(2026, 3, 31),
        filename="cas.pdf",
    )

    assert theirs["already_present"] is False
    assert str(theirs["id"]) != str(mine["id"])
    assert theirs["storage_key"] != mine["storage_key"]
    assert len(documents.documents_for_investor(db, investor)) == 1
    assert len(documents.documents_for_investor(db, other)) == 1

    # The whole point of the hash short-circuit still holds within one investor.
    assert store_one(db, store, investor)["already_present"] is True


def test_erasure_spares_another_investors_identical_document(db, store, investor) -> None:
    """The sharp end of the global UNIQUE: two investors legitimately hold the same bytes
    (a joint account's contract note, an identical NIL statement). Sharing one row meant
    erasing one investor deleted the object the other's record still pointed at."""
    other = _other_investor(db)
    mine = store_one(db, store, investor)
    theirs = documents.store_document(
        db,
        store,
        investor_id=other,
        investor_code="C002",
        doctype="CAS",
        content=PDF,
        received=date(2026, 3, 31),
        filename="cas.pdf",
    )

    privacy.erase_investor(db, investor, store=store)

    assert not store.exists(mine["storage_key"]), "the erased investor's object must go"
    survivors = documents.documents_for_investor(db, other)
    assert len(survivors) == 1
    assert store.exists(theirs["storage_key"]), "the other investor's bytes must survive"
