"""Editable checklists: built-ins as the start, every edit kept, runs record the version."""

import pytest


@pytest.fixture
def co(new_user):
    c = new_user()
    c.subject = c.post("/subjects", json={"name": "Northgate"}).json()["id"]
    return c


def answer_all(c, key, answer="no"):
    items = next(x for x in c.get("/checklists").json() if x["key"] == key)["items"]
    return c.post(f"/subjects/{c.subject}/checklists/{key}",
                  json={"items": [{"id": i["id"], "answer": answer} for i in items]})


def test_builtins_include_red_flags_and_forensic(co):
    lists = {x["key"]: x for x in co.get("/checklists").json()}
    assert {"red-flags", "forensic"} <= set(lists)
    assert lists["forensic"]["seq"] == 0 and lists["forensic"]["builtin"] and not lists["forensic"]["edited"]
    assert any("−1.78" in i["text"] for i in lists["forensic"]["items"])


def test_editing_a_builtin_keeps_ids_and_records_the_version(co, new_user, owner):
    first = answer_all(co, "red-flags").json()
    assert first["checklist_seq"] == 0
    rf = next(x for x in co.get("/checklists").json() if x["key"] == "red-flags")
    kept = rf["items"][0]
    items = [{"id": kept["id"], "text": kept["text"] + " (check the last five years)"},
             {"text": "Has the promoter sold shares in the last year?"}]
    saved = co.put("/checklists/red-flags", json={"title": "My red flags", "items": items}).json()
    assert saved["seq"] == 1 and saved["edited"] and saved["title"] == "My red flags"
    assert saved["items"][0]["id"] == kept["id"] and saved["items"][1]["id"].startswith("i-")

    run = answer_all(co, "red-flags", "yes").json()
    assert run["checklist_seq"] == 1 and [i["text"] for i in run["items"]][1] == "Has the promoter sold shares in the last year?"
    # The earlier run still reads with the wording it was answered against.
    old = owner.execute("SELECT items FROM checklist_run WHERE id = %s", (first["id"],)).fetchone()[0]
    assert len(old) == len(rf["items"]) and old[0]["text"] == kept["text"]
    # Another user still sees the built-in.
    other = next(x for x in new_user().get("/checklists").json() if x["key"] == "red-flags")
    assert other["seq"] == 0 and other["title"] != "My red flags"


def test_writing_a_new_checklist(co):
    made = co.put("/checklists/new", json={"title": "Management quality", "intro": "From concalls.",
                                          "items": [{"text": "Did guidance from two years ago come true?"},
                                                    {"text": "Did guidance from two years ago come true?"},   # duplicate
                                                    {"text": "Is capital allocation explained?"}]}).json()
    assert made["key"] == "management-quality" and len(made["items"]) == 2 and not made["builtin"]
    again = co.put("/checklists/new", json={"title": "Management quality", "items": [{"text": "x?"}]}).json()
    assert again["key"] == "management-quality-2"
    assert answer_all(co, "management-quality").status_code == 201


def test_checks(co, new_user):
    assert co.put("/checklists/nope", json={"title": "x", "items": [{"text": "y"}]}).status_code == 404
    assert co.put("/checklists/red-flags", json={"title": "x", "items": []}).status_code == 422
    assert co.post(f"/subjects/{co.subject}/checklists/red-flags", json={"items": []}).status_code == 422
    co.put("/checklists/new", json={"title": "Private list", "items": [{"text": "Mine?"}]})
    other = new_user()
    assert "private-list" not in {x["key"] for x in other.get("/checklists").json()}
    assert other.put("/checklists/private-list", json={"title": "x", "items": [{"text": "y"}]}).status_code == 404
