"""POST/GET /grievances and its sub-actions -- app.routers.grievance, against a real
database. See docs/FULL_VISION_BACKEND_ROADMAP.md section A7.

Calls the route handlers directly with the ``db`` fixture's connection, the same
pattern tests/test_db_investors.py and tests/test_db_transactions.py use: a FastAPI
route decorator returns the plain function underneath, so no HTTP client is needed to
exercise it against a real Postgres cluster. Complaint subjects, channels and reasons
below are all made up -- this needs no real client data, per the task that added this
router.

``current_user`` is passed by hand below wherever a handler declares it, standing in
for what a real ``Depends(get_current_user)`` would have resolved from a bearer token
-- calling the plain function bypasses FastAPI's own dependency injection, so nothing
here proves a request WITHOUT a token is refused. That half of the auth decision is
pinned instead in tests/test_grievance_router.py, which checks each handler's declared
dependencies directly; this file only needs to prove that, given a connection and (where
relevant) a caller identity, each handler correctly delegates to app.db.grievance and
shapes the result for the wire.
"""

from __future__ import annotations

import pytest
from app.db import grievance
from app.db.grievance import AlreadyResolvedError, GrievanceNotFoundError
from app.routers.grievance import (
    acknowledge_grievance,
    escalate_grievance,
    file_grievance,
    list_due_soon,
    list_open_grievances,
    list_overdue,
    resolve_grievance,
)
from app.schemas.grievance import EscalateIn, GrievanceIn, ResolveIn
from fastapi import HTTPException

pytestmark = pytest.mark.db

STAFF = {"id": "11111111-1111-1111-1111-111111111111", "email": "adviser@example.com"}
NIL_UUID = "00000000-0000-0000-0000-000000000000"


def test_filing_a_grievance_needs_no_investor_id(db) -> None:
    """The whole point of A7: docs/COMPLIANCE.md requires intake to accept complaints
    from people not yet matched to an investor record."""
    result = file_grievance(GrievanceIn(subject="Wrong quantity shown", channel="EMAIL"), conn=db)
    assert result["reference"].startswith("GRV-")
    assert result["status"] == "OPEN"
    assert result["due_at"] > result["raised_at"]
    assert isinstance(result["id"], str)


def test_the_reference_never_leaks_the_internal_id(db) -> None:
    result = file_grievance(GrievanceIn(subject="Statement error", channel="EMAIL"), conn=db)
    assert result["id"] not in result["reference"]


def test_filing_against_a_known_investor_is_also_accepted(db, investor) -> None:
    result = file_grievance(
        GrievanceIn(subject="Missing dividend", channel="PORTAL", investor_id=investor),
        conn=db,
    )
    listed = list_open_grievances(investor_id=investor, conn=db, current_user=STAFF)
    assert [g["id"] for g in listed] == [result["id"]]


def test_open_list_is_staff_facing_and_returns_str_ids(db) -> None:
    file_grievance(GrievanceIn(subject="Delay in resolution", channel="PHONE"), conn=db)
    listed = list_open_grievances(investor_id=None, conn=db, current_user=STAFF)
    assert len(listed) == 1
    assert isinstance(listed[0]["id"], str)
    assert listed[0]["investor_id"] is None


def test_acknowledging_marks_it_seen_without_stopping_the_clock(db) -> None:
    filed = file_grievance(GrievanceIn(subject="Slow response", channel="EMAIL"), conn=db)
    result = acknowledge_grievance(filed["id"], conn=db, current_user=STAFF)
    assert result == {"status": "acknowledged"}

    (listed,) = list_open_grievances(investor_id=None, conn=db, current_user=STAFF)
    assert listed["status"] == "ACKNOWLEDGED"
    assert listed["due_at"] == filed["due_at"], "acknowledging must not move the deadline"


def test_acknowledging_an_unknown_grievance_is_not_found(db) -> None:
    with pytest.raises(GrievanceNotFoundError):
        acknowledge_grievance(NIL_UUID, conn=db, current_user=STAFF)


def test_resolving_closes_it_and_reports_compliance(db) -> None:
    filed = file_grievance(GrievanceIn(subject="Overcharged fee", channel="EMAIL"), conn=db)
    result = resolve_grievance(
        filed["id"],
        ResolveIn(resolution="Refunded; client confirmed."),
        conn=db,
        current_user=STAFF,
    )
    assert result["within_ceiling"] is True
    assert list_open_grievances(investor_id=None, conn=db, current_user=STAFF) == []


def test_resolving_with_a_blank_resolution_is_a_400_not_a_500(db) -> None:
    """app.db.grievance.resolve raises a bare ValueError for this case -- the router
    must translate it to 400 itself, since main.py has nothing to key a global handler
    on for a plain ValueError."""
    filed = file_grievance(GrievanceIn(subject="Data mismatch", channel="EMAIL"), conn=db)
    with pytest.raises(HTTPException) as exc_info:
        resolve_grievance(filed["id"], ResolveIn(resolution="   "), conn=db, current_user=STAFF)
    assert exc_info.value.status_code == 400


def test_resolving_an_already_resolved_grievance_is_not_swallowed_as_a_400(db) -> None:
    """AlreadyResolvedError is also a ValueError subclass -- the router's blank-
    resolution except clause must not catch it ahead of app.main's 409 handler."""
    filed = file_grievance(GrievanceIn(subject="Wrong ISIN", channel="EMAIL"), conn=db)
    resolve_grievance(filed["id"], ResolveIn(resolution="Fixed."), conn=db, current_user=STAFF)

    with pytest.raises(AlreadyResolvedError):
        resolve_grievance(
            filed["id"], ResolveIn(resolution="Fixed again."), conn=db, current_user=STAFF
        )


def test_resolving_an_unknown_grievance_is_not_found(db) -> None:
    with pytest.raises(GrievanceNotFoundError):
        resolve_grievance(NIL_UUID, ResolveIn(resolution="n/a"), conn=db, current_user=STAFF)


def test_escalating_does_not_move_the_deadline(db) -> None:
    filed = file_grievance(GrievanceIn(subject="Depository delay", channel="EMAIL"), conn=db)
    result = escalate_grievance(
        filed["id"],
        EscalateIn(reason="needs the depository to respond"),
        conn=db,
        current_user=STAFF,
    )
    assert result == {"status": "escalated"}

    (listed,) = list_open_grievances(investor_id=None, conn=db, current_user=STAFF)
    assert listed["status"] == "ESCALATED"
    assert listed["due_at"] == filed["due_at"]


def test_due_soon_and_overdue_are_empty_for_a_fresh_complaint(db) -> None:
    file_grievance(GrievanceIn(subject="Just filed", channel="EMAIL"), conn=db)
    assert (
        list_due_soon(horizon_days=grievance.WARNING_HORIZON_DAYS, conn=db, current_user=STAFF)
        == []
    )
    assert list_overdue(conn=db, current_user=STAFF) == []


def test_due_soon_warns_before_the_ceiling_is_breached(db) -> None:
    filed = file_grievance(GrievanceIn(subject="Ageing complaint", channel="EMAIL"), conn=db)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE grievance SET raised_at = now() - interval '75 days' WHERE id = %s",
            (filed["id"],),
        )
    warned = list_due_soon(horizon_days=grievance.WARNING_HORIZON_DAYS, conn=db, current_user=STAFF)
    assert [g["id"] for g in warned] == [filed["id"]]
    assert list_overdue(conn=db, current_user=STAFF) == []


def test_overdue_reports_a_breach_with_a_negative_time_left(db) -> None:
    filed = file_grievance(GrievanceIn(subject="Missed the ceiling", channel="EMAIL"), conn=db)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE grievance SET raised_at = now() - interval '100 days' WHERE id = %s",
            (filed["id"],),
        )
    (breached,) = list_overdue(conn=db, current_user=STAFF)
    assert breached["id"] == filed["id"]
    assert breached["time_left"].total_seconds() < 0
