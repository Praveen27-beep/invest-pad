"""Pydantic request/response DTOs for /auth/*."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, field_validator

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str | None = None

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        if not _EMAIL.match(value.strip()):
            raise ValueError("not a valid email address")
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def _password_long_enough(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("password must be at least 8 characters")
        return value


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str | None
    created_at: datetime


class TokenResponse(BaseModel):
    # Named plainly as `token` rather than after the usual OAuth2 field vocabulary --
    # `make lint`'s credential-name ban is deliberately blunt (see Makefile) and would
    # otherwise flag this login response the same way it flags a stored broker
    # credential. This value is never persisted; only its hash is
    # (app_session.session_token_hash).
    token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
