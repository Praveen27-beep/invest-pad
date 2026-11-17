"""The thesis: versions with diffs, assumptions, evidence, decisions and checklists.

Nothing here edits history. Changing a thesis or an assumption adds a version; a decision
is a journal entry that is never changed afterwards.
"""

import difflib
import json
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import ForeignKeyViolation
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import auth, db

router = APIRouter()
PACK = json.loads((Path(__file__).resolve().parent.parent / "packs" / "investing" / "pack.json").read_text())
DECISION_TYPES = {t["key"]: t["label"] for t in PACK["decision_types"]}


@router.get("/pack")
def pack(user: dict = Depends(auth.current_user)):
    return PACK


def _subject(cur, subject_id):
    cur.execute("SELECT id FROM subject WHERE id = %s", (subject_id,))
    if not cur.fetchone():
        raise HTTPException(404, "Company not found")


def _position(cur, subject_id, create: bool = False):
    cur.execute("SELECT id, seq FROM position WHERE subject_id = %s FOR UPDATE", (subject_id,))
    row = cur.fetchone()
    if not row and create:
        _subject(cur, subject_id)
        cur.execute("INSERT INTO position (subject_id) VALUES (%s) RETURNING id, seq", (subject_id,))
        row = cur.fetchone()
    return row


# ---------------------------------------------------------------- diff

TOKEN = re.compile(r"\s+|\w+|[^\w\s]")


def diff(old: str, new: str) -> list[dict]:
    """Word-level differences between two texts, as [{op: equal|insert|delete, text}]."""
    a, b = TOKEN.findall(old), TOKEN.findall(new)
    out: list[dict] = []

    def add(op: str, text: str) -> None:
        if not text:
            return
        if out and out[-1]["op"] == op:
            out[-1]["text"] += text
        else:
            out.append({"op": op, "text": text})

    for tag, a1, a2, b1, b2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            add("equal", "".join(a[a1:a2]))
        else:
            add("delete", "".join(a[a1:a2]))
            add("insert", "".join(b[b1:b2]))
    return out


# ---------------------------------------------------------------- thesis text

class ThesisIn(BaseModel):
    body: str = Field(max_length=100_000)


@router.put("/subjects/{subject_id}/thesis")
def save_thesis(subject_id: uuid.UUID, body: ThesisIn, user: dict = Depends(auth.current_user)):
    text = body.body.strip()
    with db.as_user(user["id"]) as cur:
        position = _position(cur, subject_id, create=True)
        if position["seq"]:
            cur.execute("SELECT body FROM position_version WHERE position_id = %s AND seq = %s",
                        (position["id"], position["seq"]))
            if cur.fetchone()["body"] == text:
                return {"seq": position["seq"], "saved": False}
        seq = position["seq"] + 1
        cur.execute("INSERT INTO position_version (position_id, seq, body) VALUES (%s, %s, %s)",
                    (position["id"], seq, text))
        cur.execute("UPDATE position SET seq = %s WHERE id = %s", (seq, position["id"]))
        return {"seq": seq, "saved": True}


@router.get("/subjects/{subject_id}/thesis")
def get_thesis(subject_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        _subject(cur, subject_id)
        cur.execute("SELECT id, seq FROM position WHERE subject_id = %s", (subject_id,))
        position = cur.fetchone()
        if not position:
            return {"seq": 0, "body": "", "versions": [], "assumptions": []}
        cur.execute("SELECT seq, body, created_at FROM position_version WHERE position_id = %s ORDER BY seq DESC",
                    (position["id"],))
        versions = cur.fetchall()
        return {"seq": position["seq"], "body": versions[0]["body"] if versions else "",
                "versions": [{"seq": v["seq"], "created_at": v["created_at"]} for v in versions],
                "assumptions": _assumptions(cur, position["id"])}


@router.get("/subjects/{subject_id}/thesis/diff")
def thesis_diff(subject_id: uuid.UUID, a: int, b: int, user: dict = Depends(auth.current_user)):
    """What changed between version `a` and version `b` of the thesis."""
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT v.seq, v.body, v.created_at FROM position_version v "
                    "JOIN position p ON p.id = v.position_id "
                    "WHERE p.subject_id = %s AND v.seq IN (%s, %s)", (subject_id, a, b))
        rows = {r["seq"]: r for r in cur.fetchall()}
    if a not in rows or b not in rows:
        raise HTTPException(404, "Version not found")
    return {"from": {"seq": a, "created_at": rows[a]["created_at"]},
            "to": {"seq": b, "created_at": rows[b]["created_at"]},
            "changes": diff(rows[a]["body"], rows[b]["body"])}


# ---------------------------------------------------------------- assumptions

def _assumptions(cur, position_id) -> list[dict]:
    cur.execute(
        "SELECT a.id, a.seq, v.body, v.basis, v.state, v.reason, v.created_at AS updated_at, a.created_at "
        "FROM assumption a JOIN assumption_version v ON v.assumption_id = a.id AND v.seq = a.seq "
        "WHERE a.position_id = %s ORDER BY a.created_at", (position_id,))
    rows = cur.fetchall()
    cur.execute(
        "SELECT e.id, e.assumption_id, e.direction, e.kind, e.body, e.source_deleted, e.created_at, "
        "  e.chunk_id, c.body AS passage, c.label AS page_label, c.document_id, d.title AS document_title, "
        "  d.period AS document_period, e.note_id, n.title AS note_title "
        "FROM evidence e JOIN assumption a ON a.id = e.assumption_id "
        "LEFT JOIN chunk c ON c.id = e.chunk_id LEFT JOIN document d ON d.id = c.document_id "
        "LEFT JOIN note n ON n.id = e.note_id "
        "WHERE a.position_id = %s AND e.retracted_at IS NULL ORDER BY e.created_at", (position_id,))
    by_assumption: dict = {}
    for e in cur.fetchall():
        # A fact whose document was deleted is no longer a sourced fact. Say so rather than
        # keep presenting it as one.
        e["is_sourced_fact"] = e["kind"] == "fact" and e["chunk_id"] is not None
        by_assumption.setdefault(e.pop("assumption_id"), []).append(e)
    cur.execute(
        "SELECT s.id, s.assumption_id, s.quote, s.reason, s.created_at, c.label AS page_label, d.id AS document_id, "
        "  d.title AS document_title FROM evidence_suggestion s JOIN assumption a ON a.id = s.assumption_id "
        "JOIN chunk c ON c.id = s.chunk_id JOIN document d ON d.id = c.document_id "
        "WHERE a.position_id = %s AND s.status = 'open' ORDER BY s.created_at", (position_id,))
    suggested: dict = {}
    for s in cur.fetchall():
        suggested.setdefault(s.pop("assumption_id"), []).append(s)
    for row in rows:
        row["evidence"] = by_assumption.get(row["id"], [])
        row["suggestions"] = suggested.get(row["id"], [])
    return rows


class AssumptionIn(BaseModel):
    body: str = Field(min_length=1, max_length=2_000)
    basis: Literal["fact", "judgement"]


class AssumptionUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=2_000)
    basis: Literal["fact", "judgement"]
    state: Literal["holds", "challenged", "broken", "outdated"]
    reason: str = Field(default="", max_length=2_000)


@router.post("/subjects/{subject_id}/assumptions", status_code=201)
def add_assumption(subject_id: uuid.UUID, body: AssumptionIn, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        position = _position(cur, subject_id, create=True)
        cur.execute("INSERT INTO assumption (position_id) VALUES (%s) RETURNING id", (position["id"],))
        assumption_id = cur.fetchone()["id"]
        cur.execute("INSERT INTO assumption_version (assumption_id, seq, body, basis, state) "
                    "VALUES (%s, 1, %s, %s, 'holds')", (assumption_id, body.body.strip(), body.basis))
        return {"id": assumption_id, "seq": 1}


@router.put("/assumptions/{assumption_id}")
def update_assumption(assumption_id: uuid.UUID, body: AssumptionUpdate, user: dict = Depends(auth.current_user)):
    """Change the wording, basis or state. Recorded as a new version; a state change needs a reason."""
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT a.seq, v.body, v.basis, v.state FROM assumption a JOIN assumption_version v "
                    "ON v.assumption_id = a.id AND v.seq = a.seq WHERE a.id = %s FOR UPDATE OF a", (assumption_id,))
        current = cur.fetchone()
        if not current:
            raise HTTPException(404, "Not found")
        new = (body.body.strip(), body.basis, body.state)
        if new == (current["body"], current["basis"], current["state"]):
            return {"id": assumption_id, "seq": current["seq"], "saved": False}
        if body.state != current["state"] and not body.reason.strip():
            raise HTTPException(422, "Say why the state changed. Future you will want to know.")
        seq = current["seq"] + 1
        cur.execute("INSERT INTO assumption_version (assumption_id, seq, body, basis, state, reason) "
                    "VALUES (%s, %s, %s, %s, %s, %s)", (assumption_id, seq, *new, body.reason.strip()))
        cur.execute("UPDATE assumption SET seq = %s WHERE id = %s", (seq, assumption_id))
        return {"id": assumption_id, "seq": seq, "saved": True}


@router.get("/assumptions/{assumption_id}/versions")
def assumption_versions(assumption_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT seq, body, basis, state, reason, created_at FROM assumption_version "
                    "WHERE assumption_id = %s ORDER BY seq DESC", (assumption_id,))
        rows = cur.fetchall()
    if not rows:
        raise HTTPException(404, "Not found")
    return rows


# ---------------------------------------------------------------- evidence

class EvidenceIn(BaseModel):
    direction: Literal["for", "against"]
    kind: Literal["fact", "opinion"]          # "ai" is created only by accepting an AI answer (M6)
    body: str = Field(min_length=1, max_length=4_000)
    chunk_id: uuid.UUID | None = None
    note_id: uuid.UUID | None = None


@router.post("/assumptions/{assumption_id}/evidence", status_code=201)
def add_evidence(assumption_id: uuid.UUID, body: EvidenceIn, user: dict = Depends(auth.current_user)):
    if body.kind == "fact" and not body.chunk_id:
        raise HTTPException(422, "A fact needs a passage from a document. Without one, save it as your opinion.")
    try:
        with db.as_user(user["id"]) as cur:
            cur.execute("SELECT p.subject_id FROM assumption a JOIN position p ON p.id = a.position_id "
                        "WHERE a.id = %s", (assumption_id,))
            owner_subject = cur.fetchone()
            if not owner_subject:
                raise HTTPException(404, "Not found")
            if body.chunk_id:
                # The passage must come from a document filed under the same company.
                cur.execute("SELECT 1 FROM chunk c JOIN document d ON d.id = c.document_id "
                            "WHERE c.id = %s AND d.subject_id = %s", (body.chunk_id, owner_subject["subject_id"]))
                if not cur.fetchone():
                    raise HTTPException(404, "Passage not found in this company's documents")
            cur.execute(
                "INSERT INTO evidence (assumption_id, direction, kind, body, chunk_id, note_id) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (assumption_id, body.direction, body.kind, body.body.strip(), body.chunk_id, body.note_id))
            return cur.fetchone()
    except ForeignKeyViolation:
        raise HTTPException(404, "Note not found") from None


@router.delete("/evidence/{evidence_id}", status_code=204)
def retract_evidence(evidence_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    """Withdraw a piece of evidence. It is hidden, not erased."""
    with db.as_user(user["id"]) as cur:
        cur.execute("UPDATE evidence SET retracted_at = now() WHERE id = %s AND retracted_at IS NULL RETURNING id",
                    (evidence_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Not found")


# ---------------------------------------------------------------- decisions

class Flag(BaseModel):
    rule: str = Field(max_length=2_000)
    question: str = Field(max_length=400)


class DecisionIn(BaseModel):
    type: str
    decided_on: date
    decisive_reason: str = Field(min_length=10, max_length=2_000)
    would_change_mind: str = Field(default="", max_length=2_000)
    assumption_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    flags: list[Flag] = Field(default_factory=list, max_length=8)   # guardrail conflicts shown before recording


DECISION_COLUMNS = ("id, type, decided_on, decisive_reason, would_change_mind, position_seq, assumptions, flags, "
                    "created_at")


@router.post("/subjects/{subject_id}/decisions", status_code=201)
def record_decision(subject_id: uuid.UUID, body: DecisionIn, user: dict = Depends(auth.current_user)):
    """Write a journal entry. It freezes what the thesis and the chosen assumptions said at that moment."""
    if body.type not in DECISION_TYPES:
        raise HTTPException(422, "Unknown decision type")
    if body.decided_on > date.today():
        raise HTTPException(422, "A decision cannot be dated in the future")
    with db.as_user(user["id"]) as cur:
        _subject(cur, subject_id)
        cur.execute("SELECT id, seq FROM position WHERE subject_id = %s", (subject_id,))
        position = cur.fetchone()
        snapshot = []
        if body.assumption_ids:
            cur.execute(
                "SELECT a.id, a.seq, v.body, v.basis, v.state FROM assumption a JOIN assumption_version v "
                "ON v.assumption_id = a.id AND v.seq = a.seq WHERE a.position_id = %s AND a.id = ANY(%s) "
                "ORDER BY a.created_at", (position["id"] if position else None, body.assumption_ids))
            snapshot = [{**row, "id": str(row["id"])} for row in cur.fetchall()]
            if len(snapshot) != len(set(body.assumption_ids)):
                raise HTTPException(404, "One of those assumptions does not belong to this company")
        cur.execute(
            f"INSERT INTO decision (subject_id, type, decided_on, decisive_reason, would_change_mind, position_seq, "
            f"assumptions, flags) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING {DECISION_COLUMNS}",
            (subject_id, body.type, body.decided_on, body.decisive_reason.strip(), body.would_change_mind.strip(),
             position["seq"] if position and position["seq"] else None, Jsonb(snapshot),
             Jsonb([f.model_dump() for f in body.flags])))
        return cur.fetchone()


@router.get("/subjects/{subject_id}/decisions")
def list_decisions(subject_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute(f"SELECT {DECISION_COLUMNS} FROM decision WHERE subject_id = %s "
                    "ORDER BY decided_on DESC, created_at DESC", (subject_id,))
        return cur.fetchall()


# ---------------------------------------------------------------- checklists

class ChecklistItem(BaseModel):
    id: str = Field(max_length=60)
    answer: Literal["yes", "no", "unknown"]
    note: str = Field(default="", max_length=2_000)


class ChecklistIn(BaseModel):
    items: list[ChecklistItem] = Field(max_length=100)


@router.post("/subjects/{subject_id}/checklists/{key}", status_code=201)
def save_checklist(subject_id: uuid.UUID, key: str, body: ChecklistIn, user: dict = Depends(auth.current_user)):
    checklist = PACK["checklists"].get(key)
    if not checklist:
        raise HTTPException(404, "Unknown checklist")
    questions = {item["id"]: item["text"] for item in checklist["items"]}
    answers = {item.id: item for item in body.items}
    if set(answers) != set(questions):
        raise HTTPException(422, "Answer every item; “don't know yet” is a valid answer")
    # Store the question text with the answer, so the record still reads correctly if the
    # checklist wording changes later.
    items = [{"id": i, "text": questions[i], "answer": answers[i].answer, "note": answers[i].note.strip()}
             for i in questions]
    with db.as_user(user["id"]) as cur:
        _subject(cur, subject_id)
        cur.execute("INSERT INTO checklist_run (subject_id, checklist_key, items) VALUES (%s, %s, %s) "
                    "RETURNING id, items, created_at", (subject_id, key, Jsonb(items)))
        return cur.fetchone()


@router.get("/subjects/{subject_id}/checklists/{key}")
def get_checklist(subject_id: uuid.UUID, key: str, user: dict = Depends(auth.current_user)):
    """The latest run, and how many runs there have been."""
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT id, items, created_at, count(*) OVER () AS runs FROM checklist_run "
                    "WHERE subject_id = %s AND checklist_key = %s ORDER BY created_at DESC LIMIT 1", (subject_id, key))
        return cur.fetchone() or {"id": None, "items": [], "created_at": None, "runs": 0}


# ---------------------------------------------------------------- the reopen view

@router.get("/subjects/{subject_id}/overview")
def overview(subject_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    """What you need when you come back to a company: the last decision and the reason for
    it in your own words, what it rested on, how those assumptions stand now, what is still
    open, and what has changed since.

    Read straight from what was recorded. No model is involved.
    """
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT id, name, created_at, watch_since FROM subject WHERE id = %s", (subject_id,))
        subject = cur.fetchone()
        if not subject:
            raise HTTPException(404, "Not found")
        cur.execute(f"SELECT {DECISION_COLUMNS} FROM decision WHERE subject_id = %s "
                    "ORDER BY decided_on DESC, created_at DESC LIMIT 1", (subject_id,))
        decision = cur.fetchone()
        cur.execute("SELECT id, seq FROM position WHERE subject_id = %s", (subject_id,))
        position = cur.fetchone()
        assumptions = _assumptions(cur, position["id"]) if position else []

        if decision:
            decision["type_label"] = DECISION_TYPES.get(decision["type"], decision["type"])
            now = {str(a["id"]): a for a in assumptions}
            for then in decision["assumptions"]:
                current = now.get(then["id"])
                then["now"] = None if not current else {
                    "seq": current["seq"], "body": current["body"], "state": current["state"],
                    "reason": current["reason"], "changed": current["seq"] != then["seq"]}
            decision["thesis_changed"] = bool(position and decision["position_seq"]
                                              and position["seq"] != decision["position_seq"])

        cur.execute("SELECT id, body, captured_at, url, page_title FROM capture WHERE subject_id = %s "
                    "AND kind = 'question' AND status = 'inbox' ORDER BY captured_at DESC", (subject_id,))
        questions = cur.fetchall()

        # "Since" means since the journal entry was written (not the date it describes).
        since = decision["created_at"] if decision else None
        changes = {"since": since, "notes": [], "documents": [], "assumptions": [], "thesis_versions": 0}
        if since:
            cur.execute("SELECT id, title, seq, updated_at FROM note WHERE subject_id = %s AND updated_at > %s "
                        "ORDER BY updated_at DESC LIMIT 50", (subject_id, since))
            changes["notes"] = cur.fetchall()
            cur.execute("SELECT id, title, doc_type, period, created_at FROM document WHERE subject_id = %s "
                        "AND created_at > %s ORDER BY created_at DESC LIMIT 50", (subject_id, since))
            changes["documents"] = cur.fetchall()
            if position:
                cur.execute(
                    "SELECT v.assumption_id AS id, v.seq, v.body, v.state, v.reason, v.created_at "
                    "FROM assumption_version v JOIN assumption a ON a.id = v.assumption_id "
                    "WHERE a.position_id = %s AND v.created_at > %s ORDER BY v.created_at DESC",
                    (position["id"], since))
                changes["assumptions"] = cur.fetchall()
                cur.execute("SELECT count(*) AS n FROM position_version WHERE position_id = %s AND created_at > %s",
                            (position["id"], since))
                changes["thesis_versions"] = cur.fetchone()["n"]
        return {"subject": subject, "decision": decision, "thesis_seq": position["seq"] if position else 0,
                "assumptions": assumptions, "open_questions": questions, "changes": changes}
