"""Full export: everything the user owns, nothing anyone else owns, no secrets."""

import io
import json
import zipfile
from datetime import date

from psycopg import sql

from app import llm
from tests.test_assistant import connect
from tests.test_documents import pdf, upload
from tests.test_portfolio import load

PASSAGE = "Revenue from operations was 608 crore in FY25."


def fill(client, name):
    """Put something into as many tables as the API reaches."""
    sid = client.post("/subjects", json={"name": name}).json()["id"]
    client.post("/notes", json={"title": f"{name} first look", "subject_id": sid,
                                "blocks": [{"type": "paragraph", "content": "See [[Loose idea]]"}]})
    client.post("/notes", json={"title": "Loose idea", "blocks": [{"type": "paragraph", "content": "unfiled"}]})
    doc = upload(client, sid, pdf(PASSAGE), "Annual report FY25.pdf").json()["id"]
    client.put(f"/subjects/{sid}/thesis", json={"body": f"{name} keeps share."})
    a = client.post(f"/subjects/{sid}/assumptions", json={"body": "Revenue grows", "basis": "fact"}).json()["id"]
    client.post(f"/assumptions/{a}/evidence", json={"direction": "for", "kind": "opinion", "body": "my read"})
    client.post(f"/subjects/{sid}/decisions", json={"type": "bought", "decided_on": str(date.today()),
                                                    "decisive_reason": "Share held after coupling.",
                                                    "would_change_mind": "Share below 80%", "assumption_ids": [a]})
    client.put("/profile", json={"body": "I avoid pledged promoters."})
    connect(client, base_url=llm.TEST_MODEL_URL, model="extractive", api_key="sk-must-not-be-exported-1234")
    client.post("/questions", json={"body": "What was revenue from operations?", "subject_id": sid})
    load(client)
    client.put("/portfolio/limits", json={"key": "max_position_pct", "value": 10, "enabled": True})
    client.put(f"/subjects/{sid}/watch", json={"watching": True})
    client.get("/review")
    return sid, doc


def unzip(client):
    r = client.get("/export")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    return zipfile.ZipFile(io.BytesIO(r.content))


def test_export_has_every_owned_row_and_nothing_else(new_user, owner):
    a, b = new_user(), new_user()
    fill(a, "Northgate Power Exchange")
    fill(b, "Other Person's Co")
    z = unzip(a)
    names = z.namelist()

    tables = [r[0] for r in owner.execute(
        "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name = 'owner_id' "
        "AND table_name IN (SELECT table_name FROM information_schema.tables WHERE table_type = 'BASE TABLE')")]
    assert len(tables) > 20
    for table in tables:
        rows = json.loads(z.read(f"data/{table}.json"))
        expected = owner.execute(sql.SQL("SELECT count(*) FROM {} WHERE owner_id = %s").format(sql.Identifier(table)),
                                 (a.user_id,)).fetchone()[0]
        assert len(rows) == expected, table
        assert all(str(r["owner_id"]) == str(a.user_id) for r in rows), table

    # The record that matters is really there, not just counted.
    for table in ("subject", "note", "note_version", "note_link", "document", "chunk", "position", "position_version",
                  "assumption", "assumption_version", "evidence", "decision", "profile_version", "model_config",
                  "question", "answer", "claim", "citation", "holding_snapshot", "holding", "limit_rule", "alert",
                  "review", "review_item", "audit_log"):
        assert json.loads(z.read(f"data/{table}.json")), f"{table} is empty in the export"

    everything = b"".join(z.read(n) for n in names)
    assert b"Other Person" not in everything
    assert str(b.user_id).encode() not in everything
    assert b"sk-must-not-be-exported" not in everything and b"key_ciphertext" not in everything

    folder = "companies/Northgate Power Exchange"
    thesis = z.read(f"{folder}/thesis.md").decode()
    assert "Northgate Power Exchange keeps share." in thesis and "Share held after coupling." in thesis
    assert "Revenue grows" in thesis and "my read" in thesis
    assert f"{folder}/notes/Northgate Power Exchange first look.md" in names
    assert "notes/Loose idea.md" in names
    original = z.read(f"{folder}/documents/Annual report FY25.pdf")
    assert original.startswith(b"%PDF")
    assert "README.txt" in names


def test_export_requires_sign_in_and_is_audited(app, new_user, owner):
    from fastapi.testclient import TestClient
    assert TestClient(app).get("/export").status_code == 401
    a = new_user()
    unzip(a)
    assert owner.execute("SELECT count(*) FROM audit_log WHERE owner_id = %s AND action = 'export'",
                         (a.user_id,)).fetchone()[0] == 1


def test_awkward_names_stay_inside_their_folders(new_user):
    a = new_user()
    a.post("/subjects", json={"name": "../../etc/passwd"})
    a.post("/subjects", json={"name": "A/B: C?"})
    assert a.post("/notes", json={"title": "A/B", "blocks": []}).status_code == 201
    assert a.post("/notes", json={"title": "A_B", "blocks": []}).status_code == 201   # same file name once made safe
    names = unzip(a).namelist()
    assert all(".." not in n.split("/") and not n.startswith("/") for n in names)
    assert len([n for n in names if n.startswith("notes/")]) == 2
    assert len([n for n in names if n.endswith("thesis.md")]) == 2
