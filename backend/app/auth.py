"""Sign-up, login, logout and the current-user dependency.

Sessions are server-side: the cookie holds a random token, the database holds its
SHA-256. Passwords are hashed with argon2.
"""

import hashlib
import secrets
import time
from collections import defaultdict
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import db, ratelimit

COOKIE = "investpad_session"
router = APIRouter(prefix="/auth")
_hasher = PasswordHasher()
# Hash checked when the email is unknown, so both paths take similar time.
_DUMMY_HASH = _hasher.hash("not-a-real-password")

# Login attempts per email in the last 15 minutes. In-memory is enough for one process.
_attempts: dict[str, list[float]] = defaultdict(list)
MAX_ATTEMPTS, WINDOW = 10, 900


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=10, max_length=200)


class Signup(Credentials):
    invite: str = Field(min_length=1, max_length=100)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _start_session(request: Request, response: Response, user_id) -> None:
    cfg = request.app.state.config
    token = secrets.token_urlsafe(32)
    with db.anonymous() as cur:
        cur.execute(
            "SELECT auth_session_create(%s, %s, %s)",
            (_token_hash(token), user_id, timedelta(days=cfg.session_days)),
        )
    response.set_cookie(
        COOKIE, token, max_age=cfg.session_days * 86400,
        httponly=True, samesite="lax", secure=cfg.cookie_secure, path="/",
    )


def current_user(request: Request) -> dict:
    """FastAPI dependency: the signed-in user, or 401."""
    token = request.cookies.get(COOKIE)
    user = None
    if token:
        with db.anonymous() as cur:
            cur.execute("SELECT * FROM auth_session_user(%s)", (_token_hash(token),))
            user = cur.fetchone()
    if not user:
        raise HTTPException(401, "Not signed in")
    request.state.user_id = str(user["id"])  # for the request log
    return user


@router.post("/signup", status_code=201)
def signup(body: Signup, request: Request, response: Response):
    ratelimit.check("signup", request.client.host if request.client else "unknown")
    with db.anonymous() as cur:
        cur.execute(
            "SELECT auth_signup(%s, %s, %s) AS id",
            (body.email, _hasher.hash(body.password), body.invite),
        )
        user_id = cur.fetchone()["id"]
    if not user_id:
        # One message for a bad invite and a taken email: do not reveal which emails exist.
        raise HTTPException(400, "Sign-up failed. Check the invite code and email.")
    _start_session(request, response, user_id)
    return {"id": str(user_id), "email": body.email.lower()}


@router.post("/login")
def login(body: Credentials, request: Request, response: Response):
    email = body.email.lower()
    now = time.monotonic()
    recent = [t for t in _attempts[email] if now - t < WINDOW]
    if len(recent) >= MAX_ATTEMPTS:
        raise HTTPException(429, "Too many attempts. Try again later.")
    _attempts[email] = recent + [now]

    with db.anonymous() as cur:
        cur.execute("SELECT * FROM auth_lookup(%s)", (email,))
        row = cur.fetchone()
    try:
        _hasher.verify(row["password_hash"] if row else _DUMMY_HASH, body.password)
        ok = row is not None
    except VerifyMismatchError:
        ok = False
    if not ok:
        raise HTTPException(401, "Wrong email or password")
    _attempts.pop(email, None)
    _start_session(request, response, row["id"])
    return {"id": str(row["id"]), "email": email}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        with db.anonymous() as cur:
            cur.execute("SELECT auth_session_delete(%s)", (_token_hash(token),))
    response.delete_cookie(COOKIE, path="/")


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return {"id": str(user["id"]), "email": user["email"]}
