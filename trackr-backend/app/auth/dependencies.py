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
