"""Staged imports: stage, review, promote, discard.

The rule this module exists to enforce: **an adapter never writes to the ledger.** Parsing
produces staged rows and stops. A second explicit call, attributed to a person, promotes
them. No automated path can put a row into a client's financial record.

Why that matters more than it looks: a parser that auto-commits is a parser whose bugs land
in a client's cost basis before anyone reads the output. Staging turns a bad parse into a
discarded batch rather than a correction exercise.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from app.db import audit, documents, precedence, repository
from app.engine.dedupe import make_dedupe_key
from app.engine.types import ImportSummary, Source, Transaction, TxnType
from app.ingest.base import REVIEW_THRESHOLD, ParseResult
from app.storage.keys import content_hash

ACTION_BATCH_STAGED = "IMPORT_BATCH_STAGED"
ACTION_BATCH_PROMOTED = "IMPORT_BATCH_PROMOTED"
ACTION_BATCH_DISCARDED = "IMPORT_BATCH_DISCARDED"
ACTION_ROWS_EXCLUDED = "IMPORT_ROWS_EXCLUDED"

STATUS_STAGED = "STAGED"
STATUS_PROMOTED = "PROMOTED"
STATUS_DISCARDED = "DISCARDED"


class BatchNotFoundError(LookupError):
    pass


class BatchAlreadyResolvedError(ValueError):
    """Promoted or discarded batches are final. Re-promoting would double-count."""


class DuplicateUploadError(ValueError):
    """This exact file has been uploaded before."""

    def __init__(self, sha256: str, batch_id: str) -> None:
        self.sha256 = sha256
        self.batch_id = batch_id
        super().__init__(f"identical file already staged as batch {batch_id}")


def _txn_to_payload(txn: Transaction) -> dict[str, Any]:
    return {
        "isin": txn.isin,
        "txn_date": txn.txn_date.isoformat(),
        "txn_type": str(txn.txn_type),
        "quantity": str(txn.quantity),
        "price": str(txn.price),
        "charges": str(txn.charges),
        "account_id": txn.account_id,
        "source": str(txn.source) if txn.source else None,
        "source_ref": txn.source_ref,
    }


def _payload_to_txn(payload: dict[str, Any]) -> Transaction:
    return Transaction(
        isin=payload["isin"],
        txn_date=date.fromisoformat(payload["txn_date"]),
        txn_type=TxnType(payload["txn_type"]),
        quantity=Decimal(payload["quantity"]),
        price=Decimal(payload["price"]),
        charges=Decimal(payload.get("charges", "0")),
        account_id=payload.get("account_id"),
        source=Source(payload["source"]) if payload.get("source") else Source.TRADEBOOK,
        source_ref=payload.get("source_ref"),
    )


def stage_batch(
    conn: Any,
    adapter: Any,
    content: bytes,
    investor_id: str,
    account_id: str,
    filename: str = "",
    store: Any = None,
    investor_code: str = "",
    actor_uid: str | None = None,
) -> dict[str, Any]:
    """Parse a file into staged rows. Writes NOTHING to ``transaction``.

    Raises:
        DuplicateUploadError: this exact file was uploaded before. Caught on the hash,
            before parsing, because re-parsing a known file to discover it is known is
            wasted work on the common path -- clients send overlapping exports routinely.
    """
    digest = content_hash(content)

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM import_batch WHERE sha256 = %s", (digest,))
        existing = cur.fetchone()
    if existing:
        raise DuplicateUploadError(digest, str(existing[0]))

    result: ParseResult = adapter.parse(content, account_id=account_id, filename=filename)

    document_id = None
    if store is not None:
        stored = documents.store_document(
            conn, store, investor_id=investor_id, investor_code=investor_code or "UNKNOWN",
            doctype="TRADEBOOK", content=content, received=date.today(),
            filename=filename, content_type="text/csv", account_id=account_id,
            actor_uid=actor_uid,
        )
        document_id = stored["id"]

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO import_batch (investor_id, account_id, adapter, filename, sha256,
                                      document_id, row_count, rejected_count, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (investor_id, account_id, adapter.name, filename or None, digest, document_id,
             result.parsed, result.rejected, json.dumps(result.notes)),
        )
        batch_id = str(cur.fetchone()[0])

        for staged in result.rows:
            cur.execute(
                """
                INSERT INTO import_row (batch_id, row_number, confidence, dedupe_key, payload)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (batch_id, staged.row_number, staged.confidence,
                 make_dedupe_key(staged.transaction),
                 json.dumps({"transaction": _txn_to_payload(staged.transaction),
                             "raw": staged.raw})),
            )
        for rejection in result.rejections:
            cur.execute(
                """
                INSERT INTO import_row (batch_id, row_number, status, payload, reason)
                VALUES (%s,%s,'REJECTED',%s,%s)
                """,
                (batch_id, rejection.row_number, json.dumps({"raw": rejection.raw}),
                 rejection.reason),
            )

    audit.record(
        conn, ACTION_BATCH_STAGED, "import_batch", batch_id, actor_uid,
        {"adapter": adapter.name, "filename": filename,
         "parsed": result.parsed, "rejected": result.rejected},
    )
    return {
        "batch_id": batch_id, "parsed": result.parsed, "rejected": result.rejected,
        "sha256": digest, "document_id": document_id, "notes": result.notes,
    }


def review_batch(conn: Any, batch_id: str) -> dict[str, Any]:
    """What a human reads before deciding. Changes nothing.

    Predicts the duplicates promotion will skip, rather than leaving them to be discovered
    afterwards. "23 of your 115 rows are already in the ledger" is a fact worth knowing
    BEFORE clicking promote, not an explanation offered after.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, adapter, filename, row_count, rejected_count, notes, "
            "uploaded_at FROM import_batch WHERE id = %s",
            (batch_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise BatchNotFoundError(batch_id)
        batch = dict(zip([c.name for c in cur.description], row, strict=True))

        cur.execute(
            "SELECT row_number, reason FROM import_row "
            "WHERE batch_id = %s AND status = 'REJECTED' ORDER BY row_number",
            (batch_id,),
        )
        rejections = [{"row_number": r[0], "reason": r[1]} for r in cur.fetchall()]

        cur.execute(
            "SELECT row_number, confidence FROM import_row "
            "WHERE batch_id = %s AND status = 'STAGED' AND confidence <= %s "
            "ORDER BY confidence, row_number",
            (batch_id, REVIEW_THRESHOLD),
        )
        needs_review = [{"row_number": r[0], "confidence": r[1]} for r in cur.fetchall()]

        cur.execute(
            """
            SELECT count(*) FROM import_row r
            WHERE r.batch_id = %s AND r.status = 'STAGED'
              AND EXISTS (SELECT 1 FROM transaction t WHERE t.dedupe_key = r.dedupe_key)
            """,
            (batch_id,),
        )
        already_present = cur.fetchone()[0]

        cur.execute(
            "SELECT count(*) FROM import_row WHERE batch_id = %s AND status = 'STAGED'",
            (batch_id,),
        )
        staged = cur.fetchone()[0]

    return {
        **batch,
        "staged": staged,
        "will_insert": staged - already_present,
        "will_skip_as_duplicate": already_present,
        "rejections": rejections,
        "needs_review": needs_review,
    }


def promote_batch(conn: Any, batch_id: str, actor_uid: str) -> ImportSummary:
    """The second explicit action. Writes staged rows to the ledger.

    Requires ``actor_uid``: an unattributed promotion of client financial data is a record
    that fails exactly when somebody asks who did it. The database enforces this too.

    Reuses ``db.repository.save_transactions``, so the UNIQUE INDEX on ``dedupe_key``
    stays the enforcement rather than this module reimplementing it.

    Raises:
        BatchAlreadyResolvedError: already promoted or discarded. Re-promoting would be a
            no-op at the ledger thanks to the unique index, but it would misreport counts
            and imply a second review that never happened.
    """
    if not actor_uid:
        raise ValueError("promotion requires an actor: who is putting this in the ledger?")

    with conn.cursor() as cur:
        cur.execute("SELECT status FROM import_batch WHERE id = %s", (batch_id,))
        row = cur.fetchone()
        if row is None:
            raise BatchNotFoundError(batch_id)
        if row[0] != STATUS_STAGED:
            raise BatchAlreadyResolvedError(f"batch {batch_id} is {row[0]}")

        cur.execute(
            "SELECT id, payload FROM import_row "
            "WHERE batch_id = %s AND status = 'STAGED' ORDER BY row_number",
            (batch_id,),
        )
        staged = cur.fetchall()

    candidates = [(row_id, _payload_to_txn(p["transaction"])) for row_id, p in staged]

    # SOURCE PRECEDENCE. A contract note and a tradebook describe the same trades, and
    # dedupe_key does not catch that (see db/precedence.py). Without this guard, importing
    # both double-counts - measured at 146 trades on this project's own files. Interim
    # measure; the real fix is a source-agnostic dedupe_key. See docs/DATA_MODEL.md.
    account_id = staged[0][1]["transaction"].get("account_id") if staged else None
    known = precedence.existing_identities(conn, account_id) if account_id else {}

    to_insert: list[Transaction] = []
    excluded: list[tuple[str, str]] = []
    superseded: list[tuple[str, str, str]] = []

    for row_id, txn in candidates:
        identity = precedence.trade_identity(txn)
        existing = known.get(identity) if identity else None
        decision = precedence.decide(txn, existing[0] if existing else None,
                                     existing[1] if existing else None)
        if decision.action == precedence.ACTION_EXCLUDE:
            excluded.append((str(row_id), decision.reason))
        elif decision.action == precedence.ACTION_SUPERSEDE:
            superseded.append((str(row_id), decision.reason, decision.superseded_id))
            to_insert.append(txn)
        else:
            to_insert.append(txn)

    # A superseded row cannot be deleted - the ledger is append-only - so it is REVERSED,
    # which is the correction pattern DATA_MODEL already specifies. The history of what was
    # believed, and when it changed, survives.
    reversals = _reversals_for(conn, [sid for _, _, sid in superseded])
    transactions = reversals + to_insert

    # transaction.isin references security, so the master has to know these ISINs before
    # any row can land. Requiring it to be pre-populated would mean no import could ever be
    # the first thing to mention a security, which is backwards: the import IS how a new
    # holding is discovered. The symbol comes from the source row and is display-only, so
    # an existing name is never overwritten by a later file's spelling of it.
    securities = {
        p["transaction"]["isin"]: (p.get("raw") or {}).get("symbol")
        for _, p in staged
    }
    with conn.cursor() as cur:
        for isin, symbol in sorted(securities.items()):
            cur.execute(
                """
                INSERT INTO security (isin, symbol) VALUES (%s, %s)
                ON CONFLICT (isin) DO UPDATE
                SET symbol = COALESCE(security.symbol, EXCLUDED.symbol)
                """,
                (isin, symbol),
            )

    summary = repository.save_transactions(conn, transactions, actor_uid=actor_uid)

    with conn.cursor() as cur:
        for row_id, reason in excluded:
            cur.execute(
                "UPDATE import_row SET status = 'EXCLUDED', reason = %s WHERE id = %s",
                (reason, row_id),
            )
        for row_id, reason, _ in superseded:
            cur.execute(
                "UPDATE import_row SET status = 'SUPERSEDED', reason = %s WHERE id = %s",
                (reason, row_id),
            )
        cur.execute(
            """
            UPDATE import_row r
            SET status = CASE
                WHEN EXISTS (SELECT 1 FROM transaction t WHERE t.dedupe_key = r.dedupe_key)
                THEN 'PROMOTED'::import_row_status
                ELSE 'DUPLICATE'::import_row_status
            END
            WHERE r.batch_id = %s AND r.status = 'STAGED'
            """,
            (batch_id,),
        )
        cur.execute(
            "UPDATE import_batch SET status = 'PROMOTED', promoted_at = now(), "
            "promoted_by = %s WHERE id = %s",
            (actor_uid, batch_id),
        )

    if excluded or superseded:
        # Logged as its own audit event, not folded into the promotion summary. Somebody
        # asking "why is this trade not in the ledger?" must be able to find the answer.
        audit.record(
            conn, ACTION_ROWS_EXCLUDED, "import_batch", batch_id, actor_uid,
            {
                "excluded": [{"row": r, "reason": why} for r, why in excluded],
                "superseded": [{"row": r, "reason": why} for r, why, _ in superseded],
            },
        )

    audit.record(
        conn, ACTION_BATCH_PROMOTED, "import_batch", batch_id, actor_uid,
        {"inserted": summary.inserted, "skipped_duplicates": summary.skipped_duplicates,
         "excluded_by_precedence": len(excluded), "superseded": len(superseded)},
    )
    return summary


def _reversals_for(conn: Any, transaction_ids: list[str]) -> list[Transaction]:
    """Reversing rows for transactions a better source has superseded.

    Append-only means the earlier row cannot be deleted. DATA_MODEL's correction pattern is
    a reversing entry, so that is what this builds: the same trade with the opposite
    txn_type, marked MANUAL with an explanation in raw_payload.
    """
    if not transaction_ids:
        return []

    opposite = {TxnType.BUY: TxnType.SELL, TxnType.SELL: TxnType.BUY}
    reversals: list[Transaction] = []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT account_id, isin, txn_date, txn_type, quantity, price, charges, "
            "source, source_ref FROM transaction WHERE id = ANY(%s)",
            (transaction_ids,),
        )
        for row in cur.fetchall():
            original = TxnType(str(row[3]))
            if original not in opposite:
                continue
            reversals.append(
                Transaction(
                    isin=row[1], txn_date=row[2], txn_type=opposite[original],
                    quantity=row[4], price=row[5], charges=row[6],
                    account_id=str(row[0]), source=Source.MANUAL,
                    source_ref=f"REVERSAL-{row[8]}",
                    raw_payload={
                        "correction": "reversing entry",
                        "reason": (
                            f"superseded by a higher-precedence source; the original was "
                            f"{row[7]} and carried no charges"
                        ),
                    },
                )
            )
    return reversals


def discard_batch(
    conn: Any, batch_id: str, reason: str, actor_uid: str | None = None
) -> None:
    """Reject a batch without promoting it. A bad parse ends here.

    The staged rows are kept, not deleted: what was rejected and why is the evidence that
    review happened, and is what a later investigation reads.
    """
    if not reason or not reason.strip():
        raise ValueError("discarding requires a reason")

    with conn.cursor() as cur:
        cur.execute("SELECT status FROM import_batch WHERE id = %s", (batch_id,))
        row = cur.fetchone()
        if row is None:
            raise BatchNotFoundError(batch_id)
        if row[0] != STATUS_STAGED:
            raise BatchAlreadyResolvedError(f"batch {batch_id} is {row[0]}")

        cur.execute(
            "UPDATE import_batch SET status = 'DISCARDED', discarded_at = now(), "
            "discard_reason = %s WHERE id = %s",
            (reason, batch_id),
        )
    audit.record(
        conn, ACTION_BATCH_DISCARDED, "import_batch", batch_id, actor_uid,
        {"reason": reason},
    )
