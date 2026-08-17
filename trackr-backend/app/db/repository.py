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

from app.db import audit, crypto
from app.engine.dedupe import make_dedupe_key
from app.engine.types import ImportSummary, Source, Transaction, TxnType

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


class DuplicateInvestorCodeError(ValueError):
    """``investor.code`` is UNIQUE (docs/DATA_MODEL.md) -- this one is already taken."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"investor code {code!r} is already in use")


class InvestorNotFoundError(LookupError):
    """No investor row with this id -- checked explicitly (see create_account) so the
    router can answer 404 instead of a raw foreign-key-violation 500."""

    def __init__(self, investor_id: str) -> None:
        self.investor_id = investor_id
        super().__init__(f"no investor with id {investor_id!r}")


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
    advised_only: bool = False,
) -> list[Transaction]:
    """Read the ledger back as engine objects.

    Returns ``Transaction`` objects, not rows: the engine must not know that a database
    exists, and the boundary is enforced by what crosses it. ``NUMERIC`` arrives as
    ``Decimal`` from psycopg, so no conversion is needed and none is done -- a float
    round-trip here would silently undo the entire precision discipline.

    ORDERED BY ``(txn_date, seq)``, and the second half of that is load-bearing.
    ``engine.ledger.ordered`` sorts on ``txn_date`` alone and depends on a stable sort to
    keep same-date rows in the order they were inserted. ``created_at`` cannot supply that
    -- ``now()`` is the transaction timestamp, so every row of a bulk import shares it --
    and the previous fallback to ``id`` was a random uuid. See migration 007: replaying the
    golden fixture out of the database raised ``NegativeHoldingError`` on a SELL that had
    overtaken its own BUY.

    ``advised_only`` restricts to accounts flagged ``account.is_advised`` (docs/
    DATA_MODEL.md) -- the ``account`` join this already runs, so no new join or query path
    is added for it. Exists so a SEBI-registered adviser can report on the mandated
    account only, per contracts/openapi.yaml's ``advised_only`` parameter.
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
    if advised_only:
        clauses.append("a.is_advised = true")

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


def create_investor(
    conn: Any,
    code: str,
    display_name: str,
    family_group_id: str | None = None,
    pan: str | None = None,
    onboarding_date: date | None = None,
    actor_uid: str | None = None,
) -> dict[str, Any]:
    """Onboard a new investor. The only way an investor row is created outside
    ``app.db.load_golden``'s fixture seed -- see docs/FULL_VISION_BACKEND_ROADMAP.md A5.

    ``pan``, when given, never lands on the ``investor`` row: docs/DATA_MODEL.md is
    explicit that PAN lives only as a peppered lookup hash plus Fernet ciphertext in
    ``investor_secret``, via the same ``app.db.crypto`` module ``app.ingest.webhook``
    already routes the contract-note-password lookup through. Validated and normalised
    before the investor insert, so a bad PAN format fails the whole request without
    leaving a half-onboarded investor behind.

    ``onboarding_date`` feeds ``compute_period_xirr``'s ``start_date`` (see
    ``app.routers.analytical._period_xirr``) -- optional, nullable, never defaulted.

    Raises:
        app.db.crypto.InvalidPANError: ``pan`` does not match the mandated PAN format.
        DuplicateInvestorCodeError: ``code`` is already in use.
    """
    import psycopg

    normalised_pan = crypto.normalise_pan(pan) if pan else None

    with conn.cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO investor (code, display_name, family_group_id, onboarding_date)
                VALUES (%s, %s, %s, %s)
                RETURNING id, code, display_name, family_group_id, onboarding_date, created_at
                """,
                (code, display_name, family_group_id, onboarding_date),
            )
        except psycopg.errors.UniqueViolation as exc:
            raise DuplicateInvestorCodeError(code) from exc
        row = cur.fetchone()

    investor = {
        "id": str(row[0]),
        "code": row[1],
        "display_name": row[2],
        "family_group_id": str(row[3]) if row[3] else None,
        "onboarding_date": row[4],
        "created_at": row[5],
    }

    audit.record(
        conn,
        action=audit.ACTION_INSERT,
        entity_type="investor",
        entity_id=investor["id"],
        actor_uid=actor_uid,
        diff={"code": code},
    )

    if normalised_pan:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO investor_secret (investor_id, pan_hash, pan_enc) VALUES (%s, %s, %s)",
                (investor["id"], crypto.hash_pan(normalised_pan), crypto.encrypt(normalised_pan)),
            )
        audit.record(
            conn,
            action=audit.ACTION_SECRET_WRITTEN,
            entity_type="investor",
            entity_id=investor["id"],
            actor_uid=actor_uid,
        )

    return investor


def list_investor_ids(conn: Any) -> list[str]:
    """Every investor id -- what ``POST /ops/snapshots/run`` iterates over.

    Mirrors ``app.db.prices.held_isins``'s unscoped shape: that endpoint, like this one,
    runs across every investor in one call rather than one at a time.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM investor ORDER BY id")
        return [str(row[0]) for row in cur.fetchall()]


def get_investor_onboarding_date(conn: Any, investor_id: str) -> date | None:
    """The investor's adviser-onboarding date -- ``compute_period_xirr``'s
    ``start_date``, via ``app.routers.analytical._period_xirr``. ``None`` both when the
    column is unset (most investors today) and when ``investor_id`` doesn't exist --
    this endpoint has never enforced investor existence (``load_transactions`` just
    returns an empty ledger for an unknown id), and this feature doesn't newly start.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT onboarding_date FROM investor WHERE id = %s", (investor_id,))
        row = cur.fetchone()
    return row[0] if row else None


def create_account(
    conn: Any,
    investor_id: str,
    broker: str,
    dp_id: str | None = None,
    client_id: str | None = None,
    is_advised: bool = True,
    label: str | None = None,
    actor_uid: str | None = None,
) -> dict[str, Any]:
    """Add a demat/broker account to an investor. One row per account (docs/
    DATA_MODEL.md) -- a client's CAS routinely reveals accounts nobody knew existed, so
    onboarding must support adding more than one per investor.

    The returned dict carries an ``investor_code`` key alongside the account columns --
    not part of ``account``, but the router needs it to compute this account's
    forwarding addresses (app.ingest.addresses.forwarding_addresses) without a second
    round trip, and the existence check below already has to read the investor row.

    Raises:
        InvestorNotFoundError: no investor with ``investor_id``. Checked with a SELECT
            rather than left to ``account.investor_id``'s foreign key, so the router
            can answer a clean 404 instead of a raw ForeignKeyViolation 500.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT code FROM investor WHERE id = %s", (investor_id,))
        investor_row = cur.fetchone()
        if investor_row is None:
            raise InvestorNotFoundError(investor_id)
        investor_code = investor_row[0]

        cur.execute(
            """
            INSERT INTO account (investor_id, broker, dp_id, client_id, is_advised, label)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, investor_id, broker, dp_id, client_id, is_advised, label
            """,
            (investor_id, broker, dp_id, client_id, is_advised, label),
        )
        row = cur.fetchone()

    account = {
        "id": str(row[0]),
        "investor_id": str(row[1]),
        "broker": row[2],
        "dp_id": row[3],
        "client_id": row[4],
        "is_advised": row[5],
        "label": row[6],
        "investor_code": investor_code,
    }

    audit.record(
        conn,
        action=audit.ACTION_INSERT,
        entity_type="account",
        entity_id=account["id"],
        actor_uid=actor_uid,
        diff={"investor_id": investor_id, "broker": broker},
    )

    return account
