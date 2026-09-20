"""ISIN-change circulars against a real database -- app.db.isin_change_circulars.

Uses the real Tata Steel circular text (NSE/CML/53019, confirmed live) end to end: the
symbol join against a seeded ``security`` row, the resulting DRAFT ``security_alias``
(effective_date the EX-date, not the w.e.f. date -- the two disagree on this exact
circular), and the circuit breaker in ``feed_poll_state`` across repeated failures.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, date, datetime, timedelta

import pytest
from app.db.isin_change_circulars import (
    _BREAKER_FAILURE_THRESHOLD,
    FEED_NAME,
    refresh_isin_change_feed,
)
from app.db.security_alias import list_aliases
from app.engine.corporate_actions import Verification
from app.ingest.isin_change_feed import IsinChangeFeedFetchFailed

pytestmark = pytest.mark.db

TATA_PDF_URL = "https://nsearchives.nseindia.com/content/circulars/CML53019.pdf"


def _minimal_pdf(lines: list[str]) -> bytes:
    """A hand-built, single-page PDF carrying ``lines`` as plain text -- no PDF-writing
    library is a dependency of this repo, and a real circular PDF cannot be committed
    (``make lint``'s "no client-document-shaped files" rule, and NSE's own content, not
    ours to commit either way). This is verified to round-trip through the same
    pdfplumber extraction ``app.ingest.isin_change_feed.extract_pdf_text`` uses -- see
    ``test_isin_change_feed.py`` for the real circular text this facsimile matches
    fact-for-fact (same Sub: line, same disagreeing w.e.f./Ex-date pair)."""

    def escape(s: str) -> str:
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    content = "\n".join(
        f"BT /F1 10 Tf 50 {750 - 14 * i} Td ({escape(line)}) Tj ET"
        for i, line in enumerate(lines)
    )
    stream = content.encode("latin-1")
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R >> >> "
        "/MediaBox [0 0 612 792] /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode("latin-1"))
        out.write(body.encode("latin-1"))
        out.write(b"\nendobj\n")
    xref_start = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode())
    out.write(f"startxref\n{xref_start}\n%%EOF".encode())
    return out.getvalue()


#: Same facts as the real NSE/CML/53019 circular (confirmed live, see
#: test_isin_change_feed.py's TATA_STEEL_TEXT), including the exact one-day disagreement
#: between the w.e.f. date and the Ex-date this test relies on.
TATA_STEEL_PDF = _minimal_pdf(
    [
        "Sub: Change in ISIN - Tata Steel Limited (TATASTEEL)",
        "company shall be changed w.e.f. July 29, 2022.",
        "Sr. No. Symbol Company Name New ISIN Remarks",
        "1 TATASTEEL Tata Steel Limited INE081A01020 Sub-Division from Rs. 10/- to Re. 1/-",
        "The new ISIN shall be effective for all trades done on and from the Ex-date "
        "date i.e., July 28, 2022.",
    ]
)


def _tata_listing_payload(circular_number: str = "53019") -> bytes:
    return json.dumps(
        {
            "data": [
                {
                    "cirDate": "20220720",
                    "circDisplayNo": f"NSE/CML/{circular_number}",
                    "circNumber": circular_number,
                    "sub": "Change in ISIN - Tata Steel Limited (TATASTEEL)",
                    "circFilelink": TATA_PDF_URL,
                }
            ]
        }
    ).encode()


class _FakeCircularSource:
    def __init__(
        self,
        listing_payload: bytes | None = None,
        pdf_bytes_by_url: dict[str, bytes] | None = None,
        list_exc: Exception | None = None,
    ) -> None:
        self.list_calls = 0
        self.pdf_calls = 0
        self._listing_payload = listing_payload if listing_payload is not None else b'{"data": []}'
        self._pdf_bytes_by_url = pdf_bytes_by_url or {}
        self._list_exc = list_exc

    def list_circulars(self, start: date, end: date) -> bytes:
        self.list_calls += 1
        if self._list_exc is not None:
            raise self._list_exc
        return self._listing_payload

    def fetch_pdf(self, url: str) -> bytes:
        self.pdf_calls += 1
        return self._pdf_bytes_by_url[url]


def _seed_security(db: object, isin: str, symbol: str) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO security (isin, symbol, exchange) VALUES (%s, %s, 'NSE') "
            "ON CONFLICT DO NOTHING",
            (isin, symbol),
        )
    db.commit()


def test_full_flow_creates_draft_alias_with_ex_date_not_wef_date(db: object) -> None:
    _seed_security(db, "INE081A01012", "TATASTEEL")
    source = _FakeCircularSource(
        listing_payload=_tata_listing_payload(),
        pdf_bytes_by_url={TATA_PDF_URL: TATA_STEEL_PDF},
    )

    result = refresh_isin_change_feed(db, date(2022, 1, 1), date(2022, 12, 31), source=source)

    assert result == {
        "fetched": 1, "aliases_created": 1, "skipped": 0,
        "breaker_open": False, "error": None,
    }

    with db.cursor() as cur:
        cur.execute(
            "SELECT old_isin, new_isin, alias_created, skip_reason, ex_date, wef_date "
            "FROM isin_change_circular WHERE circular_number = '53019'"
        )
        row = cur.fetchone()
    assert row == ("INE081A01012", "INE081A01020", True, None, date(2022, 7, 28), date(2022, 7, 29))

    aliases = [a for a in list_aliases(db) if a.old_isin == "INE081A01012"]
    assert len(aliases) == 1
    alias = aliases[0]
    assert alias.current_isin == "INE081A01020"
    # The EX-date, not the w.e.f. date -- they disagree on this real circular by one
    # day, and load_transactions must start applying the alias from the ex-date.
    assert alias.effective_date == date(2022, 7, 28)
    assert alias.verification == Verification.DRAFT  # inert until a human promotes it
    assert alias.source_url == TATA_PDF_URL
    assert "Sub-Division" in alias.notes


def test_symbol_unknown_records_circular_without_alias(db: object) -> None:
    # No security row for TATASTEEL at all.
    source = _FakeCircularSource(
        listing_payload=_tata_listing_payload(),
        pdf_bytes_by_url={TATA_PDF_URL: TATA_STEEL_PDF},
    )
    result = refresh_isin_change_feed(db, date(2022, 1, 1), date(2022, 12, 31), source=source)
    assert result["aliases_created"] == 0
    assert result["skipped"] == 1

    with db.cursor() as cur:
        cur.execute(
            "SELECT alias_created, skip_reason, old_isin FROM isin_change_circular "
            "WHERE circular_number = '53019'"
        )
        row = cur.fetchone()
    assert row == (False, "symbol_unknown", None)
    assert [a for a in list_aliases(db) if a.current_isin == "INE081A01020"] == []


def test_multiple_isins_for_symbol_is_ambiguous_and_skipped(db: object) -> None:
    _seed_security(db, "INE081A01012", "TATASTEEL")
    _seed_security(db, "INE999Z01099", "TATASTEEL")  # same symbol, second ISIN
    source = _FakeCircularSource(
        listing_payload=_tata_listing_payload(),
        pdf_bytes_by_url={TATA_PDF_URL: TATA_STEEL_PDF},
    )
    result = refresh_isin_change_feed(db, date(2022, 1, 1), date(2022, 12, 31), source=source)
    assert result["aliases_created"] == 0

    with db.cursor() as cur:
        cur.execute(
            "SELECT skip_reason FROM isin_change_circular WHERE circular_number = '53019'"
        )
        (skip_reason,) = cur.fetchone()
    assert skip_reason == "multiple_isins_for_symbol"


def test_cross_issuer_mismatch_is_refused_by_the_structural_gate(db: object) -> None:
    """The new ISIN's issuer prefix (chars 1-7) does not match the resolved old ISIN --
    027's ``_assert_same_identity`` refuses this exactly as it would a hand-entered
    alias, and the refusal is what lands in ``skip_reason``, not an unhandled raise."""
    _seed_security(db, "INE999Z01099", "TATASTEEL")  # different issuer than INE081A...
    source = _FakeCircularSource(
        listing_payload=_tata_listing_payload(),
        pdf_bytes_by_url={TATA_PDF_URL: TATA_STEEL_PDF},
    )
    result = refresh_isin_change_feed(db, date(2022, 1, 1), date(2022, 12, 31), source=source)
    assert result["aliases_created"] == 0

    with db.cursor() as cur:
        cur.execute(
            "SELECT alias_created, skip_reason FROM isin_change_circular "
            "WHERE circular_number = '53019'"
        )
        alias_created, skip_reason = cur.fetchone()
    assert alias_created is False
    assert "issuer" in skip_reason.lower() or "merger" in skip_reason.lower()


def test_rerun_is_idempotent_on_circular_number(db: object) -> None:
    _seed_security(db, "INE081A01012", "TATASTEEL")
    source = _FakeCircularSource(
        listing_payload=_tata_listing_payload(),
        pdf_bytes_by_url={TATA_PDF_URL: TATA_STEEL_PDF},
    )
    first = refresh_isin_change_feed(db, date(2022, 1, 1), date(2022, 12, 31), source=source)
    assert first["aliases_created"] == 1

    second = refresh_isin_change_feed(db, date(2022, 1, 1), date(2022, 12, 31), source=source)
    assert second["fetched"] == 0  # already in isin_change_circular -- no re-fetch
    assert second["aliases_created"] == 0

    with db.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM isin_change_circular WHERE circular_number = '53019'"
        )
        (count,) = cur.fetchone()
    assert count == 1


def test_a_parse_failure_records_the_circular_without_crashing_the_poll(db: object) -> None:
    """A malformed PDF for one circular must not abort the run -- recorded with
    ``skip_reason`` describing the parse failure, same log-and-continue posture as
    ``refresh_corporate_action_feed``'s own per-row handling."""
    source = _FakeCircularSource(
        listing_payload=_tata_listing_payload(),
        pdf_bytes_by_url={TATA_PDF_URL: b"garbage, not a real circular at all"},
    )
    result = refresh_isin_change_feed(db, date(2022, 1, 1), date(2022, 12, 31), source=source)
    assert result["aliases_created"] == 0
    assert result["skipped"] == 1
    assert result["error"] is None  # the RUN succeeded; this one ROW did not

    with db.cursor() as cur:
        cur.execute(
            "SELECT alias_created, skip_reason, symbol, subject_raw "
            "FROM isin_change_circular WHERE circular_number = '53019'"
        )
        alias_created, skip_reason, symbol, subject_raw = cur.fetchone()
    assert alias_created is False
    assert skip_reason.startswith("parse_failed")
    assert symbol is None  # never extracted -- the parse never got that far
    assert "Tata Steel" in subject_raw  # but the listing's own subject IS always known


# --------------------------------------------------------------------------------------
# Circuit breaker -- state survives across separate calls, exactly as it must across
# separate weekly cron invocations.
# --------------------------------------------------------------------------------------


def test_breaker_opens_after_threshold_consecutive_failures_and_then_skips(db: object) -> None:
    failing_source = _FakeCircularSource(list_exc=IsinChangeFeedFetchFailed("down"))

    for i in range(_BREAKER_FAILURE_THRESHOLD):
        result = refresh_isin_change_feed(
            db, date(2022, 1, 1), date(2022, 12, 31), source=failing_source
        )
        assert result["breaker_open"] is False, f"should not open until the {i + 1}th failure"
        assert result["error"] is not None

    with db.cursor() as cur:
        cur.execute(
            "SELECT consecutive_failures, breaker_open_until FROM feed_poll_state "
            "WHERE feed = %s",
            (FEED_NAME,),
        )
        failures, breaker_open_until = cur.fetchone()
    assert failures == _BREAKER_FAILURE_THRESHOLD
    assert breaker_open_until > datetime.now(UTC)

    # The next poll must skip entirely -- zero HTTP calls attempted, not one attempted
    # and caught.
    calls_before = failing_source.list_calls
    result = refresh_isin_change_feed(
        db, date(2022, 1, 1), date(2022, 12, 31), source=failing_source
    )
    assert result["breaker_open"] is True
    assert failing_source.list_calls == calls_before  # no request was made at all


def test_a_success_closes_the_breaker_and_resets_the_failure_count(db: object) -> None:
    _seed_security(db, "INE081A01012", "TATASTEEL")
    failing_source = _FakeCircularSource(list_exc=IsinChangeFeedFetchFailed("down"))
    for _ in range(_BREAKER_FAILURE_THRESHOLD - 1):
        refresh_isin_change_feed(db, date(2022, 1, 1), date(2022, 12, 31), source=failing_source)

    working_source = _FakeCircularSource(
        listing_payload=_tata_listing_payload(),
        pdf_bytes_by_url={TATA_PDF_URL: TATA_STEEL_PDF},
    )
    result = refresh_isin_change_feed(
        db, date(2022, 1, 1), date(2022, 12, 31), source=working_source
    )
    assert result["breaker_open"] is False
    assert result["error"] is None

    with db.cursor() as cur:
        cur.execute(
            "SELECT consecutive_failures, breaker_open_until FROM feed_poll_state "
            "WHERE feed = %s",
            (FEED_NAME,),
        )
        failures, breaker_open_until = cur.fetchone()
    assert failures == 0
    assert breaker_open_until is None


def test_breaker_state_is_per_feed_name(db: object) -> None:
    """A row keyed by a DIFFERENT feed name must be untouched -- feed_poll_state is
    shared infrastructure, not exclusive to this feed."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO feed_poll_state (feed, consecutive_failures, breaker_open_until) "
            "VALUES ('some_other_feed', 99, %s)",
            (datetime.now(UTC) + timedelta(days=30),),
        )
    db.commit()

    _seed_security(db, "INE081A01012", "TATASTEEL")
    source = _FakeCircularSource(
        listing_payload=_tata_listing_payload(),
        pdf_bytes_by_url={TATA_PDF_URL: TATA_STEEL_PDF},
    )
    result = refresh_isin_change_feed(db, date(2022, 1, 1), date(2022, 12, 31), source=source)
    assert result["breaker_open"] is False  # this feed's own row, not the other one

    with db.cursor() as cur:
        cur.execute(
            "SELECT consecutive_failures FROM feed_poll_state WHERE feed = 'some_other_feed'"
        )
        (failures,) = cur.fetchone()
    assert failures == 99  # untouched
