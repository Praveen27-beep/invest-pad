"""POST /auth/register, POST /auth/login, POST /auth/refresh, GET /auth/me.

Register provisions a personal investor in the same transaction it creates the user:
a new login must never land on the frontend's old fallback of "whatever investor id is
in localStorage". Login echoes back the caller's oldest owned investor, so every client
takes its investor identity from the token response, not from anywhere shared.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import service
from app.auth.dependencies import get_current_user
from app.auth.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.config import Settings, get_settings
from app.database import get_conn
from app.db.repository import create_personal_investor, first_investor_id_for_user
from app.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])

#: Same posture as dependencies.get_current_user's bearer -- but refresh cannot go
#: through ``get_current_user`` itself: its whole job is to accept a token whose exp has
#: passed, which current_user must keep refusing.
_bearer = HTTPBearer(auto_error=False)


@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("5/minute")
def register(
    request: Request,
    body: RegisterRequest,
    conn: Any = Depends(get_conn),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    user = service.register(conn, body.email, body.password, body.display_name)
    investor = create_personal_investor(
        conn, owner_user_id=user["id"], display_name=body.display_name
    )
    token, expires_in = service.issue_token(settings, conn, user["id"])
    return TokenResponse(
        token=token,
        expires_in=expires_in,
        user=UserResponse(**user),
        investor_id=investor["id"],
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(
    request: Request,
    body: LoginRequest,
    conn: Any = Depends(get_conn),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    token, expires_in, user = service.login(conn, settings, body.email, body.password)
    return TokenResponse(
        token=token,
        expires_in=expires_in,
        user=UserResponse(**user),
        investor_id=first_investor_id_for_user(conn, str(user["id"])),
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
def refresh(
    request: Request,
    conn: Any = Depends(get_conn),
    settings: Settings = Depends(get_settings),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> TokenResponse:
    """A fresh token for a token the session table still recognises. The response is a
    full ``TokenResponse`` -- same shape as login -- so clients apply it through the
    exact path they already have, investor_id included."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        token, expires_in, user = service.refresh(conn, settings, credentials.credentials)
    except service.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return TokenResponse(
        token=token,
        expires_in=expires_in,
        user=UserResponse(**user),
        investor_id=first_investor_id_for_user(conn, str(user["id"])),
    )


@router.get("/me", response_model=UserResponse)
def me(current: dict[str, Any] = Depends(get_current_user)) -> UserResponse:
    return UserResponse(**current)
