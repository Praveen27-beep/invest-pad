"""The Invest-pad API."""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import auth, capture, config, db, documents, notes, thesis

log = logging.getLogger("investpad")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    app.state.config = config.load()
    db.open_pool(app.state.config.database_url)
    yield
    db.close_pool()


app = FastAPI(title="Invest-pad", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(notes.router)
app.include_router(capture.router)
app.include_router(documents.router)
app.include_router(thesis.router)


@app.middleware("http")
async def guard_and_log(request: Request, call_next):
    """Two jobs: refuse cross-site writes, and write one log line per request.

    The log line carries who, what and how long. It never carries a body, a query
    string, a header or a cookie, so a password or key cannot end up in it.
    """
    started = time.perf_counter()
    request_id = uuid.uuid4().hex[:12]

    # Cross-site request forgery rides on the browser's cookie, so the check applies to
    # requests that carry one. The extension sends a token and no cookie.
    origin = request.headers.get("origin")
    if (request.method not in ("GET", "HEAD", "OPTIONS") and auth.COOKIE in request.cookies
            and origin and origin not in request.app.state.config.allowed_origins):
        response = JSONResponse({"detail": "Cross-site request refused"}, status_code=403)
    else:
        try:
            response = await call_next(request)
        except Exception as exc:
            # Log the type only: an exception message can quote user input.
            log.error("request_id=%s unhandled %s", request_id, type(exc).__name__)
            response = JSONResponse({"detail": "Internal error"}, status_code=500)

    log.info(
        "request_id=%s user=%s %s %s status=%s ms=%d",
        request_id, getattr(request.state, "user_id", "-"),
        request.method, request.url.path, response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    response.headers["X-Request-Id"] = request_id
    return response


@app.get("/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- subjects (companies)

class SubjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    identifiers: dict[str, str] = Field(default_factory=dict)


SUBJECT_COLUMNS = "id, name, identifiers, pack, created_at"


@app.get("/subjects")
def list_subjects(user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute(f"SELECT {SUBJECT_COLUMNS} FROM subject ORDER BY name")
        return cur.fetchall()


@app.post("/subjects", status_code=201)
def create_subject(body: SubjectIn, user: dict = Depends(auth.current_user)):
    try:
        with db.as_user(user["id"]) as cur:
            cur.execute(
                f"INSERT INTO subject (name, identifiers) VALUES (%s, %s) RETURNING {SUBJECT_COLUMNS}",
                (body.name.strip(), Jsonb(body.identifiers)),
            )
            row = cur.fetchone()
            cur.execute("INSERT INTO audit_log (action, object) VALUES ('subject.create', %s)",
                        (str(row["id"]),))
            return row
    except UniqueViolation:
        raise HTTPException(409, "You already have a company with that name") from None


@app.get("/subjects/{subject_id}")
def get_subject(subject_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute(f"SELECT {SUBJECT_COLUMNS} FROM subject WHERE id = %s", (subject_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return row


@app.delete("/subjects/{subject_id}", status_code=204)
def delete_subject(subject_id: uuid.UUID, request: Request, user: dict = Depends(auth.current_user)):
    """Deletes the company and everything filed under it, including uploaded files."""
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT id FROM document WHERE subject_id = %s", (subject_id,))
        document_ids = [row["id"] for row in cur.fetchall()]
        cur.execute("DELETE FROM subject WHERE id = %s RETURNING id", (subject_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Not found")
        cur.execute("INSERT INTO audit_log (action, object) VALUES ('subject.delete', %s)",
                    (str(subject_id),))
    documents.remove_files(request, user["id"], document_ids)
