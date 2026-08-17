"""Grievance intake and the 90-day clock, against a real cluster.

The interesting assertions are the ones about what CANNOT be done: extend the deadline,
close without saying how, or backdate a closure into the window.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.db import grievance, privacy

pytestmark = pytest.mark.db


def raise_one(db, subject="Statement shows wrong quantity", investor_id=None):
    return grievance.raise_grievance(
        db, subject=subject, channel="EMAIL",
        detail="Client says June holdings are overstated.", investor_id=investor_id,
    )


def test_raising_starts_a_ninety_day_clock(db) -> None:
    row = raise_one(db)
    assert row["status"] == "OPEN"
    assert (row["due_at"] - row["raised_at"]).days == grievance.REDRESSAL_CEILING_DAYS


def test_the_deadline_cannot_be_extended(db) -> None:
    """A deadline the application sets is one the application can set wrongly.

    A direct attempt to push the ceiling out is not rejected loudly -- it is discarded.
    The trigger recomputes due_at from raised_at on every write, so there is no path,
    application or manual, that moves a statutory deadline.
    """
    row = raise_one(db)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE grievance SET due_at = now() + interval '999 days' WHERE id = %s",
            (row["id"],),
        )
        cur.execute("SELECT due_at, raised_at FROM grievance WHERE id = %s", (row["id"],))
        due_at, raised_at = cur.fetchone()
    assert (due_at - raised_at).days == grievance.REDRESSAL_CEILING_DAYS
    assert due_at == row["due_at"]


def test_reference_is_quotable_and_not_a_uuid(db) -> None:
    row = raise_one(db)
    assert row["reference"].startswith("GRV-")
    assert str(row["id"]) not in row["reference"]


def test_references_are_unique(db) -> None:
    refs = {raise_one(db)["reference"] for _ in range(20)}
    assert len(refs) == 20


def test_intake_accepts_a_complaint_from_an_unknown_person(db) -> None:
    """A route that only accepts complaints from known clients is not an intake route."""
    row = raise_one(db, investor_id=None)
    assert row["id"]
    assert grievance.open_grievances(db)[0]["investor_id"] is None


def test_acknowledging_does_not_stop_the_clock(db) -> None:
    row = raise_one(db)
    grievance.acknowledge(db, row["id"])
    still_open = grievance.open_grievances(db)
    assert len(still_open) == 1
    assert still_open[0]["status"] == "ACKNOWLEDGED"


def test_resolution_closes_it_and_reports_compliance(db) -> None:
    row = raise_one(db)
    result = grievance.resolve(db, row["id"], "Reissued the statement; client confirmed.")
    assert result["within_ceiling"] is True
    assert grievance.open_grievances(db) == []


def test_cannot_resolve_without_saying_how(db) -> None:
    """RESOLVED with an empty resolution is how a redressal record becomes worthless."""
    row = raise_one(db)
    with pytest.raises(ValueError, match="without recording how"):
        grievance.resolve(db, row["id"], "   ")


def test_database_also_refuses_an_empty_resolution(db) -> None:
    """Enforced below the application, so another writer cannot bypass it."""
    import psycopg

    row = raise_one(db)
    with db.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "UPDATE grievance SET status='RESOLVED', resolved_at=now(), resolution='' "
            "WHERE id = %s",
            (row["id"],),
        )
    db.rollback()


def test_resolution_cannot_predate_the_complaint(db) -> None:
    """Backdating a closure into the window would fake compliance in the very record
    meant to evidence it."""
    import psycopg

    row = raise_one(db)
    with db.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "UPDATE grievance SET status='RESOLVED', resolution='done', "
            "resolved_at = raised_at - interval '1 day' WHERE id = %s",
            (row["id"],),
        )
    db.rollback()


def test_a_resolved_grievance_cannot_be_reopened(db) -> None:
    row = raise_one(db)
    grievance.resolve(db, row["id"], "Corrected.")
    with pytest.raises(grievance.AlreadyResolvedError):
        grievance.resolve(db, row["id"], "Corrected again.")


def test_escalation_does_not_extend_the_deadline(db) -> None:
    """The ceiling is statutory. Internal process does not move it."""
    row = raise_one(db)
    grievance.escalate(db, row["id"], reason="needs the depository to respond")

    (still_open,) = grievance.open_grievances(db)
    assert still_open["status"] == "ESCALATED"
    assert still_open["due_at"] == row["due_at"]


def test_due_soon_warns_before_the_breach_not_after(db) -> None:
    """By the time something is overdue the obligation has already been missed."""
    row = raise_one(db)
    assert grievance.due_soon(db) == [], "not yet inside the horizon"

    with db.cursor() as cur:
        cur.execute(
            "UPDATE grievance SET raised_at = now() - interval '75 days' WHERE id = %s",
            (row["id"],),
        )
    warned = grievance.due_soon(db)
    assert len(warned) == 1
    assert grievance.overdue(db) == [], "warned while still compliant"


def test_overdue_reports_a_breach(db) -> None:
    row = raise_one(db)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE grievance SET raised_at = now() - interval '100 days' WHERE id = %s",
            (row["id"],),
        )
    breached = grievance.overdue(db)
    assert len(breached) == 1
    assert breached[0]["reference"] == row["reference"]
    assert breached[0]["time_left"] < timedelta(0)


def test_resolved_grievances_never_appear_as_overdue(db) -> None:
    row = raise_one(db)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE grievance SET raised_at = now() - interval '100 days' WHERE id = %s",
            (row["id"],),
        )
    grievance.resolve(db, row["id"], "Late, but resolved and recorded as such.")
    assert grievance.overdue(db) == []


def test_open_list_is_ordered_by_urgency(db) -> None:
    later = raise_one(db, subject="less urgent")
    sooner = raise_one(db, subject="more urgent")
    with db.cursor() as cur:
        cur.execute(
            "UPDATE grievance SET raised_at = now() - interval '80 days' WHERE id = %s",
            (sooner["id"],),
        )
    assert [g["subject"] for g in grievance.open_grievances(db)] == [
        "more urgent", "less urgent",
    ]
    assert later["id"]


def test_every_transition_is_audited(db) -> None:
    row = raise_one(db)
    grievance.acknowledge(db, row["id"])
    grievance.resolve(db, row["id"], "Corrected.")

    with db.cursor() as cur:
        cur.execute("SELECT action FROM audit_log WHERE entity_type = 'grievance'")
        actions = {r[0] for r in cur.fetchall()}
    assert actions == {
        grievance.ACTION_RAISED, grievance.ACTION_ACKNOWLEDGED, grievance.ACTION_RESOLVED,
    }


# --- interaction with erasure --------------------------------------------------


def test_a_grievance_survives_the_complainants_erasure(db, investor) -> None:
    """How a complaint was handled is a record of OUR conduct, not only of theirs.

    The investor link is severed, so nothing personal remains attached, but the fact that
    a complaint was made and redressed does not vanish.
    """
    row = raise_one(db, investor_id=investor)
    privacy.erase_investor(db, investor)

    with db.cursor() as cur:
        cur.execute("SELECT investor_id, subject FROM grievance WHERE id = %s", (row["id"],))
        remaining = cur.fetchone()
    assert remaining is not None, "the redressal record must not vanish with the investor"
    assert remaining[0] is None, "but the investor link is severed"


def test_open_grievances_can_be_found_per_investor(db, investor) -> None:
    raise_one(db, investor_id=investor)
    raise_one(db, investor_id=None)
    assert len(grievance.open_grievances(db, investor_id=investor)) == 1
    assert len(grievance.open_grievances(db)) == 2
