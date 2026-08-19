"""The NIFTY 50 TRI adapter -- docs/ENGINE_SPEC.md section 6.

Offline, against a trimmed real-shaped response (the API double-encodes JSON; see
``fixtures/nifty_tri_sample.json``). The load-bearing check is that parsing reads
``TotalReturnsIndex`` specifically -- the field name that IS the TRI/price-index
distinction ENGINE_SPEC section 6 requires. A silent swap to a plain price-value field
(this endpoint's own ``NTR_Value``, or any other index-value endpoint) is exactly the
failure this file exists to catch before it reaches production.
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
SAMPLE = (FIXTURES / "nifty_tri_sample.json").read_bytes()


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


def test_missing_d_envelope_raises_format_error() -> None:
    with pytest.raises(IndexSourceFormatError):
        parse_nifty_tri(json.dumps({"unexpected": "shape"}).encode("utf-8"))


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
