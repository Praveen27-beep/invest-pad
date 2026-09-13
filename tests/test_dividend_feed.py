"""Reading dividend notices out of NSE's free-text ``subject`` field, and refusing to.

The refusals carry more weight than the successes here. A missed notice produces no
candidate and is recoverable on the next run or by hand; a misread one produces a wrong
rupee figure attached to a real security, and nothing downstream can tell that apart from
a correct read -- the same argument parse_corporate_action_feed's docstring makes about
ratio strings, applied to amounts.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from app.ingest.corporate_action_feed import (
    CorporateActionFeedFormatError,
    parse_corporate_action_feed,
    parse_dividend_feed,
)


def _record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "isin": "INE153T01027",
        "symbol": "TEST",
        "exDate": "17-Oct-2026",
        "recDate": "18-Oct-2026",
        "subject": "Dividend - Rs 1.50 Per Share",
    }
    base.update(overrides)
    return base


def _payload(*records: dict[str, object]) -> bytes:
    return json.dumps(list(records)).encode()


def _one(subject: str, **overrides: object):
    rows = parse_dividend_feed(_payload(_record(subject=subject, **overrides)))
    return rows[0] if rows else None


# ------------------------------------------------------------------ the common shapes


def test_a_plain_dividend_notice_parses() -> None:
    row = _one("Dividend - Rs 1.50 Per Share")
    assert row.amount_per_share == Decimal("1.50")
    assert row.kind == "UNSPECIFIED"
    assert row.ex_date == date(2026, 10, 17)
    assert row.record_date == date(2026, 10, 18)
    assert row.raw_subject == "Dividend - Rs 1.50 Per Share"


@pytest.mark.parametrize(
    ("subject", "kind"),
    [
        ("Interim Dividend - Rs 5 Per Share", "INTERIM"),
        ("Final Dividend - Rs 2.50 Per Share", "FINAL"),
        ("Special Dividend - Rs 10 Per Share", "SPECIAL"),
        ("Dividend - Rs 1.25 Per Share", "UNSPECIFIED"),
    ],
)
def test_the_kind_is_read_when_the_notice_names_it(subject: str, kind: str) -> None:
    assert _one(subject).kind == kind


@pytest.mark.parametrize(
    ("subject", "amount"),
    [
        ("Dividend - Rs 1.50 Per Share", "1.50"),
        ("Dividend Rs.1.50/- Per Share", "1.50"),
        ("Interim Dividend - Re. 1 Per Share", "1"),
        ("Dividend - Rs 12 Per Share", "12"),
        ("Dividend - Rs 0.50 Per Share", "0.50"),
        ("Interim Dividend Rs 225 Per Share", "225"),
    ],
)
def test_real_amount_phrasings_parse(subject: str, amount: str) -> None:
    """"Re." for exactly one rupee and "Rs." for everything else is Indian English
    grammar, not a typo to normalise away -- the same distinction _SPLIT_RE already
    carries. Missing it would silently drop every Re. 1 dividend."""
    assert _one(subject).amount_per_share == Decimal(amount)


# ---------------------------------------------------------------------- the refusals


def test_a_percentage_declaration_is_refused() -> None:
    """"Dividend - 150%" means 150% OF FACE VALUE.

    Computing it needs the face value at that time, which this feed does not carry and
    which a later split changes. Reading "150" as Rs 150 would be a 100x error on what is
    probably a Rs 1.50 dividend.
    """
    assert _one("Dividend - 150%") is None
    assert _one("Interim Dividend - 25% i.e. Rs 2.50 Per Share") is None


def test_two_amounts_in_one_subject_are_refused() -> None:
    """Both amounts and both kinds are present, but PAIRING them is an inference about
    text order, and getting it backwards swaps a Rs 2 special with a Rs 1.50 interim."""
    assert _one("Interim Dividend Rs 1.50 Per Share And Special Dividend Rs 2 Per Share") is None


def test_two_kinds_named_without_two_amounts_are_also_refused() -> None:
    """The amount could be read but not attributed to a kind."""
    assert _one("Interim And Final Dividend - Rs 3 Per Share") is None


@pytest.mark.parametrize(
    "subject",
    [
        "Dividend On Preference Share - Rs 1.50 Per Share",
        "Scheme Of Arrangement - Dividend Rs 2 Per Share",
        "Dividend On Debenture - Rs 5 Per Share",
        "Dividend - Rs 3 Per Share - Partly Paid",
    ],
)
def test_another_instruments_dividend_is_refused(subject: str) -> None:
    """_DISQUALIFYING_TERMS is reused unchanged.

    A preference-share or debenture "dividend" is a different instrument's income and must
    not land against an equity ISIN.
    """
    assert _one(subject) is None


def test_a_notice_with_no_amount_at_all_is_refused() -> None:
    assert _one("Dividend") is None
    assert _one("Annual General Meeting / Dividend") is None


def test_a_bare_number_is_not_read_as_an_amount() -> None:
    """Requiring the currency marker is what stops this regex reading a ratio, a face
    value, a percentage or a year as a rupee amount. A deliberate false negative."""
    assert _one("Dividend - 1.50 Per Share") is None


def test_a_zero_dividend_is_refused() -> None:
    assert _one("Dividend - Rs 0 Per Share") is None


def test_a_non_dividend_notice_is_not_returned() -> None:
    assert _one("Bonus 1:1") is None
    assert _one("Sub-Division (Split) - From Rs.10/- To Rs.2/-") is None


# ------------------------------------------------------------------------- the dates


def test_a_dash_ex_date_is_skipped_not_raised() -> None:
    """NSE sends "-" for a date not yet fixed. Without an ex-date there is no eligibility
    cutoff, so there is nothing computable -- and a guessed date would be worse."""
    assert parse_dividend_feed(_payload(_record(exDate="-"))) == []


def test_a_missing_record_date_is_not_a_format_error() -> None:
    """recDate is deliberately outside _REQUIRED_FIELDS, so a feed that stops sending it
    degrades to a missing display field rather than a run-stopping format error."""
    record = _record()
    del record["recDate"]
    row = parse_dividend_feed(_payload(record))[0]
    assert row.record_date is None
    assert row.amount_per_share == Decimal("1.50")


def test_a_dash_record_date_is_simply_absent() -> None:
    assert _one("Dividend - Rs 1.50 Per Share", recDate="-").record_date is None


def test_a_record_date_before_the_ex_date_is_dropped_not_the_notice() -> None:
    """Cannot be true, and in practice means the fields were transposed.

    The ex-date is what eligibility uses and the record date is display only, so losing
    the record date costs nothing while losing the notice would cost a real dividend.
    """
    row = _one("Dividend - Rs 1.50 Per Share", recDate="01-Oct-2026")
    assert row is not None
    assert row.record_date is None
    assert row.ex_date == date(2026, 10, 17)


def test_a_blank_isin_or_subject_is_skipped_not_raised() -> None:
    assert parse_dividend_feed(_payload(_record(isin=""))) == []
    assert parse_dividend_feed(_payload(_record(subject=""))) == []


# ------------------------------------------------------------- the format contract


def test_not_a_json_array_is_a_format_error() -> None:
    with pytest.raises(CorporateActionFeedFormatError):
        parse_dividend_feed(b'{"isin": "INE153T01027"}')


def test_not_valid_json_is_a_format_error() -> None:
    with pytest.raises(CorporateActionFeedFormatError):
        parse_dividend_feed(b"<html>403</html>")


def test_a_row_missing_a_required_field_is_a_format_error() -> None:
    """Same contract and same required fields as parse_corporate_action_feed -- a missing
    field every row has always carried is the clearest signal NSE reshaped the API."""
    bad = _record()
    del bad["subject"]
    with pytest.raises(CorporateActionFeedFormatError):
        parse_dividend_feed(_payload(bad))


# --------------------------------------------------- the two parsers over one payload


def test_one_payload_serves_both_parsers_without_overlap() -> None:
    """One fetch, two parsers, no row claimed twice.

    The bonus/split parser still drops dividends -- which is now correct rather than
    merely incomplete, because this parser is what reads them.
    """
    payload = _payload(
        _record(subject="Bonus 1:1"),
        _record(subject="Interim Dividend - Rs 1.50 Per Share", exDate="20-Oct-2026"),
        _record(subject="Sub-Division (Split) - From Rs.10/- To Rs.2/-", exDate="21-Oct-2026"),
        _record(subject="Annual General Meeting", exDate="22-Oct-2026"),
    )

    actions = parse_corporate_action_feed(payload)
    dividends = parse_dividend_feed(payload)

    assert [a.action_type.value for a in actions] == ["BONUS", "SPLIT"]
    assert [d.ex_date for d in dividends] == [date(2026, 10, 20)]


def test_a_dividend_feed_row_carries_no_quantity_or_total() -> None:
    """Multiplying by a holder's position is what turns a declaration into an expectation,
    and that happens on read -- never in an ingestion row."""
    from app.ingest.corporate_action_feed import DividendFeedRow

    fields = set(DividendFeedRow.__dataclass_fields__)
    assert not fields & {"quantity", "total", "gross", "net", "tds"}
