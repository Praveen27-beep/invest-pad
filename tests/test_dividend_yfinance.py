"""yfinance as the historic-depth dividend source -- and the float boundary.

NSE's notices API has no historical depth, so a years-deep ledger can never have its
dividends discovered there. This is the only free source that does. What it carries is an
ex-date and an amount and nothing else: no record date, no payment date, no kind, and no
evidence that anybody was paid.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.ingest.corporate_action_yfinance import (
    YfinanceDividendSource,
    YfinanceSource,
    discover_dividend_candidates,
)


class _FakeYfinance:
    """Injected in place of the real library, exactly as the split tests do -- no network
    call, and no dependence on Yahoo still saying the same thing tomorrow."""

    def __init__(self, series: dict[date, float]):
        self._series = series

    def dividends(self, symbol: str) -> dict[date, float]:
        return dict(self._series)


def test_a_dividend_history_becomes_candidates() -> None:
    source = _FakeYfinance({date(2024, 7, 18): 10.0, date(2025, 7, 10): 5.5})
    candidates = discover_dividend_candidates(source, "INE002A01018", "RELIANCE")

    assert {c.ex_date for c in candidates} == {date(2024, 7, 18), date(2025, 7, 10)}
    assert {c.amount_per_share for c in candidates} == {Decimal("10"), Decimal("5.5")}
    assert all(c.isin == "INE002A01018" for c in candidates)
    assert all("RELIANCE.NS" in c.source_url for c in candidates)


def test_a_float_amount_does_not_carry_its_binary_error() -> None:
    """THE LOAD-BEARING CONVERSION TEST.

    Decimal(1.1) is 1.100000000000000088817841970012523233890533447265625. Compared for
    equality against the NSE notice's clean 1.1 during corroboration, that would never
    match -- silently turning every cross-source agreement into a DISPUTED conflict and
    defeating the only verification a dividend has. Going through str() is what avoids it.
    """
    candidates = discover_dividend_candidates(
        _FakeYfinance({date(2025, 7, 10): 1.1}), "INE002A01018", "RELIANCE"
    )
    assert candidates[0].amount_per_share == Decimal("1.1")
    assert candidates[0].amount_per_share == Decimal("1.100000")


def test_a_float_amount_compares_equal_to_a_parsed_notice_amount() -> None:
    """The property the conversion exists to preserve, stated end to end."""
    from app.engine.dividend_events import amounts_agree

    yf = discover_dividend_candidates(
        _FakeYfinance({date(2025, 7, 10): 1.1}), "INE002A01018", "RELIANCE"
    )[0]
    from_notice = Decimal("1.10")  # as parse_dividend_feed would read "Rs 1.10 Per Share"
    assert amounts_agree(yf.amount_per_share, from_notice)


def test_a_zero_amount_is_skipped() -> None:
    """Yahoo occasionally carries a zero row for a cancelled or restated declaration, and
    a zero dividend is not a dividend."""
    candidates = discover_dividend_candidates(
        _FakeYfinance({date(2025, 7, 10): 0.0, date(2025, 8, 1): 2.0}),
        "INE002A01018", "RELIANCE",
    )
    assert [c.ex_date for c in candidates] == [date(2025, 8, 1)]


def test_a_negative_amount_is_skipped() -> None:
    candidates = discover_dividend_candidates(
        _FakeYfinance({date(2025, 7, 10): -1.0}), "INE002A01018", "RELIANCE"
    )
    assert candidates == []


def test_an_empty_history_is_not_an_error() -> None:
    assert discover_dividend_candidates(_FakeYfinance({}), "INE002A01018", "RELIANCE") == []


def test_a_candidate_carries_no_kind() -> None:
    """The kind is genuinely absent from the data, not merely hard to parse.

    Inferring it -- from the month, from a position in the year, from the size relative to
    previous payouts -- would be exactly the invention CLAUDE.md forbids. UNSPECIFIED is
    supplied by the caller when it builds a DividendEvent, which is why nothing in this
    module imports an engine enum.
    """
    from app.ingest.corporate_action_yfinance import YfinanceDividendCandidate

    assert "kind" not in YfinanceDividendCandidate.__dataclass_fields__


def test_a_candidate_carries_no_payment_evidence() -> None:
    """Pinned because this is the whole distinction the design turns on: a candidate from
    here is a DECLARATION, and nothing about it says anybody was paid."""
    from app.ingest.corporate_action_yfinance import YfinanceDividendCandidate

    fields = set(YfinanceDividendCandidate.__dataclass_fields__)
    assert not fields & {"payment_date", "paid", "received", "net", "tds", "credited"}


def test_the_real_source_satisfies_the_dividend_protocol() -> None:
    """One injected fake stands in for both split and dividend lookups, exactly as one
    real Ticker serves both -- so the protocol has to be satisfied by the same class."""
    assert isinstance(YfinanceSource(), YfinanceDividendSource)
    assert isinstance(_FakeYfinance({}), YfinanceDividendSource)
