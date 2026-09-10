"""DB-layer glue for verified corporate actions: CRUD on the ``corporate_action``
reference table, and staging matched corrections into the exact ``import_batch``/
``import_row`` pipeline every file adapter already uses.

Nothing here writes to ``transaction`` directly. Promotion is
``app.db.imports.promote_batch``, reused unchanged -- a batch staged by this module is
indistinguishable, at review/promote/discard time, from one staged by a file upload.
That is the point: the "adapter never writes to the ledger" rule
(``app.db.imports``'s own docstring) holds here with zero new enforcement code, because
this was never given a second path to the ledger in the first place.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

from app.db import audit
from app.db.imports import ACTION_BATCH_STAGED, _txn_to_payload
from app.db.prices import latest_prices, prices_on_date
from app.db.repository import load_transactions, save_transactions
from app.engine.corporate_actions import (
    CorpActionType,
    CorporateAction,
    Verification,
    check_price_consistency,
    check_sourced,
    free_share_effect,
    screen,
)
from app.engine.dedupe import make_dedupe_key
from app.engine.holdings import quantity_held_before
from app.engine.types import ZERO, ImportSummary, Source, Transaction, TxnType
from app.ingest.corporate_action_matcher import stage_corporate_actions as _match

logger = logging.getLogger("corporate_actions")

#: import_batch.adapter value for a batch this module staged, as opposed to a real
#: file-upload adapter's name. Carries no parser, no file, no document_id -- review and
#: promote do not need to know the difference, but a human reading import_batch does.
ADAPTER_NAME = "corporate_action_matcher"

_SELECT_COLUMNS = (
    "id, isin, action_type::text, ex_date, bonus_new, bonus_for, "
    "face_value_before, face_value_after, resulting_isin, "
    "demerger_new, demerger_for, price_cum, price_ex, "
    "source, source_url, verification::text, notes, "
    "price_waived, price_waiver_reason"
)


def _row_to_action(row: tuple) -> CorporateAction:
    (
        id_, isin, action_type, ex_date, bonus_new, bonus_for,
        face_value_before, face_value_after, resulting_isin,
        demerger_new, demerger_for, price_cum, price_ex,
        source, source_url, verification, notes,
        price_waived, price_waiver_reason,
    ) = row
    return CorporateAction(
        id=str(id_),
        isin=isin,
        action_type=CorpActionType(action_type),
        ex_date=ex_date,
        bonus_new=bonus_new,
        bonus_for=bonus_for,
        face_value_before=face_value_before,
        face_value_after=face_value_after,
        resulting_isin=resulting_isin,
        demerger_new=demerger_new,
        demerger_for=demerger_for,
        price_cum=price_cum,
        price_ex=price_ex,
        source=source,
        source_url=source_url,
        verification=Verification(verification),
        notes=notes or "",
        price_waived=price_waived,
        price_waiver_reason=price_waiver_reason or "",
    )


def add_corporate_action(
    conn: Any, action: CorporateAction, actor_uid: str | None = None
) -> str:
    """Insert one corporate action -- the manual/bulk entry path, same product shape as
    MProfit's Bulk Corporate Action form (date, security, action type, the primitive
    ratio facts).

    ``action`` must already construct cleanly: ``CorporateAction.__post_init__`` raises
    ``CorporateActionRatioError`` for an unusable record before this is ever called --
    an incomplete row fails at entry, not at match time. The table's own
    ``UNIQUE (isin, action_type, ex_date)`` constraint is the same DUPLICATE guard
    ``app.engine.corporate_actions.screen()`` applies to a batch already in memory,
    enforced here too since two humans can enter the same notice independently.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO corporate_action (
                isin, action_type, ex_date, bonus_new, bonus_for,
                face_value_before, face_value_after, resulting_isin,
                demerger_new, demerger_for, price_cum, price_ex,
                source, source_url, verification, notes,
                price_waived, price_waiver_reason
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                action.isin, action.action_type.value, action.ex_date,
                action.bonus_new, action.bonus_for,
                action.face_value_before, action.face_value_after, action.resulting_isin,
                action.demerger_new, action.demerger_for,
                action.price_cum, action.price_ex,
                action.source, action.source_url,
                action.verification.value, action.notes or None,
                action.price_waived, action.price_waiver_reason or None,
            ),
        )
        action_id = str(cur.fetchone()[0])

    audit.record(
        conn,
        audit.ACTION_CORPORATE_ACTION_ADDED,
        "corporate_action",
        action_id,
        actor_uid,
        {
            "isin": action.isin,
            "action_type": action.action_type.value,
            "ex_date": action.ex_date.isoformat(),
            "source": action.source,
        },
    )

    # RETROACTIVE SWEEP. A brand-new VERIFIED entry can explain a gap that has been
    # sitting in someone's ledger since before this entry existed -- exactly the
    # KAMAHOLD/GENSOL situation this feature was built for. Every account that has ever
    # transacted this ISIN gets checked immediately, not just future imports.
    # ``apply_known_actions_for_account`` is idempotent, so this is safe to call even
    # for accounts that already have the resulting transaction.
    if action.verification is Verification.VERIFIED:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT DISTINCT account_id FROM "transaction" WHERE isin = %s',
                (action.isin,),
            )
            account_ids = [row[0] for row in cur.fetchall()]
        for account_id in account_ids:
            apply_known_actions_for_account(conn, str(account_id), actor_uid=actor_uid)

    return action_id


def list_corporate_actions(
    conn: Any, isins: list[str] | None = None, verification: Verification | None = None
) -> list[CorporateAction]:
    """Every corporate action on file, optionally restricted to ``isins`` -- matched on
    EITHER the action's own ``isin`` or its ``resulting_isin``, since a DEMERGER is
    filed under the parent security but is what explains a discrepancy on the child --
    and optionally to one ``verification`` status, e.g. every ``DRAFT`` row for the
    ``Exceptions`` surface (``list_pending_corporate_actions`` below)."""
    query = f"SELECT {_SELECT_COLUMNS} FROM corporate_action"
    clauses: list[str] = []
    params: list[Any] = []
    if isins:
        clauses.append("(isin = ANY(%s) OR resulting_isin = ANY(%s))")
        params += [isins, isins]
    if verification is not None:
        clauses.append("verification = %s")
        params.append(verification.value)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY ex_date"
    with conn.cursor() as cur:
        cur.execute(query, params)
        return [_row_to_action(row) for row in cur.fetchall()]


def get_corporate_action(conn: Any, action_id: str) -> CorporateAction | None:
    """One corporate action by id, or ``None`` -- the direct lookup the ``Exceptions``
    router endpoints (verify/dispute) need after mutating a row, instead of listing
    everything and filtering client-side."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_SELECT_COLUMNS} FROM corporate_action WHERE id = %s", (action_id,))
        row = cur.fetchone()
        return _row_to_action(row) if row else None


def list_pending_corporate_actions(conn: Any) -> list[CorporateAction]:
    """Every ``DRAFT`` row -- the ``Exceptions`` surface. Deliberately named apart from
    ``list_corporate_actions(verification=DRAFT)``, which it wraps: on a healthy feed
    this should be short and rare, an exception list, not a queue someone works through
    daily -- see ``docs/ENGINE_SPEC.md``'s note on why it's named that way."""
    return list_corporate_actions(conn, verification=Verification.DRAFT)


def verify_corporate_action(conn: Any, action_id: str, actor_uid: str | None = None) -> None:
    """Promote a ``DRAFT`` row to ``VERIFIED`` -- the one legitimate ``UPDATE`` this
    module performs. Safe against CLAUDE.md's append-only rule because it targets
    ``corporate_action`` (maintained reference/master data with its own review state),
    never ``transaction`` (the append-only ledger) -- this function writes no
    transaction row itself; it only unlocks ``add_corporate_action``'s retroactive
    sweep, reused unchanged, to do that.

    Used two ways: a human confirming an ``Exceptions`` entry by hand, and the
    automated feed's own self-correcting retry (``refresh_corporate_action_feed``)
    promoting a row that failed its guards on an earlier run and now passes -- same
    function, same audit trail, the caller is what differs.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE corporate_action SET verification = %s WHERE id = %s AND verification != %s",
            (Verification.VERIFIED.value, action_id, Verification.VERIFIED.value),
        )
        if cur.rowcount == 0:
            return  # already VERIFIED, or no such row -- nothing to sweep

        cur.execute(
            f"SELECT {_SELECT_COLUMNS} FROM corporate_action WHERE id = %s", (action_id,)
        )
        action = _row_to_action(cur.fetchone())

    audit.record(
        conn, audit.ACTION_CORPORATE_ACTION_VERIFIED, "corporate_action", action_id, actor_uid,
        {"isin": action.isin, "action_type": action.action_type.value},
    )

    with conn.cursor() as cur:
        cur.execute('SELECT DISTINCT account_id FROM "transaction" WHERE isin = %s', (action.isin,))
        account_ids = [row[0] for row in cur.fetchall()]
    for account_id in account_ids:
        apply_known_actions_for_account(conn, str(account_id), actor_uid=actor_uid)


class PriceEvidenceWaiverError(ValueError):
    """Raised by ``waive_price_evidence`` when a row does not qualify -- distinct from
    a plain 404/lookup miss, which the caller (a router) turns into its own HTTP status."""


def waive_price_evidence(
    conn: Any, action_id: str, reason: str, actor_uid: str | None = None
) -> None:
    """The one legitimate way to unblock a BONUS/SPLIT whose price evidence is not
    merely missing but PERMANENTLY UNOBTAINABLE -- its ``ex_date`` predates
    ``app.prices.pipe.NSE_BHAVCOPY_EARLIEST``, the confirmed floor of this system's
    bhavcopy archive (see ``025_price_evidence_waiver.sql``). No feed run or backfill
    will ever populate ``price_cum``/``price_ex`` for such a row, so
    ``check_price_consistency``'s ``NO_PRICE_EVIDENCE`` guard would otherwise quarantine
    it forever -- the KAMAHOLD/GENSOL case this exists for.

    NOT a blanket bypass. Refuses any action whose ex_date falls within the archive's
    range: for those, price evidence genuinely IS obtainable (by ``refresh_corporate_
    action_feed``'s normal self-correcting retry, or a manual backfill), so the guard
    must keep doing its job undiminished. Also refuses an unsourced or already-disputed
    row -- a waiver only ever removes the price check, never ``check_sourced`` or
    ``check_verified``, which ``screen()`` still applies afterwards exactly as before.

    Requires a non-empty ``reason``, same posture as ``dispute_corporate_action``'s
    ``reason`` -- an audited human judgement call needs a stated basis, not just a click.
    """
    from app.prices.pipe import NSE_BHAVCOPY_EARLIEST

    if not reason.strip():
        raise PriceEvidenceWaiverError("a waiver needs a stated reason")

    action = get_corporate_action(conn, action_id)
    if action is None:
        raise PriceEvidenceWaiverError(f"no such corporate action: {action_id}")
    if action.action_type not in (CorpActionType.BONUS, CorpActionType.SPLIT):
        raise PriceEvidenceWaiverError(
            f"price evidence is not required for {action.action_type.value}; nothing to waive"
        )
    if action.ex_date >= NSE_BHAVCOPY_EARLIEST:
        raise PriceEvidenceWaiverError(
            f"ex_date {action.ex_date} is within this system's price archive "
            f"({NSE_BHAVCOPY_EARLIEST} onward) -- price evidence is obtainable and must "
            "be, not waived"
        )
    if not action.source or not action.source_url:
        raise PriceEvidenceWaiverError("cannot waive an unsourced action -- add a source first")

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE corporate_action SET price_waived = true, price_waiver_reason = %s, "
            "verification = %s WHERE id = %s AND verification != %s",
            (reason, Verification.VERIFIED.value, action_id, Verification.DISPUTED.value),
        )
        if cur.rowcount == 0:
            return  # DISPUTED -- a waiver cannot resurrect a rejected row

    audit.record(
        conn, audit.ACTION_CORPORATE_ACTION_PRICE_WAIVED, "corporate_action", action_id,
        actor_uid, {"isin": action.isin, "action_type": action.action_type.value, "reason": reason},
    )

    with conn.cursor() as cur:
        cur.execute('SELECT DISTINCT account_id FROM "transaction" WHERE isin = %s', (action.isin,))
        account_ids = [row[0] for row in cur.fetchall()]
    for account_id in account_ids:
        apply_known_actions_for_account(conn, str(account_id), actor_uid=actor_uid)


def dispute_corporate_action(
    conn: Any, action_id: str, actor_uid: str | None = None, reason: str = ""
) -> None:
    """Mark a row ``DISPUTED`` -- permanently excludes it from ever matching
    (``screen()``'s ``check_verified`` guard) and, just as importantly, from the
    automated feed's retry sweep ever re-attempting it. The only way out of
    ``DISPUTED`` is a human entering a corrected record; this function never deletes
    the row, so a bad feed notice stays visible as a record of what was rejected and
    why, not silently gone."""
    with conn.cursor() as cur:
        note = f"\nDISPUTED: {reason}" if reason else "\nDISPUTED"
        cur.execute(
            "UPDATE corporate_action SET verification = %s, "
            "notes = COALESCE(NULLIF(notes, ''), '') || %s WHERE id = %s",
            (Verification.DISPUTED.value, note, action_id),
        )
    audit.record(
        conn, audit.ACTION_CORPORATE_ACTION_DISPUTED, "corporate_action", action_id, actor_uid,
        {"reason": reason},
    )


def stage_corporate_actions(
    conn: Any,
    investor_id: str,
    account_id: str,
    declared_holdings: dict[str, Decimal],
    actor_uid: str | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Reconcile this account against ``declared_holdings``, match against verified
    corporate actions on file, and stage the result -- the MProfit "Apply" step: never
    silent, always landing in the same review-then-confirm flow
    (``/ingest/stage/{batch_id}`` -> ``/promote``) a file upload goes through.

    Idempotent the way a file upload is: ``app.db.imports.stage_batch`` short-circuits
    on ``UNIQUE (account_id, sha256)`` so re-uploading identical bytes returns the
    existing batch rather than a duplicate. There is no file here to hash, so this
    function hashes what was actually matched instead and applies the identical rule by
    hand -- running this again with nothing changed returns the same batch, not a
    second one sitting alongside it.
    """
    transactions = load_transactions(conn, investor_id=investor_id, account_id=account_id)
    isins = sorted({t.isin for t in transactions} | set(declared_holdings))
    actions = list_corporate_actions(conn, isins)

    result = _match(transactions, declared_holdings, actions, account_id, as_of=as_of)

    digest = hashlib.sha256(
        json.dumps(
            {
                "matched": [
                    {
                        "isin": r.transaction.isin,
                        "txn_type": str(r.transaction.txn_type),
                        "quantity": str(r.transaction.quantity),
                        "source_ref": r.transaction.source_ref,
                    }
                    for r in result.rows
                ],
                "as_of": as_of.isoformat() if as_of else None,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM import_batch WHERE sha256 = %s AND account_id = %s",
            (digest, account_id),
        )
        existing = cur.fetchone()
        if existing:
            return {
                "batch_id": str(existing[0]),
                "parsed": result.parsed,
                "rejected": result.rejected,
                "notes": result.notes,
            }

        cur.execute(
            """
            INSERT INTO import_batch (investor_id, account_id, adapter, filename, sha256,
                                      row_count, rejected_count, notes)
            VALUES (%s,%s,%s,NULL,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                investor_id, account_id, ADAPTER_NAME, digest,
                result.parsed, result.rejected, json.dumps(result.notes),
            ),
        )
        batch_id = str(cur.fetchone()[0])

        for staged in result.rows:
            cur.execute(
                """
                INSERT INTO import_row (batch_id, row_number, confidence, dedupe_key, payload)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (
                    batch_id, staged.row_number, staged.confidence,
                    make_dedupe_key(staged.transaction),
                    json.dumps(
                        {"transaction": _txn_to_payload(staged.transaction), "raw": staged.raw}
                    ),
                ),
            )
        for rejection in result.rejections:
            cur.execute(
                """
                INSERT INTO import_row (batch_id, row_number, status, payload, reason)
                VALUES (%s,%s,'REJECTED',%s,%s)
                """,
                (
                    batch_id, rejection.row_number,
                    json.dumps({"raw": rejection.raw}), rejection.reason,
                ),
            )

    audit.record(
        conn,
        ACTION_BATCH_STAGED,
        "import_batch",
        batch_id,
        actor_uid,
        {"adapter": ADAPTER_NAME, "parsed": result.parsed, "rejected": result.rejected},
    )

    return {
        "batch_id": batch_id,
        "parsed": result.parsed,
        "rejected": result.rejected,
        "notes": result.notes,
    }


_TXN_TYPE = {
    "BONUS": TxnType.BONUS,
    "SPLIT_ADJ": TxnType.SPLIT_ADJ,
    "DEMERGER_IN": TxnType.DEMERGER_IN,
}


def apply_known_actions_for_account(
    conn: Any, account_id: str, actor_uid: str | None = None
) -> ImportSummary:
    """Apply every VERIFIED, guard-passing corporate action on file to this account's
    ledger directly -- no declared-holdings statement, no staging, no promote click.

    THE SAFETY ARGUMENT, stated once here because it is the reason this is allowed to
    skip the review-then-promote flow every other write to the ledger goes through.
    ``screen()`` (unchanged, reused) already requires a VERIFIED, sourced action whose
    recorded ratio is corroborated by the actual cum/ex price move -- three independent
    checks, not one. Given that, applying it is not a guess: a real corporate action
    credits EVERY eligible holder of record automatically and unconditionally (that is
    what "corporate action" means -- nobody opts in), so the only remaining question is
    eligibility, which ``quantity_held_before`` answers directly from this account's own
    ledger with no external input needed. This is a stronger safety position than
    ``stage_corporate_actions``'s reconcile-against-a-declared-statement path, not a
    weaker one -- that path exists for DISCOVERING an action nothing verified explains
    yet; this one is for APPLYING one that is already fully verified.

    IDEMPOTENT on TWO independent levels, deliberately, not one. ``source_ref`` matches
    the exact string ``app.ingest.corporate_action_matcher``'s staged rows build, so the
    two paths' ``dedupe_key`` values agree and ``save_transactions``'s
    ``ON CONFLICT DO NOTHING`` absorbs a re-run. But a dedupe_key match requires an
    EXACT string, and this table's ``source``/``source_url`` text is free-form and can
    legitimately be edited or reworded later -- so this also checks the account's own
    ledger directly for an existing ``CORP_ACTION`` row on the same (isin, ex_date,
    txn_type) before ever building a candidate, which recognises "this was already
    applied" regardless of exactly what text produced it the first time. That check is
    the one this function actually depends on for correctness; the dedupe_key agreement
    is a second, redundant backstop, not the only thing standing between here and a
    silently duplicated bonus.

    KNOWN LIMITATION, not silently glossed over: eligibility is computed from THIS
    account's ledger as it stands right now. If an older contract note surfaces LATER
    (more pre-action history lands after this already ran), the earlier-applied
    quantity can go stale. Nothing here rewrites it -- CLAUDE.md's ledger is
    append-only -- so a stale auto-applied row is corrected the same way any other
    ledger mistake is: a human reviews it and appends the reversing and correct rows by
    hand, same as a bad parse or a superseded source always has been.
    """
    transactions = load_transactions(conn, account_id=account_id)
    if not transactions:
        return ImportSummary()

    isins = sorted({t.isin for t in transactions})
    actions = list_corporate_actions(conn, isins)
    safe_actions, _failures = screen(actions)

    # The primary idempotency check -- content-based, not string-based. A CORP_ACTION
    # row already sitting at this exact (isin, ex_date, txn_type) means some path
    # (this one, a prior run, or a human's manual/staged entry) already applied this
    # action here, whatever source_ref text it happened to carry.
    already_applied = {
        (t.isin, t.txn_date, t.txn_type)
        for t in transactions
        if t.source is Source.CORP_ACTION
    }

    to_insert: list[Transaction] = []
    for action in safe_actions:
        held_qty = quantity_held_before(transactions, action.isin, action.ex_date)
        if held_qty <= ZERO:
            continue  # not a holder of record -- this action does not apply here
        isin, txn_type, quantity = free_share_effect(action, held_qty)
        if quantity <= ZERO:
            continue
        if (isin, action.ex_date, _TXN_TYPE[txn_type]) in already_applied:
            continue
        to_insert.append(
            Transaction(
                isin=isin,
                txn_date=action.ex_date,
                txn_type=_TXN_TYPE[txn_type],
                quantity=quantity,
                price=ZERO,
                account_id=account_id,
                source=Source.CORP_ACTION,
                # SAME format app.ingest.corporate_action_matcher's staged rows use --
                # deliberately, not incidentally: dedupe_key is derived from this
                # string, so the auto-apply sweep and the manual stage/review/promote
                # path must produce an IDENTICAL source_ref for the same event, or the
                # two paths fail to recognise each other's work and double-credit it.
                source_ref=f"{action.source} {action.source_url}",
            )
        )

    summary = save_transactions(conn, to_insert, actor_uid=actor_uid)
    if summary.inserted:
        audit.record(
            conn,
            audit.ACTION_CORPORATE_ACTION_AUTO_APPLIED,
            "account",
            account_id,
            actor_uid,
            {
                "inserted": summary.inserted,
                "isins": sorted({t.isin for t in to_insert}),
            },
        )
    return summary


def apply_known_actions_for_investor(
    conn: Any, investor_id: str, actor_uid: str | None = None
) -> ImportSummary:
    """``apply_known_actions_for_account`` across every account this investor has --
    holdings are computed per account (advised vs self-directed, one broker vs
    another), so eligibility has to be checked per account too, not on the investor's
    combined ledger."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM account WHERE investor_id = %s", (investor_id,))
        account_ids = [row[0] for row in cur.fetchall()]

    total = ImportSummary()
    for account_id in account_ids:
        result = apply_known_actions_for_account(conn, str(account_id), actor_uid)
        total = ImportSummary(
            inserted=total.inserted + result.inserted,
            skipped_duplicates=total.skipped_duplicates + result.skipped_duplicates,
            rejected=total.rejected + result.rejected,
        )
    return total


#: NSE's corporate-filings API is INTERIM -- see app.ingest.corporate_action_feed's
#: module docstring. Recorded here as the ``source`` every auto-fetched row carries, so
#: a human reading the reference table can see where a given entry actually came from.
_FEED_SOURCE_NAME = "NSE corporate-filings API"
_FEED_SOURCE_URL = "https://www.nseindia.com/companies-listing/corporate-filings-actions"


def _price_evidence(conn: Any, isin: str, ex_date: date) -> tuple[Decimal | None, Decimal | None]:
    """(price_cum, price_ex) for a BONUS/SPLIT candidate, from bhavcopy already stored
    by this system's own daily price pipe -- never fetched fresh here, never guessed.

    cum = the most recent close ON OR BEFORE the day before ex_date (``latest_prices``'s
    walk-back handles a preceding weekend/holiday); ex = the EXACT ex_date close, no
    carry-forward (``prices_on_date`` -- the same distinction
    ``app.routers.holdings._portfolio`` relies on for "has today's bhavcopy settled
    yet?"). Either can legitimately be ``None`` if bhavcopy hasn't caught up yet -- not
    an error, just not yet resolvable; the caller lands the candidate in ``Exceptions``
    and the next feed run retries it.
    """
    cum_day = date.fromordinal(ex_date.toordinal() - 1)
    cum = latest_prices(conn, [isin], as_of=cum_day).get(isin)
    ex = prices_on_date(conn, [isin], ex_date).get(isin)
    return cum, ex


def _evaluate_bonus_split(
    conn: Any,
    isin: str,
    action_type: CorpActionType,
    ex_date: date,
    bonus_new: int | None,
    bonus_for: int | None,
    face_value_before: Decimal | None,
    face_value_after: Decimal | None,
    notes: str,
    source: str = _FEED_SOURCE_NAME,
    source_url: str = _FEED_SOURCE_URL,
) -> CorporateAction:
    """Build a candidate BONUS/SPLIT ``CorporateAction`` with real price evidence
    attached, tentatively marked VERIFIED so ``check_sourced``/``check_price_consistency``
    can be asked "if this were verified, would it pass?" -- the caller
    (``refresh_corporate_action_feed``, ``discover_from_yfinance``) is what actually
    decides the stored verification, based on the answer.

    ``source``/``source_url`` default to the NSE-notices feed's own identity; pass
    explicit values for a different candidate source (``discover_from_yfinance`` does)
    so the reference table always records which discovery path actually found it.
    """
    price_cum, price_ex = _price_evidence(conn, isin, ex_date)
    return CorporateAction(
        isin=isin, action_type=action_type, ex_date=ex_date,
        source=source, source_url=source_url,
        verification=Verification.VERIFIED,
        bonus_new=bonus_new, bonus_for=bonus_for,
        face_value_before=face_value_before, face_value_after=face_value_after,
        price_cum=price_cum, price_ex=price_ex, notes=notes,
    )


def refresh_corporate_action_feed(
    conn: Any,
    start: date,
    end: date,
    source: Any | None = None,
    actor_uid: str | None = None,
) -> dict[str, Any]:
    """Fetch NSE's corporate-actions notices for ``[start, end]``, auto-verify every
    BONUS/SPLIT that passes ``check_sourced``/``check_price_consistency``, and land
    everything else in ``Exceptions`` -- see ``docs/ENGINE_SPEC.md`` §7 "Automated
    ingestion" for the full trust-model writeup this implements.

    SELF-CORRECTING RETRY, not just fresh notices: every existing ``DRAFT`` row is
    re-evaluated on every run too (fresh price evidence looked up again), so a
    candidate that failed only for want of a not-yet-published bhavcopy close
    self-promotes to VERIFIED the moment that price lands, with no human step and no
    need for a brand-new notice to re-trigger it.

    Never raises on a routine failure -- a fetch or parse problem is logged and
    returns an error in the result dict rather than propagating, the same
    log-and-continue posture ``_run_snapshots`` (``app.routers.analytical``) already
    uses for a daily job. A single malformed row cannot abort the run: it is
    evaluated, found wanting, and lands in ``Exceptions`` like any other row that
    doesn't pass -- it does not stop the rows around it from being processed.
    """
    from app.ingest.corporate_action_feed import (
        CorporateActionFeedFetchFailed,
        CorporateActionFeedFormatError,
        nse_corporate_action_feed,
        parse_corporate_action_feed,
    )

    feed = source or nse_corporate_action_feed()
    try:
        payload = feed.fetch(start, end)
    except CorporateActionFeedFetchFailed as exc:
        logger.warning("corporate-action feed fetch failed for %s..%s: %s", start, end, exc)
        return {"fetched": 0, "verified": 0, "exceptions": 0, "error": str(exc)}

    try:
        feed_rows = parse_corporate_action_feed(payload)
    except CorporateActionFeedFormatError as exc:
        logger.warning("corporate-action feed format changed for %s..%s: %s", start, end, exc)
        return {"fetched": 0, "verified": 0, "exceptions": 0, "error": str(exc)}

    verified = 0
    exceptions = 0
    seen_keys: set[tuple[str, CorpActionType, date]] = set()

    for row in feed_rows:
        key = (row.isin, row.action_type, row.ex_date)
        seen_keys.add(key)
        try:
            candidate = _evaluate_bonus_split(
                conn, row.isin, row.action_type, row.ex_date,
                row.bonus_new, row.bonus_for, row.face_value_before, row.face_value_after,
                notes=row.raw_subject,
            )
            failure = check_sourced(candidate) or check_price_consistency(candidate)
            if failure is not None:
                candidate = replace(
                    candidate, verification=Verification.DRAFT,
                    notes=f"{candidate.notes}\n{failure.code}: {failure.detail}",
                )
                exceptions += 1
            else:
                verified += 1
            add_corporate_action(conn, candidate, actor_uid=actor_uid)
            # Commit PER ROW, deliberately, not once at the end of the run: without
            # this, a later row's UniqueViolation -> rollback() would also discard
            # every earlier row's already-successful, still-uncommitted insert in the
            # same run -- Postgres aborts the whole transaction on an error until
            # rolled back, and rollback undoes everything since the last commit, not
            # just the offending statement. Log-and-continue only actually isolates
            # one bad row from the rest if each row's work is committed before moving
            # on to the next.
            conn.commit()
        except psycopg.errors.UniqueViolation:
            conn.rollback()
            # Already on file (an earlier run's fetch, VERIFIED or still in
            # Exceptions) -- benign, expected on a re-fetched notice. If it's still
            # pending, the loop below retries it along with every other pending row.
        except Exception:
            conn.rollback()
            logger.warning(
                "corporate-action candidate failed for isin=%s ex_date=%s -- skipped, "
                "not aborting the run", row.isin, row.ex_date, exc_info=True,
            )

    reevaluable = (CorpActionType.BONUS, CorpActionType.SPLIT)
    for pending in list_pending_corporate_actions(conn):
        key = (pending.isin, pending.action_type, pending.ex_date)
        if key in seen_keys or pending.action_type not in reevaluable:
            continue  # not this run's business, or not a type this feed re-evaluates
        try:
            candidate = _evaluate_bonus_split(
                conn, pending.isin, pending.action_type, pending.ex_date,
                pending.bonus_new, pending.bonus_for,
                pending.face_value_before, pending.face_value_after,
                notes=pending.notes,
            )
            if check_sourced(candidate) or check_price_consistency(candidate):
                continue  # still not resolvable -- retried again next run
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE corporate_action SET price_cum = %s, price_ex = %s WHERE id = %s",
                    (candidate.price_cum, candidate.price_ex, pending.id),
                )
            verify_corporate_action(conn, pending.id, actor_uid=actor_uid)
            conn.commit()  # per-row, same reasoning as the fetch loop above
            verified += 1
        except Exception:
            conn.rollback()
            logger.warning(
                "corporate-action retry failed for isin=%s ex_date=%s -- skipped",
                pending.isin, pending.ex_date, exc_info=True,
            )

    return {"fetched": len(feed_rows), "verified": verified, "exceptions": exceptions}


def discover_from_yfinance(
    conn: Any,
    isins: list[str] | None = None,
    source: Any | None = None,
    actor_uid: str | None = None,
) -> dict[str, Any]:
    """The second free discovery source -- see ``app.ingest.corporate_action_yfinance``
    for why this exists (NSE's own notices feed has no historical depth) and why every
    candidate is still exactly as untrusted as one from that feed until it passes the
    same ``check_sourced``/``check_price_consistency`` guards, reused unchanged below.

    Occasional, not a daily rolling window like ``refresh_corporate_action_feed``: a
    ticker's whole split history comes back in one call, there is no date range to page
    through, and it does not change day to day the way live notices do. A candidate
    this misses is retried for free anyway -- ``refresh_corporate_action_feed``'s own
    self-correcting retry loop re-evaluates every pending ``DRAFT`` row regardless of
    which path discovered it, so a yfinance candidate that only failed for want of a
    not-yet-published price still self-promotes on the next daily feed run.

    ``isins`` defaults to every ISIN this system has ever held
    (``app.db.prices.held_isins``) -- never Yahoo's full universe, which would waste
    calls on securities nobody here owns.
    """
    from app.db.prices import held_isins
    from app.ingest.corporate_action_yfinance import (
        YFINANCE_SOURCE_NAME,
        YfinanceSource,
        discover_candidates,
    )
    from app.securities import lookup as lookup_securities

    yf_source = source or YfinanceSource()
    target_isins = isins if isins is not None else held_isins(conn)
    meta = lookup_securities(conn, target_isins)

    discovered = 0
    verified = 0
    exceptions = 0
    duplicates = 0
    errors: dict[str, str] = {}

    for isin in target_isins:
        symbol = (meta.get(isin) or {}).get("symbol")
        if not symbol:
            continue  # no security master row for this ISIN -- add_corporate_action's
            # FK would reject it anyway; skip before spending a network call on it.
        try:
            candidates = discover_candidates(yf_source, isin, symbol)
        except Exception as exc:
            errors[isin] = str(exc)
            logger.warning(
                "yfinance split lookup failed for isin=%s symbol=%s", isin, symbol, exc_info=True
            )
            continue

        for candidate in candidates:
            discovered += 1
            try:
                action = _evaluate_bonus_split(
                    conn, candidate.isin, CorpActionType.BONUS, candidate.ex_date,
                    candidate.bonus_new, candidate.bonus_for, None, None,
                    notes=f"Discovered via yfinance split history for {symbol}.NS.",
                    source=YFINANCE_SOURCE_NAME, source_url=candidate.source_url,
                )
                failure = check_sourced(action) or check_price_consistency(action)
                if failure is not None:
                    action = replace(
                        action, verification=Verification.DRAFT,
                        notes=f"{action.notes}\n{failure.code}: {failure.detail}",
                    )
                add_corporate_action(conn, action, actor_uid=actor_uid)
                conn.commit()  # per-row, same reasoning as refresh_corporate_action_feed
                # Counted only once the row is actually ON FILE, deliberately: a
                # duplicate that rolls back below has verified nothing, and reporting it
                # as verified would overstate what a run actually did.
                if failure is not None:
                    exceptions += 1
                else:
                    verified += 1
            except psycopg.errors.UniqueViolation:
                conn.rollback()
                duplicates += 1
                # Already on file -- another discovery path (or a prior run of this one)
                # found the same event. Benign and expected: the two paths agreeing is
                # the system working, not a problem to report.
            except Exception:
                conn.rollback()
                logger.warning(
                    "yfinance candidate failed for isin=%s ex_date=%s -- skipped, not "
                    "aborting the run", candidate.isin, candidate.ex_date, exc_info=True,
                )

    return {
        "isins_checked": len(target_isins),
        "discovered": discovered,
        "verified": verified,
        "exceptions": exceptions,
        "duplicates": duplicates,
        "errors": errors,
    }
