"""ingest/gmail_oauth.py -- exercised against a fake Gmail service.

No network, no credentials, no mailbox. The point of the adapter's shape is that the
Gmail client is injected, so the pagination and MIME-walking logic -- which is where the
bugs actually live -- is testable without any of that.
"""

from __future__ import annotations

import base64
from datetime import date, datetime
from typing import Any

from app.ingest.gmail_oauth import (
    KNOWN_SENDERS,
    SCOPES,
    MailDocument,
    build_query,
    fetch_documents,
    poll,
    retroactive_scan,
)


def encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode()


class FakeGmail:
    """Minimal stand-in for the Gmail client, including its paging behaviour."""

    def __init__(self, messages: dict[str, dict[str, Any]], page_size: int = 2):
        self._messages = messages
        self._page_size = page_size
        self.list_calls = 0

    # the client's fluent shape: service.users().messages().get(...).execute()
    def users(self):
        return self

    def messages(self):
        return self

    def attachments(self):
        return _Attachments(self._messages)

    def list(self, userId, q, maxResults, pageToken=None):  # noqa: N803 - Google's API
        self.list_calls += 1
        ids = sorted(self._messages)
        start = int(pageToken or 0)
        page = ids[start : start + self._page_size]
        nxt = start + self._page_size
        return _Execute(
            {
                "messages": [{"id": i} for i in page],
                **({"nextPageToken": str(nxt)} if nxt < len(ids) else {}),
            }
        )

    def get(self, userId, id, format):  # noqa: A002, N803 - Google's API
        return _Execute(self._messages[id])


class _Attachments:
    def __init__(self, messages):
        self._messages = messages

    def get(self, userId, messageId, id):  # noqa: A002, N803 - Google's API
        return _Execute({"data": self._messages[messageId]["_attachments"][id]})


class _Execute:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


def message(
    mid: str, sender: str, filename: str, body: bytes, day: str, inline: bool = True
) -> dict[str, Any]:
    epoch_ms = int(datetime.fromisoformat(f"{day}T00:00:00").timestamp() * 1000)
    part: dict[str, Any] = {"filename": filename}
    attachments: dict[str, str] = {}
    if inline:
        part["body"] = {"data": encode(body)}
    else:
        part["body"] = {"attachmentId": f"att-{mid}"}
        attachments[f"att-{mid}"] = encode(body)
    return {
        "internalDate": str(epoch_ms),
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": f"Statement {mid}"},
            ],
            # nested one level deep, as real multipart mail is
            "parts": [{"filename": "", "body": {}}, {"parts": [part]}],
        },
        "_attachments": attachments,
    }


CDSL = "CDSL <donotreply@cdslindia.co.in>"
ZERODHA = "Zerodha <noreply@zerodha.net>"


def test_scope_is_read_only() -> None:
    """Never widen this. A wider scope buys nothing and costs review burden."""
    assert SCOPES == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert all("readonly" in s for s in SCOPES)


def test_query_targets_known_senders_with_attachments() -> None:
    q = build_query()
    assert "has:attachment" in q
    assert "from:donotreply@cdslindia.co.in" in q
    assert "after:" not in q, "an unbounded query is what makes the scan retroactive"


def test_query_bounds_on_a_date_when_polling() -> None:
    assert "after:2026/04/01" in build_query(after=date(2026, 4, 1))


def test_retroactive_scan_pages_through_everything() -> None:
    """Gmail caps a page at 500. Stopping at page one silently truncates history."""
    msgs = {
        f"m{i}": message(f"m{i}", CDSL, f"cas{i}.pdf", b"%PDF-1.4", "2026-01-05")
        for i in range(5)
    }
    service = FakeGmail(msgs, page_size=2)
    found = list(retroactive_scan(service))
    assert len(found) == 5
    assert service.list_calls == 3, "5 messages at 2 per page must take 3 requests"


def test_attachments_are_fetched_when_stored_out_of_line() -> None:
    """Large attachments arrive as an id to fetch separately, not inline."""
    msgs = {"m1": message("m1", CDSL, "cas.pdf", b"%PDF-BIG", "2026-01-05", inline=False)}
    (doc,) = fetch_documents(FakeGmail(msgs), "m1")
    assert doc.content == b"%PDF-BIG"


def test_document_carries_provenance_and_classification() -> None:
    msgs = {"m1": message("m1", ZERODHA, "cn.pdf", b"%PDF", "2026-02-11")}
    (doc,) = fetch_documents(FakeGmail(msgs), "m1")
    assert isinstance(doc, MailDocument)
    assert doc.doctype == "CONTRACT_NOTE"
    assert doc.received == date(2026, 2, 11)
    assert doc.suggested_source == "EMAIL"
    assert doc.message_id == "m1"


def test_classification_is_by_sender_not_content() -> None:
    """Zerodha sends four document types from one address; sniffing misclassifies."""
    cas = fetch_documents(FakeGmail({"a": message("a", CDSL, "x.pdf", b"1", "2026-01-01")}), "a")
    cn = fetch_documents(FakeGmail({"b": message("b", ZERODHA, "x.pdf", b"1", "2026-01-01")}), "b")
    assert cas[0].doctype == "CAS"
    assert cn[0].doctype == "CONTRACT_NOTE"


def test_unwanted_attachments_are_skipped() -> None:
    msgs = {"m1": message("m1", CDSL, "logo.png", b"\x89PNG", "2026-01-05")}
    assert fetch_documents(FakeGmail(msgs), "m1") == []


def test_poll_rewinds_a_day_and_advances_the_mark() -> None:
    """Gmail's after: is day-granular, so overlap is deliberate -- dedupe absorbs it."""
    msgs = {"m1": message("m1", CDSL, "cas.pdf", b"%PDF", "2026-03-10")}
    docs, mark = poll(FakeGmail(msgs), date(2026, 3, 1))
    assert len(docs) == 1
    assert mark == date(2026, 3, 10)


def test_poll_never_moves_the_mark_backwards() -> None:
    docs, mark = poll(FakeGmail({}), date(2026, 3, 1))
    assert docs == []
    assert mark == date(2026, 3, 1)


def test_adapter_produces_documents_only() -> None:
    """The layer boundary: attachments out, nothing else.

    No Transaction, no valuation, no ledger write. Parsing belongs to the contract-note
    parser, which is what lets it be tested with no mailbox in the loop.
    """
    msgs = {"m1": message("m1", CDSL, "cas.pdf", b"%PDF", "2026-01-05")}
    assert all(isinstance(d, MailDocument) for d in retroactive_scan(FakeGmail(msgs)))


def test_known_senders_cover_both_depositories_and_the_brokers() -> None:
    assert {"CAS", "CONTRACT_NOTE"} == set(KNOWN_SENDERS.values())
    assert any("cdsl" in s for s in KNOWN_SENDERS)
    assert any("nsdl" in s for s in KNOWN_SENDERS)
