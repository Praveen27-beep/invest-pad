"""FastAPI wiring for JWT auth. Kept separate from ``service.py`` so that module stays
framework-free -- the same separation ``app/database.py`` keeps from ``app/db/connection.py``.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import service
from app.auth.service import InvalidTokenError
from app.config import Settings, get_settings
from app.database import get_conn
from app.db.repository import get_investor_owner, investor_exists

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    conn: Any = Depends(get_conn),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Require a valid bearer token. Raises 401 if it is missing, malformed, expired, or
    its session has been revoked -- one status for all four, per ``InvalidTokenError``'s
    docstring: telling a caller which check failed is a free oracle."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        return service.current_user(conn, settings, credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


def _authorise(conn: Any, current_user: dict[str, Any], investor_id: str | None) -> None:
    """The one ownership decision every scoped endpoint shares. 404 for an unknown
    investor (it reveals nothing), 403 when the row exists but belongs to someone else
    or to nobody yet -- never 404 for the not-yours case, which would let a caller
    probe which investor ids exist."""
    if investor_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such investor")
    if not investor_exists(conn, investor_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no such investor: {investor_id}")
    owner = get_investor_owner(conn, investor_id)
    if owner != str(current_user["id"]):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "this investor belongs to another account"
            if owner
            else "this investor is unclaimed; run app.db.assign_owner to claim it",
        )


def assert_owned_investor(
    conn: Any, current_user: dict[str, Any], investor_id: str
) -> None:
    """Programmatic twin of ``require_owned_investor`` -- for handlers whose scope
    arrives outside the request path, e.g. POST /ingest/csv's ``investor_id`` form
    field."""
    _authorise(conn, current_user, investor_id)


def require_owned_investor(
    investor_id: str,
    conn: Any = Depends(get_conn),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> None:
    """Route-level guard: the authenticated user must own ``{investor_id}``. Resolves
    ``investor_id`` from the path -- or the query string, for endpoints like
    /privacy/export that scope by query parameter instead."""
    _authorise(conn, current_user, investor_id)


def require_owned_batch(
    batch_id: str,
    conn: Any = Depends(get_conn),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> None:
    """Route-level guard for /ingest/stage/{batch_id}/*: authorises against the batch's
    investor, not the batch itself -- a batch id guessed right but owned by someone else
    must read exactly like one that does not exist."""
    with conn.cursor() as cur:
        cur.execute("SELECT investor_id FROM import_batch WHERE id = %s", (batch_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(batch_id))
    _authorise(conn, current_user, str(row[0]))
