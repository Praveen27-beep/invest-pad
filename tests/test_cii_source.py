"""The CII CSV adapter -- docs/TAX_ENGINE.md's "Indexation" section, the loader/seeding
half established for Session 4 (docs/PHASE3_PROMPTS.md), mirroring
tests/test_fmv_31jan2018_source.py's structure for the sibling source.
"""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from app.prices.cii_source import CIISourceFormatError, parse_cii_csv


def _csv_bytes(header: list[str], rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    buffer.write(",".join(header) + "\n")
    for row in rows:
        buffer.write(",".join(row) + "\n")
    return buffer.getvalue().encode("utf-8")


def test_parses_fy_cii_and_source() -> None:
    payload = _csv_bytes(
        ["financial_year", "cii_value", "source"],
        [
            ["2012-13", "200", "CBDT notification"],
            ["2013-14", "220", "CBDT notification"],
        ],
    )
    rows = parse_cii_csv(payload)
    by_fy = {r.financial_year: r for r in rows}
    assert by_fy["2012-13"].cii_value == Decimal("200")
    assert by_fy["2012-13"].source == "CBDT notification"
    assert by_fy["2013-14"].cii_value == Decimal("220")


def test_row_with_blank_field_is_skipped_not_raised() -> None:
    payload = _csv_bytes(
        ["financial_year", "cii_value", "source"],
        [
            ["", "200", "CBDT"],
            ["2013-14", "", "CBDT"],
            ["2014-15", "240", ""],
            ["2015-16", "254", "CBDT"],
        ],
    )
    rows = parse_cii_csv(payload)
    assert [r.financial_year for r in rows] == ["2015-16"]


def test_missing_financial_year_column_is_rejected() -> None:
    payload = _csv_bytes(["cii_value", "source"], [["200", "CBDT"]])
    with pytest.raises(CIISourceFormatError, match="financial_year"):
        parse_cii_csv(payload)


def test_missing_cii_value_column_is_rejected() -> None:
    payload = _csv_bytes(["financial_year", "source"], [["2012-13", "CBDT"]])
    with pytest.raises(CIISourceFormatError, match="cii_value"):
        parse_cii_csv(payload)


def test_missing_source_column_is_rejected() -> None:
    payload = _csv_bytes(["financial_year", "cii_value"], [["2012-13", "200"]])
    with pytest.raises(CIISourceFormatError, match="source"):
        parse_cii_csv(payload)


def test_malformed_financial_year_is_rejected() -> None:
    payload = _csv_bytes(
        ["financial_year", "cii_value", "source"], [["2012", "200", "CBDT"]]
    )
    with pytest.raises(CIISourceFormatError, match="2012"):
        parse_cii_csv(payload)


def test_non_positive_cii_value_is_rejected() -> None:
    payload = _csv_bytes(
        ["financial_year", "cii_value", "source"], [["2012-13", "0", "CBDT"]]
    )
    with pytest.raises(CIISourceFormatError, match="2012-13"):
        parse_cii_csv(payload)

    payload = _csv_bytes(
        ["financial_year", "cii_value", "source"], [["2012-13", "-5", "CBDT"]]
    )
    with pytest.raises(CIISourceFormatError, match="2012-13"):
        parse_cii_csv(payload)


def test_unreadable_cii_value_is_rejected() -> None:
    payload = _csv_bytes(
        ["financial_year", "cii_value", "source"],
        [["2012-13", "not-a-number", "CBDT"]],
    )
    with pytest.raises(CIISourceFormatError, match="2012-13"):
        parse_cii_csv(payload)
