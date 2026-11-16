"""Notes: versions, links, backlinks, rename, search, delete, and isolation."""

import psycopg
import pytest


def block(block_id: str, text: str, children=None) -> dict:
    return {"id": block_id, "type": "paragraph", "content": [{"type": "text", "text": text}],
            "children": children or []}


def make_note(client, title, *texts, subject_id=None):
    blocks = [block(f"b{i}", t) for i, t in enumerate(texts, 1)]
    r = client.post("/notes", json={"title": title, "blocks": blocks, "subject_id": subject_id})
    assert r.status_code == 201, r.text
    return r.json()


def test_create_read_and_list_by_company(new_user):
    a = new_user()
    company = a.post("/subjects", json={"name": "IEX"}).json()
    note = make_note(a, "Market coupling", "Coupling removes the liquidity edge.", subject_id=company["id"])
    make_note(a, "Unfiled thought", "No company yet.")

    got = a.get(f"/notes/{note['id']}").json()
    assert got["title"] == "Market coupling" and got["seq"] == 1
    assert got["blocks"][0]["content"][0]["text"] == "Coupling removes the liquidity edge."
    assert [n["title"] for n in a.get("/notes", params={"subject_id": company["id"]}).json()] == ["Market coupling"]
    assert len(a.get("/notes").json()) == 2


def test_duplicate_title_is_refused_case_insensitively(new_user):
    a = new_user()
    make_note(a, "Thesis")
    assert a.post("/notes", json={"title": "  thesis ", "blocks": []}).status_code == 409


def test_note_for_unknown_company_is_refused(new_user):
    a = new_user()
    r = a.post("/notes", json={"title": "x", "blocks": [], "subject_id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 404


def test_every_save_is_a_new_version_and_old_ones_stay_readable(new_user):
    a = new_user()
    note = make_note(a, "Thesis", "Version one text.")
    url = f"/notes/{note['id']}"

    r = a.put(url, json={"title": "Thesis", "blocks": [block("b1", "Version two text.")]}).json()
    assert r == {"id": note["id"], "seq": 2, "saved": True, "links_updated_in": 0}
    # Saving the same content again does not create a version.
    assert a.put(url, json={"title": "Thesis", "blocks": [block("b1", "Version two text.")]}).json()["saved"] is False

    versions = a.get(f"{url}/versions").json()
    assert [v["seq"] for v in versions] == [2, 1]
    assert a.get(f"{url}/versions/1").json()["body"] == "Version one text."
    assert a.get(f"{url}/versions/2").json()["body"] == "Version two text."
    assert a.get(url).json()["blocks"][0]["content"][0]["text"] == "Version two text."
    assert a.get(f"{url}/versions/3").status_code == 404


def test_links_and_backlinks(new_user):
    a = new_user()
    thesis = make_note(a, "IEX thesis", "Depends on [[Market coupling]] and on [[Not written yet]].")
    coupling = make_note(a, "Market coupling", "See the main view in [[iex THESIS|my thesis]].")

    got = a.get(f"/notes/{thesis['id']}").json()
    links = {link["title_key"]: link["id"] for link in got["links"]}
    assert links == {"market coupling": coupling["id"], "not written yet": None}
    assert [(b["title"], b["block_id"]) for b in got["backlinks"]] == [("Market coupling", "b1")]
    assert "my thesis" in got["backlinks"][0]["snippet"]

    assert a.get("/notes/resolve", params={"title": "market COUPLING"}).json()["id"] == coupling["id"]
    assert a.get("/notes/resolve", params={"title": "Not written yet"}).status_code == 404


def test_links_inside_nested_blocks_and_block_links(new_user):
    a = new_user()
    target = make_note(a, "Concall Q4", "Management said share loss could be 20 to 40 percent in DAM.")
    nested = [block("outer", "Evidence:", children=[block("inner", "Quote is at [[Concall Q4#^b1]].")])]
    source = a.post("/notes", json={"title": "Evidence list", "blocks": nested}).json()

    back = a.get(f"/notes/{target['id']}").json()["backlinks"]
    assert back == [{"id": source["id"], "title": "Evidence list", "block_id": "inner",
                     "target_block_id": "b1", "snippet": "Quote is at [[Concall Q4#^b1]]."}]


def test_unlinked_mentions_are_whole_word_and_exclude_linked_notes(new_user):
    a = new_user()
    target = make_note(a, "DAM")
    make_note(a, "Plain mention", "Volume in DAM fell this quarter.")
    make_note(a, "Linked mention", "Volume in [[DAM]] fell; DAM matters.")
    make_note(a, "Substring only", "The Amsterdam exchange is different.")

    mentions = a.get(f"/notes/{target['id']}").json()["unlinked_mentions"]
    assert [m["title"] for m in mentions] == ["Plain mention"]
    assert "DAM fell" in mentions[0]["snippet"]


def test_removing_a_link_removes_the_backlink(new_user):
    a = new_user()
    target = make_note(a, "Target")
    source = make_note(a, "Source", "Points at [[Target]].")
    assert len(a.get(f"/notes/{target['id']}").json()["backlinks"]) == 1
    a.put(f"/notes/{source['id']}", json={"title": "Source", "blocks": [block("b1", "No link now.")]})
    assert a.get(f"/notes/{target['id']}").json()["backlinks"] == []


def test_rename_keeps_links_working_and_records_why(new_user):
    a = new_user()
    target = make_note(a, "Coupling", "Body.")
    source = make_note(a, "Thesis", "Rests on [[Coupling]] and [[coupling#^b1|the quote]]; also [[Couplings]].")

    r = a.put(f"/notes/{target['id']}", json={"title": "Market coupling", "blocks": [block("b1", "Body.")]}).json()
    assert r["links_updated_in"] == 1

    after = a.get(f"/notes/{source['id']}").json()
    text = after["blocks"][0]["content"][0]["text"]
    assert text == "Rests on [[Market coupling]] and [[Market coupling#^b1|the quote]]; also [[Couplings]]."
    assert after["seq"] == 2
    assert [b["title"] for b in a.get(f"/notes/{target['id']}").json()["backlinks"]] == ["Thesis", "Thesis"]

    versions = a.get(f"/notes/{source['id']}/versions").json()
    assert "renamed" in versions[0]["reason"] and versions[1]["reason"] is None
    # The earlier version still shows what was written at the time.
    assert "[[Coupling]]" in a.get(f"/notes/{source['id']}/versions/1").json()["body"]


def test_search_finds_current_text_only_and_ranks_titles(new_user):
    a = new_user()
    note = make_note(a, "Governance", "Promoter pledged shares in 2024.")
    make_note(a, "Other", "A passing remark about governance standards.")
    a.post("/subjects", json={"name": "Governance Ltd"})

    found = a.get("/search", params={"q": "governance"}).json()
    assert [n["title"] for n in found["notes"]] == ["Governance", "Other"]
    assert [s["name"] for s in found["subjects"]] == ["Governance Ltd"]
    assert "<<pledged>>" in a.get("/search", params={"q": "pledge"}).json()["notes"][0]["snippet"]

    # Text that was edited away is no longer found; it lives on in the old version only.
    a.put(f"/notes/{note['id']}", json={"title": "Governance", "blocks": [block("b1", "Rewritten.")]})
    assert a.get("/search", params={"q": "pledged"}).json()["notes"] == []
    assert a.get("/search", params={"q": "  "}).json() == {"notes": [], "subjects": []}


def test_delete_removes_versions_and_links(new_user, owner):
    a = new_user()
    target = make_note(a, "Target")
    source = make_note(a, "Source", "A unique-marker-xyz and [[Target]].")
    a.put(f"/notes/{source['id']}",
          json={"title": "Source", "blocks": [block("b1", "unique-marker-xyz v2 [[Target]]")]})

    assert a.delete(f"/notes/{source['id']}").status_code == 204
    assert a.get(f"/notes/{source['id']}").status_code == 404
    assert a.get(f"/notes/{source['id']}/versions").status_code == 404
    assert a.get(f"/notes/{target['id']}").json()["backlinks"] == []
    for table in ("note", "note_version", "note_link"):
        left = owner.execute(f"SELECT count(*) FROM {table} WHERE to_jsonb({table})::text LIKE '%%unique-marker-xyz%%'")
        assert left.fetchone()[0] == 0, table


def test_deleting_a_company_deletes_its_notes(new_user):
    a = new_user()
    company = a.post("/subjects", json={"name": "Gone Ltd"}).json()
    note = make_note(a, "About Gone", "text", subject_id=company["id"])
    a.delete(f"/subjects/{company['id']}")
    assert a.get(f"/notes/{note['id']}").status_code == 404


def test_other_users_see_nothing(new_user):
    a, b = new_user(), new_user()
    note = make_note(a, "Secret thesis", "zebra-keyword and [[Shared title]]")
    a.put(f"/notes/{note['id']}", json={"title": "Secret thesis", "blocks": [block("b1", "zebra-keyword again")]})
    url = f"/notes/{note['id']}"

    assert b.get("/notes").json() == []
    assert b.get(url).status_code == 404
    assert b.get(f"{url}/versions").status_code == 404
    assert b.get(f"{url}/versions/1").status_code == 404
    assert b.put(url, json={"title": "Hijack", "blocks": []}).status_code == 404
    assert b.delete(url).status_code == 404
    assert b.get("/search", params={"q": "zebra-keyword"}).json() == {"notes": [], "subjects": []}
    assert b.get("/notes/resolve", params={"title": "Secret thesis"}).status_code == 404

    # B may use the same title; A's links and mentions never surface in B's note.
    mine = make_note(b, "Secret thesis")
    make_note(a, "A second note", "mentions Shared title and links [[Secret thesis]]")
    shared = make_note(b, "Shared title")
    assert b.get(f"/notes/{mine['id']}").json()["backlinks"] == []
    assert b.get(f"/notes/{shared['id']}").json()["backlinks"] == []
    assert b.get(f"/notes/{shared['id']}").json()["unlinked_mentions"] == []
    assert a.get(url).json()["title"] == "Secret thesis"


def test_a_note_cannot_be_attached_to_someone_elses_company(new_user):
    a, b = new_user(), new_user()
    company = a.post("/subjects", json={"name": "A's company"}).json()
    assert b.post("/notes", json={"title": "x", "blocks": [], "subject_id": company["id"]}).status_code == 404


def test_history_cannot_be_rewritten_even_by_the_api_role(new_user, urls):
    a = new_user()
    make_note(a, "Immutable", "original")
    with psycopg.connect(urls["app"]) as conn:
        conn.execute("SELECT set_config('app.user_id', %s, true)", (a.user_id,))
        assert conn.execute("SELECT count(*) FROM note_version").fetchone()[0] == 1
        for statement in ("UPDATE note_version SET body = 'rewritten'", "DELETE FROM note_version"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)
            conn.rollback()
            conn.execute("SELECT set_config('app.user_id', %s, true)", (a.user_id,))


def test_oversized_note_is_refused(new_user):
    a = new_user()
    r = a.post("/notes", json={"title": "Huge", "blocks": [block("b1", "x" * 2_100_000)]})
    assert r.status_code == 413
