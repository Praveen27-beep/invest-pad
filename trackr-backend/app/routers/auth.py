"""POST /auth/register, POST /auth/login, GET /auth/me."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.auth import service
from app.auth.dependencies import get_current_user
from app.auth.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.config import Settings, get_settings
from app.database import get_conn

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(
    body: RegisterRequest,
    conn: Any = Depends(get_conn),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    user = service.register(conn, body.email, body.password, body.display_name)
    token, expires_in = service.issue_token(settings, conn, user["id"])
    return TokenResponse(token=token, expires_in=expires_in, user=UserResponse(**user))


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    conn: Any = Depends(get_conn),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    token, expires_in, user = service.login(conn, settings, body.email, body.password)
    return TokenResponse(token=token, expires_in=expires_in, user=UserResponse(**user))


@router.get("/me", response_model=UserResponse)
def me(current: dict[str, Any] = Depends(get_current_user)) -> UserResponse:
    return UserResponse(**current)
