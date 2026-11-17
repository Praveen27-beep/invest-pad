"""Contradiction scan: does a new document cut against any of my assumptions?

Run on request for one document (a button, so nothing is spent without the user asking).
One model call per document: the live assumptions of that company, plus the passages of
the document that best match each one. What comes back is a suggestion with an exact
quotation, checked against the passage; it becomes evidence only if the user accepts it,
and never changes an assumption's state.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from . import ask, auth, db, llm, ratelimit

router = APIRouter()

SYSTEM = """You check whether passages from a company document contradict or weaken an investor's \
assumptions about that company. Use ONLY the passages provided.

Rules:
- Report a passage only if it gives a concrete reason the assumption may not hold. Agreement, \
neutral context or vague risk language is not a contradiction.
- "quote" must be copied word for word from the passage, at least one full clause.
- "reason" is one sentence on how the quotation bears on the assumption. Do not say what to buy, \
sell or hold, or how much.
- If nothing contradicts, return an empty list. Do not invent problems.

Reply with JSON only: {"contradictions": [{"assumption": "A1", "source": "S1", "quote": "...", "reason": "..."}]}"""

PER_ASSUMPTION = 3


def scan_document(cfg, owner_id, document_id) -> dict:
    with db.as_user(owner_id) as cur:
        cur.execute("SELECT subject_id, status FROM document WHERE id = %s", (document_id,))
        doc = cur.fetchone()
        if not doc:
            raise LookupError
        if doc["status"] != "ready":
            return {"found": 0, "note": "This document has no readable text yet."}
        cur.execute(
            "SELECT a.id, v.body FROM assumption a JOIN position p ON p.id = a.position_id "
            "JOIN assumption_version v ON v.assumption_id = a.id AND v.seq = a.seq "
            "WHERE p.subject_id = %s AND v.state IN ('holds', 'challenged') ORDER BY a.created_at", (doc["subject_id"],))
        assumptions = cur.fetchall()
        if not assumptions:
            return {"found": 0, "note": "This company has no live assumptions to check against."}
        sources, links = {}, {}
        for i, a in enumerate(assumptions, 1):
            cur.execute(
                "SELECT id, body FROM chunk WHERE document_id = %s "
                "AND tsv @@ websearch_to_tsquery('english', %s) "
                "ORDER BY ts_rank(tsv, websearch_to_tsquery('english', %s)) DESC LIMIT %s",
                (document_id, _or(a["body"]), _or(a["body"]), PER_ASSUMPTION))
            for c in cur.fetchall():
                key = next((k for k, s in sources.items() if s["chunk_id"] == c["id"]), None)
                if key is None:
                    key = f"S{len(sources) + 1}"
                    sources[key] = {"chunk_id": c["id"], "text": c["body"]}
                links.setdefault(f"A{i}", []).append(key)
        model = ask.pick_model(cfg, cur)
    if not sources:
        return {"found": 0, "note": "No passage in this document touches your assumptions."}
    if model is None:
        return {"found": 0, "note": "No model is connected, so nothing was sent anywhere. Add one in Settings."}

    named = {f"A{i}": a for i, a in enumerate(assumptions, 1)}
    user = "\n".join(f'<assumption id="{k}">{ask.fence(a["body"])}</assumption>' for k, a in named.items()) + "\n\n" + \
        "\n".join(f'<source id="{k}">\n{ask.fence(s["text"])}\n</source>' for k, s in sources.items())
    try:
        reply = llm.parse_json(ask._call(cfg, owner_id, model, "scan", SYSTEM, user))
    except llm.ModelError as exc:
        return {"found": 0, "note": str(exc)}

    kept, removed = [], 0
    for item in (reply.get("contradictions") if isinstance(reply.get("contradictions"), list) else [])[:20]:
        if not isinstance(item, dict):
            removed += 1
            continue
        a, s = named.get(str(item.get("assumption"))), sources.get(str(item.get("source")))
        quote, reason = str(item.get("quote") or "").strip(), str(item.get("reason") or "").strip()
        ok, _ = ask.verify_claim({"text": reason, "quote": quote, "source": "S"}, {"S": s} if s else {})
        if a and ok:
            kept.append((a["id"], s["chunk_id"], quote, reason[:600]))
        else:
            removed += 1
    with db.as_user(owner_id) as cur:
        for row in kept:
            cur.execute("INSERT INTO evidence_suggestion (assumption_id, chunk_id, quote, reason) "
                        "VALUES (%s, %s, %s, %s) ON CONFLICT (owner_id, assumption_id, chunk_id) DO NOTHING", row)
    note = (f"{len(kept)} passage(s) may cut against your assumptions." if kept
            else "Nothing in this document contradicts your assumptions.")
    if removed:
        note += f" {removed} suggestion(s) from the model were dropped because the quotation did not check out."
    return {"found": len(kept), "note": note}


def _or(text: str) -> str:
    """Match any of the assumption's words, not all of them."""
    words = [w for w in "".join(ch if ch.isalnum() else " " for ch in text).split() if len(w) > 2]
    return " or ".join(words[:30])


@router.post("/documents/{document_id}/scan")
def scan(document_id: uuid.UUID, request: Request, user: dict = Depends(auth.current_user)):
    ratelimit.check("scan", str(user["id"]))
    try:
        return scan_document(request.app.state.config, user["id"], document_id)
    except LookupError as e:
        raise HTTPException(404, "Not found") from e


@router.post("/suggestions/{suggestion_id}/{action}")
def decide(suggestion_id: uuid.UUID, action: str, user: dict = Depends(auth.current_user)):
    """Accept (becomes AI evidence against the assumption, citing the passage) or dismiss."""
    if action not in ("accept", "dismiss"):
        raise HTTPException(404, "Not found")
    with db.as_user(user["id"]) as cur:
        cur.execute("UPDATE evidence_suggestion SET status = %s WHERE id = %s AND status = 'open' "
                    "RETURNING assumption_id, chunk_id, reason",
                    ("accepted" if action == "accept" else "dismissed", suggestion_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Not found")
        if action == "accept":
            cur.execute("INSERT INTO evidence (assumption_id, direction, kind, body, chunk_id) "
                        "VALUES (%s, 'against', 'ai', %s, %s) RETURNING id", (row["assumption_id"], row["reason"], row["chunk_id"]))
            return {"evidence_id": cur.fetchone()["id"]}
        return {"dismissed": True}
