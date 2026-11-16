"""The assistant's HTTP surface: model connections, "How I invest", asking questions,
and the guardrail check before a decision."""

import uuid
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from psycopg.errors import ForeignKeyViolation
from pydantic import BaseModel, Field

from . import ask, auth, db, llm
from .capture import _hash, token_user

router = APIRouter()


# ---------------------------------------------------------------- models

class ModelIn(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    base_url: str = Field(min_length=8, max_length=300, pattern=r"^(https?://|test://)")
    model: str = Field(min_length=1, max_length=120)
    api_key: str = Field(default="", max_length=400)
    price_in: Decimal = Field(default=Decimal(0), ge=0, le=1000)
    price_out: Decimal = Field(default=Decimal(0), ge=0, le=1000)


MODEL_COLUMNS = "id, label, base_url, model, key_last4, price_in, price_out, created_at"


@router.get("/models")
def list_models(request: Request, user: dict = Depends(auth.current_user)):
    cfg = request.app.state.config
    with db.as_user(user["id"]) as cur:
        cur.execute(f"SELECT {MODEL_COLUMNS} FROM model_config ORDER BY created_at DESC")
        mine = cur.fetchall()
        cur.execute("SELECT coalesce(sum(cost_usd) FILTER (WHERE payer = 'platform'), 0) AS platform, "
                    "coalesce(sum(cost_usd) FILTER (WHERE payer = 'own'), 0) AS own, count(*) AS calls "
                    "FROM usage WHERE created_at >= date_trunc('month', now())")
        month = cur.fetchone()
    return {"models": mine, "included": bool(cfg.platform_model_url), "month": month,
            "caps": {"per_task": cfg.task_cost_cap, "monthly_credit": cfg.monthly_credit},
            "test_model_url": llm.TEST_MODEL_URL}


@router.post("/models", status_code=201)
def add_model(body: ModelIn, request: Request, user: dict = Depends(auth.current_user)):
    """Connect a model. The key is encrypted before it is stored and is never returned."""
    key = body.api_key.strip()
    with db.as_user(user["id"]) as cur:
        cur.execute(
            f"INSERT INTO model_config (label, base_url, model, key_ciphertext, key_last4, price_in, price_out) "
            f"VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING {MODEL_COLUMNS}",
            (body.label.strip(), body.base_url.strip().rstrip("/"), body.model.strip(),
             llm.encrypt(request.app.state.config.secret_key, key), key[-4:] if len(key) >= 8 else "",
             body.price_in, body.price_out))
        row = cur.fetchone()
        cur.execute("INSERT INTO audit_log (action, object) VALUES ('model.add', %s)", (str(row["id"]),))
        return row


@router.delete("/models/{model_id}", status_code=204)
def remove_model(model_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute("DELETE FROM model_config WHERE id = %s RETURNING id", (model_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Not found")
        cur.execute("INSERT INTO audit_log (action, object) VALUES ('model.remove', %s)", (str(model_id),))


# ---------------------------------------------------------------- how I invest

class ProfileIn(BaseModel):
    body: str = Field(max_length=20_000)


@router.get("/profile")
def get_profile(user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT seq, body, created_at FROM profile_version ORDER BY seq DESC")
        versions = cur.fetchall()
    return {"seq": versions[0]["seq"] if versions else 0, "body": versions[0]["body"] if versions else "",
            "versions": [{"seq": v["seq"], "created_at": v["created_at"]} for v in versions]}


@router.put("/profile")
def save_profile(body: ProfileIn, user: dict = Depends(auth.current_user)):
    text = body.body.strip()
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(current_owner()::text))")
        cur.execute("SELECT seq, body FROM profile_version ORDER BY seq DESC LIMIT 1")
        last = cur.fetchone()
        if last and last["body"] == text:
            return {"seq": last["seq"], "saved": False}
        seq = (last["seq"] if last else 0) + 1
        cur.execute("INSERT INTO profile_version (seq, body) VALUES (%s, %s)", (seq, text))
        return {"seq": seq, "saved": True}


# ---------------------------------------------------------------- questions

class QuestionIn(BaseModel):
    body: str = Field(min_length=3, max_length=2_000)
    subject_id: uuid.UUID | None = None
    model_id: uuid.UUID | None = None


def _create_question(request, background, owner_id, body: QuestionIn, source: str) -> dict:
    try:
        with db.as_user(owner_id) as cur:
            cur.execute("INSERT INTO question (body, subject_id, model_id, source) VALUES (%s, %s, %s, %s) "
                        "RETURNING id, body, subject_id, status, source, created_at",
                        (body.body.strip(), body.subject_id, body.model_id, source))
            question = cur.fetchone()
    except ForeignKeyViolation:
        raise HTTPException(404, "Company or model not found") from None
    background.add_task(ask.answer_question, request.app.state.config, owner_id, question["id"])
    return question


def _read_question(cur, question_id) -> dict:
    cur.execute("SELECT id, body, subject_id, status, source, created_at FROM question WHERE id = %s", (question_id,))
    question = cur.fetchone()
    if not question:
        raise HTTPException(404, "Not found")
    cur.execute("SELECT id, outcome, note, model, removed, created_at FROM answer WHERE question_id = %s "
                "ORDER BY created_at DESC LIMIT 1", (question_id,))
    answer = cur.fetchone()
    if answer:
        cur.execute(
            "SELECT c.id, c.body, x.quote, x.chunk_id, k.document_id, k.label AS page_label, "
            "  d.title AS document_title, d.period AS document_period, x.note_id, n.title AS note_title "
            "FROM claim c JOIN citation x ON x.claim_id = c.id "
            "LEFT JOIN chunk k ON k.id = x.chunk_id LEFT JOIN document d ON d.id = k.document_id "
            "LEFT JOIN note n ON n.id = x.note_id WHERE c.answer_id = %s ORDER BY c.ordinal", (answer["id"],))
        answer["claims"] = cur.fetchall()
        if answer["outcome"] == "answered" and not answer["claims"]:
            # Every source this answer quoted has since been deleted, and its claims with them.
            answer["outcome"], answer["note"] = "unknown", "The sources this answer quoted have been deleted."
    question["answer"] = answer
    return question


@router.post("/questions", status_code=201)
def ask_question(body: QuestionIn, request: Request, background: BackgroundTasks,
                 user: dict = Depends(auth.current_user)):
    return _create_question(request, background, user["id"], body, "app")


@router.get("/questions")
def list_questions(subject_id: uuid.UUID | None = None, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT id FROM question WHERE (%s::uuid IS NULL OR subject_id = %s) "
                    "ORDER BY created_at DESC LIMIT 30", (subject_id, subject_id))
        return [_read_question(cur, row["id"]) for row in cur.fetchall()]


@router.get("/questions/{question_id}")
def get_question(question_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        return _read_question(cur, question_id)


@router.delete("/questions/{question_id}", status_code=204)
def delete_question(question_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute("DELETE FROM question WHERE id = %s RETURNING id", (question_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Not found")


# The notepad may ask too, if its token was given that permission. It can read back only
# questions that were asked from the notepad.

def asking_token(request: Request, owner: str = Depends(token_user)) -> str:
    token = request.headers["authorization"][7:].strip()
    with db.anonymous() as cur:
        cur.execute("SELECT token_can_ask(%s) AS ok", (_hash(token),))
        if not cur.fetchone()["ok"]:
            raise HTTPException(403, "This token may save captures but not ask questions. Create one that can, "
                                     "in Settings.")
    return owner


@router.post("/ext/questions", status_code=201)
def ext_ask(body: QuestionIn, request: Request, background: BackgroundTasks, owner: str = Depends(asking_token)):
    body.model_id = None
    return _create_question(request, background, owner, body, "extension")


@router.get("/ext/questions/{question_id}")
def ext_answer(question_id: uuid.UUID, owner: str = Depends(asking_token)):
    with db.as_user(owner) as cur:
        question = _read_question(cur, question_id)
    if question["source"] != "extension":
        raise HTTPException(404, "Not found")
    return question


# ---------------------------------------------------------------- AI claim -> evidence

class AcceptIn(BaseModel):
    assumption_id: uuid.UUID
    direction: str = Field(pattern="^(for|against)$")


@router.post("/claims/{claim_id}/accept", status_code=201)
def accept_claim(claim_id: uuid.UUID, body: AcceptIn, user: dict = Depends(auth.current_user)):
    """Keep an AI statement as evidence. It stays labelled as AI, with the passage it quoted."""
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT c.body, x.chunk_id, x.note_id FROM claim c JOIN citation x ON x.claim_id = c.id "
                    "WHERE c.id = %s LIMIT 1", (claim_id,))
        claim = cur.fetchone()
        cur.execute("SELECT 1 FROM assumption WHERE id = %s", (body.assumption_id,))
        if not claim or not cur.fetchone():
            raise HTTPException(404, "Not found")
        cur.execute("INSERT INTO evidence (assumption_id, direction, kind, body, chunk_id, note_id, accepted_claim) "
                    "VALUES (%s, %s, 'ai', %s, %s, %s, %s) RETURNING id",
                    (body.assumption_id, body.direction, claim["body"], claim["chunk_id"], claim["note_id"],
                     str(claim_id)))
        return cur.fetchone()


# ---------------------------------------------------------------- guardrail

class DecisionDraft(BaseModel):
    type: str = Field(max_length=40)
    decisive_reason: str = Field(min_length=10, max_length=2_000)
    would_change_mind: str = Field(default="", max_length=2_000)


@router.post("/subjects/{subject_id}/decisions/check")
def check(subject_id: uuid.UUID, body: DecisionDraft, request: Request, user: dict = Depends(auth.current_user)):
    """Before recording: does this decision sit badly with any rule in "How I invest"?"""
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT name FROM subject WHERE id = %s", (subject_id,))
        subject = cur.fetchone()
        if not subject:
            raise HTTPException(404, "Not found")
        cur.execute("SELECT v.body FROM position p JOIN position_version v ON v.position_id = p.id AND v.seq = p.seq "
                    "WHERE p.subject_id = %s", (subject_id,))
        thesis = cur.fetchone()
        cur.execute("SELECT v.body, v.state FROM assumption a JOIN position p ON p.id = a.position_id "
                    "JOIN assumption_version v ON v.assumption_id = a.id AND v.seq = a.seq WHERE p.subject_id = %s",
                    (subject_id,))
        assumptions = [f"{a['body']} ({a['state']})" for a in cur.fetchall()]
    return ask.check_decision(request.app.state.config, user["id"], {
        "company": subject["name"], "type": body.type, "reason": body.decisive_reason,
        "would_change_mind": body.would_change_mind, "thesis": thesis["body"] if thesis else "",
        "assumptions": assumptions})
