"""NSE ISIN-change circular parser, throttle and backoff --
app.ingest.isin_change_feed.

The three circular texts below are real, confirmed-live extractions (pdfplumber), not
invented -- ``TATA_STEEL_TEXT`` from NSE/CML/53019 (2022-07-20), ``ORIANA_TEXT`` from
NSE/CML/76380 (2026-09-16), ``LE_MERITE_TEXT`` from NSE/CML/74438 (2026-05-27).
``ORIANA_TEXT`` is the one that matters most: its Remarks cell wraps across the data
row ("Sub-Division from Rs. 10/- to" appears BEFORE "1 ORIANA ... INE0OUT01027", "Rs.
2/-" appears AFTER), which is what ``_extract_remarks`` exists to undo -- a parser
naively looking only after the ISIN would silently drop the leading fragment.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import date

import pytest
from app.ingest.isin_change_feed import (
    CircularListing,
    IsinChangeCircularFormatError,
    IsinChangeFeedFetchFailed,
    NseCircularListSource,
    _is_transient,
    _TokenBucket,
    parse_circular_listing,
    parse_isin_change_circular,
)

TATA_STEEL_TEXT = (
    "National Stock Exchange of India\nCircular\nDepartment: Listing\nDownload Ref No: "
    "NSE/CML/53019 Date: July 20, 2022\nCircular Ref. No: 0833/2022\nTo All Members\n"
    "Sub: Change in ISIN – Tata Steel Limited (TATASTEEL)\nMembers of the Exchange "
    "are hereby informed that the ISIN Code for the equity shares of the following\n"
    "company shall be changed w.e.f. July 29, 2022.\nSr. No. Symbol Company Name New "
    "ISIN Remarks\n1 TATASTEEL Tata Steel Limited INE081A01020 Sub-Division from Rs. "
    "10/- to Re. 1/-\nThe new ISIN shall be effective for all trades done on and from "
    "the Ex-date date i.e., July 28, 2022.\nFor and on behalf of\nNational Stock "
    "Exchange of India Limited\nYogesh Deshmukh\nSenior Manager"
)

#: The wrapped-Remarks case -- see module docstring.
ORIANA_TEXT = (
    "National Stock Exchange of India\nCircular\nDepartment: Listing\nDownload Ref No: "
    "NSE/CML/76380 Date: September 16, 2026\nCircular Ref. No: 1626/2026\nTo All "
    "Members\nSub: Change in ISIN – Oriana Power Limited (ORIANA)\nMembers of the "
    "Exchange are hereby informed that the ISIN Code for the equity shares of the "
    "following\ncompany shall be changed w.e.f. September 18, 2026.\nSr.\nSymbol "
    "Company Name New ISIN Remarks\nNo.\nSub-Division from Rs. 10/- to\n1 ORIANA "
    "Oriana Power Limited INE0OUT01027\nRs. 2/-\nThe new ISIN shall be effective for "
    "all trades done on and from the Ex-date i.e., September 18, 2026.\nFor and on "
    "behalf of\nNational Stock Exchange of India Limited\nPranali Honrao\nManager"
)

LE_MERITE_TEXT = (
    "National Stock Exchange of India\nCircular\nDepartment: Listing\nDownload Ref No: "
    "NSE/CML /74438 Date: May 27 , 202 6\nCircular Ref. No: 0860 /2026\nTo All "
    "Members\nSub: Change in ISIN – Le Merite Exports Limited (LEMERITE)\nMembers "
    "of the Exchange are hereby informed that the ISIN Code for the equity shares of "
    "the following\ncompany shall be changed w.e.f. May 29, 2026.\nSr.\nSymbol Company "
    "Name New ISIN Remarks\nNo.\n1 LEMERITE Le Merite Exports Limited INE0G1L01025 "
    "Sub-Division from Rs. 10/- to Rs. 2/-\nThe new ISIN shall be effective for all "
    "trades done on and from the Ex-date i.e., May 29, 2026.\nFor and on behalf of\n"
    "National Stock Exchange of India Limited\nDhwani Shah\nManager"
)


@pytest.mark.parametrize(
    ("text", "symbol", "new_isin", "remarks", "wef", "ex"),
    [
        (
            TATA_STEEL_TEXT, "TATASTEEL", "INE081A01020",
            "Sub-Division from Rs. 10/- to Re. 1/-",
            date(2022, 7, 29), date(2022, 7, 28),
        ),
        (
            ORIANA_TEXT, "ORIANA", "INE0OUT01027",
            "Sub-Division from Rs. 10/- to Rs. 2/-",
            date(2026, 9, 18), date(2026, 9, 18),
        ),
        (
            LE_MERITE_TEXT, "LEMERITE", "INE0G1L01025",
            "Sub-Division from Rs. 10/- to Rs. 2/-",
            date(2026, 5, 29), date(2026, 5, 29),
        ),
    ],
)
def test_parses_real_circulars(text, symbol, new_isin, remarks, wef, ex) -> None:
    parsed = parse_isin_change_circular(text)
    assert parsed.symbol == symbol
    assert parsed.new_isin == new_isin
    assert parsed.remarks_raw == remarks
    assert parsed.wef_date == wef
    assert parsed.ex_date == ex


def test_wef_and_ex_date_can_disagree() -> None:
    """Tata Steel's own circular: "changed w.e.f. July 29" but "effective ... from the
    Ex-date ... July 28" -- one day apart. The consumer (app.db.isin_change_circulars)
    must use ex_date, never wef_date, for security_alias.effective_date."""
    parsed = parse_isin_change_circular(TATA_STEEL_TEXT)
    assert parsed.wef_date != parsed.ex_date
    assert parsed.ex_date == date(2022, 7, 28)


def test_wrapped_remarks_cell_is_reassembled_in_reading_order() -> None:
    """The specific bug a naive "text after the ISIN" parser has: it would silently
    read Oriana's remarks as just "Rs. 2/-", dropping "Sub-Division from Rs. 10/- to"
    entirely, because that fragment appears BEFORE the data row in pdfplumber's output.
    """
    parsed = parse_isin_change_circular(ORIANA_TEXT)
    assert parsed.remarks_raw == "Sub-Division from Rs. 10/- to Rs. 2/-"


@pytest.mark.parametrize(
    "mangled",
    [
        "Sub: Change in ISIN -- nothing else here",
        TATA_STEEL_TEXT.replace("INE081A01020", "NOTANISINATALL"),
        TATA_STEEL_TEXT.replace("w.e.f. July 29, 2022", "at some point"),
        TATA_STEEL_TEXT.replace("Ex-date date i.e., July 28, 2022", "later"),
        TATA_STEEL_TEXT.split("The new ISIN shall be effective")[0],  # table never closes
    ],
)
def test_malformed_circular_raises_format_error_not_a_bare_exception(mangled: str) -> None:
    with pytest.raises(IsinChangeCircularFormatError):
        parse_isin_change_circular(mangled)


def test_a_non_equity_circular_says_so_instead_of_naming_the_regex() -> None:
    """A debt-series ISIN change has no equity trading symbol to put in its "Sub:" line,
    so it fails this guard every time and correctly creates nothing. What it lands in
    ``isin_change_circular.skip_reason`` is the message asserted here, and the reason that
    wording is worth a test is that the reviewer of a queue row is a human months later:
    "missing the symbol in the Sub: line" read as a parser bug, when it was the system
    working. Still a parse_failed, still in the queue -- the same absence is what a real
    equity circular's format change would look like, so the message names the likely cause
    without deciding it."""
    with pytest.raises(IsinChangeCircularFormatError) as exc:
        parse_isin_change_circular(
            "Sub: Change in ISIN - Some Issuer Limited 9.25% NCD Series I\n"
            "The ISIN shall be changed w.e.f. July 29, 2026\n"
        )

    message = str(exc.value)
    assert "non-equity" in message
    assert "skips by design" in message
    # The escape hatch for the case this is NOT: a real equity circular whose format moved.
    assert "format has changed" in message


# --------------------------------------------------------------------------------------
# Circulars-list filter -- real captured payloads, 2022-2025 (58/56/73/59 "Change in
# ISIN" matches respectively, matching what was independently counted live).
# --------------------------------------------------------------------------------------


def _listing_payload(*rows: dict) -> bytes:
    return json.dumps({"data": list(rows)}).encode()


def _row(**overrides) -> dict:
    base = {
        "cirDate": "20260916", "circDisplayNo": "NSE/CML/76380", "circNumber": "76380",
        "sub": "Change in ISIN - Oriana Power Limited (ORIANA)",
        "circFilelink": "https://nsearchives.nseindia.com/content/circulars/CML76380.pdf",
    }
    return {**base, **overrides}


def test_listing_filter_matches_isin_change_subject_case_insensitively() -> None:
    payload = _listing_payload(_row(sub="CHANGE IN ISIN - Foo Ltd (FOO)"))
    listings = parse_circular_listing(payload)
    assert len(listings) == 1
    assert listings[0] == CircularListing(
        circular_number="76380", circular_ref="NSE/CML/76380",
        circular_date=date(2026, 9, 16),
        subject="CHANGE IN ISIN - Foo Ltd (FOO)",
        pdf_url="https://nsearchives.nseindia.com/content/circulars/CML76380.pdf",
    )


def test_listing_filter_ignores_unrelated_circulars() -> None:
    payload = _listing_payload(
        _row(sub="Applicability of Short-Term Additional Surveillance Measure (ST-ASM)"),
        _row(sub="Samuhik Prativedan Manch"),
    )
    assert parse_circular_listing(payload) == []


def test_listing_filter_on_real_captured_payload() -> None:
    """One real day's worth of circulars (113 rows, 2026-09-15..18), containing exactly
    one ISIN change -- Oriana Power, confirmed live."""
    real_payload = _listing_payload(
        _row(sub="Applicability of Short-Term Additional Surveillance Measure (ST-ASM)"),
        _row(
            sub="Change in ISIN - Oriana Power Limited (ORIANA)",
            circNumber="76380", circDisplayNo="NSE/CML/76380", cirDate="20260916",
        ),
        _row(sub="Samuhik Prativedan Manch"),
    )
    listings = parse_circular_listing(real_payload)
    assert len(listings) == 1
    assert listings[0].circular_number == "76380"


def test_listing_format_error_on_broken_json() -> None:
    with pytest.raises(IsinChangeCircularFormatError):
        parse_circular_listing(b"not json")


def test_listing_format_error_on_missing_required_field() -> None:
    # A matching subject with none of the other fields NSE's listing has always
    # carried so far -- the signal the shape changed, not a row to quietly skip.
    payload = json.dumps({"data": [{"sub": "Change in ISIN - Foo (FOO)"}]}).encode()
    with pytest.raises(IsinChangeCircularFormatError):
        parse_circular_listing(payload)


# --------------------------------------------------------------------------------------
# Rate throttle -- 3 req/sec, shared across every call one poll makes.
# --------------------------------------------------------------------------------------


def test_token_bucket_paces_calls_at_the_configured_rate() -> None:
    clock = [0.0]
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    def fake_now() -> float:
        return clock[0]

    bucket = _TokenBucket(rate=3, sleep=fake_sleep, now=fake_now)
    for _ in range(6):
        bucket.wait()
        clock[0] += 0.01  # simulate a fast local call between throttle checks

    # 6 calls at 3/sec must span at least (6-1)/3 == 1.667s of enforced spacing.
    assert clock[0] >= 5 * (1 / 3)


def test_token_bucket_does_not_sleep_when_calls_are_already_spaced_out() -> None:
    clock = [0.0]
    sleeps: list[float] = []
    bucket = _TokenBucket(
        rate=3, sleep=lambda s: sleeps.append(s), now=lambda: clock[0]
    )
    bucket.wait()
    clock[0] += 10.0  # long enough gap that no throttling is needed
    bucket.wait()
    assert sleeps == []


# --------------------------------------------------------------------------------------
# Backoff and non-retry classification.
# --------------------------------------------------------------------------------------


def test_5xx_and_network_errors_are_transient() -> None:
    assert _is_transient(urllib.error.HTTPError("u", 503, "x", {}, None))
    assert _is_transient(urllib.error.HTTPError("u", 500, "x", {}, None))
    assert _is_transient(urllib.error.URLError("boom"))
    assert _is_transient(TimeoutError())
    assert _is_transient(OSError("connection reset"))


def test_4xx_is_not_transient() -> None:
    assert not _is_transient(urllib.error.HTTPError("u", 403, "x", {}, None))
    assert not _is_transient(urllib.error.HTTPError("u", 404, "x", {}, None))


class _FlakyOpener:
    """Fails with a given exception ``fail_times`` times, then succeeds -- or never
    succeeds if ``fail_times`` is None."""

    def __init__(self, exc: Exception, fail_times: int | None) -> None:
        self.exc = exc
        self.fail_times = fail_times
        self.calls = 0

    def __call__(self, request, timeout=None, context=None):
        self.calls += 1
        if self.fail_times is None or self.calls <= self.fail_times:
            raise self.exc
        return _FakeResponse(b'{"data": []}')


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_transient_failure_is_retried_and_eventually_succeeds() -> None:
    sleeps: list[float] = []
    opener = _FlakyOpener(urllib.error.HTTPError("u", 503, "x", {}, None), fail_times=2)
    source = NseCircularListSource(opener=opener, sleep=sleeps.append)
    payload = source.list_circulars(date(2026, 1, 1), date(2026, 1, 31))
    assert json.loads(payload) == {"data": []}
    # The throttle's own pacing sleeps (real time.monotonic-based, sub-second) share
    # this same injected callable, so assert the two BACKOFF delays appear -- not that
    # they're the only or the first entries -- rather than an exact, throttle-sensitive
    # prefix.
    assert 1.0 in sleeps
    assert 2.0 in sleeps
    assert sleeps.index(1.0) < sleeps.index(2.0)


def test_backoff_delays_grow_exponentially_1_2_4_8() -> None:
    sleeps: list[float] = []
    opener = _FlakyOpener(urllib.error.HTTPError("u", 503, "x", {}, None), fail_times=4)
    source = NseCircularListSource(opener=opener, sleep=sleeps.append)
    source.list_circulars(date(2026, 1, 1), date(2026, 1, 31))
    backoff_sleeps = [s for s in sleeps if s >= 1.0]
    assert backoff_sleeps == [1.0, 2.0, 4.0, 8.0]


def test_transient_failure_exhausts_retries_and_raises_fetch_failed() -> None:
    opener = _FlakyOpener(urllib.error.HTTPError("u", 503, "x", {}, None), fail_times=None)
    source = NseCircularListSource(opener=opener, sleep=lambda s: None)
    with pytest.raises(IsinChangeFeedFetchFailed):
        source.list_circulars(date(2026, 1, 1), date(2026, 1, 31))


def test_non_transient_failure_is_not_retried() -> None:
    opener = _FlakyOpener(urllib.error.HTTPError("u", 403, "x", {}, None), fail_times=None)
    source = NseCircularListSource(opener=opener, sleep=lambda s: None)
    with pytest.raises(IsinChangeFeedFetchFailed):
        source.list_circulars(date(2026, 1, 1), date(2026, 1, 31))
    # The homepage warm-up is the first opener call and fails with the same 403 --
    # non-transient, so _retrying raises immediately without a second attempt. Only
    # ONE opener call total: the list URL itself is never even requested.
    assert opener.calls == 1


class _WarmupSucceedsListBlocked:
    """The realistic anti-bot shape: the homepage warms up fine, and the API call
    itself is the one that 403s -- confirmed live as the actual failure mode
    ``corporate_action_feed``'s docstring documents for this same anti-bot layer."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, request, timeout=None, context=None):
        self.calls += 1
        if self.calls == 1:
            return _FakeResponse(b"")
        raise urllib.error.HTTPError("u", 403, "blocked", {}, None)


def test_non_transient_failure_on_the_list_call_itself_is_not_retried() -> None:
    opener = _WarmupSucceedsListBlocked()
    source = NseCircularListSource(opener=opener, sleep=lambda s: None)
    with pytest.raises(IsinChangeFeedFetchFailed):
        source.list_circulars(date(2026, 1, 1), date(2026, 1, 31))
    # Warm-up (1) + the blocked list call (1) = 2, and no retry beyond that.
    assert opener.calls == 2


# --------------------------------------------------------------------------------------
