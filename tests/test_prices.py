"""The price pipe. Offline, against trimmed REAL bhavcopy files.

The gate lives here: both exchanges are required, and the proof is two real holdings that
each appear on only one of them.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from app.prices.alerts import CollectingNotifier
from app.prices.pipe import fetch_day, merge, trading_days
from app.prices.sources import FetchFailed, NotPublished
from app.prices.udiff import BhavcopyFormatError, parse

FIXTURES = Path(__file__).parent.parent / "fixtures" / "bhavcopy"
PRICE_DATE = date(2026, 8, 12)

#: BSE-only in this portfolio: KALYANI-M.
BSE_ONLY = "INE0N6U01018"
#: NSE-only in this portfolio: KDL-SM. BUILD_PLAN called both of these "BSE-only"; the live
#: data says otherwise, and the gate is stronger for it -- each single-exchange pipe loses
#: a different real holding.
NSE_ONLY = "INE0O4R01018"

GOLDEN_PATH = Path(__file__).parent.parent / "fixtures" / "golden_portfolio.json"
HELD = (
    {h["isin"] for h in json.loads(GOLDEN_PATH.read_text())["expected"]["holdings"]}
    if GOLDEN_PATH.exists()
    else set()
)


def payload(exchange: str) -> bytes:
    return (FIXTURES / f"{exchange.lower()}_20260812.csv").read_bytes()


class FakeSource:
    def __init__(self, exchange: str, data: bytes | Exception):
        self.exchange = exchange
        self._data = data

    def fetch(self, on: date) -> bytes:
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


def both_sources():
    return [FakeSource("NSE", payload("nse")), FakeSource("BSE", payload("bse"))]


# --- parsing -------------------------------------------------------------------


@pytest.mark.parametrize("exchange", ["NSE", "BSE"])
def test_one_parser_reads_both_exchanges(exchange: str) -> None:
    """NSE and BSE publish identical UDiFF headers, so there is one parser, not two."""
    rows = parse(payload(exchange), exchange)
    assert rows
    assert all(r.exchange == exchange for r in rows)
    assert all(r.price_date == PRICE_DATE for r in rows)


def test_prices_are_decimal(dummy=None) -> None:
    row = parse(payload("NSE"), "NSE")[0]
    assert isinstance(row.close, Decimal)


def test_rows_are_keyed_by_isin_not_symbol(dummy=None) -> None:
    """Tickers get renamed and reused; ISINs do not."""
    rows = parse(payload("NSE"), "NSE")
    assert all(r.isin.startswith("IN") and len(r.isin) == 12 for r in rows)
    assert len({r.isin for r in rows}) == len(rows)


def test_a_changed_format_raises_rather_than_returning_nothing() -> None:
    """Parsing zero rows out of a changed file is how a pipe reports success while
    delivering no prices.

    The message says "the layout changed", not "this is a legacy file": a legacy file
    only reaches this parser after sources._to_udiff_csv has re-shaped it, so arriving
    here un-reshaped means the format moved under us. An earlier version claimed the
    legacy format had no ISIN column at all, which real fetched files disprove.
    """
    with pytest.raises(BhavcopyFormatError, match="layout changed"):
        parse(b"SYMBOL,SERIES,CLOSE\nBLS,EQ,263.00\n", "NSE")


def test_an_empty_file_raises() -> None:
    with pytest.raises(BhavcopyFormatError):
        parse(b"", "NSE")


def test_a_zip_is_transparently_decompressed() -> None:
    """NSE ships a ZIP and BSE ships bare CSV; detected, not configured."""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("bhav.csv", payload("NSE").decode())
    assert parse(buffer.getvalue(), "NSE") == parse(payload("NSE"), "NSE")


# --- HttpBhavcopySource.fetch() -------------------------------------------------


class _FakeHttpResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeHttpResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_bse_weekend_html_response_is_not_published_not_a_format_error() -> None:
    """Confirmed live, 2026-08-30 (a Sunday): BSE answers a non-trading day with HTTP 200
    and its own marketing homepage, not a 404. Falling through to parse() would raise
    BhavcopyFormatError and alert every single weekend -- exactly the "trains whoever
    reads the alerts to ignore them" failure NotPublished's own docstring warns about."""
    from app.prices.sources import HttpBhavcopySource

    html = b'<!DOCTYPE html><html lang="en"><head><title>BSE</title></head></html>'
    source = HttpBhavcopySource(
        "BSE", "https://example.invalid/{d}", opener=lambda *a, **k: _FakeHttpResponse(html)
    )
    with pytest.raises(NotPublished):
        source.fetch(date(2026, 8, 30))


def test_a_real_udiff_response_is_never_mistaken_for_html() -> None:
    from app.prices.sources import HttpBhavcopySource

    body = payload("NSE")
    source = HttpBhavcopySource(
        "NSE", "https://example.invalid/{d}", opener=lambda *a, **k: _FakeHttpResponse(body)
    )
    assert source.fetch(PRICE_DATE) == body


# --- legacy NSE archive fallback (pre-2024 dates) -------------------------------


def legacy_payload() -> str:
    """A real, trimmed 17-Oct-2023 legacy bhavcopy excerpt -- GENSOL (EQ), a BE-series
    row, and a non-equity (TB, a T-Bill) row, captured from the actual archive while
    building this fallback. See app.prices.sources.legacy_nse_source."""
    return (FIXTURES / "nse_legacy_20231017.csv").read_text()


def test_legacy_csv_reshapes_into_udiff_columns() -> None:
    """The whole point of _to_udiff_csv: udiff.parse, the one bhavcopy parser, reads
    the re-shaped output with no changes of its own."""
    from app.prices.sources import _to_udiff_csv

    rows = {r.isin: r for r in parse(_to_udiff_csv(legacy_payload()), "NSE")}
    gensol = rows["INE06H201014"]
    assert gensol.close == Decimal("882.2")
    assert gensol.price_date == date(2023, 10, 17)
    assert gensol.symbol == "GENSOL"
    assert gensol.series == "EQ"


def test_legacy_csv_includes_be_series() -> None:
    """BE (trade-to-trade) is still cash-segment equity, not a reason to drop a row."""
    from app.prices.sources import _to_udiff_csv

    rows = {r.isin: r for r in parse(_to_udiff_csv(legacy_payload()), "NSE")}
    assert "INE144J01027" in rows


def test_legacy_csv_filters_non_equity_series() -> None:
    """A T-Bill's "close" is a yield-derived price, not a share price -- valuing an
    equity holding at one would be nonsense, same reasoning as udiff.EQUITY_INSTRUMENTS."""
    from app.prices.sources import _to_udiff_csv

    rows = {r.isin: r for r in parse(_to_udiff_csv(legacy_payload()), "NSE")}
    assert "IN002023Y151" not in rows


class _FakeSubSource:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.calls: list[date] = []

    def fetch(self, on: date) -> bytes:
        self.calls.append(on)
        return self._body


def test_nse_bhavcopy_source_uses_legacy_before_the_cutover() -> None:
    from app.prices.sources import NSE_CURRENT_FORMAT_SINCE, TieredBhavcopySource

    current, legacy = _FakeSubSource(b"current"), _FakeSubSource(b"legacy")
    source = TieredBhavcopySource("NSE", current, legacy)

    before = NSE_CURRENT_FORMAT_SINCE - timedelta(days=1)
    assert source.fetch(before) == b"legacy"
    assert legacy.calls == [before]
    assert current.calls == []


def test_nse_bhavcopy_source_uses_current_format_on_and_after_the_cutover() -> None:
    from app.prices.sources import NSE_CURRENT_FORMAT_SINCE, TieredBhavcopySource

    current, legacy = _FakeSubSource(b"current"), _FakeSubSource(b"legacy")
    source = TieredBhavcopySource("NSE", current, legacy)

    assert source.fetch(NSE_CURRENT_FORMAT_SINCE) == b"current"
    assert current.calls == [NSE_CURRENT_FORMAT_SINCE]
    assert legacy.calls == []


# --- THE GATE ------------------------------------------------------------------


@pytest.mark.skipif(not GOLDEN_PATH.exists(), reason="golden_portfolio.json is local-only")
def test_every_held_isin_is_priced_by_the_union() -> None:
    """The session gate. Neither feed alone is enough."""
    result = fetch_day(PRICE_DATE, sources=both_sources())
    priced = {p.isin for p in result.prices}
    missing = sorted(HELD - priced)
    assert missing == [], f"held ISINs with no price: {missing}"


def test_a_bse_only_holding_is_lost_without_bse() -> None:
    nse_alone = fetch_day(PRICE_DATE, sources=[FakeSource("NSE", payload("nse"))])
    assert BSE_ONLY not in {p.isin for p in nse_alone.prices}

    both = fetch_day(PRICE_DATE, sources=both_sources())
    assert BSE_ONLY in {p.isin for p in both.prices}


def test_an_nse_only_holding_is_lost_without_nse() -> None:
    """The half BUILD_PLAN got backwards. KDL-SM is NSE-only, not BSE-only."""
    bse_alone = fetch_day(PRICE_DATE, sources=[FakeSource("BSE", payload("bse"))])
    assert NSE_ONLY not in {p.isin for p in bse_alone.prices}

    both = fetch_day(PRICE_DATE, sources=both_sources())
    assert NSE_ONLY in {p.isin for p in both.prices}


# --- merge rules ---------------------------------------------------------------


def test_nse_wins_where_both_quote() -> None:
    """DATA_MODEL: deeper liquidity."""
    nse = {r.isin: r for r in parse(payload("NSE"), "NSE")}
    bse = {r.isin: r for r in parse(payload("BSE"), "BSE")}
    dual = [i for i in nse if i in bse and nse[i].close != bse[i].close]
    assert dual, "fixture must contain at least one ISIN both exchanges quote differently"

    merged = {p.isin: p for p in merge({"NSE": list(nse.values()), "BSE": list(bse.values())})}
    for isin in dual:
        assert merged[isin].close == nse[isin].close
        assert merged[isin].source == "NSE_BHAVCOPY"
        assert "BSE" in merged[isin].also_quoted_by, "the other quote is still recorded"


def test_a_single_feed_isin_keeps_its_own_source() -> None:
    merged = {p.isin: p for p in fetch_day(PRICE_DATE, sources=both_sources()).prices}
    assert merged[BSE_ONLY].source == "BSE_BHAVCOPY"
    assert merged[NSE_ONLY].source == "NSE_BHAVCOPY"
    assert merged[BSE_ONLY].also_quoted_by == ()


# --- failure handling ----------------------------------------------------------


def test_a_closed_market_is_not_a_failure() -> None:
    """Weekends and holidays have no file. Alerting on them trains people to ignore alerts."""
    notifier = CollectingNotifier()
    result = fetch_day(
        date(2026, 8, 15),
        sources=[
            FakeSource("NSE", NotPublished("holiday")),
            FakeSource("BSE", NotPublished("holiday")),
        ],
        notifier=notifier,
    )
    assert result.succeeded
    assert result.not_published == ["NSE", "BSE"]
    assert notifier.alerts == [], "a holiday must not alert"


def test_a_fetch_failure_alerts() -> None:
    notifier = CollectingNotifier()
    result = fetch_day(
        PRICE_DATE,
        sources=[
            FakeSource("NSE", FetchFailed("NSE: HTTP 403")),
            FakeSource("BSE", payload("bse")),
        ],
        notifier=notifier,
    )
    assert not result.succeeded
    assert "NSE" in result.failures
    subjects = " ".join(a["subject"] for a in notifier.alerts)
    assert "NSE" in subjects


def test_half_a_run_is_reported_as_dangerous_not_fine() -> None:
    """One feed still prices most holdings, which is what makes a half-failure dangerous."""
    notifier = CollectingNotifier()
    result = fetch_day(
        PRICE_DATE,
        sources=[FakeSource("NSE", payload("nse")), FakeSource("BSE", FetchFailed("BSE: timeout"))],
        notifier=notifier,
    )
    assert result.prices, "prices were still produced"
    assert not result.succeeded, "but the run did NOT succeed"
    assert result.only_one_exchange
    assert any("one exchange" in a["subject"].lower() for a in notifier.alerts)
    assert BSE_ONLY not in {p.isin for p in result.prices}


def test_a_changed_format_alerts_too() -> None:
    notifier = CollectingNotifier()
    result = fetch_day(
        PRICE_DATE,
        sources=[FakeSource("NSE", b"WRONG,COLUMNS\n1,2\n"), FakeSource("BSE", payload("bse"))],
        notifier=notifier,
    )
    assert "NSE" in result.failures
    assert notifier.alerts


# --- calendar ------------------------------------------------------------------


def test_trading_days_skips_weekends() -> None:
    days = trading_days(date(2026, 8, 10), date(2026, 8, 16))
    assert date(2026, 8, 15) not in days, "Saturday"
    assert date(2026, 8, 16) not in days, "Sunday"
    assert len(days) == 5


def test_no_holiday_calendar_is_maintained() -> None:
    """A holiday still appears as a trading day here and 404s at the exchange.

    Deliberate: a hardcoded calendar needs maintaining every year, and being wrong either
    skips a real trading day or alerts on a real holiday. The exchange's own 404 is
    self-maintaining.
    """
    independence_day = date(2026, 8, 15)
    assert independence_day.weekday() == 5, "falls on a Saturday in 2026 anyway"


# --- live smoke test, deliberately opt-in --------------------------------------


@pytest.mark.network
def test_live_bhavcopy_still_parses() -> None:
    """The only thing a fixture cannot catch: the exchange changing its URL or format.

    Skipped by default. Run with `pytest -m network`.
    """
    from app.prices.sources import bse_source, nse_source

    target = date.today()
    for _ in range(7):
        target = target - __import__("datetime").timedelta(days=1)
        if target.weekday() < 5:
            break

    for source in (nse_source(), bse_source()):
        try:
            rows = parse(source.fetch(target), source.exchange)
        except NotPublished:
            pytest.skip(f"{source.exchange}: nothing published for {target}")
        assert rows, f"{source.exchange} returned no usable rows"
        assert all(r.isin for r in rows)


# --- legacy BSE archive (pre-2024 dates) -----------------------------------------
#
# The hole this closes: GUJTHEM (BSE scrip 506879) was BSE-only in Oct 2023, so no NSE
# file has its split evidence at any price. Fixtures below are REAL captured rows.


def bse_legacy(name: str) -> str:
    return (FIXTURES / f"bse_legacy_{name}.csv").read_text()


def test_bse_legacy_reshapes_into_udiff_columns() -> None:
    """Different column names, a two-digit year, and a different equity marker than NSE's
    legacy file -- all described as data, so one normaliser and one parser serve both."""
    from app.prices.sources import BSE_LEGACY_LAYOUT, _to_udiff_csv

    reshaped = _to_udiff_csv(bse_legacy("20231009"), BSE_LEGACY_LAYOUT)
    rows = {r.isin: r for r in parse(reshaped, "BSE")}
    gujthem = rows["INE942C01029"]
    assert gujthem.close == Decimal("1047.80")
    assert gujthem.price_date == date(2023, 10, 9), "09-Oct-23 is 2023, not 0023"


def test_bse_legacy_filters_non_equity_instruments() -> None:
    """SC_TYPE 'Q' is equity; the same file carries preference ('P') and bond rows whose
    ISINs differ from their equity sibling only in the series digits. Letting one through
    would quietly supply the wrong instrument's price -- the NCRPS trap again."""
    from app.prices.sources import BSE_LEGACY_LAYOUT, _to_udiff_csv

    raw = bse_legacy("20231009")
    assert "INE919I04010" in raw, "fixture must contain a preference row to exclude"
    rows = {r.isin for r in parse(_to_udiff_csv(raw, BSE_LEGACY_LAYOUT), "BSE")}
    assert "INE919I04010" not in rows
    assert rows == {"INE942C01029"}


def test_bse_legacy_and_current_formats_agree_on_an_overlap_date() -> None:
    """THE correctness proof for the re-shaping, not merely that it parses.

    2024-01-02 is served by BOTH BSE formats. Normalised, they must describe the same
    market -- same ISINs, same closes. Captured from the real files, where all 3,975
    equity closes agreed exactly.
    """
    from app.prices.sources import BSE_LEGACY_LAYOUT, _to_udiff_csv

    legacy = {
        r.isin: r.close
        for r in parse(_to_udiff_csv(bse_legacy("20240102"), BSE_LEGACY_LAYOUT), "BSE")
    }
    current = {
        r.isin: r.close
        for r in parse((FIXTURES / "bse_20240102.csv").read_bytes(), "BSE")
    }
    assert legacy, "fixture must not be empty"
    assert legacy == current, "the two formats disagree about the same trading day"


def test_bse_legacy_html_response_is_not_published() -> None:
    """BSE answers a date it does not have with HTTP 200 and an HTML page. Parsing that
    as zero rows would report a successful fetch of an empty market."""
    from app.prices.sources import legacy_bse_source

    html = b'<!DOCTYPE html><html><head><title>BSE</title></head></html>'

    class _Opener:
        def open(self, request, timeout=None):
            return _FakeHttpResponse(html)

    with pytest.raises(NotPublished):
        legacy_bse_source(opener_factory=lambda: _Opener()).fetch(date(2023, 10, 9))


def test_bse_tier_dispatches_on_the_same_boundary_as_nse() -> None:
    from app.prices.sources import NSE_CURRENT_FORMAT_SINCE, TieredBhavcopySource

    current, legacy = _FakeSubSource(b"current"), _FakeSubSource(b"legacy")
    source = TieredBhavcopySource("BSE", current, legacy)

    assert source.fetch(NSE_CURRENT_FORMAT_SINCE - timedelta(days=1)) == b"legacy"
    assert source.fetch(NSE_CURRENT_FORMAT_SINCE) == b"current"
    assert source.fetch(NSE_CURRENT_FORMAT_SINCE + timedelta(days=1)) == b"current"


def test_gujthem_split_evidence_is_reachable_from_bse_alone() -> None:
    """The acceptance test for this whole change: cum on the retired ISIN, ex on its
    replacement, one exchange, real captured data. 1047.80 / 225.15 = 4.65 against an
    expected x5 -- inside check_price_consistency's band, WITHOUT that guard changing.
    """
    from app.engine.corporate_actions import (
        CorpActionType,
        CorporateAction,
        Verification,
        check_price_consistency,
    )
    from app.prices.sources import BSE_LEGACY_LAYOUT, _to_udiff_csv

    cum_csv = _to_udiff_csv(bse_legacy("20231009"), BSE_LEGACY_LAYOUT)
    ex_csv = _to_udiff_csv(bse_legacy("20231010"), BSE_LEGACY_LAYOUT)
    cum = {r.isin: r.close for r in parse(cum_csv, "BSE")}
    ex = {r.isin: r.close for r in parse(ex_csv, "BSE")}

    action = CorporateAction(
        isin="INE942C01045", action_type=CorpActionType.SPLIT, ex_date=date(2023, 10, 10),
        face_value_before=Decimal(5), face_value_after=Decimal(1),
        price_cum=cum["INE942C01029"],   # the RETIRED identifier
        price_ex=ex["INE942C01045"],     # its replacement
        source="BSE legacy bhavcopy", source_url="https://example.invalid/bse",
        verification=Verification.VERIFIED,
    )
    assert action.multiplier() == 5
    assert check_price_consistency(action) is None, "existing guard, better evidence"


def test_a_bse_only_action_without_evidence_still_fails_closed() -> None:
    """Coverage improving must not make the engine less demanding. No prices, no pass."""
    from app.engine.corporate_actions import (
        CorpActionType,
        CorporateAction,
        Verification,
        check_price_consistency,
    )

    action = CorporateAction(
        isin="INE942C01045", action_type=CorpActionType.SPLIT, ex_date=date(2023, 10, 10),
        face_value_before=Decimal(5), face_value_after=Decimal(1),
        source="BSE legacy bhavcopy", source_url="https://example.invalid/bse",
        verification=Verification.VERIFIED,
    )
    failure = check_price_consistency(action)
    assert failure is not None and failure.code == "NO_PRICE_EVIDENCE"
