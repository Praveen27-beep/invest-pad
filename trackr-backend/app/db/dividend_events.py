"""DB-layer CRUD for the ``dividend_event`` reference table -- migration 029.

Nothing here writes to ``transaction``, and deliberately there is no function that could.
The corporate-action module has ``apply_known_actions_for_account`` because a bonus is
credited to every holder of record unconditionally, which makes eligibility the only open
question; a dividend's open question is RECEIPT, which no feed behind this table answers.
So this module stops at maintained reference data, and the path to a ``DIVIDEND`` ledger
row stays the existing ``import_batch``/``promote`` flow with a human or a credit advice
in it. The absence of an apply function here is the design, not an omission to fill in
later -- see migration 029's header.

THE ONE NON-OBVIOUS RULE IN THIS MODULE is ``match_unspecified``'s: how a candidate whose
source did not say "interim" or "final" is reconciled against an event already on file
that does. Read that docstring before changing anything about uniqueness.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from app.db import audit
from app.engine.corporate_actions import Verification
from app.engine.dividend_events import DividendEvent, DividendKind

logger = logging.getLogger("dividend_events")

_SELECT_COLUMNS = (
    "id, isin, ex_date, record_date, payment_date, amount_per_share, kind::text, "
    "source, source_url, corroborated_by, corroborated_url, verification::text, notes"
)


def _row_to_event(row: tuple) -> DividendEvent:
    (
        id_, isin, ex_date, record_date, payment_date, amount_per_share, kind,
        source, source_url, corroborated_by, corroborated_url, verification, notes,
    ) = row
    return DividendEvent(
        id=str(id_),
        isin=isin,
        ex_date=ex_date,
        record_date=record_date,
        payment_date=payment_date,
        amount_per_share=amount_per_share,
        kind=DividendKind(kind),
        source=source,
        source_url=source_url,
        corroborated_by=corroborated_by,
        corroborated_url=corroborated_url,
        verification=Verification(verification),
        notes=notes or "",
    )


class DividendEventDateError(ValueError):
    """A candidate's dates cannot be true together -- a record or payment date before the
    ex-date, which in practice means a misread or transposed field rather than an unusual
    corporate timetable.

    Raised in Python as well as enforced by migration 029's CHECK constraints, so a caller
    that wants to land the candidate in ``Exceptions`` with a readable note can catch this
    instead of taking a ``CheckViolation`` and rolling back a whole statement.
    """


def validate_dates(event: DividendEvent) -> None:
    """Raise ``DividendEventDateError`` if the dates are impossible. Mirrors the table's
    own constraints; see that class's docstring for why both exist."""
    if event.record_date is not None and event.record_date < event.ex_date:
        raise DividendEventDateError(
            f"record date {event.record_date} precedes ex-date {event.ex_date}"
        )
    if event.payment_date is not None and event.payment_date < event.ex_date:
        raise DividendEventDateError(
            f"payment date {event.payment_date} precedes ex-date {event.ex_date}"
        )


def add_dividend_event(
    conn: Any, event: DividendEvent, actor_uid: str | None = None
) -> str:
    """Insert one declared dividend. Raises ``psycopg.errors.UniqueViolation`` on a
    repeat of ``(isin, ex_date, kind)``, which callers treat as benign -- the same posture
    ``refresh_corporate_action_feed`` already takes for a re-fetched notice."""
    validate_dates(event)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dividend_event (
                isin, ex_date, record_date, payment_date, amount_per_share, kind,
                source, source_url, corroborated_by, corroborated_url, verification, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                event.isin, event.ex_date, event.record_date, event.payment_date,
                event.amount_per_share, event.kind.value,
                event.source, event.source_url,
                event.corroborated_by, event.corroborated_url,
                event.verification.value, event.notes or None,
            ),
        )
        event_id = str(cur.fetchone()[0])

    audit.record(
        conn,
        audit.ACTION_DIVIDEND_EVENT_ADDED,
        "dividend_event",
        event_id,
        actor_uid,
        {
            "isin": event.isin,
            "ex_date": event.ex_date.isoformat(),
            "kind": event.kind.value,
            "amount_per_share": str(event.amount_per_share),
            "source": event.source,
        },
    )
    return event_id


def list_dividend_events(
    conn: Any,
    isins: list[str] | None = None,
    verification: Verification | None = None,
    ex_date_from: date | None = None,
    ex_date_to: date | None = None,
) -> list[DividendEvent]:
    """Declared dividends on file, optionally filtered. Ordered by ex-date then ISIN so a
    caller rendering a calendar does not have to re-sort.

    No ``resulting_isin`` clause, unlike ``list_corporate_actions``: a dividend has no
    second security. An ISIN change is handled where it belongs -- at the read boundary,
    through ``app.db.security_alias`` -- not by matching two columns here.
    """
    query = f"SELECT {_SELECT_COLUMNS} FROM dividend_event"
    clauses: list[str] = []
    params: list[Any] = []
    if isins:
        clauses.append("isin = ANY(%s)")
        params.append(isins)
    if verification is not None:
        clauses.append("verification = %s")
        params.append(verification.value)
    if ex_date_from is not None:
        clauses.append("ex_date >= %s")
        params.append(ex_date_from)
    if ex_date_to is not None:
        clauses.append("ex_date <= %s")
        params.append(ex_date_to)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY ex_date, isin"
    with conn.cursor() as cur:
        cur.execute(query, params)
        return [_row_to_event(row) for row in cur.fetchall()]


def get_dividend_event(conn: Any, event_id: str) -> DividendEvent | None:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_SELECT_COLUMNS} FROM dividend_event WHERE id = %s", (event_id,))
        row = cur.fetchone()
        return _row_to_event(row) if row else None


def list_pending_dividend_events(conn: Any) -> list[DividendEvent]:
    """Every ``DRAFT`` row -- the ``Exceptions`` surface.

    Unlike ``list_pending_corporate_actions``, this is expected to be LONG rather than
    short, and that is not a sign of a broken feed. A dividend reaches ``VERIFIED`` only
    once a second source agrees (``check_cross_sourced``), so every dividend seen by just
    one feed so far sits here legitimately, waiting. Any UI over this must say so, or it
    reads as a backlog of failures.
    """
    return list_dividend_events(conn, verification=Verification.DRAFT)


def match_unspecified(
    conn: Any, isin: str, ex_date: date
) -> list[DividendEvent]:
    """Events already on file for this ``(isin, ex_date)``, whatever their kind.

    WHY THIS EXISTS, AND WHY IT RETURNS A LIST RATHER THAN ONE EVENT. The table is unique
    on ``(isin, ex_date, kind)``, and one of the two feeds cannot supply a kind:
    ``Ticker.dividends`` carries only an ex-date and an amount. So a yfinance candidate
    arrives as ``UNSPECIFIED`` while the NSE notice for the SAME dividend may already be
    on file as ``INTERIM``. Inserting the candidate as-is would create a second row for
    one real event -- and worse, it would mean the two sources never corroborate each
    other, silently defeating the only verification a dividend has.

    So an unspecified candidate must be matched, not inserted blindly. The rule, and the
    reason it is fail-closed:

      - EXACTLY ONE event on file for that (isin, ex_date): the candidate is about that
        event. ``corroborate`` it.
      - NOTHING on file: insert it as ``UNSPECIFIED``. A later classified notice for the
        same ex-date will find it through this same lookup.
      - MORE THAN ONE event on file (an interim and a special sharing an ex-date): the
        candidate is AMBIGUOUS. Which one did this source mean? Nothing here can tell, and
        picking either would attach corroborating evidence to a dividend it may not
        describe. Corroborate NEITHER, and leave a note -- a wrong corroboration is worse
        than a missing one, because it converts DRAFT into VERIFIED on false evidence.

    That last branch is the fail-closed case and the reason this returns every match
    rather than a single row: the caller must be able to SEE that there was more than one.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_SELECT_COLUMNS} FROM dividend_event WHERE isin = %s AND ex_date = %s "
            "ORDER BY kind",
            (isin, ex_date),
        )
        return [_row_to_event(row) for row in cur.fetchall()]


def corroborate_dividend_event(
    conn: Any,
    event_id: str,
    source: str,
    source_url: str,
    amount_per_share: Decimal,
    actor_uid: str | None = None,
) -> Verification:
    """Record that a second, distinct source read this event -- and decide what that does
    to its verification. Returns the resulting state.

    Three outcomes, and the middle one is the important one:

      - The second source AGREES on the amount -> ``corroborated_by``/``corroborated_url``
        are set and the event is promoted to ``VERIFIED``. It may now produce a
        projection. It still may not produce a ledger row.
      - The second source DISAGREES on the amount -> ``DISPUTED``, with both readings
        written into ``notes``. NOT a second row, not an average, not "prefer the newer":
        one fact, two contradictory claims, and no basis in this module for choosing. A
        human reads the company's filing.
      - The "second" source is the SAME source -> rejected without a write. Two reads of
        one feed are one observation; the table's own CHECK refuses it too.

    Never downgrades a ``VERIFIED`` event that a human promoted, and never revisits a
    ``DISPUTED`` one -- a human's explicit rejection is the one state automation does not
    overturn, exactly as ``refresh_corporate_action_feed`` treats ``DISPUTED``.
    """
    event = get_dividend_event(conn, event_id)
    if event is None:
        raise LookupError(f"no dividend_event {event_id}")
    if event.verification is Verification.DISPUTED:
        return Verification.DISPUTED  # a human's rejection stands
    if source == event.source:
        return event.verification  # not a second observation

    if amount_per_share != event.amount_per_share:
        note = (
            f"{event.notes}\nAMOUNT_CONFLICT: {event.source} reports "
            f"{event.amount_per_share}/share, {source} reports {amount_per_share}/share"
        ).strip()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE dividend_event SET verification = %s, notes = %s WHERE id = %s",
                (Verification.DISPUTED.value, note, event_id),
            )
        audit.record(
            conn, audit.ACTION_DIVIDEND_EVENT_DISPUTED, "dividend_event", event_id, actor_uid,
            {
                "isin": event.isin,
                "reason": "AMOUNT_CONFLICT",
                "reported": str(amount_per_share),
                "on_file": str(event.amount_per_share),
                "reported_by": source,
            },
        )
        return Verification.DISPUTED

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE dividend_event
               SET corroborated_by = %s, corroborated_url = %s, verification = %s
             WHERE id = %s
            """,
            (source, source_url, Verification.VERIFIED.value, event_id),
        )
    audit.record(
        conn, audit.ACTION_DIVIDEND_EVENT_CORROBORATED, "dividend_event", event_id, actor_uid,
        {"isin": event.isin, "corroborated_by": source, "amount_per_share": str(amount_per_share)},
    )
    return Verification.VERIFIED


def verify_dividend_event(
    conn: Any, event_id: str, actor_uid: str | None = None
) -> None:
    """A human promotes an event to ``VERIFIED`` by hand.

    Deliberately does NOT require ``check_cross_sourced`` to pass. A person can read the
    company's own filing, which is a stronger and differently-originated piece of evidence
    than two redistributors agreeing -- see that guard's docstring on why their agreement
    is corroboration rather than proof. This is the one path that can verify a
    single-sourced dividend, and it is a human taking responsibility for it.

    Unlike ``verify_corporate_action``, this triggers NO retroactive ledger sweep: there
    is nothing to sweep, because a verified declaration still has no receipt behind it.
    Verification here unlocks a projection, and nothing else.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE dividend_event SET verification = %s WHERE id = %s AND verification <> %s",
            (Verification.VERIFIED.value, event_id, Verification.VERIFIED.value),
        )
        if cur.rowcount == 0:
            return
    event = get_dividend_event(conn, event_id)
    audit.record(
        conn, audit.ACTION_DIVIDEND_EVENT_VERIFIED, "dividend_event", event_id, actor_uid,
        {"isin": event.isin if event else None, "manual": True},
    )


def dispute_dividend_event(
    conn: Any, event_id: str, reason: str, actor_uid: str | None = None
) -> None:
    """Mark an event rejected. Terminal as far as automation is concerned -- no feed run
    revisits a ``DISPUTED`` row, the same contract ``corporate_action`` has."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE dividend_event SET verification = %s, notes = %s WHERE id = %s",
            (Verification.DISPUTED.value, reason, event_id),
        )
    audit.record(
        conn, audit.ACTION_DIVIDEND_EVENT_DISPUTED, "dividend_event", event_id, actor_uid,
        {"reason": reason, "manual": True},
    )


def update_dividend_event_dates(
    conn: Any,
    event_id: str,
    record_date: date | None = None,
    payment_date: date | None = None,
) -> None:
    """Fill in a record or payment date a later fetch supplied and an earlier one did not.

    Only ever fills a NULL -- ``COALESCE`` on the existing value, so a date already on
    file is never overwritten by a later source. A contradiction between two sources about
    a date is not silently resolved here; it is the same class of problem as an amount
    conflict and belongs in ``notes`` and ``DISPUTED``, not in a last-writer-wins update.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE dividend_event
               SET record_date  = COALESCE(record_date, %s),
                   payment_date = COALESCE(payment_date, %s)
             WHERE id = %s
            """,
            (record_date, payment_date, event_id),
        )


__all__ = [
    "DividendEventDateError",
    "add_dividend_event",
    "corroborate_dividend_event",
    "dispute_dividend_event",
    "get_dividend_event",
    "list_dividend_events",
    "list_pending_dividend_events",
    "match_unspecified",
    "update_dividend_event_dates",
    "validate_dates",
    "verify_dividend_event",
]
