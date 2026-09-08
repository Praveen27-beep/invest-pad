"""The NIFTY 50 TRI adapter -- docs/ENGINE_SPEC.md section 6.

Offline, against trimmed real-shaped responses. The load-bearing check is that parsing
reads ``TotalReturnsIndex`` specifically -- the field name that IS the TRI/price-index
distinction ENGINE_SPEC section 6 requires. A silent swap to a plain price-value field
(this endpoint's own ``NTR_Value``, or any other index-value endpoint) is exactly the
failure this file exists to catch before it reaches production.

BOTH envelope shapes are pinned here, because the endpoint has served both and the move
between them is what took the benchmark line dark once already: a bare JSON array (what
``/BackPage/`` returns today) and ASP.NET's double-encoded ``{"d": "<json>"}`` (what the
retired ``/Backpage.aspx/`` path returned, ``fixtures/nifty_tri_sample.json``). A reader
that handles only today's shape would go dark again the moment it moves back.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from app.prices.index_sources import (
    NIFTY_TRI_INDEX_NAME,
    IndexSourceFetchFailed,
    IndexSourceFormatError,
    _format_request_date,
    _parse_response_date,
    parse_nifty_tri,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
#: The legacy double-encoded envelope, kept as the fixture it always was.
SAMPLE = (FIXTURES / "nifty_tri_sample.json").read_bytes()

#: The same three records in the shape the live endpoint returns today: a bare array,
#: no envelope. Built from SAMPLE rather than typed out again so the two can never drift
#: into testing different data and hiding a difference in the records themselves.
BARE_SAMPLE = json.dumps(json.loads(json.loads(SAMPLE)["d"])).encode("utf-8")


def test_parses_every_row_of_the_sample_response() -> None:
    rows = parse_nifty_tri(SAMPLE)

    assert len(rows) == 3
    assert rows[0].index_name == NIFTY_TRI_INDEX_NAME
    assert rows[0].level_date == date(2024, 1, 10)
    assert rows[0].close == Decimal("25412.35")


def test_reads_total_returns_index_not_ntr_value() -> None:
    """The pin: NTR_Value (net total return, post-tax) sits right next to
    TotalReturnsIndex in the same real record and is NOT what must be stored -- picking
    the wrong field silently would still parse cleanly, just wrong."""
    rows = parse_nifty_tri(SAMPLE)
    assert rows[0].close != Decimal("24988.10")  # that row's NTR_Value
    assert rows[0].close == Decimal("25412.35")  # that row's TotalReturnsIndex


def test_record_missing_total_returns_index_field_is_rejected() -> None:
    """If the endpoint (or a future source swapped in for it) ever answers with a plain
    price-index record instead -- no TotalReturnsIndex field at all -- this must fail
    loudly rather than silently store nothing or store the wrong number."""
    payload = json.dumps(
        {"d": json.dumps([{"Index Name": "Nifty 50", "Date": "10 Jan 2024", "Close": "22000"}])}
    ).encode("utf-8")

    with pytest.raises(IndexSourceFormatError, match="TotalReturnsIndex"):
        parse_nifty_tri(payload)


def test_malformed_outer_envelope_raises_format_error() -> None:
    with pytest.raises(IndexSourceFormatError):
        parse_nifty_tri(b"not json at all")


def test_unrecognised_envelope_raises_format_error() -> None:
    """Neither a bare array nor a 'd' envelope."""
    with pytest.raises(IndexSourceFormatError):
        parse_nifty_tri(json.dumps({"unexpected": "shape"}).encode("utf-8"))


def test_html_block_page_raises_format_error() -> None:
    """What a rejected request actually gets back. This is the exact failure that left
    ``index_level`` empty and the dashboard's benchmark line undrawable: the endpoint
    answers 200 with a web page, so nothing upstream looks broken."""
    with pytest.raises(IndexSourceFormatError, match="not JSON"):
        parse_nifty_tri(b"<!DOCTYPE html> <html><head><title>NIFTY Indices</title></head></html>")


# --- both envelope shapes parse identically ---------------------------------------------


def test_parses_the_bare_array_the_live_endpoint_returns() -> None:
    """``/BackPage/`` answers with a plain JSON array, not the ``[WebMethod]`` double
    encoding the retired ``.aspx`` path used."""
    rows = parse_nifty_tri(BARE_SAMPLE)

    assert len(rows) == 3
    assert rows[0].level_date == date(2024, 1, 10)
    assert rows[0].close == Decimal("25412.35")


def test_both_envelope_shapes_yield_the_same_rows() -> None:
    assert parse_nifty_tri(BARE_SAMPLE) == parse_nifty_tri(SAMPLE)


def test_bare_array_is_still_held_to_the_total_returns_index_field() -> None:
    """The TRI/price-index pin is a property of the records, not of the envelope they
    arrived in -- a price-index record must be rejected in either shape."""
    payload = json.dumps([{"Index Name": "Nifty 50", "Date": "10 Jan 2024", "Close": "22000"}])

    with pytest.raises(IndexSourceFormatError, match="TotalReturnsIndex"):
        parse_nifty_tri(payload.encode("utf-8"))


# --- date formatting, both directions, locale-independent -------------------------------


def test_request_date_format_is_dd_mon_yyyy() -> None:
    assert _format_request_date(date(2024, 1, 10)) == "10-Jan-2024"
    assert _format_request_date(date(2026, 12, 1)) == "01-Dec-2026"


def test_response_date_parses_dd_space_mon_space_yyyy() -> None:
    assert _parse_response_date("10 Jan 2024") == date(2024, 1, 10)
    assert _parse_response_date("22 May 2026") == date(2026, 5, 22)


def test_response_date_rejects_unrecognised_month() -> None:
    with pytest.raises(ValueError):
        _parse_response_date("10 Foo 2024")


# --- fetch failure classification --------------------------------------------------------


class _RaisingOpener:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def __call__(self, *args: object, **kwargs: object) -> None:
        raise self._exc


def test_network_error_raises_fetch_failed() -> None:
    from app.prices.index_sources import NiftyTriSource

    source = NiftyTriSource(opener=_RaisingOpener(OSError("connection reset")))
    with pytest.raises(IndexSourceFetchFailed):
        source.fetch(date(2024, 1, 1), date(2024, 1, 31))


# --- the second index: NIFTY 500 TRI -----------------------------------------------------


class _CapturingOpener:
    """Records the request instead of sending it, then answers with a canned payload."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.request: object = None

    def __call__(self, request, *args: object, **kwargs: object):
        self.request = request
        payload = self.payload

        class _Response:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc: object) -> bool:
                return False

            def read(self_inner) -> bytes:
                return payload

        return _Response()


def test_fetch_asks_for_json_not_html() -> None:
    """The shared BROWSER_HEADERS ask for text/html, which is right for a bhavcopy file
    and wrong here -- this endpoint is content-negotiated, and an HTML Accept is one of
    the things that steers a request onto the block page instead of the records."""
    from app.prices.index_sources import NiftyTriSource

    opener = _CapturingOpener(BARE_SAMPLE)
    NiftyTriSource(opener=opener).fetch(date(2024, 1, 1), date(2024, 1, 31))

    accept = opener.request.get_header("Accept")  # type: ignore[attr-defined]
    assert "application/json" in accept
    assert "text/html" not in accept


def test_fetch_posts_to_the_live_path_not_the_retired_aspx_one() -> None:
    """``/Backpage.aspx/getTotalReturnIndexString`` answers 302 to an HTML page now. It
    is pinned negatively because the failure it causes is invisible: a 200, a body that
    is not JSON, an empty ``index_level``, and a benchmark line that simply never draws."""
    from app.prices.index_sources import NIFTY_TRI_URL

    assert NIFTY_TRI_URL.endswith("/BackPage/getTotalReturnIndexString")
    assert ".aspx" not in NIFTY_TRI_URL


def test_nifty_500_asks_the_endpoint_for_nifty_500() -> None:
    """The request name and the storage key are separate fields precisely so this can be
    pinned: sending 'NIFTY 50' while storing under 'NIFTY500_TRI' would fill the dashboard's
    benchmark line with the wrong index and nothing would look broken."""
    from app.prices.index_sources import NIFTY_500_TRI, NiftyTriSource

    opener = _CapturingOpener(SAMPLE)
    source = NiftyTriSource(opener=opener, index=NIFTY_500_TRI)
    source.fetch(date(2024, 1, 1), date(2024, 1, 31))

    body = opener.request.data.decode("utf-8")  # type: ignore[attr-defined]
    assert "NIFTY 500" in body
    assert "'name':'NIFTY 50'" not in body
    assert source.index_name == "NIFTY500_TRI"


def test_nifty_500_rows_are_stored_under_their_own_key() -> None:
    from app.prices.index_sources import NIFTY_500_TRI

    rows = parse_nifty_tri(SAMPLE, NIFTY_500_TRI)
    assert rows
    assert all(row.index_name == "NIFTY500_TRI" for row in rows)


def test_the_registry_covers_every_fetchable_benchmark_name() -> None:
    """The router looks names up here after validating them against its own Literal; a
    name in one and not the other is a 500 waiting to happen."""
    from app.prices.index_sources import TRI_INDICES

    assert set(TRI_INDICES) == {"NIFTY50_TRI", "NIFTY500_TRI"}
    assert all(key == index.storage_name for key, index in TRI_INDICES.items())


# --- the daily refresh keeps index_level current --------------------------------------


def test_index_refresh_failure_does_not_fail_the_price_run() -> None:
    """The benchmark line is a decoration on a chart whose subject is priced from
    bhavcopy. A TRI source that is down must be REPORTED by the price-refresh job, never
    raised out of it: failing the run that keeps every valuation in the product correct,
    because an optional comparison line went stale, is the tail wagging the dog."""
    from app.routers import analytical

    def _always_fails(*args: object, **kwargs: object) -> int:
        raise IndexSourceFetchFailed("niftyindices unreachable")

    original = analytical.fetch_and_store
    analytical.fetch_and_store = _always_fails  # type: ignore[assignment]
    try:
        stored, failures = analytical._refresh_index_levels(object(), date(2026, 9, 4))
    finally:
        analytical.fetch_and_store = original  # type: ignore[assignment]

    assert stored == {}
    assert set(failures) == {"NIFTY50_TRI", "NIFTY500_TRI"}
    assert "unreachable" in failures["NIFTY50_TRI"]


def test_index_refresh_covers_every_fetchable_series_over_a_trailing_window() -> None:
    """Both series, and a range rather than the single day, so a missed or failed run
    heals on the next one without a separate backfill."""
    from app.routers import analytical

    calls: list[tuple[date, date, str]] = []

    def _record(_conn: object, start: date, end: date, index: object = None, **_: object) -> int:
        calls.append((start, end, index.storage_name))  # type: ignore[union-attr]
        return 7

    original = analytical.fetch_and_store
    analytical.fetch_and_store = _record  # type: ignore[assignment]
    try:
        stored, failures = analytical._refresh_index_levels(object(), date(2026, 9, 4))
    finally:
        analytical.fetch_and_store = original  # type: ignore[assignment]

    assert failures == {}
    assert stored == {"NIFTY50_TRI": 7, "NIFTY500_TRI": 7}
    assert {c[2] for c in calls} == {"NIFTY50_TRI", "NIFTY500_TRI"}
    for start, end, _ in calls:
        assert end == date(2026, 9, 4)
        assert (end - start).days == analytical.INDEX_REFRESH_LOOKBACK_DAYS
