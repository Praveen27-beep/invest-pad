"""The repository -- ``save_transactions`` and ``load_transactions``. Nothing else.

Deliberately small. There is no update path and no delete path, because the ledger is
append-only; and no holdings persistence, because holdings are computed on read. If this
module ever grows an ``update_transaction`` or a ``save_holdings``, the architecture has
been broken.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from db import audit
from engine.dedupe import make_dedupe_key
from engine.types import ImportSummary, Source, Transaction, TxnType

#: Postgres SQLSTATE for a unique-index violation.
UNIQUE_VIOLATION = "23505"

_INSERT = """
INSERT INTO transaction (
    account_id, isin, txn_date, txn_type, quantity, price, charges,
    dividend_amount, source, source_ref, dedupe_key, raw_payload
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (dedupe_key) DO NOTHING
RETURNING id
"""


def save_transactions(
    conn: Any,
    transactions: list[Transaction],
    actor_uid: str | None = None,
) -> ImportSummary:
    """Append transactions, skipping duplicates.

    A duplicate is NOT an error. Re-importing a file must be a no-op that still produces
    an honest summary, because email forwarding will deliver the same contract note twice
    and a client uploading a full history sends overlapping tradebook exports by
    necessity -- Console caps each download at 365 days.

    ``ON CONFLICT (dedupe_key) DO NOTHING`` puts the enforcement in the UNIQUE INDEX
    rather than in a prior SELECT. A check-then-insert would race: two concurrent imports
    of the same file could both find nothing and both insert.

    The audit row shares this transaction. If it fails, the inserts roll back with it.
    """
    inserted = 0
    skipped = 0

    with conn.cursor() as cur:
        for txn in transactions:
            key = txn.dedupe_key or make_dedupe_key(txn)
            cur.execute(
                _INSERT,
                (
                    txn.account_id,
                    txn.isin,
                    txn.txn_date,
                    str(txn.txn_type),
                    txn.quantity,
                    txn.price,
                    txn.charges,
                    txn.dividend_amount,
                    str(txn.source) if txn.source else Source.MANUAL.value,
                    txn.source_ref,
                    key,
                    json.dumps(txn.raw_payload) if txn.raw_payload else None,
                ),
            )
            if cur.fetchone() is None:
                skipped += 1
            else:
                inserted += 1

    audit.record(
        conn,
        action=audit.ACTION_IMPORT,
        entity_type="transaction",
        actor_uid=actor_uid,
        diff={"inserted": inserted, "skipped_duplicates": skipped, "offered": len(transactions)},
    )

    return ImportSummary(inserted=inserted, skipped_duplicates=skipped, rejected=[])


def load_transactions(
    conn: Any,
    investor_id: str | None = None,
    account_id: str | None = None,
    isin: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[Transaction]:
    """Read the ledger back as engine objects.

    Returns ``Transaction`` objects, not rows: the engine must not know that a database
    exists, and the boundary is enforced by what crosses it. ``NUMERIC`` arrives as
    ``Decimal`` from psycopg, so no conversion is needed and none is done -- a float
    round-trip here would silently undo the entire precision discipline.
    """
    clauses: list[str] = []
    params: list[Any] = []

    if investor_id:
        clauses.append("a.investor_id = %s")
        params.append(investor_id)
    if account_id:
        clauses.append("t.account_id = %s")
        params.append(account_id)
    if isin:
        clauses.append("t.isin = %s")
        params.append(isin)
    if date_from:
        clauses.append("t.txn_date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("t.txn_date <= %s")
        params.append(date_to)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT t.id, t.account_id, t.isin, t.txn_date, t.txn_type, t.quantity,
                   t.price, t.charges, t.dividend_amount, t.source, t.source_ref,
                   t.dedupe_key, t.raw_payload, t.created_at
            FROM transaction t
            JOIN account a ON a.id = t.account_id
            {where}
            ORDER BY t.txn_date, t.created_at, t.id
            """,
            params,
        )
        return [
            Transaction(
                id=str(row[0]),
                account_id=str(row[1]),
                isin=row[2],
                txn_date=row[3],
                txn_type=TxnType(row[4]),
                quantity=row[5],
                price=row[6],
                charges=row[7],
                dividend_amount=row[8],
                source=Source(row[9]),
                source_ref=row[10],
                dedupe_key=row[11],
                raw_payload=row[12],
                created_at=row[13],
            )
            for row in cur.fetchall()
        ]
