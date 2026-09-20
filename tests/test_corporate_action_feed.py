"""NSE corporate-actions feed parser -- app.ingest.corporate_action_feed.

Every disqualifying case here was found against a REAL live pull (2026-09-10, a
three-month window, 982 raw notices), not invented: the NCRPS and Rs/Re cases are
confirmed real notices this parser got wrong on the first pass.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from app.engine.corporate_actions import CorpActionType
from app.ingest.corporate_action_feed import (
    CorporateActionFeedFormatError,
    FeedRow,
    parse_corporate_action_feed,
)


def _payload(*records: dict) -> bytes:
    return json.dumps(list(records)).encode()


def _record(**overrides) -> dict:
    base = {
        "isin": "INE153T01027", "symbol": "TEST", "exDate": "17-Oct-2026",
        "subject": "Bonus 1:1",
    }
    return {**base, **overrides}


def test_a_plain_bonus_notice_parses() -> None:
    rows = parse_corporate_action_feed(_payload(_record(subject="Bonus 1:1")))
    assert rows == [
        FeedRow(
            isin="INE153T01027", symbol="TEST", action_type=CorpActionType.BONUS,
            ex_date=date(2026, 10, 17), bonus_new=1, bonus_for=1, raw_subject="Bonus 1:1",
        )
    ]


def test_a_larger_ratio_bonus_parses() -> None:
    rows = parse_corporate_action_feed(_payload(_record(subject="Bonus Issue 4:1")))
    assert rows[0].bonus_new == 4
    assert rows[0].bonus_for == 1


def test_a_plain_split_notice_parses() -> None:
    subject = "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share"
    rows = parse_corporate_action_feed(_payload(_record(subject=subject)))
    assert rows == [
        FeedRow(
            isin="INE153T01027", symbol="TEST", action_type=CorpActionType.SPLIT,
            ex_date=date(2026, 10, 17), face_value_before=Decimal("10"),
            face_value_after=Decimal("2"), raw_subject=subject,
        )
    ]


def test_a_split_to_re_1_parses():
    """Regression: 'Re' (singular, exactly Rs 1) was silently missed entirely before
    this was fixed -- confirmed against a real pull, 7 of 15 real notices in one
    three-month window used this phrasing for a split down to face value 1."""
    subject = "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share"
    rows = parse_corporate_action_feed(_payload(_record(subject=subject)))
    assert rows[0].action_type is CorpActionType.SPLIT
    assert rows[0].face_value_before == Decimal("10")
    assert rows[0].face_value_after == Decimal("1")


def test_a_scheme_of_arrangement_bonus_is_not_classified():
    """Regression: 'Scheme Of Arrangement - Bonus Ncrps 46:1' matches the bare bonus
    ratio regex but NCRPS is Non-Convertible Redeemable Preference Shares, a different
    instrument -- applying 46:1 to this ISIN's equity quantity would be a real, wrong
    number, not a theoretical risk. Confirmed against a real live notice."""
    rows = parse_corporate_action_feed(
        _payload(_record(subject="Scheme Of Arrangement - Bonus Ncrps 46:1"))
    )
    assert rows == []


@pytest.mark.parametrize(
    "term",
    [
        "Merger", "Demerger", "Amalgamation", "Preference Share", "Debenture", "Warrant",
        "Capital Reduction", "Reduction Of Capital",
    ],
)
def test_other_disqualifying_terms_are_not_classified(term: str) -> None:
    rows = parse_corporate_action_feed(_payload(_record(subject=f"Bonus 1:1 - {term}")))
    assert rows == []


@pytest.mark.parametrize(
    "subject",
    [
        # Real, confirmed-live subjects: "Capital Reduction Pursuant To Nclt Order"
        # (2020-2022 pull) and "Capital Reduction" (2023-2025 pull) -- neither was
        # ratio-shaped, so this pins the disqualification rather than a ratio miss.
        "Capital Reduction",
        "Capital Reduction Pursuant To Nclt Order",
    ],
)
def test_real_capital_reduction_subjects_produce_no_candidate(subject: str) -> None:
    assert parse_corporate_action_feed(_payload(_record(subject=subject))) == []


def test_an_unrecognised_notice_type_is_simply_not_included() -> None:
    """A dividend, rights issue, or anything else this parser doesn't cover is not an
    error -- it's just absent from the result. Out of scope by design, not a failure."""
    rows = parse_corporate_action_feed(_payload(_record(subject="Dividend - Rs 1.50 Per Share")))
    assert rows == []


def test_a_dash_ex_date_is_skipped_not_raised() -> None:
    """NSE sends '-' as a real, routine value for a not-yet-fixed ex-date."""
    rows = parse_corporate_action_feed(_payload(_record(exDate="-")))
    assert rows == []


def test_a_blank_isin_or_subject_is_skipped_not_raised() -> None:
    rows = parse_corporate_action_feed(_payload(_record(isin=""), _record(subject="")))
    assert rows == []


def test_not_a_json_array_is_a_format_error() -> None:
    with pytest.raises(CorporateActionFeedFormatError):
        parse_corporate_action_feed(json.dumps({"not": "a list"}).encode())


def test_not_valid_json_is_a_format_error() -> None:
    with pytest.raises(CorporateActionFeedFormatError):
        parse_corporate_action_feed(b"<!doctype html><html>not json</html>")


def test_a_row_missing_a_required_field_is_a_format_error() -> None:
    bad = _record()
    del bad["exDate"]
    with pytest.raises(CorporateActionFeedFormatError):
        parse_corporate_action_feed(_payload(bad))
