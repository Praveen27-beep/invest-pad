"""Captures: quick notes and questions from the browser extension, and the inbox.

Two kinds of caller use this file:
  the extension, signed in with a token (the /ext/* routes) — it can add a capture and
  list company names, nothing else;
  the web app, signed in with a session — it creates tokens and works the inbox.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.errors import ForeignKeyViolation
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import auth, db
from .notes import _write_version, body_of

router = APIRouter()
TOKEN_PREFIX = "ipx_"  # noqa: S105 - a public prefix, so a leaked token is recognisable


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------- tokens (web app)

class TokenIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    can_ask: bool = False     # may this browser also ask questions and read the answers?


@router.post("/tokens", status_code=201)
def create_token(body: TokenIn, user: dict = Depends(auth.current_user)):
    """The token is returned once, here, and never again."""
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT token_create(%s, %s, %s) AS id", (_hash(token), body.label.strip(), body.can_ask))
        token_id = cur.fetchone()["id"]
        cur.execute("INSERT INTO audit_log (action, object) VALUES ('token.create', %s)", (str(token_id),))
    return {"id": token_id, "label": body.label.strip(), "can_ask": body.can_ask, "token": token}


@router.get("/tokens")
def list_tokens(user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT * FROM token_list()")
        return cur.fetchall()


@router.delete("/tokens/{token_id}", status_code=204)
def revoke_token(token_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT token_revoke(%s) AS ok", (token_id,))
        if not cur.fetchone()["ok"]:
            raise HTTPException(404, "Not found")
        cur.execute("INSERT INTO audit_log (action, object) VALUES ('token.revoke', %s)", (str(token_id),))


# ---------------------------------------------------------------- the extension

def token_user(request: Request) -> str:
    """FastAPI dependency for /ext/*: the owner of the bearer token, or 401.

    Cookies are ignored on purpose. These routes accept the token and nothing else.
    """
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    owner = None
    if token.startswith(TOKEN_PREFIX):
        with db.anonymous() as cur:
            cur.execute("SELECT token_owner(%s) AS owner", (_hash(token),))
            owner = cur.fetchone()["owner"]
    if not owner:
        raise HTTPException(401, "Token not recognised")
    request.state.user_id = str(owner)
    return owner


class CaptureIn(BaseModel):
    client_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
    kind: Literal["note", "question"]
    body: str = Field(min_length=1, max_length=20_000)
    selection: str = Field(default="", max_length=20_000)
    url: str = Field(default="", max_length=2_000)
    page_title: str = Field(default="", max_length=500)
    captured_at: datetime | None = None
    subject_id: uuid.UUID | None = None


@router.get("/ext/subjects")
def ext_subjects(owner: str = Depends(token_user)):
    with db.as_user(owner) as cur:
        cur.execute("SELECT id, name FROM subject ORDER BY name")
        return cur.fetchall()


@router.post("/ext/captures", status_code=201)
def ext_capture(body: CaptureIn, owner: str = Depends(token_user)):
    """Add a capture. Sending the same client_id again is a no-op, so the extension can
    safely retry anything it is not sure arrived."""
    if not body.body.strip():
        raise HTTPException(422, "Nothing to save")
    captured_at = body.captured_at or datetime.now(UTC)
    try:
        with db.as_user(owner) as cur:
            cur.execute(
                "INSERT INTO capture (client_id, kind, body, selection, url, page_title, captured_at, subject_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (owner_id, client_id) DO NOTHING RETURNING id",
                (body.client_id, body.kind, body.body.strip(), body.selection, body.url, body.page_title,
                 captured_at, body.subject_id))
            row = cur.fetchone()
            return {"saved": row is not None}
    except ForeignKeyViolation:
        raise HTTPException(404, "Company not found") from None


# ---------------------------------------------------------------- the inbox (web app)

COLUMNS = "id, kind, body, selection, url, page_title, captured_at, status, subject_id, note_id"


class CaptureUpdate(BaseModel):
    subject_id: uuid.UUID | None = None
    status: Literal["inbox", "dismissed"] | None = None


@router.get("/captures")
def list_captures(status: Literal["inbox", "filed", "dismissed"] = "inbox", user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute(f"SELECT {COLUMNS} FROM capture WHERE status = %s ORDER BY captured_at DESC LIMIT 200", (status,))
        return cur.fetchall()


@router.patch("/captures/{capture_id}")
def update_capture(capture_id: uuid.UUID, body: CaptureUpdate, user: dict = Depends(auth.current_user)):
    """Set or clear the company, or dismiss / restore."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(422, "Nothing to change")
    assignments = ", ".join(f"{name} = %s" for name in fields)  # names come from the model, not the request
    try:
        with db.as_user(user["id"]) as cur:
            cur.execute(f"UPDATE capture SET {assignments} WHERE id = %s RETURNING {COLUMNS}",
                        (*fields.values(), capture_id))
            row = cur.fetchone()
    except ForeignKeyViolation:
        raise HTTPException(404, "Company not found") from None
    if not row:
        raise HTTPException(404, "Not found")
    return row


@router.post("/captures/{capture_id}/note", status_code=201)
def capture_to_note(capture_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    """Turn a capture into a note, keeping what was selected and where it came from."""
    with db.as_user(user["id"]) as cur:
        cur.execute(f"SELECT {COLUMNS} FROM capture WHERE id = %s FOR UPDATE", (capture_id,))
        cap = cur.fetchone()
        if not cap:
            raise HTTPException(404, "Not found")
        if cap["note_id"]:
            return {"note_id": cap["note_id"]}

        first_line = cap["body"].strip().splitlines()[0][:80].strip() or "Capture"
        title, n = first_line, 1
        while True:  # titles are unique per user; add (2), (3)… if needed
            cur.execute("SELECT 1 FROM note WHERE title_key = %s", (title.lower(),))
            if not cur.fetchone():
                break
            n += 1
            title = f"{first_line} ({n})"

        def para(text: str, kind: str = "paragraph") -> dict:
            return {"id": uuid.uuid4().hex, "type": kind, "content": [{"type": "text", "text": text, "styles": {}}],
                    "children": []}

        blocks = [para(line) for line in cap["body"].splitlines() if line.strip()]
        if cap["selection"]:
            blocks.append(para(cap["selection"], "quote"))
        if cap["url"]:
            source = f"Source: {cap['page_title'] or cap['url']} — {cap['url']}"
            blocks.append(para(f"{source} (captured {cap['captured_at']:%d %b %Y})"))

        cur.execute("INSERT INTO note (subject_id, title, blocks, body) VALUES (%s, %s, %s, %s) RETURNING id",
                    (cap["subject_id"], title, Jsonb(blocks), body_of(blocks)))
        note_id = cur.fetchone()["id"]
        _write_version(cur, note_id, 1, title, blocks, reason="created from a capture")
        cur.execute("UPDATE capture SET status = 'filed', note_id = %s WHERE id = %s", (note_id, capture_id))
        return {"note_id": note_id}


@router.delete("/captures/{capture_id}", status_code=204)
def delete_capture(capture_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute("DELETE FROM capture WHERE id = %s RETURNING id", (capture_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Not found")
