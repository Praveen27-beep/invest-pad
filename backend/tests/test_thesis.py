"""Thesis versions and diffs, assumptions, evidence, decisions, checklist, and the reopen view."""

from datetime import date, timedelta

import psycopg
import pytest

from app.thesis import diff
from tests.test_documents import pdf, upload


@pytest.fixture
def co(new_user):
    client = new_user()
    client.subject = client.post("/subjects", json={"name": "Northgate Power Exchange"}).json()["id"]
    client.base = f"/subjects/{client.subject}"
    return client


def assume(client, text, basis="judgement"):
    return client.post(f"{client.base}/assumptions", json={"body": text, "basis": basis}).json()["id"]


def passage(client, text="Management said share loss in the day-ahead market could be 20 to 40 percent."):
    doc = upload(client, client.subject, pdf(text), f"call-{abs(hash(text))}.pdf").json()
    return doc["id"], client.get(f"/documents/{doc['id']}/passages").json()[0]["id"]


def test_thesis_versions_and_diff(co):
    assert co.get(f"{co.base}/thesis").json() == {"seq": 0, "body": "", "versions": [], "assumptions": []}
    assert co.put(f"{co.base}/thesis", json={"body": "Exchange keeps share after coupling."}).json()["seq"] == 1
    assert co.put(f"{co.base}/thesis", json={"body": "Exchange keeps share after coupling."}).json()["saved"] is False
    assert co.put(f"{co.base}/thesis", json={"body": "Exchange keeps most share after coupling. Gas adds upside."}
                  ).json() == {"seq": 2, "saved": True}

    thesis = co.get(f"{co.base}/thesis").json()
    assert thesis["seq"] == 2 and thesis["body"].endswith("Gas adds upside.")
    assert [v["seq"] for v in thesis["versions"]] == [2, 1]

    changes = co.get(f"{co.base}/thesis/diff", params={"a": 1, "b": 2}).json()["changes"]
    inserted = [c["text"].strip() for c in changes if c["op"] == "insert"]
    assert inserted == ["most", "Gas adds upside."]
    assert not [c for c in changes if c["op"] == "delete"]
    assert co.get(f"{co.base}/thesis/diff", params={"a": 1, "b": 9}).status_code == 404


def test_diff_reconstructs_both_sides():
    old, new = "Margins stay above 80%.\nNo debt.", "Margins stay near 75%.\nNo debt. Fee cut is a risk."
    ops = diff(old, new)
    assert "".join(o["text"] for o in ops if o["op"] != "insert") == old
    assert "".join(o["text"] for o in ops if o["op"] != "delete") == new
    assert diff("same", "same") == [{"op": "equal", "text": "same"}] and diff("", "") == []


def test_assumption_changes_are_versions_and_state_changes_need_a_reason(co):
    a = assume(co, "Participants will not move to other exchanges.")
    url = f"/assumptions/{a}"
    same = {"body": "Participants will not move to other exchanges.", "basis": "judgement", "state": "holds"}
    assert co.put(url, json=same).json()["saved"] is False
    assert co.put(url, json={**same, "state": "challenged"}).status_code == 422
    r = co.put(url, json={**same, "state": "challenged", "reason": "A large trader said it now uses all three."})
    assert r.json() == {"id": a, "seq": 2, "saved": True}
    assert co.put(url, json={**same, "state": "challenged", "body": "Most participants will stay."}).json()["seq"] == 3

    versions = co.get(f"{url}/versions").json()
    assert [(v["seq"], v["state"]) for v in versions] == [(3, "challenged"), (2, "challenged"), (1, "holds")]
    assert versions[1]["reason"].startswith("A large trader")
    [now] = co.get(f"{co.base}/thesis").json()["assumptions"]
    assert (now["seq"], now["body"], now["state"]) == (3, "Most participants will stay.", "challenged")


def test_fact_evidence_must_cite_a_passage_from_this_company(co):
    a = assume(co, "Share loss will be limited.", basis="fact")
    doc_id, chunk_id = passage(co)
    other = co.post("/subjects", json={"name": "Other Co"}).json()["id"]
    other_chunk = co.get(f"/documents/{upload(co, other, pdf('Other text here.'), 'o.pdf').json()['id']}/passages"
                         ).json()[0]["id"]
    url = f"/assumptions/{a}/evidence"

    assert co.post(url, json={"direction": "for", "kind": "fact", "body": "They guide to 20-40%."}).status_code == 422
    assert co.post(url, json={"direction": "for", "kind": "fact", "body": "x", "chunk_id": other_chunk}).status_code == 404
    assert co.post(url, json={"direction": "for", "kind": "ai", "body": "x"}).status_code == 422
    assert co.post(url, json={"direction": "against", "kind": "fact", "body": "Management's own range is wide.",
                              "chunk_id": chunk_id}).status_code == 201
    assert co.post(url, json={"direction": "for", "kind": "opinion", "body": "Switching costs are real."}).status_code == 201

    fact, opinion = co.get(f"{co.base}/thesis").json()["assumptions"][0]["evidence"]
    assert (fact["kind"], fact["direction"], fact["is_sourced_fact"], fact["page_label"]) == ("fact", "against", True, "p. 1")
    assert "20 to 40 percent" in fact["passage"] and fact["document_id"] == doc_id
    assert (opinion["kind"], opinion["is_sourced_fact"], opinion["passage"]) == ("opinion", False, None)


def test_deleting_the_document_demotes_the_fact_and_removes_the_passage(co, owner):
    a = assume(co, "Share loss will be limited.", basis="fact")
    doc_id, chunk_id = passage(co, "Unique marker numbat-4410 appears in this passage only.")
    co.post(f"/assumptions/{a}/evidence", json={"direction": "for", "kind": "fact", "chunk_id": chunk_id,
                                                "body": "In my words: management expects limited loss."})
    assert co.delete(f"/documents/{doc_id}").status_code == 204

    [e] = co.get(f"{co.base}/thesis").json()["assumptions"][0]["evidence"]
    assert e["source_deleted"] is True and e["is_sourced_fact"] is False
    assert e["chunk_id"] is None and e["passage"] is None
    assert e["body"] == "In my words: management expects limited loss."     # the investor's own words stay
    left = owner.execute("SELECT count(*) FROM evidence WHERE to_jsonb(evidence)::text LIKE '%numbat-4410%'")
    assert left.fetchone()[0] == 0


def test_evidence_can_be_retracted_but_not_erased(co, owner):
    a = assume(co, "x holds")
    e = co.post(f"/assumptions/{a}/evidence", json={"direction": "for", "kind": "opinion", "body": "weak point"}).json()
    assert co.delete(f"/evidence/{e['id']}").status_code == 204
    assert co.delete(f"/evidence/{e['id']}").status_code == 404
    assert co.get(f"{co.base}/thesis").json()["assumptions"][0]["evidence"] == []
    assert owner.execute("SELECT count(*) FROM evidence WHERE id = %s", (e["id"],)).fetchone()[0] == 1


def test_decision_freezes_thesis_and_assumptions(co):
    co.put(f"{co.base}/thesis", json={"body": "v1"})
    a1, a2 = assume(co, "Coupling is limited to DAM."), assume(co, "Gas exchange adds upside.")
    body = {"type": "bought", "decided_on": str(date.today()), "assumption_ids": [a1],
            "decisive_reason": "Asymmetric: downside is part of DAM share, upside is a growing market.",
            "would_change_mind": "Coupling extended to RTM."}
    d = co.post(f"{co.base}/decisions", json=body)
    assert d.status_code == 201
    assert d.json()["position_seq"] == 1
    assert d.json()["assumptions"] == [{"id": a1, "seq": 1, "body": "Coupling is limited to DAM.",
                                       "basis": "judgement", "state": "holds"}]

    # Later changes do not touch what the journal recorded.
    co.put(f"{co.base}/thesis", json={"body": "v2"})
    co.put(f"/assumptions/{a1}", json={"body": "Coupling is limited to DAM.", "basis": "judgement",
                                       "state": "broken", "reason": "Regulator extended it to RTM."})
    [entry] = co.get(f"{co.base}/decisions").json()
    assert entry["position_seq"] == 1 and entry["assumptions"][0]["state"] == "holds"
    assert a2 not in str(entry["assumptions"])


def test_decision_rules(co, new_user):
    good = {"type": "passed", "decided_on": str(date.today()), "decisive_reason": "Governance: promoter pledge."}
    assert co.post(f"{co.base}/decisions", json={**good, "decisive_reason": "too short"}).status_code == 422
    assert co.post(f"{co.base}/decisions", json={**good, "type": "yolo"}).status_code == 422
    future = str(date.today() + timedelta(days=2))
    assert co.post(f"{co.base}/decisions", json={**good, "decided_on": future}).status_code == 422

    other = new_user()
    other.subject = other.post("/subjects", json={"name": "Theirs"}).json()["id"]
    other.base = f"/subjects/{other.subject}"
    foreign = assume(other, "not yours")
    assert co.post(f"{co.base}/decisions", json={**good, "assumption_ids": [foreign]}).status_code == 404
    # A decision needs no thesis: "passed after the red-flag check" is a complete entry.
    plain = co.post(f"{co.base}/decisions", json=good).json()
    assert plain["position_seq"] is None and plain["assumptions"] == []


def test_checklist_runs_are_kept(co):
    items = co.get("/pack").json()["checklists"]["red-flags"]["items"]
    answers = [{"id": i["id"], "answer": "unknown"} for i in items]
    assert co.get(f"{co.base}/checklists/red-flags").json()["runs"] == 0
    assert co.post(f"{co.base}/checklists/red-flags", json={"items": answers[:-1]}).status_code == 422
    assert co.post(f"{co.base}/checklists/nope", json={"items": answers}).status_code == 404
    assert co.post(f"{co.base}/checklists/red-flags", json={"items": answers}).status_code == 201
    answers[0] = {"id": items[0]["id"], "answer": "yes", "note": "Auditor resigned in FY24."}
    co.post(f"{co.base}/checklists/red-flags", json={"items": answers})

    latest = co.get(f"{co.base}/checklists/red-flags").json()
    assert latest["runs"] == 2
    assert latest["items"][0] == {"id": items[0]["id"], "text": items[0]["text"], "answer": "yes",
                                  "note": "Auditor resigned in FY24."}


def test_reopen_view_returns_the_decisive_reason_without_any_document(co):
    """The success test, at the API: one call gives the decision, the reason in the
    investor's own words, what it rested on, how that stands now, and what changed since."""
    empty = co.get(f"{co.base}/overview").json()
    assert empty["decision"] is None and empty["changes"]["since"] is None

    co.put(f"{co.base}/thesis", json={"body": "Incumbent keeps share; new markets add growth."})
    a1, a2 = assume(co, "Coupling is limited to the day-ahead market."), assume(co, "Participants stay put.")
    reason = "Governance is clean and the downside is limited to part of DAM; I opened a small position."
    co.post(f"{co.base}/decisions", json={"type": "bought", "decided_on": str(date.today()),
                                          "decisive_reason": reason, "assumption_ids": [a1, a2],
                                          "would_change_mind": "Coupling extended to the real-time market."})

    # Time passes: an assumption breaks, the thesis is revised, new material arrives.
    co.put(f"/assumptions/{a1}", json={"body": "Coupling is limited to the day-ahead market.", "basis": "judgement",
                                       "state": "broken", "reason": "Order extends coupling to RTM."})
    co.put(f"{co.base}/thesis", json={"body": "Incumbent keeps most share; new markets add growth."})
    co.post("/notes", json={"title": "RTM order", "subject_id": co.subject, "blocks": []})
    upload(co, co.subject, pdf("New concall text."), "Q3FY27 concall.pdf")

    view = co.get(f"{co.base}/overview").json()
    d = view["decision"]
    assert (d["type_label"], d["decisive_reason"], d["would_change_mind"]) == (
        "Bought", reason, "Coupling extended to the real-time market.")
    assert d["thesis_changed"] is True
    then_a1, then_a2 = d["assumptions"]
    assert then_a1["state"] == "holds" and then_a1["now"]["state"] == "broken" and then_a1["now"]["changed"] is True
    assert then_a1["now"]["reason"] == "Order extends coupling to RTM."
    assert then_a2["now"]["changed"] is False

    changes = view["changes"]
    assert [n["title"] for n in changes["notes"]] == ["RTM order"]
    assert [x["doc_type"] for x in changes["documents"]] == ["concall"]
    assert [(x["id"], x["state"]) for x in changes["assumptions"]] == [(a1, "broken")]
    assert changes["thesis_versions"] == 1


def test_open_questions_appear_on_the_reopen_view(co, app):
    from tests.test_capture import extension
    ext = extension(app, co)
    ext.post("/ext/captures", json={"client_id": "q-00000001", "kind": "question", "subject_id": co.subject,
                                    "body": "Does coupling reach RTM?"})
    ext.post("/ext/captures", json={"client_id": "n-00000001", "kind": "note", "subject_id": co.subject, "body": "fyi"})
    assert [q["body"] for q in co.get(f"{co.base}/overview").json()["open_questions"]] == ["Does coupling reach RTM?"]


def test_other_users_cannot_reach_any_of_it(co, new_user):
    co.put(f"{co.base}/thesis", json={"body": "private thesis"})
    a = assume(co, "private assumption")
    e = co.post(f"/assumptions/{a}/evidence", json={"direction": "for", "kind": "opinion", "body": "private"}).json()
    co.post(f"{co.base}/decisions", json={"type": "passed", "decided_on": str(date.today()),
                                          "decisive_reason": "private decisive reason"})
    b = new_user()
    for path in ("thesis", "overview"):
        assert b.get(f"{co.base}/{path}").status_code == 404
    assert b.get(f"{co.base}/decisions").json() == []
    assert b.get(f"{co.base}/thesis/diff", params={"a": 1, "b": 1}).status_code == 404
    assert b.put(f"{co.base}/thesis", json={"body": "hijack"}).status_code == 404
    assert b.post(f"{co.base}/assumptions", json={"body": "x", "basis": "fact"}).status_code == 404
    assert b.get(f"/assumptions/{a}/versions").status_code == 404
    assert b.put(f"/assumptions/{a}", json={"body": "x", "basis": "fact", "state": "broken", "reason": "r"}).status_code == 404
    assert b.post(f"/assumptions/{a}/evidence", json={"direction": "for", "kind": "opinion", "body": "x"}).status_code == 404
    assert b.delete(f"/evidence/{e['id']}").status_code == 404
    assert b.post(f"{co.base}/decisions", json={"type": "passed", "decided_on": str(date.today()),
                                                "decisive_reason": "not my company"}).status_code == 404
    assert b.get(f"{co.base}/checklists/red-flags").json()["runs"] == 0
    assert co.get(f"{co.base}/thesis").json()["body"] == "private thesis"


@pytest.mark.parametrize("statement", [
    "UPDATE position_version SET body = 'rewritten'", "DELETE FROM position_version",
    "UPDATE assumption_version SET state = 'holds'", "DELETE FROM assumption_version",
    "UPDATE decision SET decisive_reason = 'a different reason entirely'", "DELETE FROM decision",
    "DELETE FROM evidence", "UPDATE checklist_run SET items = '[]'",
])
def test_the_api_role_cannot_rewrite_the_record(co, urls, statement):
    co.put(f"{co.base}/thesis", json={"body": "v1"})
    with psycopg.connect(urls["app"]) as conn:
        conn.execute("SELECT set_config('app.user_id', %s, true)", (co.user_id,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(statement)
