"""Extension tokens, captures and the inbox."""

from fastapi.testclient import TestClient

EXT_ORIGIN = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"


def extension(app, new_user_client, label="Laptop Chrome"):
    """Create a token for a user and return a cookie-less client that uses it."""
    token = new_user_client.post("/tokens", json={"label": label}).json()
    client = TestClient(app, headers={"Authorization": f"Bearer {token['token']}", "Origin": EXT_ORIGIN})
    client.token_id = token["id"]
    return client


def cap(client_id="capture-0001", **extra):
    return {"client_id": client_id, "kind": "question", "body": "Does coupling apply to RTM?", **extra}


def test_capture_arrives_in_the_inbox_with_its_context(app, new_user):
    a = new_user()
    ext = extension(app, a)
    r = ext.post("/ext/captures", json=cap(
        selection="Coupling of DAM begins January 2026.", url="https://example.com/article?id=7",
        page_title="CERC order explained", captured_at="2026-11-01T09:30:00+05:30"))
    assert r.status_code == 201 and r.json() == {"saved": True}

    [item] = a.get("/captures").json()
    assert item["kind"] == "question" and item["body"] == "Does coupling apply to RTM?"
    assert item["selection"] == "Coupling of DAM begins January 2026."
    assert item["url"] == "https://example.com/article?id=7" and item["page_title"] == "CERC order explained"
    assert item["captured_at"].startswith("2026-11-01T04:00:00")   # stored in UTC
    assert item["status"] == "inbox" and item["subject_id"] is None


def test_retrying_the_same_capture_does_not_duplicate_it(app, new_user):
    a = new_user()
    ext = extension(app, a)
    assert ext.post("/ext/captures", json=cap()).json() == {"saved": True}
    assert ext.post("/ext/captures", json=cap()).json() == {"saved": False}
    assert len(a.get("/captures").json()) == 1


def test_extension_can_pick_a_company_but_only_its_owners(app, new_user):
    a, b = new_user(), new_user()
    mine = a.post("/subjects", json={"name": "IEX"}).json()
    theirs = b.post("/subjects", json={"name": "B's company"}).json()
    ext = extension(app, a)

    assert ext.get("/ext/subjects").json() == [{"id": mine["id"], "name": "IEX"}]
    assert ext.post("/ext/captures", json=cap("capture-mine", subject_id=mine["id"])).status_code == 201
    assert ext.post("/ext/captures", json=cap("capture-theirs", subject_id=theirs["id"])).status_code == 404
    assert [c["subject_id"] for c in a.get("/captures").json()] == [mine["id"]]
    assert b.get("/captures").json() == []


def test_token_can_do_nothing_else(app, new_user):
    a = new_user()
    note = a.post("/notes", json={"title": "Private", "blocks": []}).json()
    ext = extension(app, a)
    ext.post("/ext/captures", json=cap())
    for method, path in [("get", "/captures"), ("get", "/notes"), ("get", f"/notes/{note['id']}"),
                         ("get", "/subjects"), ("get", "/search?q=x"), ("get", "/auth/me"), ("get", "/tokens"),
                         ("post", "/tokens"), ("delete", f"/notes/{note['id']}")]:
        assert getattr(ext, method)(path).status_code == 401, path


def test_bad_revoked_and_missing_tokens_are_refused(app, new_user):
    a = new_user()
    ext = extension(app, a)
    assert ext.post("/ext/captures", json=cap("capture-before")).status_code == 201

    assert TestClient(app).post("/ext/captures", json=cap()).status_code == 401
    wrong = TestClient(app, headers={"Authorization": "Bearer ipx_not-a-real-token"})
    assert wrong.post("/ext/captures", json=cap()).status_code == 401
    # A signed-in browser session is not a token.
    assert a.post("/ext/captures", json=cap()).status_code == 401

    assert a.delete(f"/tokens/{ext.token_id}").status_code == 204
    assert ext.post("/ext/captures", json=cap("capture-after")).status_code == 401
    assert ext.get("/ext/subjects").status_code == 401
    assert a.delete(f"/tokens/{ext.token_id}").status_code == 404      # already revoked
    assert len(a.get("/captures").json()) == 1


def test_token_is_shown_once_and_stored_only_as_a_hash(app, new_user, owner):
    a, b = new_user(), new_user()
    created = a.post("/tokens", json={"label": "Work laptop"}).json()
    assert created["token"].startswith("ipx_")

    [listed] = a.get("/tokens").json()
    assert listed["label"] == "Work laptop" and "token" not in listed and listed["last_used_at"] is None
    assert b.get("/tokens").json() == []
    assert b.delete(f"/tokens/{created['id']}").status_code == 404

    stored = owner.execute("SELECT token_hash FROM extension_token WHERE id = %s", (created["id"],)).fetchone()[0]
    assert created["token"] not in stored and len(stored) == 64

    TestClient(app, headers={"Authorization": f"Bearer {created['token']}"}).get("/ext/subjects")
    assert a.get("/tokens").json()[0]["last_used_at"] is not None


def test_invalid_captures_are_rejected(app, new_user):
    ext = extension(app, new_user())
    assert ext.post("/ext/captures", json=cap(body="   ")).status_code == 422
    assert ext.post("/ext/captures", json=cap(kind="bookmark")).status_code == 422
    assert ext.post("/ext/captures", json=cap(body="x" * 20_001)).status_code == 422
    assert ext.post("/ext/captures", json=cap(client_id="bad id!")).status_code == 422


def test_inbox_assign_dismiss_restore_delete(app, new_user):
    a, b = new_user(), new_user()
    company = a.post("/subjects", json={"name": "IEX"}).json()
    other = b.post("/subjects", json={"name": "Not yours"}).json()
    extension(app, a).post("/ext/captures", json=cap())
    [item] = a.get("/captures").json()
    url = f"/captures/{item['id']}"

    assert a.patch(url, json={"subject_id": company["id"]}).json()["subject_id"] == company["id"]
    assert a.patch(url, json={"subject_id": other["id"]}).status_code == 404
    assert a.patch(url, json={}).status_code == 422

    assert a.patch(url, json={"status": "dismissed"}).json()["status"] == "dismissed"
    assert a.get("/captures").json() == []
    assert len(a.get("/captures", params={"status": "dismissed"}).json()) == 1
    assert a.patch(url, json={"status": "inbox"}).json()["subject_id"] == company["id"]   # company kept

    for method, kwargs in [("patch", {"json": {"status": "dismissed"}}), ("delete", {})]:
        assert getattr(b, method)(url, **kwargs).status_code == 404
    assert b.post(f"{url}/note").status_code == 404

    assert a.delete(url).status_code == 204
    assert a.get("/captures").json() == []


def test_capture_becomes_a_note_with_its_source(app, new_user):
    a = new_user()
    company = a.post("/subjects", json={"name": "IEX"}).json()
    ext = extension(app, a)
    ext.post("/ext/captures", json=cap(
        "capture-one", kind="note", body="Fee cap may fall from 2 paise\nCheck the CERC order",
        selection="CERC retained the ceiling in 2023.", url="https://example.com/fees",
        page_title="Fee review", captured_at="2026-11-02T10:00:00Z", subject_id=company["id"]))
    ext.post("/ext/captures", json=cap("capture-two", kind="note", body="Fee cap may fall from 2 paise"))
    second, first = a.get("/captures").json()

    note_id = a.post(f"/captures/{first['id']}/note").json()["note_id"]
    assert a.post(f"/captures/{first['id']}/note").json()["note_id"] == note_id      # asking twice is safe
    note = a.get(f"/notes/{note_id}").json()
    assert note["title"] == "Fee cap may fall from 2 paise" and note["subject_id"] == company["id"]
    assert [b["type"] for b in note["blocks"]] == ["paragraph", "paragraph", "quote", "paragraph"]
    body = a.get(f"/notes/{note_id}/versions/1").json()
    assert "CERC retained the ceiling in 2023." in body["body"]
    assert "Source: Fee review — https://example.com/fees (captured 02 Nov 2026)" in body["body"]
    assert body["reason"] == "created from a capture"

    # Same first line again: the title gets a number instead of failing.
    other_id = a.post(f"/captures/{second['id']}/note").json()["note_id"]
    assert a.get(f"/notes/{other_id}").json()["title"] == "Fee cap may fall from 2 paise (2)"

    assert a.get("/captures").json() == []
    filed = a.get("/captures", params={"status": "filed"}).json()
    assert {c["note_id"] for c in filed} == {note_id, other_id}
    # Deleting the note leaves the capture, without the dangling pointer.
    a.delete(f"/notes/{note_id}")
    assert sorted(str(c["note_id"]) for c in a.get("/captures", params={"status": "filed"}).json()) == \
        sorted(["None", other_id])


def test_cookie_requests_still_need_a_trusted_origin(new_user):
    a = new_user()
    assert a.post("/tokens", json={"label": "x"}, headers={"Origin": EXT_ORIGIN}).status_code == 403
