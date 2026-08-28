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

from app.db import audit, documents, holdings, precedence, repository
from app.engine.dedupe import make_dedupe_key
from app.engine.types import ImportSummary, Source, Transaction, TxnType
from app.ingest.base import REVIEW_THRESHOLD, ParseResult
from app.storage.keys import content_hash

ACTION_BATCH_STAGED = "IMPORT_BATCH_STAGED"
ACTION_BATCH_PROMOTED = "IMPORT_BATCH_PROMOTED"
ACTION_BATCH_DISCARDED = "IMPORT_BATCH_DISCARDED"
ACTION_BATCH_REPARSED = "IMPORT_BATCH_REPARSED"
ACTION_ROWS_EXCLUDED = "IMPORT_ROWS_EXCLUDED"

STATUS_STAGED = "STAGED"
STATUS_PROMOTED = "PROMOTED"
STATUS_DISCARDED = "DISCARDED"


class BatchNotFoundError(LookupError):
    pass


class BatchAlreadyResolvedError(ValueError):
    """Promoted or discarded batches are final. Re-promoting would double-count."""


class DuplicateUploadError(ValueError):
    """This exact file has already been staged for this account."""

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
        "stt": str(txn.stt),
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
        stt=Decimal(payload.get("stt", "0")),
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
    doctype: str = "TRADEBOOK",
    content_type: str = "text/csv",
) -> dict[str, Any]:
    """Parse a file into staged rows. Writes NOTHING to ``transaction``.

    ``doctype``/``content_type`` default to the values every caller used before these
    parameters existed (CSV/tradebook adapters) -- existing behaviour is unchanged.
    A caller staging a PDF (contract note, CAS) should pass ``doctype="CONTRACT_NOTE"``
    or ``"CAS"`` and ``content_type="application/pdf"``; passing neither previously
    meant every PDF this system has ever staged was recorded in ``document`` as a
    TRADEBOOK/text-csv, which is wrong metadata on an otherwise-correctly-stored object.

    If ``adapter`` defines ``parse_declared_holdings`` (currently only
    app.ingest.cas_pdf.CasPdfAdapter), its result is written to ``holding_snapshot`` via
    app.db.holdings.record_snapshot after staging succeeds -- centralized here so every
    caller (email and upload) gets it without duplicating the glue. This is separate
    from the staged-rows-and-review flow: holding_snapshot carries no promote gate (see
    app.db.holdings' docstring), so this write happens unconditionally, not gated on
    review.

    Raises:
        DuplicateUploadError: this exact file was staged before, for this account.
            Caught on the hash, before parsing, because re-parsing a known file to
            discover it is known is wasted work on the common path -- clients send
            overlapping exports routinely.

            Scoped to the destination account, matching dedupe_key's account_id term:
            matched globally instead, another tenant's identical upload blocked this one
            and named a batch the ownership guard would refuse to serve -- a cross-tenant
            dead end that leaked someone else's batch id. A file hash identifies bytes,
            not a tenant.
    """
    digest = content_hash(content)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM import_batch WHERE sha256 = %s AND account_id = %s",
            (digest, account_id),
        )
        existing = cur.fetchone()
    if existing:
        raise DuplicateUploadError(digest, str(existing[0]))

    result: ParseResult = adapter.parse(content, account_id=account_id, filename=filename)

    document_id = None
    if store is not None:
        stored = documents.store_document(
            conn, store, investor_id=investor_id, investor_code=investor_code or "UNKNOWN",
            doctype=doctype, content=content, received=date.today(),
            filename=filename, content_type=content_type, account_id=account_id,
            actor_uid=actor_uid,
        )
        document_id = str(stored["id"])

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

    declared_holdings = 0
    parse_declared_holdings = getattr(adapter, "parse_declared_holdings", None)
    if parse_declared_holdings is not None:
        declared = parse_declared_holdings(content, account_id)
        declared_holdings = holdings.record_snapshot(conn, declared)

    return {
        "batch_id": batch_id, "parsed": result.parsed, "rejected": result.rejected,
        "sha256": digest, "document_id": document_id, "notes": result.notes,
        "declared_holdings": declared_holdings,
    }


def reparse_batch(
    conn: Any, store: Any, batch_id: str, adapter: Any, actor_uid: str | None = None
) -> dict[str, Any]:
    """Re-run ``adapter.parse()`` against a STAGED batch's ORIGINALLY STORED bytes,
    replacing its staged/rejected rows with the fresh result.

    This is the recovery path docs/INGESTION.md's "Where documents land" section
    promises but nothing implemented until now: "storing before parsing is what
    makes a parser bug survivable... the fix is to reparse the originals." Without
    it, the only way to retry a document is re-uploading it -- and ``stage_batch``'s
    duplicate check is a permanent per-account sha256 lookup with no status filter,
    so re-uploading identical bytes returns the SAME batch, forever, no matter what
    changed since (a PAN added after the fact, a parser bug fixed after the fact).
    Real case this was built for: a CAS PDF staged before the investor's PAN was on
    file rejects with "could not unlock" -- adding the PAN afterward does nothing
    until something actually re-parses the stored original against it.

    Only a STAGED batch may be reparsed, matching promote_batch/discard_batch's own
    guard: a promoted batch's rows are the ledger's provenance record and must not
    change under it; a discarded batch is deliberately final.

    Raises:
        BatchNotFoundError: no such batch.
        BatchAlreadyResolvedError: already promoted or discarded.
        ValueError: the batch has no stored document (only possible if it was staged
            without a ``store``, which no real caller does).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, account_id, filename, document_id, adapter, sha256 "
            "FROM import_batch WHERE id = %s",
            (batch_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise BatchNotFoundError(batch_id)
        batch_status, account_id, filename, document_id, adapter_name, sha256 = row
        if batch_status != STATUS_STAGED:
            raise BatchAlreadyResolvedError(f"batch {batch_id} is {batch_status}")
        if document_id is None:
            raise ValueError(f"batch {batch_id} has no stored document to reparse")
        if adapter.name != adapter_name:
            raise ValueError(
                f"batch {batch_id} was staged with adapter {adapter_name!r}, "
                f"not {adapter.name!r}"
            )

        cur.execute("SELECT storage_key FROM document WHERE id = %s", (document_id,))
        (storage_key,) = cur.fetchone()

    content = store.get(storage_key)
    result: ParseResult = adapter.parse(
        content, account_id=str(account_id), filename=filename or ""
    )

    with conn.cursor() as cur:
        # REPLACED, not appended: a reparse answers "what would this document produce
        # now", not "union of every attempt". Safe to delete unconditionally -- the
        # STAGED-only guard above means nothing here has been promoted, so no row
        # being removed is the ledger's provenance record for anything live.
        cur.execute("DELETE FROM import_row WHERE batch_id = %s", (batch_id,))
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
        cur.execute(
            "UPDATE import_batch SET row_count = %s, rejected_count = %s, notes = %s "
            "WHERE id = %s",
            (result.parsed, result.rejected, json.dumps(result.notes), batch_id),
        )

    declared_holdings = 0
    parse_declared_holdings = getattr(adapter, "parse_declared_holdings", None)
    if parse_declared_holdings is not None:
        declared = parse_declared_holdings(content, str(account_id))
        declared_holdings = holdings.record_snapshot(conn, declared)

    audit.record(
        conn, ACTION_BATCH_REPARSED, "import_batch", batch_id, actor_uid,
        {"adapter": adapter.name, "parsed": result.parsed, "rejected": result.rejected},
    )
    return {
        "batch_id": batch_id, "parsed": result.parsed, "rejected": result.rejected,
        "sha256": sha256, "document_id": str(document_id), "notes": result.notes,
        "declared_holdings": declared_holdings,
    }


def list_batches(
    conn: Any, investor_id: str, batch_status: str | None = "STAGED"
) -> list[dict[str, Any]]:
    """The batches one investor can see, newest first -- the answer to "where is that
    batch id?" that does not require keeping the upload response around. ``None`` lists
    every status; anything else filters on ``import_batch_status`` (invalid values are a
    caller bug and surface as a Postgres error)."""
    query = (
        "SELECT id, filename, adapter, status::text, row_count, rejected_count, uploaded_at "
        "FROM import_batch WHERE investor_id = %s"
    )
    params: list[Any] = [investor_id]
    if batch_status is not None:
        query += " AND status = %s"
        params.append(batch_status)
    query += " ORDER BY uploaded_at DESC, id"

    with conn.cursor() as cur:
        cur.execute(query, params)
        return [
            {
                "batch_id": str(row[0]),
                "filename": row[1],
                "adapter": row[2],
                "status": row[3],
                "row_count": row[4],
                "rejected_count": row[5],
                "uploaded_at": row[6],
            }
            for row in cur.fetchall()
        ]


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
            "SELECT account_id, isin, txn_date, txn_type, quantity, price, charges, stt, "
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
                    # stt is a SUBSET of charges (never zeroed independently) --
                    # carrying it through the same way charges is carried through keeps
                    # the "stt <= charges" invariant true on this synthetic row too.
                    stt=row[7],
                    account_id=str(row[0]), source=Source.MANUAL,
                    source_ref=f"REVERSAL-{row[9]}",
                    raw_payload={
                        "correction": "reversing entry",
                        "reason": (
                            f"superseded by a higher-precedence source; the original was "
                            f"{row[8]} and carried no charges"
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
