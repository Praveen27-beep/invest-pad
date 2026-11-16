"""Documents: upload, extraction, passages, retrieval and deletion."""

import hashlib
import logging
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from pydantic import BaseModel, Field

from . import auth, db, extract

router = APIRouter()
log = logging.getLogger("investpad")

COLUMNS = ("id, subject_id, title, filename, format, doc_type, period, doc_date, sha256, size_bytes, "
           "status, status_note, pages, created_at")
MEDIA = {"pdf": "application/pdf",
         "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _path(request: Request, owner_id, document_id) -> Path:
    """Where a document's original file lives. Both parts are UUIDs, never user text."""
    return Path(request.app.state.config.files_dir) / str(uuid.UUID(str(owner_id))) / str(uuid.UUID(str(document_id)))


# ---------------------------------------------------------------- upload and processing

@router.post("/documents", status_code=201)
def upload(
    request: Request, background: BackgroundTasks,
    file: UploadFile = File(...), subject_id: uuid.UUID = Form(...),
    title: str = Form("", max_length=300), doc_type: str = Form("", max_length=60),
    period: str = Form("", max_length=30), doc_date: date | None = Form(None),
    user: dict = Depends(auth.current_user),
):
    cfg = request.app.state.config
    data = file.file.read(cfg.max_upload_bytes + 1)
    if len(data) > cfg.max_upload_bytes:
        raise HTTPException(413, f"File is larger than {cfg.max_upload_bytes // 1_000_000} MB")
    fmt = extract.sniff(data)
    if not fmt:
        raise HTTPException(415, "Only PDF, Excel (.xlsx) and Word (.docx) files can be uploaded")

    filename = Path(file.filename or "document").name[:200]
    guess = extract.guess_metadata(filename)
    try:
        with db.as_user(user["id"]) as cur:
            cur.execute(
                f"INSERT INTO document (subject_id, title, filename, format, doc_type, period, doc_date, sha256, "
                f"size_bytes) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING {COLUMNS}",
                (subject_id, title.strip() or filename.rsplit(".", 1)[0], filename, fmt,
                 doc_type.strip() or guess["doc_type"], period.strip() or guess["period"], doc_date,
                 hashlib.sha256(data).hexdigest(), len(data)))
            doc = cur.fetchone()
            cur.execute("INSERT INTO audit_log (action, object) VALUES ('document.upload', %s)", (str(doc["id"]),))
    except ForeignKeyViolation:
        raise HTTPException(404, "Company not found") from None
    except UniqueViolation:
        raise HTTPException(409, "This file is already uploaded for this company") from None

    path = _path(request, user["id"], doc["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    # Extraction can take a while for a long report, so it runs after the response is sent.
    background.add_task(process, user["id"], doc["id"], fmt, path)
    return doc


def process(owner_id, document_id, fmt: str, path: Path) -> None:
    """Extract text and store passages. Safe to run again: it replaces earlier passages."""
    try:
        pages = extract.extract(path.read_bytes(), fmt)
        status, note = "ready", ""
        total = sum(len(text) for _, _, text in pages)
        if total < extract.MIN_TEXT_PER_PDF:
            status = "no_text"
            note = ("No readable text was found. If this is a scanned document, it needs text recognition, "
                    "which Invest-pad does not do yet.")
    except extract.Unreadable as exc:
        pages, status, note = [], "failed", str(exc)
    except Exception as exc:  # noqa: BLE001
        log.error("document %s failed: %s", document_id, type(exc).__name__)
        pages, status, note = [], "failed", "Something went wrong while reading this file."

    with db.as_user(owner_id) as cur:
        cur.execute("SELECT 1 FROM document WHERE id = %s FOR UPDATE", (document_id,))
        if not cur.fetchone():
            return  # deleted while we were reading it
        cur.execute("DELETE FROM chunk WHERE document_id = %s", (document_id,))
        ordinal = 0
        for number, label, text in pages:
            for body in extract.passages(text):
                ordinal += 1
                cur.execute("INSERT INTO chunk (document_id, ordinal, page, label, body) VALUES (%s, %s, %s, %s, %s)",
                            (document_id, ordinal, number, label, body))
        cur.execute("UPDATE document SET status = %s, status_note = %s, pages = %s WHERE id = %s",
                    (status, note, len(pages), document_id))


# ---------------------------------------------------------------- reading

@router.get("/documents")
def list_documents(subject_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute(f"SELECT {COLUMNS} FROM document WHERE subject_id = %s ORDER BY doc_date DESC NULLS LAST, "
                    "created_at DESC", (subject_id,))
        return cur.fetchall()


def _document(cur, document_id):
    cur.execute(f"SELECT {COLUMNS} FROM document WHERE id = %s", (document_id,))
    doc = cur.fetchone()
    if not doc:
        raise HTTPException(404, "Not found")
    return doc


@router.get("/documents/{document_id}")
def get_document(document_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        doc = _document(cur, document_id)
        cur.execute("SELECT count(*) AS passages FROM chunk WHERE document_id = %s", (document_id,))
        return doc | cur.fetchone()


@router.get("/documents/{document_id}/passages")
def get_passages(document_id: uuid.UUID, page: int | None = None, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        _document(cur, document_id)
        cur.execute("SELECT id, ordinal, page, label, body FROM chunk WHERE document_id = %s "
                    "AND (%s::int IS NULL OR page = %s) ORDER BY ordinal LIMIT 400", (document_id, page, page))
        return cur.fetchall()


@router.get("/documents/{document_id}/file")
def download(document_id: uuid.UUID, request: Request, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        doc = _document(cur, document_id)
    path = _path(request, user["id"], document_id)
    if not path.exists():
        raise HTTPException(404, "The original file is missing")
    return FileResponse(path, media_type=MEDIA[doc["format"]], filename=doc["filename"],
                        headers={"X-Content-Type-Options": "nosniff"})


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    doc_type: str | None = Field(default=None, max_length=60)
    period: str | None = Field(default=None, max_length=30)
    doc_date: date | None = None


@router.patch("/documents/{document_id}")
def update_document(document_id: uuid.UUID, body: DocumentUpdate, user: dict = Depends(auth.current_user)):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(422, "Nothing to change")
    assignments = ", ".join(f"{name} = %s" for name in fields)  # names come from the model, not the request
    with db.as_user(user["id"]) as cur:
        cur.execute(f"UPDATE document SET {assignments} WHERE id = %s RETURNING {COLUMNS}",
                    (*fields.values(), document_id))
        doc = cur.fetchone()
    if not doc:
        raise HTTPException(404, "Not found")
    return doc


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: uuid.UUID, request: Request, user: dict = Depends(auth.current_user)):
    """Remove the document, every passage cut from it, and the original file."""
    with db.as_user(user["id"]) as cur:
        cur.execute("DELETE FROM document WHERE id = %s RETURNING id", (document_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Not found")
        cur.execute("INSERT INTO audit_log (action, object) VALUES ('document.delete', %s)", (str(document_id),))
    _path(request, user["id"], document_id).unlink(missing_ok=True)


def remove_files(request: Request, owner_id, document_ids) -> None:
    """Delete original files for documents that were removed by a cascade (e.g. their company)."""
    for document_id in document_ids:
        _path(request, owner_id, document_id).unlink(missing_ok=True)


# ---------------------------------------------------------------- retrieval

@router.get("/retrieve")
def retrieve(q: str, subject_id: uuid.UUID | None = None, period: str | None = None,
             doc_type: str | None = None, limit: int = 8, user: dict = Depends(auth.current_user)):
    """Find the passages most relevant to a question, from documents and from notes.

    The company, period and type filters are applied before ranking, inside the query, so
    a passage from the wrong company or year can never outrank the right one.
    """
    return find_passages(user["id"], q, subject_id, period, doc_type, limit)


def find_passages(owner_id, q: str, subject_id=None, period=None, doc_type=None, limit: int = 8) -> dict:
    q = q.strip()
    limit = max(1, min(limit, 30))
    if not q:
        return {"passages": [], "notes": []}
    headline = "ts_headline('english', {col}, query, 'MaxWords=40, MinWords=15, StartSel=<<, StopSel=>>')"
    with db.as_user(owner_id) as cur:
        # A question is many words; requiring all of them (AND) would miss most passages.
        # Rank on any of them (OR) and let the ranking put the best matches first.
        cur.execute("SELECT replace(websearch_to_tsquery('english', %s)::text, '&', '|') AS tsq", (q,))
        tsq = cur.fetchone()["tsq"]
        if not tsq:
            return {"passages": [], "notes": []}
        cur.execute(
            f"SELECT c.id, c.document_id, c.page, c.label, c.body, d.title, d.doc_type, d.period, d.doc_date, "
            f"  d.subject_id, ts_rank_cd(c.tsv, query) AS score, {headline.format(col='c.body')} AS snippet "
            "FROM chunk c JOIN document d ON d.id = c.document_id, to_tsquery('english', %s) AS query "
            "WHERE c.tsv @@ query AND (%s::uuid IS NULL OR d.subject_id = %s) "
            "  AND (%s::text IS NULL OR d.period = %s) AND (%s::text IS NULL OR d.doc_type = %s) "
            "ORDER BY score DESC, d.doc_date DESC NULLS LAST, c.ordinal LIMIT %s",
            (tsq, subject_id, subject_id, period, period, doc_type, doc_type, limit))
        found = cur.fetchall()
        cur.execute(
            f"SELECT n.id, n.title, n.subject_id, n.seq, n.updated_at, ts_rank_cd(n.tsv, query) AS score, "
            f"  {headline.format(col='n.body')} AS snippet "
            "FROM note n, to_tsquery('english', %s) AS query "
            "WHERE n.tsv @@ query AND (%s::uuid IS NULL OR n.subject_id = %s) "
            "ORDER BY score DESC, n.updated_at DESC LIMIT %s", (tsq, subject_id, subject_id, limit))
        return {"passages": found, "notes": cur.fetchall()}
