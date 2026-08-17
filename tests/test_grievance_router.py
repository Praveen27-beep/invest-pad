"""app.routers.grievance -- request validation, response shaping, and the auth-wiring
decision itself, none of which need a database.

``app.schemas.grievance`` is the exact boundary FastAPI validates these request bodies
against, the same split ``tests/test_transactions_router.py`` and
``tests/test_reconcile_router.py`` use for their sibling endpoints.
``app.routers.grievance._out_row``/``_summary_row`` are the exact boundary the response
is shaped through, tested directly against a synthetic row shaped like what psycopg
actually returns (a ``uuid.UUID`` object, not a string) -- the same thing
``tests/test_db_investors.py`` proves against a real cluster, pinned here without one.

This codebase has no dependency on ``httpx``/``fastapi.testclient`` (not in
trackr-backend/pyproject.toml, not installed) -- which is why every other "router
test" in this suite (test_investors_router.py, test_reconcile_router.py,
test_transactions_router.py) is a schema/pure-function test rather than a live HTTP
round trip; this file follows the same constraint. The auth decision for this router
-- POST /grievances is
unauthenticated, everything else requires a bearer token -- is exactly the kind of
thing that regresses silently if someone later "helpfully" makes this router look more
like app.routers.privacy. Since there's no TestClient to send a token-less request and
check for a 401, the tests below instead pin it at the level that is actually testable
here: each handler's own declared dependencies.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.auth.dependencies import get_current_user
from app.routers import grievance as grievance_router
from app.schemas.grievance import EscalateIn, GrievanceIn, ResolveIn
from fastapi.params import Depends
from pydantic import ValidationError

# --- request validation ----------------------------------------------------------------


def test_grievance_in_requires_subject_and_channel() -> None:
    with pytest.raises(ValidationError):
        GrievanceIn()


def test_grievance_in_investor_id_and_detail_default_to_none() -> None:
    body = GrievanceIn(subject="Wrong quantity shown", channel="EMAIL")
    assert body.investor_id is None
    assert body.detail is None


def test_grievance_in_accepts_a_complaint_with_no_investor_id() -> None:
    """docs/COMPLIANCE.md: intake accepts complaints from people not yet matched to an
    investor record -- the request body must not require one."""
    body = GrievanceIn(subject="Statement looks wrong", channel="PHONE")
    assert body.investor_id is None


def test_resolve_in_requires_resolution() -> None:
    with pytest.raises(ValidationError):
        ResolveIn()


def test_escalate_in_requires_reason() -> None:
    with pytest.raises(ValidationError):
        EscalateIn()


# --- response shaping --------------------------------------------------------------


def _synthetic_row(**overrides: object) -> dict[str, object]:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    row: dict[str, object] = {
        "id": uuid.uuid4(),
        "reference": "GRV-2026-ABCDEF",
        "investor_id": uuid.uuid4(),
        "subject": "Wrong quantity shown",
        "channel": "EMAIL",
        "status": "OPEN",
        "raised_at": now,
        "due_at": now + timedelta(days=90),
        "time_left": timedelta(days=90),
    }
    row.update(overrides)
    return row


def test_out_row_stringifies_the_uuid_id() -> None:
    """psycopg hands app.db.grievance a real uuid.UUID for a uuid column, uncast --
    the router, not the db module, owns the HTTP wire format."""
    row = _synthetic_row()
    out = grievance_router._out_row(row)
    assert out["id"] == str(row["id"])
    assert isinstance(out["id"], str)


def test_summary_row_stringifies_investor_id_when_present() -> None:
    row = _synthetic_row()
    summary = grievance_router._summary_row(row)
    assert summary["investor_id"] == str(row["investor_id"])
    assert isinstance(summary["investor_id"], str)


def test_summary_row_keeps_investor_id_none_for_an_unmatched_complainant() -> None:
    row = _synthetic_row(investor_id=None)
    summary = grievance_router._summary_row(row)
    assert summary["investor_id"] is None


def test_summary_row_carries_time_left_through_unchanged() -> None:
    row = _synthetic_row(time_left=timedelta(days=-3))
    summary = grievance_router._summary_row(row)
    assert summary["time_left"] == timedelta(days=-3)


# --- the auth decision itself -----------------------------------------------------


def _depends_on(fn: object, dependency: object) -> bool:
    for param in inspect.signature(fn).parameters.values():
        if isinstance(param.default, Depends) and param.default.dependency is dependency:
            return True
    return False


def test_filing_a_grievance_has_no_auth_dependency() -> None:
    """The one deliberate exception: docs/COMPLIANCE.md requires intake to accept
    complaints from people not yet matched to an investor record, and app_user
    (008_auth.sql) is an adviser login a complainant never holds. If this test starts
    failing, someone has copied app.routers.privacy's pattern onto intake by reflex."""
    assert not _depends_on(grievance_router.file_grievance, get_current_user)


@pytest.mark.parametrize(
    "handler",
    [
        grievance_router.list_open_grievances,
        grievance_router.list_due_soon,
        grievance_router.list_overdue,
        grievance_router.acknowledge_grievance,
        grievance_router.resolve_grievance,
        grievance_router.escalate_grievance,
    ],
)
def test_every_staff_action_requires_auth(handler: object) -> None:
    """Listing, acknowledging, resolving, escalating are all staff work on a complaint
    already in the system -- unlike intake, none of these should be reachable by
    someone who has never had a relationship with the practice."""
    assert _depends_on(handler, get_current_user)
