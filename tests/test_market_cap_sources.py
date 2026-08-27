"""The AMFI large/mid/small-cap classification adapter -- FEATURE_BACKLOG.md's
"Market-cap breakdown" line, the other half of "Sector / market-cap breakdown".

Offline, against a trimmed real-shaped workbook (``fixtures/amfi_market_cap_sample.xlsx``,
built from a verified live pull of AMFI's own published list), mirroring
``tests/test_sector_sources.py``'s structure for the sibling source.
"""

from __future__ import annotations

import io
from pathlib import Path

import openpyxl
import pytest
from app.prices.market_cap_sources import (
    MarketCapSourceFetchFailed,
    MarketCapSourceFormatError,
    parse_amfi_market_cap_list,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
SAMPLE = (FIXTURES / "amfi_market_cap_sample.xlsx").read_bytes()


def _workbook_bytes(header: list[str], rows: list[list[object]]) -> bytes:
    """Build a minimal in-memory .xlsx payload for an edge-case test -- there is no
    reason to check in a fixture file for a single constructed row."""
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_parses_every_row_of_the_sample() -> None:
    rows = parse_amfi_market_cap_list(SAMPLE)
    assert len(rows) == 9


def test_reads_isin_and_bucket_correctly() -> None:
    rows = parse_amfi_market_cap_list(SAMPLE)
    by_isin = {r.isin: r for r in rows}
    reliance = by_isin["INE002A01018"]
    assert reliance.bucket == "Large Cap"
    assert reliance.company_name == "Reliance Industries Ltd"


def test_large_mid_small_boundaries_present() -> None:
    rows = parse_amfi_market_cap_list(SAMPLE)
    buckets = {r.isin: r.bucket for r in rows}
    assert buckets["INE129A01019"] == "Large Cap"  # rank 100
    assert buckets["INE323A01026"] == "Mid Cap"  # rank 101
    assert buckets["INE233A01035"] == "Mid Cap"  # rank 250
    assert buckets["INE048G01026"] == "Small Cap"  # rank 251
    assert {r.bucket for r in rows} == {"Large Cap", "Mid Cap", "Small Cap"}


def test_row_with_blank_isin_or_category_is_skipped_not_raised() -> None:
    payload = _workbook_bytes(
        ["Company name", "ISIN", "Categorization as per SEBI Circular dated Oct 6, 2017"],
        [
            ["Foo Ltd.", "", "Large Cap"],
            ["Bar Ltd.", "INE000B01002", ""],
            ["Baz Ltd.", "INE000C01003", "Small Cap"],
        ],
    )
    rows = parse_amfi_market_cap_list(payload)
    assert [r.isin for r in rows] == ["INE000C01003"]


def test_missing_isin_column_is_rejected() -> None:
    payload = _workbook_bytes(
        ["Company name", "Categorization as per SEBI Circular dated Oct 6, 2017"],
        [["Foo Ltd.", "Large Cap"]],
    )
    with pytest.raises(MarketCapSourceFormatError, match="ISIN"):
        parse_amfi_market_cap_list(payload)


def test_missing_category_column_is_rejected() -> None:
    payload = _workbook_bytes(
        ["Company name", "ISIN"],
        [["Foo Ltd.", "INE000A01001"]],
    )
    with pytest.raises(MarketCapSourceFormatError, match="Categorization"):
        parse_amfi_market_cap_list(payload)


def test_unrecognised_category_value_is_rejected() -> None:
    payload = _workbook_bytes(
        ["Company name", "ISIN", "Categorization as per SEBI Circular dated Oct 6, 2017"],
        [["Foo Ltd.", "INE000A01001", "Mega Cap"]],
    )
    with pytest.raises(MarketCapSourceFormatError, match="Mega Cap"):
        parse_amfi_market_cap_list(payload)


# --- fetch failure classification --------------------------------------------------------


class _RaisingOpener:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def __call__(self, *args: object, **kwargs: object) -> None:
        raise self._exc


def test_network_error_raises_fetch_failed() -> None:
    from app.prices.market_cap_sources import AmfiMarketCapSource

    source = AmfiMarketCapSource(opener=_RaisingOpener(OSError("connection reset")))
    with pytest.raises(MarketCapSourceFetchFailed):
        source.fetch()
