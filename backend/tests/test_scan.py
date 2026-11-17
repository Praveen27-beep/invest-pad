"""Contradiction scan: suggestions only, quotations checked, user decides, deletion removes them."""

import pytest

from tests.test_assistant import connect
from tests.test_documents import pdf, upload

PAGE = ("Our largest customer gave notice that it will move its trading to a rival exchange from April.\n"
        "Volumes grew 12 percent in the year.")


@pytest.fixture
def co(new_user):
    c = new_user()
    c.subject = c.post("/subjects", json={"name": "Northgate"}).json()["id"]
    c.assumption = c.post(f"/subjects/{c.subject}/assumptions",
                          json={"body": "Customers will keep trading on the exchange", "basis": "judgement"}).json()["id"]
    c.doc = upload(c, c.subject, pdf(PAGE), "Q2 update.pdf").json()["id"]
    return c


def suggestions(c):
    return c.get(f"/subjects/{c.subject}/thesis").json()["assumptions"][0]["suggestions"]


def test_a_checked_contradiction_becomes_a_suggestion_not_evidence(co, model):
    connect(co)
    model.reply = {"contradictions": [
        {"assumption": "A1", "source": "S1", "quote": "Our largest customer gave notice that it will move its trading",
         "reason": "The largest customer is leaving, which cuts against customers staying."},
        {"assumption": "A1", "source": "S1", "quote": "Customers are all leaving next week",   # not in the passage
         "reason": "Invented."},
        {"assumption": "A9", "source": "S1", "quote": "Volumes grew 12 percent in the year", "reason": "No such assumption."},
    ]}
    r = co.post(f"/documents/{co.doc}/scan").json()
    assert r["found"] == 1 and "2 suggestion(s)" in r["note"]
    assert "Customers will keep trading" in model.calls[0]["user"] and "largest customer" in model.calls[0]["user"]
    s = suggestions(co)
    assert len(s) == 1 and s[0]["document_title"] == "Q2 update"
    thesis = co.get(f"/subjects/{co.subject}/thesis").json()["assumptions"][0]
    assert thesis["evidence"] == [] and thesis["state"] == "holds"       # nothing changes until the user decides

    assert co.post(f"/documents/{co.doc}/scan").json()["found"] == 1      # rescan does not duplicate
    assert len(suggestions(co)) == 1

    e = co.post(f"/suggestions/{s[0]['id']}/accept").json()
    assert e["evidence_id"]
    ev = co.get(f"/subjects/{co.subject}/thesis").json()["assumptions"][0]["evidence"]
    assert [(x["direction"], x["kind"]) for x in ev] == [("against", "ai")] and "largest customer" in ev[0]["passage"]
    assert suggestions(co) == []
    assert co.post(f"/suggestions/{s[0]['id']}/accept").status_code == 404


def test_numbers_and_advice_are_dropped(co, model):
    connect(co)
    model.reply = {"contradictions": [
        {"assumption": "A1", "source": "S1", "quote": "Our largest customer gave notice that it will move its trading",
         "reason": "Loses 40 percent of volume."},                                  # number not in the quote
        {"assumption": "A1", "source": "S1", "quote": "Our largest customer gave notice that it will move its trading",
         "reason": "You should sell before April."}]}
    assert co.post(f"/documents/{co.doc}/scan").json()["found"] == 0


def test_dismiss_and_delete(co, model, owner):
    connect(co)
    model.reply = {"contradictions": [{"assumption": "A1", "source": "S1", "reason": "The largest customer is leaving.",
                                       "quote": "Our largest customer gave notice that it will move its trading"}]}
    co.post(f"/documents/{co.doc}/scan")
    sid = suggestions(co)[0]["id"]
    assert co.post(f"/suggestions/{sid}/dismiss").json() == {"dismissed": True}
    assert suggestions(co) == []
    assert co.delete(f"/documents/{co.doc}").status_code == 204
    assert owner.execute("SELECT count(*) FROM evidence_suggestion WHERE owner_id = %s", (co.user_id,)).fetchone()[0] == 0


def test_nothing_is_sent_without_a_model_or_assumptions(co, model, new_user):
    assert "No model" in co.post(f"/documents/{co.doc}/scan").json()["note"]
    assert model.calls == []
    other = new_user()
    assert other.post(f"/documents/{co.doc}/scan").status_code == 404
