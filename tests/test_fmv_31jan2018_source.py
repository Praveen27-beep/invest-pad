"""The fmv_31jan2018 CSV adapter -- docs/TAX_ENGINE.md's "Grandfathering" section,
the loader/seeding half established in Session 3 (docs/PHASE3_PROMPTS.md), mirroring
tests/test_market_cap_sources.py's structure for the sibling sources.
"""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from app.prices.fmv_31jan2018_source import (
    FmvSourceFormatError,
    parse_fmv_31jan2018_csv,
)


def _csv_bytes(header: list[str], rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    buffer.write(",".join(header) + "\n")
    for row in rows:
        buffer.write(",".join(row) + "\n")
    return buffer.getvalue().encode("utf-8")


def test_parses_isin_and_fmv() -> None:
    payload = _csv_bytes(
        ["ISIN", "fmv_31jan2018"],
        [["INE002A01018", "1234.567890"], ["INE009A01021", "987.65"]],
    )
    rows = parse_fmv_31jan2018_csv(payload)
    by_isin = {r.isin: r.fmv_31jan2018 for r in rows}
    assert by_isin["INE002A01018"] == Decimal("1234.567890")
    assert by_isin["INE009A01021"] == Decimal("987.65")


def test_row_with_blank_isin_or_fmv_is_skipped_not_raised() -> None:
    payload = _csv_bytes(
        ["ISIN", "fmv_31jan2018"],
        [["", "100"], ["INE000B01002", ""], ["INE000C01003", "50"]],
    )
    rows = parse_fmv_31jan2018_csv(payload)
    assert [r.isin for r in rows] == ["INE000C01003"]


def test_missing_isin_column_is_rejected() -> None:
    payload = _csv_bytes(["fmv_31jan2018"], [["100"]])
    with pytest.raises(FmvSourceFormatError, match="ISIN"):
        parse_fmv_31jan2018_csv(payload)


def test_missing_fmv_column_is_rejected() -> None:
    payload = _csv_bytes(["ISIN"], [["INE000A01001"]])
    with pytest.raises(FmvSourceFormatError, match="fmv_31jan2018"):
        parse_fmv_31jan2018_csv(payload)


def test_non_positive_fmv_is_rejected() -> None:
    payload = _csv_bytes(["ISIN", "fmv_31jan2018"], [["INE000A01001", "0"]])
    with pytest.raises(FmvSourceFormatError, match="INE000A01001"):
        parse_fmv_31jan2018_csv(payload)

    payload = _csv_bytes(["ISIN", "fmv_31jan2018"], [["INE000A01001", "-5"]])
    with pytest.raises(FmvSourceFormatError, match="INE000A01001"):
        parse_fmv_31jan2018_csv(payload)


def test_unreadable_fmv_value_is_rejected() -> None:
    payload = _csv_bytes(["ISIN", "fmv_31jan2018"], [["INE000A01001", "not-a-number"]])
    with pytest.raises(FmvSourceFormatError, match="INE000A01001"):
        parse_fmv_31jan2018_csv(payload)
