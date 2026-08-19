"""The NSE sector/industry classification adapter -- FEATURE_BACKLOG.md's "Allocation
(by holding, sector)" line.

Offline, against a trimmed real-shaped response (``fixtures/nse_sector_sample.csv``, a
verified live pull from NSE's NIFTY Total Market constituent list).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.prices.sector_sources import (
    SectorSourceFetchFailed,
    SectorSourceFormatError,
    parse_nse_sector_list,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
SAMPLE = (FIXTURES / "nse_sector_sample.csv").read_bytes()


def test_parses_every_row_of_the_sample() -> None:
    rows = parse_nse_sector_list(SAMPLE)
    assert len(rows) == 17


def test_reads_isin_symbol_and_sector_correctly() -> None:
    rows = parse_nse_sector_list(SAMPLE)
    by_isin = {r.isin: r for r in rows}
    reliance = by_isin["INE002A01018"]
    assert reliance.symbol == "RELIANCE"
    assert reliance.sector == "Oil Gas & Consumable Fuels"
    assert reliance.company_name == "Reliance Industries Ltd."


def test_multiple_distinct_sectors_present() -> None:
    rows = parse_nse_sector_list(SAMPLE)
    sectors = {r.sector for r in rows}
    assert "Financial Services" in sectors
    assert "Information Technology" in sectors
    assert len(sectors) >= 5


def test_non_eq_series_rows_are_excluded() -> None:
    payload = (
        b"Company Name,Industry,Symbol,Series,ISIN Code\n"
        b"Foo Ltd.,Services,FOO,BE,INE000A01001\n"
        b"Bar Ltd.,Services,BAR,EQ,INE000B01002\n"
    )
    rows = parse_nse_sector_list(payload)
    assert [r.isin for r in rows] == ["INE000B01002"]


def test_row_with_blank_isin_or_sector_is_skipped_not_raised() -> None:
    payload = (
        b"Company Name,Industry,Symbol,Series,ISIN Code\n"
        b"Foo Ltd.,,FOO,EQ,INE000A01001\n"
        b"Bar Ltd.,Services,BAR,EQ,\n"
        b"Baz Ltd.,Services,BAZ,EQ,INE000C01003\n"
    )
    rows = parse_nse_sector_list(payload)
    assert [r.isin for r in rows] == ["INE000C01003"]


def test_missing_industry_column_is_rejected() -> None:
    payload = b"Company Name,Symbol,Series,ISIN Code\nFoo Ltd.,FOO,EQ,INE000A01001\n"
    with pytest.raises(SectorSourceFormatError, match="Industry"):
        parse_nse_sector_list(payload)


def test_missing_isin_column_is_rejected() -> None:
    payload = b"Company Name,Industry,Symbol,Series\nFoo Ltd.,Services,FOO,EQ\n"
    with pytest.raises(SectorSourceFormatError, match="ISIN Code"):
        parse_nse_sector_list(payload)


# --- fetch failure classification --------------------------------------------------------


class _RaisingOpener:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def __call__(self, *args: object, **kwargs: object) -> None:
        raise self._exc


def test_network_error_raises_fetch_failed() -> None:
    from app.prices.sector_sources import NseSectorSource

    source = NseSectorSource(opener=_RaisingOpener(OSError("connection reset")))
    with pytest.raises(SectorSourceFetchFailed):
        source.fetch()
