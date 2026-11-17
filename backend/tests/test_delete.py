"""Deleting a document, a note or a company leaves none of its text anywhere (non-negotiable).

The check is generic: put a marker word in the source, let it spread the ways the product
spreads text (passages, answers, claims, citations, accepted AI evidence), delete the
source, then search every text and JSON column of every table the user owns for the
marker. A table added later is searched without anyone remembering to add it here.
"""

import pytest
from psycopg import sql

from app import llm
from tests.test_assistant import connect
from tests.test_documents import pdf, upload

MARKER = "Zorblax"


def leftovers(owner, user_id) -> list[str]:
    cols = owner.execute(
        "SELECT c.table_name, c.column_name FROM information_schema.columns c "
        "JOIN information_schema.tables t USING (table_schema, table_name) "
        "WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE' AND c.data_type IN ('text', 'jsonb') "
        "AND c.table_name IN (SELECT table_name FROM information_schema.columns "
        "                      WHERE table_schema = 'public' AND column_name = 'owner_id')").fetchall()
    found = []
    for table, column in cols:
        q = sql.SQL("SELECT count(*) FROM {} WHERE owner_id = %s AND {}::text ILIKE %s").format(
            sql.Identifier(table), sql.Identifier(column))
        if owner.execute(q, (user_id, f"%{MARKER}%")).fetchone()[0]:
            found.append(f"{table}.{column}")
    return found


@pytest.fixture
def spread(new_user):
    """A company whose document and note carry the marker into answers and evidence."""
    co = new_user()
    co.subject = co.post("/subjects", json={"name": "Northgate"}).json()["id"]
    co.doc = upload(co, co.subject, pdf(f"Revenue from operations was 608 crore in FY25 from {MARKER} contracts."),
                    "AR FY25.pdf").json()["id"]
    co.note = co.post("/notes", json={"title": "Channel check", "subject_id": co.subject, "blocks": [
        {"type": "paragraph", "content": f"Dealers say the {MARKER} range sells out in revenue terms."}]}).json()["id"]
    a = co.post(f"/subjects/{co.subject}/assumptions", json={"body": "Revenue grows", "basis": "fact"}).json()["id"]
    connect(co, base_url=llm.TEST_MODEL_URL, model="extractive", api_key="")
    for text in ("What was revenue from operations?", "What do dealers say about the range?"):
        q = co.post("/questions", json={"body": text, "subject_id": co.subject}).json()
        for c in co.get(f"/questions/{q['id']}").json()["answer"]["claims"]:
            assert co.post(f"/claims/{c['id']}/accept", json={"assumption_id": a, "direction": "for"}).status_code == 201
    co.assumption = a
    return co


def test_the_marker_really_spreads(spread, owner):
    found = leftovers(owner, spread.user_id)
    assert {"chunk.body", "note.body", "citation.quote", "evidence.body"} <= set(found), found


def test_deleting_the_document_and_note_removes_every_copy(spread, owner):
    assert spread.delete(f"/documents/{spread.doc}").status_code == 204
    assert spread.delete(f"/notes/{spread.note}").status_code == 204
    assert leftovers(owner, spread.user_id) == []
    # The user's record still shows that evidence existed and lost its source.
    ev = spread.get(f"/subjects/{spread.subject}/thesis").json()
    rows = [e for a in ev["assumptions"] for e in a["evidence"]]
    assert rows and all(e["source_deleted"] for e in rows if e["kind"] == "ai")


def test_deleting_the_company_removes_every_copy(spread, owner):
    assert spread.delete(f"/subjects/{spread.subject}").status_code == 204
    assert leftovers(owner, spread.user_id) == []


def test_a_claim_with_one_deleted_source_goes_entirely(new_user, owner):
    co = new_user()
    sid = co.post("/subjects", json={"name": "Two sources"}).json()["id"]
    d1 = upload(co, sid, pdf("Revenue was 608 crore in FY25."), "a.pdf").json()["id"]
    d2 = upload(co, sid, pdf("Revenue was 702 crore in FY26."), "b.pdf").json()["id"]
    chunks = [r[0] for r in owner.execute("SELECT id FROM chunk WHERE owner_id = %s ORDER BY document_id = %s DESC",
                                          (co.user_id, d1))]
    q = owner.execute("INSERT INTO question (owner_id, subject_id, body, status) VALUES (%s, %s, 'q', 'ready') RETURNING id",
                      (co.user_id, sid)).fetchone()[0]
    ans = owner.execute("INSERT INTO answer (owner_id, question_id, outcome) VALUES (%s, %s, 'answered') RETURNING id",
                        (co.user_id, q)).fetchone()[0]
    claim = owner.execute("INSERT INTO claim (owner_id, answer_id, ordinal, body) VALUES (%s, %s, 1, 'Revenue grew') "
                          "RETURNING id", (co.user_id, ans)).fetchone()[0]
    for c in chunks:
        owner.execute("INSERT INTO citation (owner_id, claim_id, chunk_id, quote) VALUES (%s, %s, %s, 'x')",
                      (co.user_id, claim, c))
    assert co.delete(f"/documents/{d1}").status_code == 204
    assert owner.execute("SELECT count(*) FROM claim WHERE id = %s", (claim,)).fetchone()[0] == 0
    assert owner.execute("SELECT count(*) FROM citation WHERE claim_id = %s", (claim,)).fetchone()[0] == 0
    assert co.get(f"/documents/{d2}").status_code == 200
