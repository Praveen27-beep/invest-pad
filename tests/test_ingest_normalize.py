"""Printed notation -> canonical Decimal, or a refusal. Never a guess, never a float."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.ingest.normalize import (
    NotADateError,
    NotANumberError,
    normalize_date,
    normalize_money,
)

TODAY = date(2026, 9, 5)


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("1000", "1000"),
        ("1,000.00", "1000.00"),
        ("1,00,000.00", "100000.00"),  # Indian lakh grouping
        ("1 000.00", "1000.00"),
        ("Rs. 1,000.00", "1000.00"),
        ("₹1,000.00", "1000.00"),
        ("-1,000.00", "-1000.00"),
        ("2663.95", "2663.95"),
        ("0.0000", "0.0000"),
    ],
)
def test_accepted_notations(printed: str, expected: str) -> None:
    assert normalize_money(printed) == Decimal(expected)


@pytest.mark.parametrize(
    ("printed", "expected"),
    [("(7.00)", "-7.00"), ("(1,000.00)", "-1000.00"), ("(Rs. 47,951.10)", "-47951.10")],
)
def test_accounting_negatives(printed: str, expected: str) -> None:
    """THE GAP this module exists for. Every charge on a real note is printed as a
    bracketed negative, and the prompt tells the model to copy it verbatim --
    ``zerodha_contract_note._decimal`` raises on exactly this input."""
    assert normalize_money(printed) == Decimal(expected)


def test_bracketed_zero_stays_zero() -> None:
    """-0 is not a thing the ledger should ever carry."""
    assert normalize_money("(0.00)") == Decimal("0.00")


def test_trailing_zeros_are_preserved() -> None:
    """Decimal keeps scale, and scale is information: 7.00 was printed to the paisa."""
    assert str(normalize_money("7.00")) == "7.00"


def test_the_result_is_never_a_float() -> None:
    for printed in ("1,000.00", "(7.00)", "0.0000"):
        value = normalize_money(printed)
        assert isinstance(value, Decimal)
        assert not isinstance(value, float)


@pytest.mark.parametrize("printed", ["1.000,00", "-1.234.567,89"])
def test_european_notation_is_refused_not_guessed(printed: str) -> None:
    """1.000,00 could be 1.0 or 1000.0. An Indian broker prints neither this way, so the
    honest answer is to refuse -- guessing here is the silent corruption the whole
    verification layer exists to prevent."""
    with pytest.raises(NotANumberError, match="European"):
        normalize_money(printed)


@pytest.mark.parametrize(
    "printed", ["", "   ", "N/A", "-", "1.5e3", "12.34.56", "abc", "1,000.00 CR", "()"]
)
def test_unreadable_values_raise_rather_than_defaulting(printed: str) -> None:
    """CLAUDE.md rule 4's shape: a value we cannot read fails loudly. Returning 0 here
    would understate a cost basis and nothing downstream would complain."""
    with pytest.raises(NotANumberError):
        normalize_money(printed)


def test_none_raises() -> None:
    with pytest.raises(NotANumberError):
        normalize_money(None)  # type: ignore[arg-type]


# --- dates ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("12/08/2026", date(2026, 8, 12)),
        ("12-08-2026", date(2026, 8, 12)),
        ("2026-08-12", date(2026, 8, 12)),
        ("12-Aug-2026", date(2026, 8, 12)),
    ],
)
def test_accepted_date_formats(printed: str, expected: date) -> None:
    assert normalize_date(printed, today=TODAY) == expected


def test_day_first_is_not_a_preference() -> None:
    """05/09/2026 is 5 September on an Indian document, not 9 May. An ambiguous date
    silently read month-first is wrong for the first twelve days of every month."""
    assert normalize_date("05/09/2026", today=TODAY) == date(2026, 9, 5)


def test_a_future_trade_is_refused() -> None:
    with pytest.raises(NotADateError, match="future"):
        normalize_date("01/01/2099", today=TODAY)


def test_a_trade_before_dematerialisation_is_refused() -> None:
    with pytest.raises(NotADateError, match="predates"):
        normalize_date("01/01/1970", today=TODAY)


def test_the_ceiling_is_injected_not_read_from_the_clock() -> None:
    """Pins that the bound is a parameter -- a test that depended on the real clock would
    start failing on its own one day."""
    assert normalize_date("05/09/2026", today=date(2026, 9, 5)) == date(2026, 9, 5)
    with pytest.raises(NotADateError):
        normalize_date("05/09/2026", today=date(2026, 9, 4))


@pytest.mark.parametrize("printed", ["", "not a date", "32/01/2026", "2026-13-01"])
def test_unparseable_dates_raise(printed: str) -> None:
    with pytest.raises(NotADateError):
        normalize_date(printed, today=TODAY)
