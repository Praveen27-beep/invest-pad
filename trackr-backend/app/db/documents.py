"""Document persistence -- the pointer, the provenance, and the audit trail.

The bytes live in object storage; this module holds the row that knows where. Split that
way because the two have different failure modes and different lifecycles, and because a
database that stored megabytes of PDF would make every backup and restore worse for no
benefit.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.db import audit
from app.storage.base import DEFAULT_URL_TTL_SECONDS
from app.storage.keys import content_hash, investor_prefix, object_key


def find_by_hash(conn: Any, sha256: str, investor_id: str) -> dict[str, Any] | None:
    """This investor's document with these bytes, if they already sent them.

    Scoped to the investor deliberately. Searched globally, the second investor to send
    identical bytes -- a joint account's contract note, an identical NIL statement -- was
    handed the first one's row: their document id, their storage_key, and no record of the
    second upload at all. See migration 020.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, investor_id, storage_key, doctype, byte_size, received_at "
            "FROM document WHERE sha256 = %s AND investor_id = %s",
            (sha256, investor_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return dict(zip([c.name for c in cur.description], row, strict=True))


def store_document(
    conn: Any,
    store: Any,
    investor_id: str,
    investor_code: str,
    doctype: str,
    content: bytes,
    received: date,
    filename: str = "",
    content_type: str = "application/pdf",
    account_id: str | None = None,
    source_message_id: str | None = None,
    actor_uid: str | None = None,
) -> dict[str, Any]:
    """Put the bytes in storage and record the pointer. Idempotent on content.

    Re-storing an identical document FOR THE SAME INVESTOR returns the existing row and
    does not duplicate it. That is not an optimisation: email forwarding delivers the same
    statement more than once, and a client uploading their history sends overlapping files
    by necessity. Another investor sending the same bytes gets their own row and their own
    object -- see find_by_hash and migration 020.

    Order matters. The object is written FIRST, then the row. The reverse order can leave a
    row pointing at nothing, which looks like data loss; this order can at worst leave an
    object with no row, which a prefix sweep finds. Prefer the recoverable failure.
    """
    digest = content_hash(content)

    existing = find_by_hash(conn, digest, investor_id)
    if existing is not None:
        # find_by_hash returns the raw row, so ``id`` is a psycopg UUID object, not the
        # string the callers (and StageResultOut) expect. Stringify it before returning.
        return {**existing, "id": str(existing["id"]), "already_present": True}

    key = object_key(investor_code, doctype, received, content, filename)
    store.put(key, content, content_type)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO document (investor_id, account_id, doctype, storage_key, sha256,
                                  byte_size, content_type, filename, source_message_id,
                                  received_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                investor_id,
                account_id,
                doctype,
                key,
                digest,
                len(content),
                content_type,
                filename or None,
                source_message_id,
                received,
            ),
        )
        document_id = str(cur.fetchone()[0])

    audit.record(
        conn,
        audit.ACTION_DOCUMENT_STORED,
        "document",
        document_id,
        actor_uid,
        {"doctype": doctype, "bytes": len(content), "storage_key": key},
    )
    return {
        "id": document_id,
        "storage_key": key,
        "sha256": digest,
        "byte_size": len(content),
        "already_present": False,
    }


def documents_for_investor(conn: Any, investor_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, doctype, storage_key, sha256, byte_size, filename, received_at, "
            "stored_at, parse_status FROM document WHERE investor_id = %s "
            "ORDER BY received_at DESC, stored_at DESC",
            (investor_id,),
        )
        columns = [c.name for c in cur.description]
        return [dict(zip(columns, r, strict=True)) for r in cur.fetchall()]


def signed_url_for(
    conn: Any,
    store: Any,
    document_id: str,
    ttl_seconds: int = DEFAULT_URL_TTL_SECONDS,
    actor_uid: str | None = None,
) -> str:
    """Issue a short-lived URL, and audit the issuance.

    Audited HERE, at issuance, not when the URL is followed. Following it happens at the
    storage provider, which this system may never hear about -- so the moment access is
    granted is the only moment it can honestly be recorded.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT storage_key, investor_id FROM document WHERE id = %s", (document_id,))
        row = cur.fetchone()
        if row is None:
            raise LookupError(f"no such document: {document_id}")
        key, investor_id = row[0], str(row[1])

    audit.record(
        conn,
        audit.ACTION_DOCUMENT_ACCESSED,
        "document",
        document_id,
        actor_uid,
        {"investor_id": investor_id, "ttl_seconds": ttl_seconds},
    )
    return store.signed_url(key, ttl_seconds)


def delete_documents_for_investor(
    conn: Any,
    store: Any,
    investor_id: str,
    investor_code: str,
    actor_uid: str | None = None,
) -> int:
    """Remove an investor's objects and rows. Returns how many documents were removed.

    OBJECTS FIRST. An erasure that drops the rows and leaves the PDFs is not an erasure --
    the file holding the PAN and the full holdings would outlive the record of it, and
    nothing left in the system would know it was there. Deleting objects first means a
    failure part-way leaves rows pointing at missing objects, which is visible and
    re-runnable, rather than orphaned files nobody can find.
    """
    documents = documents_for_investor(conn, investor_id)

    if hasattr(store, "delete_prefix"):
        store.delete_prefix(investor_prefix(investor_code))
    else:
        for doc in documents:
            store.delete(doc["storage_key"])

    with conn.cursor() as cur:
        cur.execute("DELETE FROM document WHERE investor_id = %s", (investor_id,))

    if documents:
        audit.record(
            conn,
            audit.ACTION_DOCUMENT_DELETED,
            "investor",
            investor_id,
            actor_uid,
            {"documents_deleted": len(documents)},
        )
    return len(documents)
