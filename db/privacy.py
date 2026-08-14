"""DPDP data-principal rights: export and erasure.

Both are rights, not favours. They have to work on demand, which means they have to be
built and tested before client data lands rather than written in a hurry when the first
request arrives.
"""

from __future__ import annotations

from typing import Any

from db import audit, crypto, documents

#: Session flag the append-only trigger checks. Erasure is the ONE path allowed to delete
#: from the ledger, and it has to announce itself to do so -- see 001_core.sql.
ERASURE_FLAG = "app.erasure_authorised"


class LegalHoldError(PermissionError):
    """Erasure refused: an open legal hold covers this investor."""

    def __init__(self, investor_id: str, reasons: list[str]) -> None:
        self.investor_id = investor_id
        self.reasons = reasons
        super().__init__(
            f"Erasure refused for investor {investor_id}: open legal hold "
            f"({'; '.join(reasons)}). Where a dispute has been raised, records are kept "
            "until it resolves or SEBI directs otherwise."
        )


def open_holds(conn: Any, investor_id: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT reason FROM legal_hold WHERE investor_id = %s AND released_at IS NULL",
            (investor_id,),
        )
        return [row[0] for row in cur.fetchall()]


def place_legal_hold(
    conn: Any, investor_id: str, reason: str, actor_uid: str | None = None
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO legal_hold (investor_id, reason) VALUES (%s, %s) RETURNING id",
            (investor_id, reason),
        )
        hold_id = str(cur.fetchone()[0])
    audit.record(
        conn, audit.ACTION_LEGAL_HOLD_PLACED, "investor", investor_id, actor_uid,
        {"hold_id": hold_id, "reason": reason},
    )
    return hold_id


def release_legal_hold(conn: Any, hold_id: str, actor_uid: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE legal_hold SET released_at = now() WHERE id = %s AND released_at IS NULL",
            (hold_id,),
        )
    audit.record(conn, audit.ACTION_LEGAL_HOLD_RELEASED, "legal_hold", hold_id, actor_uid)


def export_investor(
    conn: Any,
    investor_id: str,
    include_identifiers: bool = False,
    actor_uid: str | None = None,
) -> dict[str, Any]:
    """Everything held about one investor -- the DPDP portability right.

    ``include_identifiers`` decrypts PAN and demat. Off by default: an export is usually
    wanted for its portfolio content, and decrypting identifiers that nobody asked for
    widens the blast radius of wherever the export file ends up. Turning it on is logged
    as a distinct access event, because reading personal data is itself something the
    principal is entitled to know about.
    """
    export: dict[str, Any] = {}

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, code, display_name, family_group_id, created_at "
            "FROM investor WHERE id = %s",
            (investor_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise LookupError(f"no such investor: {investor_id}")
        export["investor"] = dict(
            zip([c.name for c in cur.description], row, strict=True)
        )

        for table, sql in (
            ("accounts", "SELECT * FROM account WHERE investor_id = %s"),
            ("consents", "SELECT * FROM client_consent WHERE investor_id = %s"),
            ("legal_holds", "SELECT * FROM legal_hold WHERE investor_id = %s"),
            (
                "transactions",
                "SELECT t.* FROM transaction t JOIN account a ON a.id = t.account_id "
                "WHERE a.investor_id = %s ORDER BY t.txn_date",
            ),
        ):
            cur.execute(sql, (investor_id,))
            columns = [c.name for c in cur.description]
            export[table] = [dict(zip(columns, r, strict=True)) for r in cur.fetchall()]

        if include_identifiers:
            cur.execute(
                "SELECT pan_enc, demat_enc FROM investor_secret WHERE investor_id = %s",
                (investor_id,),
            )
            secret = cur.fetchone()
            if secret:
                export["identifiers"] = {
                    "pan": crypto.decrypt(secret[0]) if secret[0] else None,
                    "demat": crypto.decrypt(secret[1]) if secret[1] else None,
                }
            audit.record(
                conn, audit.ACTION_SECRET_READ, "investor", investor_id, actor_uid,
                {"reason": "export with identifiers"},
            )

    # Documents are LISTED, never embedded. A portability export carrying megabytes of
    # decrypted PDF is a second copy of the most sensitive thing in the system, in a file
    # that then travels by email. The list plus a signed URL is the safer shape.
    export["documents"] = documents.documents_for_investor(conn, investor_id)

    audit.record(
        conn, audit.ACTION_EXPORT, "investor", investor_id, actor_uid,
        {
            "documents": len(export["documents"]),
            "include_identifiers": include_identifiers,
            "transactions": len(export["transactions"]),
            "accounts": len(export["accounts"]),
        },
    )
    return export


def erase_investor(
    conn: Any, investor_id: str, actor_uid: str | None = None, store: Any = None
) -> dict[str, int]:
    """Delete everything about one investor. Returns what was removed.

    Refuses while a legal hold is open. Otherwise sets ``app.erasure_authorised`` LOCAL --
    the one thing that lets the append-only trigger permit a delete -- and cascades from
    ``investor``.

    THE AUDIT TRAIL SURVIVES. The ``audit_log`` rows for this investor are deliberately
    not deleted: erasing the evidence that you erased would defeat both DPDP's access-log
    duty and SEBI's five-year record. Those rows reference an investor id that no longer
    resolves, which is the point -- they record that something happened without retaining
    what it was about.

    Raises:
        LegalHoldError: an open hold covers this investor.
    """
    holds = open_holds(conn, investor_id)
    if holds:
        raise LegalHoldError(investor_id, holds)

    # Documents first, and before any row is touched. A PDF holding the PAN and the full
    # holdings that outlives the record of it is not an erasure - it is a leak with no
    # index. Passing no store is allowed only where no documents exist, and is asserted.
    docs_removed = 0
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM document WHERE investor_id = %s", (investor_id,))
        doc_count = cur.fetchone()[0]
        cur.execute("SELECT code FROM investor WHERE id = %s", (investor_id,))
        row = cur.fetchone()
        investor_code = row[0] if row else ""

    if doc_count and store is None:
        raise ValueError(
            f"investor {investor_id} has {doc_count} stored documents but no store was "
            "given. Refusing to erase database rows while leaving the files behind."
        )
    if store is not None:
        docs_removed = documents.delete_documents_for_investor(
            conn, store, investor_id, investor_code, actor_uid
        )

    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM transaction t JOIN account a ON a.id = t.account_id "
            "WHERE a.investor_id = %s",
            (investor_id,),
        )
        txn_count = cur.fetchone()[0]

        # Announce the erasure to the append-only trigger. LOCAL, so it expires with this
        # transaction and cannot leak authorisation into any later statement.
        cur.execute(f"SET LOCAL {ERASURE_FLAG} = 'on'")
        cur.execute("DELETE FROM investor WHERE id = %s", (investor_id,))
        removed = cur.rowcount

    # Recorded AFTER the delete and outside the flag's usefulness, so the trail is the
    # last thing written and cannot itself be cascaded away.
    audit.record(
        conn, audit.ACTION_ERASURE, "investor", investor_id, actor_uid,
        {"transactions_deleted": txn_count, "investors_deleted": removed,
         "documents_deleted": docs_removed},
    )
    return {"investors": removed, "transactions": txn_count, "documents": docs_removed}
