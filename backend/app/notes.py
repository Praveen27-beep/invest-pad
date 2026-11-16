"""Notes: block documents with versions, [[links]], backlinks and search.

A note's blocks are stored exactly as the editor sends them. The server only needs two
things from a block: its `id` and its text. Anything shaped like
`{"id": ..., "content": [{"text": ...}], "children": [...]}` works, so the storage does
not depend on one editor library.
"""

import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import auth, db

router = APIRouter()

# [[Title]], [[Title|shown text]], [[Title#^block-id]], [[Title#^block-id|shown text]]
LINK = re.compile(r"\[\[([^\[\]|#]+?)(?:#\^([A-Za-z0-9-]+))?(?:\|[^\[\]]*)?\]\]")
MAX_BLOCKS_BYTES = 2_000_000


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    subject_id: uuid.UUID | None = None
    blocks: list[dict] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    blocks: list[dict]


# ---------------------------------------------------------------- blocks -> text and links

def _inline_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Table rows and cells are separated by a space; inline runs of text are not.
        separate = any(isinstance(c, dict) and ("cells" in c or c.get("type") == "tableCell") for c in content)
        return (" " if separate else "").join(_inline_text(c) for c in content)
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        # A link wraps styled text in "content"; a table keeps its text in rows of cells.
        parts = [_inline_text(content.get(key)) for key in ("content", "rows", "cells")]
        return " ".join(p for p in parts if p)
    return ""


def walk(blocks: list[dict]):
    """Yield (block_id, text) for every block, depth first."""
    for block in blocks:
        if not isinstance(block, dict):
            continue
        yield str(block.get("id") or ""), _inline_text(block.get("content"))
        yield from walk(block.get("children") or [])


def body_of(blocks: list[dict]) -> str:
    return "\n".join(text for _, text in walk(blocks) if text)


def links_of(blocks: list[dict]) -> list[tuple]:
    """(from_block_id, to_title_key, to_block_id, snippet) for every [[link]]."""
    found = []
    for block_id, text in walk(blocks):
        for match in LINK.finditer(text):
            title_key = match.group(1).strip().lower()
            if title_key:
                found.append((block_id or None, title_key, match.group(2), text[:300]))
    return found


def _replace_link_titles(value, old_key: str, new_title: str):
    """Return `value` with every [[old...]] link retargeted to new_title."""
    def swap(match: re.Match) -> str:
        if match.group(1).strip().lower() != old_key:
            return match.group(0)
        start, end = match.span(1)
        whole = match.group(0)
        offset = match.start()
        return whole[: start - offset] + new_title + whole[end - offset:]

    if isinstance(value, str):
        return LINK.sub(swap, value)
    if isinstance(value, list):
        return [_replace_link_titles(v, old_key, new_title) for v in value]
    if isinstance(value, dict):
        return {k: _replace_link_titles(v, old_key, new_title) if k in ("text", "content", "children") else v
                for k, v in value.items()}
    return value


# ---------------------------------------------------------------- storage helpers

def _write_version(cur, note_id, seq: int, title: str, blocks: list[dict], reason: str | None = None):
    """Record a version and rebuild the note's outgoing links from it."""
    cur.execute(
        "INSERT INTO note_version (note_id, seq, title, blocks, body, reason) VALUES (%s, %s, %s, %s, %s, %s)",
        (note_id, seq, title, Jsonb(blocks), body_of(blocks), reason),
    )
    cur.execute("DELETE FROM note_link WHERE from_note_id = %s", (note_id,))
    for from_block, to_key, to_block, snippet in links_of(blocks):
        cur.execute(
            "INSERT INTO note_link (from_note_id, from_block_id, to_title_key, to_block_id, snippet) "
            "VALUES (%s, %s, %s, %s, %s)",
            (note_id, from_block, to_key, to_block, snippet),
        )


def _check_size(blocks: list[dict]) -> None:
    if len(json.dumps(blocks)) > MAX_BLOCKS_BYTES:
        raise HTTPException(413, "Note is too large")


SUMMARY = "id, subject_id, title, seq, created_at, updated_at"


# ---------------------------------------------------------------- endpoints

@router.post("/notes", status_code=201)
def create_note(body: NoteIn, user: dict = Depends(auth.current_user)):
    _check_size(body.blocks)
    title = body.title.strip()
    try:
        with db.as_user(user["id"]) as cur:
            cur.execute(
                f"INSERT INTO note (subject_id, title, blocks, body) VALUES (%s, %s, %s, %s) RETURNING {SUMMARY}",
                (body.subject_id, title, Jsonb(body.blocks), body_of(body.blocks)),
            )
            note = cur.fetchone()
            _write_version(cur, note["id"], 1, title, body.blocks)
            return note
    except UniqueViolation:
        raise HTTPException(409, "You already have a note with that title") from None
    except ForeignKeyViolation:
        raise HTTPException(404, "Company not found") from None


@router.get("/notes")
def list_notes(subject_id: uuid.UUID | None = None, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute(
            f"SELECT {SUMMARY} FROM note WHERE (%s::uuid IS NULL OR subject_id = %s) ORDER BY updated_at DESC",
            (subject_id, subject_id),
        )
        return cur.fetchall()


@router.get("/notes/resolve")
def resolve_title(title: str, user: dict = Depends(auth.current_user)):
    """Find the note a [[Title]] link points at."""
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT id, title FROM note WHERE title_key = %s", (title.strip().lower(),))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "No note with that title yet")
    return row


@router.get("/notes/{note_id}")
def get_note(note_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute(f"SELECT {SUMMARY}, title_key, blocks FROM note WHERE id = %s", (note_id,))
        note = cur.fetchone()
        if not note:
            raise HTTPException(404, "Not found")
        title_key = note.pop("title_key")

        # Where this note points. `id` is NULL when the target has not been written yet.
        cur.execute(
            "SELECT DISTINCT l.to_title_key AS title_key, l.to_block_id AS block_id, n.id, n.title "
            "FROM note_link l LEFT JOIN note n ON n.title_key = l.to_title_key "
            "WHERE l.from_note_id = %s ORDER BY 1", (note_id,))
        note["links"] = cur.fetchall()

        # Notes that link here.
        cur.execute(
            "SELECT n.id, n.title, l.from_block_id AS block_id, l.to_block_id AS target_block_id, l.snippet "
            "FROM note_link l JOIN note n ON n.id = l.from_note_id "
            "WHERE l.to_title_key = %s AND n.id <> %s ORDER BY n.updated_at DESC", (title_key, note_id))
        note["backlinks"] = cur.fetchall()

        # Notes that mention this title in plain text without linking it.
        note["unlinked_mentions"] = []
        if len(title_key) >= 3:
            cur.execute(
                "SELECT id, title, body FROM note WHERE id <> %s AND position(%s in lower(body)) > 0 "
                "AND id NOT IN (SELECT from_note_id FROM note_link WHERE to_title_key = %s) "
                "ORDER BY updated_at DESC LIMIT 50", (note_id, title_key, title_key))
            whole_word = re.compile(rf"(?<!\w){re.escape(title_key)}(?!\w)", re.IGNORECASE)
            for row in cur.fetchall():
                hit = whole_word.search(row["body"])
                if hit:
                    start = max(0, hit.start() - 80)
                    note["unlinked_mentions"].append(
                        {"id": row["id"], "title": row["title"], "snippet": row["body"][start: hit.end() + 80]})
        return note


@router.put("/notes/{note_id}")
def save_note(note_id: uuid.UUID, body: NoteUpdate, user: dict = Depends(auth.current_user)):
    """Save = a new version. Nothing already saved is changed."""
    _check_size(body.blocks)
    title = body.title.strip()
    try:
        with db.as_user(user["id"]) as cur:
            cur.execute("SELECT title, title_key, blocks, seq FROM note WHERE id = %s FOR UPDATE", (note_id,))
            current = cur.fetchone()
            if not current:
                raise HTTPException(404, "Not found")
            if current["title"] == title and current["blocks"] == body.blocks:
                return {"id": note_id, "seq": current["seq"], "saved": False}

            seq = current["seq"] + 1
            cur.execute(
                "UPDATE note SET title = %s, blocks = %s, body = %s, seq = %s, updated_at = now() WHERE id = %s",
                (title, Jsonb(body.blocks), body_of(body.blocks), seq, note_id))
            _write_version(cur, note_id, seq, title, body.blocks)

            renamed = 0
            if title.lower() != current["title_key"]:
                renamed = _retarget_links(cur, current["title_key"], title, exclude=note_id)
            return {"id": note_id, "seq": seq, "saved": True, "links_updated_in": renamed}
    except UniqueViolation:
        raise HTTPException(409, "You already have a note with that title") from None


def _retarget_links(cur, old_key: str, new_title: str, exclude) -> int:
    """After a rename, point other notes' [[old title]] links at the new title.

    Each affected note gets a new version marked as automatic, so its history shows what
    changed and why. Its earlier versions keep the old link text.
    """
    cur.execute(
        "SELECT id, title, blocks, seq FROM note WHERE id <> %s "
        "AND id IN (SELECT from_note_id FROM note_link WHERE to_title_key = %s) FOR UPDATE", (exclude, old_key))
    rows = cur.fetchall()
    for row in rows:
        blocks = _replace_link_titles(row["blocks"], old_key, new_title)
        cur.execute(
            "UPDATE note SET blocks = %s, body = %s, seq = %s, updated_at = now() WHERE id = %s",
            (Jsonb(blocks), body_of(blocks), row["seq"] + 1, row["id"]))
        _write_version(cur, row["id"], row["seq"] + 1, row["title"], blocks,
                       reason=f"link updated: a note was renamed to “{new_title}”")
    return len(rows)


@router.get("/notes/{note_id}/versions")
def list_versions(note_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT seq, title, reason, created_at, length(body) AS chars FROM note_version "
                    "WHERE note_id = %s ORDER BY seq DESC", (note_id,))
        rows = cur.fetchall()
    if not rows:
        raise HTTPException(404, "Not found")
    return rows


@router.get("/notes/{note_id}/versions/{seq}")
def get_version(note_id: uuid.UUID, seq: int, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT seq, title, blocks, body, reason, created_at FROM note_version "
                    "WHERE note_id = %s AND seq = %s", (note_id, seq))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return row


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    """Owner delete: the note, all its versions and its links go together."""
    with db.as_user(user["id"]) as cur:
        cur.execute("DELETE FROM note WHERE id = %s RETURNING id", (note_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Not found")
        cur.execute("INSERT INTO audit_log (action, object) VALUES ('note.delete', %s)", (str(note_id),))


@router.get("/search")
def search(q: str = "", user: dict = Depends(auth.current_user)):
    """Keyword search over the current text of notes, plus company names."""
    q = q.strip()
    if not q:
        return {"notes": [], "subjects": []}
    with db.as_user(user["id"]) as cur:
        cur.execute(
            "SELECT id, subject_id, title, updated_at, "
            "  ts_headline('english', body, query, 'MaxWords=30, MinWords=10, StartSel=<<, StopSel=>>') AS snippet "
            "FROM note, websearch_to_tsquery('english', %s) AS query "
            "WHERE tsv @@ query ORDER BY ts_rank(tsv, query) DESC, updated_at DESC LIMIT 30", (q,))
        notes = cur.fetchall()
        cur.execute("SELECT id, name FROM subject WHERE name ILIKE %s ORDER BY name LIMIT 10",
                    ("%" + q.replace("%", r"\%").replace("_", r"\_") + "%",))
        return {"notes": notes, "subjects": cur.fetchall()}
