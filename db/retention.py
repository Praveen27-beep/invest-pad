"""Retention policy -- 5 years by default, suspended by a legal hold.

SEBI Reg. 19 requires five years for advisory records; DPDP requires one year for access
logs. The longer obligation governs, so the default is five. Configurable per entity type
because that is what ``docs/COMPLIANCE.md`` asks for, not because shortening it is a good
idea.

This module REPORTS what is due for deletion. It does not delete. Automatic destruction
of client records on a timer is exactly the kind of thing that should require a human to
look at a list first.
"""

from __future__ import annotations

from datetime import date
from typing import Any

DEFAULT_RETAIN_YEARS = 5


def retain_years(conn: Any, entity_type: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT retain_years FROM retention_policy WHERE entity_type = %s", (entity_type,)
        )
        row = cur.fetchone()
        return row[0] if row else DEFAULT_RETAIN_YEARS


def cutoff(conn: Any, entity_type: str, as_of: date) -> date:
    """The date before which records of this type are past retention."""
    years = retain_years(conn, entity_type)
    try:
        return as_of.replace(year=as_of.year - years)
    except ValueError:
        # 29 February. Step back a day rather than forward, so the cutoff never lands
        # later than intended and destroys something a day early.
        return as_of.replace(month=2, day=28, year=as_of.year - years)


def due_for_deletion(conn: Any, as_of: date) -> list[dict[str, Any]]:
    """Investors whose records are past retention AND not under legal hold.

    A held investor is never listed, at any age. Where a dispute has been raised, records
    are kept until it resolves or SEBI directs otherwise -- a cleanup job must not be able
    to quietly destroy evidence in a live matter.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.id, i.code, i.created_at,
                   (SELECT max(t.txn_date) FROM transaction t
                    JOIN account a ON a.id = t.account_id
                    WHERE a.investor_id = i.id) AS last_activity
            FROM investor i
            WHERE NOT EXISTS (
                SELECT 1 FROM legal_hold h
                WHERE h.investor_id = i.id AND h.released_at IS NULL
            )
            """
        )
        columns = [c.name for c in cur.description]
        rows = [dict(zip(columns, r, strict=True)) for r in cur.fetchall()]

    limit = cutoff(conn, "investor", as_of)
    due = []
    for row in rows:
        # Retention runs from the LAST interaction, not the first: an active client's
        # early records stay for as long as the relationship does.
        last = row["last_activity"] or row["created_at"].date()
        if last < limit:
            due.append({**row, "retained_until": limit, "last_activity": last})
    return due
