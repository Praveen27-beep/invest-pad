"""Ask can answer "why did I buy?" from the decision record, citing the decision."""

import re

import pytest

from tests.test_assistant import ask_q, claim, connect
from tests.test_documents import pdf, upload

REASON = "Market share held at ninety percent even after the coupling announcement."


@pytest.fixture
def co(new_user):
    c = new_user()
    c.subject = c.post("/subjects", json={"name": "Northgate"}).json()["id"]
    upload(c, c.subject, pdf("Revenue from operations was 608 crore in FY25."), "AR.pdf")
    a = c.post(f"/subjects/{c.subject}/assumptions", json={"body": "Share stays above 80%", "basis": "judgement"}).json()["id"]
    r = c.post(f"/subjects/{c.subject}/decisions", json={"type": "bought", "decided_on": "2026-03-02", "decisive_reason": REASON,
                                                        "would_change_mind": "Share below 80%", "assumption_ids": [a]})
    assert r.status_code == 201, r.text
    c.assumption = a
    return c


def decision_source(model) -> str:
    sent = model.calls[0]["user"]
    return re.search(r'<source id="(S\d+)" from="My decision', sent).group(1)


def test_why_did_i_buy_cites_the_decision(co, model):
    connect(co)
    model.reply = {"claims": []}
    ask_q(co, "Why did I buy this?")
    sent = model.calls[0]["user"]
    assert "My decision: Bought, 2026-03-02" in sent and REASON in sent and "Share stays above 80%" in sent
    sid = decision_source(model)

    model.reply = {"claims": [claim("You bought because share held at ninety percent.", REASON, source=sid)]}
    a = ask_q(co, "Why did I buy this?")
    assert a["outcome"] == "answered"
    c = a["claims"][0]
    assert c["decision_id"] and c["decision_type"] == "bought" and str(c["decision_date"]) == "2026-03-02"
    assert c["document_id"] is None and c["note_id"] is None
    # Your own decision is not evidence for the assumptions under it.
    r = co.post(f"/claims/{c['id']}/accept", json={"assumption_id": co.assumption, "direction": "for"})
    assert r.status_code == 422


def test_unscoped_question_finds_the_company_by_name(co, model):
    connect(co)
    model.reply = {"claims": []}
    co.post("/questions", json={"body": "Why did I buy Northgate?"})
    assert "My decision: Bought" in model.calls[0]["user"]
    co.post("/questions", json={"body": "Why did I buy anything?"})
    assert all("My decision" not in c["user"] for c in model.calls[1:])   # no company named: no decisions sent


def test_a_misquoted_decision_is_dropped_and_others_never_see_it(co, model, new_user, app):
    connect(co)
    model.reply = {"claims": []}
    ask_q(co, "Why did I buy this?")
    sid = decision_source(model)
    model.reply = {"claims": [claim("You bought for the dividend.", "I bought it for the dividend yield", source=sid)]}
    assert ask_q(co, "Why did I buy this?")["outcome"] == "unknown"

    other = new_user()
    other.subject = other.post("/subjects", json={"name": "Northgate"}).json()["id"]
    connect(other)
    model.calls.clear()
    model.reply = {"claims": []}
    other.post("/questions", json={"body": "Why did I buy Northgate?", "subject_id": other.subject})
    assert all(REASON not in c["user"] for c in model.calls)


def test_deleting_the_company_removes_decision_claims(co, model, owner):
    connect(co)
    model.reply = {"claims": []}
    ask_q(co, "Why did I buy this?")
    model.reply = {"claims": [claim("Share held.", REASON, source=decision_source(model))]}
    ask_q(co, "Why did I buy this?")
    assert owner.execute("SELECT count(*) FROM citation WHERE owner_id = %s AND decision_id IS NOT NULL",
                         (co.user_id,)).fetchone()[0] == 1
    assert co.delete(f"/subjects/{co.subject}").status_code == 204
    assert owner.execute("SELECT count(*) FROM citation WHERE owner_id = %s", (co.user_id,)).fetchone()[0] == 0
    assert owner.execute("SELECT count(*) FROM claim WHERE owner_id = %s", (co.user_id,)).fetchone()[0] == 0
