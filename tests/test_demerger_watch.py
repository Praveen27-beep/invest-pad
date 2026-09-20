"""app.ingest.demerger_watch -- notification only, never an alias, never a corporate
action, never a queue.

``"Scheme Of Arrangement - Bonus Ncrps 46:1"`` is the same real, confirmed-live subject
``test_corporate_action_feed.py`` uses to prove ``parse_corporate_action_feed`` correctly
REFUSES to classify it. This file proves the other half: that refusal is exactly the row
this module is for, so the notice does not just vanish.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from app.ingest.corporate_action_feed import (
    CorporateActionFeedFetchFailed,
    CorporateActionFeedFormatError,
)
from app.ingest.demerger_watch import (
    DemergerNotice,
    check_demerger_watch,
    find_demerger_notices,
)


def _payload(*records: dict) -> bytes:
    return json.dumps(list(records)).encode()


def _record(**overrides) -> dict:
    base = {
        "isin": "INE153T01027", "symbol": "TEST", "exDate": "17-Oct-2026",
        "subject": "Scheme Of Arrangement - Bonus Ncrps 46:1",
    }
    return {**base, **overrides}


def test_finds_the_real_confirmed_live_scheme_notice() -> None:
    """The exact subject test_corporate_action_feed.py proves is correctly refused a
    ratio classification -- this module's whole reason to exist is that refusal must
    not also mean silence."""
    notices = find_demerger_notices(_payload(_record()))
    assert notices == [
        DemergerNotice(
            isin="INE153T01027", symbol="TEST",
            subject="Scheme Of Arrangement - Bonus Ncrps 46:1",
            ex_date=date(2026, 10, 17),
        )
    ]


@pytest.mark.parametrize("term", ["Merger", "Demerger", "Amalgamation"])
def test_finds_each_demerger_shaped_term(term: str) -> None:
    notices = find_demerger_notices(_payload(_record(subject=f"{term} of Foo into Bar")))
    assert len(notices) == 1
    assert notices[0].subject == f"{term} of Foo into Bar"


@pytest.mark.parametrize(
    "subject",
    [
        # Real, confirmed-live subjects from the same two 3-year audit that added
        # these terms to corporate_action_feed.py's _DISQUALIFYING_TERMS -- widening
        # THIS regex is notification-only, so it was added without the "is it
        # ratio-shaped" caution that gated the disqualification-list change.
        "Capital Reduction",
        "Capital Reduction Pursuant To Nclt Order",
        "Reduction Of Capital",
    ],
)
def test_finds_capital_reduction_notices(subject: str) -> None:
    notices = find_demerger_notices(_payload(_record(subject=subject)))
    assert len(notices) == 1
    assert notices[0].subject == subject


@pytest.mark.parametrize(
    "subject",
    ["Bonus 1:1", "Sub-Division - From Rs.10/- To Rs.2/-", "Preference Share", "Debenture"],
)
def test_ignores_non_demerger_notices(subject: str) -> None:
    assert find_demerger_notices(_payload(_record(subject=subject))) == []


def test_unfixed_ex_date_is_none_not_an_error() -> None:
    """"-" is NSE's own routine value for a date not yet fixed -- a demerger's
    apportionment letter can easily predate a fixed ex-date."""
    notices = find_demerger_notices(_payload(_record(exDate="-")))
    assert notices[0].ex_date is None


def test_a_row_missing_a_required_field_is_skipped_not_raised_on() -> None:
    """This module's own bug surface stays out of parse_corporate_action_feed's
    format-guarantee territory -- a malformed row here is silently skipped."""
    payload = json.dumps([{"subject": "Demerger of Foo"}]).encode()
    assert find_demerger_notices(payload) == []


def test_broken_json_still_raises_format_error() -> None:
    with pytest.raises(CorporateActionFeedFormatError):
        find_demerger_notices(b"not json")


def test_a_non_array_payload_raises_format_error() -> None:
    with pytest.raises(CorporateActionFeedFormatError):
        find_demerger_notices(json.dumps({"not": "a list"}).encode())


# --------------------------------------------------------------------------------------
# check_demerger_watch -- the DB-free-write, log-only orchestration.
# --------------------------------------------------------------------------------------


class _FakeFeed:
    def __init__(self, payload: bytes | None = None, exc: Exception | None = None) -> None:
        self.payload = payload if payload is not None else b"[]"
        self.exc = exc
        self.calls = 0

    def fetch(self, start, end):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.payload


class _FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def execute(self, *args, **kwargs) -> None:
        pass

    def fetchall(self) -> list[tuple]:
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        pass


class _FakeConn:
    def __init__(self, tracked_symbols: list[str]) -> None:
        self._rows = [(s,) for s in tracked_symbols]

    def cursor(self):
        return _FakeCursor(self._rows)


def test_logs_one_warning_per_tracked_symbol_touched(caplog) -> None:
    payload = _payload(
        _record(symbol="TATASTEEL", subject="Demerger of the steel business"),
        _record(symbol="UNTRACKED", subject="Amalgamation of Foo and Bar"),
    )
    conn = _FakeConn(tracked_symbols=["TATASTEEL"])
    feed = _FakeFeed(payload=payload)

    with caplog.at_level("WARNING", logger="demerger_watch"):
        logged = check_demerger_watch(conn, source=feed, today=date(2026, 9, 20))

    assert logged == 1
    assert any("TATASTEEL" in r.message for r in caplog.records)
    assert not any("UNTRACKED" in r.message for r in caplog.records)


def test_no_tracked_symbol_touched_logs_nothing(caplog) -> None:
    payload = _payload(_record(symbol="SOMEOTHERCO", subject="Demerger of Foo"))
    conn = _FakeConn(tracked_symbols=["TATASTEEL"])
    feed = _FakeFeed(payload=payload)

    with caplog.at_level("WARNING", logger="demerger_watch"):
        logged = check_demerger_watch(conn, source=feed, today=date(2026, 9, 20))

    assert logged == 0
    assert caplog.records == []


def test_writes_nothing_to_the_database() -> None:
    """The whole point: a NOTIFICATION, not a row. _FakeConn's cursor only ever
    SELECTs -- an INSERT/UPDATE call would be a signature mismatch on a real
    connection, but the stronger guarantee is structural: this module has no import of
    anything that writes, and no function here takes an object to persist."""
    payload = _payload(_record(symbol="TATASTEEL", subject="Demerger of Foo"))
    conn = _FakeConn(tracked_symbols=["TATASTEEL"])
    logged = check_demerger_watch(conn, source=_FakeFeed(payload=payload), today=date(2026, 9, 20))
    assert logged == 1  # reaching this line at all proves no write was attempted or required


def test_fetch_failure_returns_zero_and_never_raises(caplog) -> None:
    conn = _FakeConn(tracked_symbols=["TATASTEEL"])
    feed = _FakeFeed(exc=CorporateActionFeedFetchFailed("NSE down"))

    with caplog.at_level("WARNING", logger="demerger_watch"):
        logged = check_demerger_watch(conn, source=feed, today=date(2026, 9, 20))

    assert logged == 0
    assert any("skipping this run" in r.message for r in caplog.records)


def test_format_failure_returns_zero_and_never_raises(caplog) -> None:
    conn = _FakeConn(tracked_symbols=["TATASTEEL"])
    feed = _FakeFeed(payload=b"not json")

    with caplog.at_level("WARNING", logger="demerger_watch"):
        logged = check_demerger_watch(conn, source=feed, today=date(2026, 9, 20))

    assert logged == 0


def test_settings_flag_defaults_to_disabled() -> None:
    from app.config import Settings

    settings = Settings(
        _env_file=None,
        debug=True,
        database_url="postgresql://localhost/test",
        portfolio_encryption_key="test-encryption-key",
        portfolio_pan_pepper="test-pan-pepper",
        jwt_secret="test-jwt-secret",
    )
    assert settings.demerger_watch_enabled is False
