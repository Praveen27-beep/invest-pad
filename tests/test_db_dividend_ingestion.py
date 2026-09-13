"""The two declared-dividend sources meeting in the database -- Phase 1.

The question every test here asks is the same one: when a second source reports something,
does the system recognise it as the SAME dividend, a DIFFERENT dividend, or a case it
cannot tell apart? The third answer is the one that has to work, because the cost of
getting it wrong is a DRAFT event promoted to VERIFIED on evidence that describes a
different dividend -- and VERIFIED is what the product will show.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from app.db import dividend_events as de
from app.engine.corporate_actions import Verification
from app.engine.dividend_events import DividendEvent, DividendKind

pytestmark = pytest.mark.db

ISIN = "INE153T01027"  # seeded by the ``investor`` fixture (symbol BLS)
ACTOR = "22222222-2222-2222-2222-222222222222"
EX = date(2025, 7, 10)

NSE = "NSE corporate filings"
NSE_URL = "https://www.nseindia.com/companies-listing/corporate-filings-actions"
YF = "Yahoo Finance (yfinance)"
YF_URL = "https://finance.yahoo.com/quote/BLS.NS/history"


def _nse(amount: str = "1.50", kind: DividendKind = DividendKind.INTERIM, **kw) -> DividendEvent:
    return DividendEvent(
        isin=ISIN, ex_date=kw.pop("ex_date", EX), amount_per_share=Decimal(amount), kind=kind,
        source=NSE, source_url=NSE_URL, verification=Verification.DRAFT, **kw,
    )


def _yf(amount: str = "1.50", **kw) -> DividendEvent:
    return DividendEvent(
        isin=ISIN, ex_date=kw.pop("ex_date", EX), amount_per_share=Decimal(amount),
        kind=DividendKind.UNSPECIFIED, source=YF, source_url=YF_URL,
        verification=Verification.DRAFT, **kw,
    )


# ------------------------------------------------------------- case 4: nothing on file


def test_a_first_sighting_lands_draft(db: object, investor: str) -> None:
    """One source is not enough to project from. DRAFT is the honest resting state."""
    assert de.upsert_declared_dividend(db, _nse(), actor_uid=ACTOR) == de.OUTCOME_INSERTED
    db.commit()

    events = de.list_dividend_events(db, isins=[ISIN])
    assert len(events) == 1
    assert events[0].verification is Verification.DRAFT


# ------------------------------------------------- case 1: the same event, same source


def test_the_same_source_reporting_twice_changes_nothing(db: object, investor: str) -> None:
    """Re-running one feed is idempotent and does NOT look like confirmation.

    Two reads of one source are one observation -- the precise mistake the cross-source
    design exists to prevent.
    """
    de.upsert_declared_dividend(db, _nse(), actor_uid=ACTOR)
    db.commit()
    assert de.upsert_declared_dividend(db, _nse(), actor_uid=ACTOR) == de.OUTCOME_UNCHANGED
    db.commit()

    events = de.list_dividend_events(db, isins=[ISIN])
    assert len(events) == 1
    assert events[0].verification is Verification.DRAFT
    assert events[0].corroborated_by is None


# ------------------------------------- case 3: yfinance arrives second, no kind to give


def test_an_unspecified_second_source_corroborates_a_named_event(
    db: object, investor: str
) -> None:
    """WITHOUT THIS CASE THE TWO FEEDS WOULD NEVER CORROBORATE EACH OTHER AT ALL.

    Ticker.dividends cannot supply a kind, so a yfinance candidate is always UNSPECIFIED
    while the NSE notice for the same dividend is INTERIM. Matching on (isin, ex_date)
    rather than the full key is what lets them meet.
    """
    de.upsert_declared_dividend(db, _nse(kind=DividendKind.INTERIM), actor_uid=ACTOR)
    db.commit()

    assert de.upsert_declared_dividend(db, _yf(), actor_uid=ACTOR) == de.OUTCOME_CORROBORATED
    db.commit()

    events = de.list_dividend_events(db, isins=[ISIN])
    assert len(events) == 1, "one dividend, not two"
    assert events[0].verification is Verification.VERIFIED
    assert events[0].kind is DividendKind.INTERIM, "the named kind survives"
    assert events[0].corroborated_by == YF


# --------------------------------------- case 2: NSE arrives second, and names the kind


def test_a_named_second_source_classifies_an_unspecified_event(
    db: object, investor: str
) -> None:
    """The historic pass runs first and finds a dividend with no label; the notice feed
    later supplies one.

    The row was always THIS dividend -- what was missing was its name. Upgrading the label
    with better information is a reference-data correction, not a different fact, so this
    must not insert a second row.
    """
    assert de.upsert_declared_dividend(db, _yf(), actor_uid=ACTOR) == de.OUTCOME_INSERTED
    db.commit()

    outcome = de.upsert_declared_dividend(
        db, _nse(kind=DividendKind.FINAL, record_date=date(2025, 7, 11)), actor_uid=ACTOR
    )
    db.commit()

    assert outcome == de.OUTCOME_CLASSIFIED
    events = de.list_dividend_events(db, isins=[ISIN])
    assert len(events) == 1
    assert events[0].kind is DividendKind.FINAL
    assert events[0].verification is Verification.VERIFIED
    assert events[0].corroborated_by == NSE
    assert events[0].record_date == date(2025, 7, 11), "the later source's date is filled in"


def test_classification_still_refuses_a_contradictory_amount(db: object, investor: str) -> None:
    """Better information about the LABEL does not license accepting a different NUMBER."""
    de.upsert_declared_dividend(db, _yf(amount="1.50"), actor_uid=ACTOR)
    db.commit()

    outcome = de.upsert_declared_dividend(
        db, _nse(amount="1.75", kind=DividendKind.FINAL), actor_uid=ACTOR
    )
    db.commit()

    assert outcome == de.OUTCOME_CONFLICT
    event = de.list_dividend_events(db, isins=[ISIN])[0]
    assert event.verification is Verification.DISPUTED
    assert event.kind is DividendKind.UNSPECIFIED, "no relabelling on contradictory evidence"
    assert "AMOUNT_CONFLICT" in event.notes


# ------------------------------------------------------------------ case 5: ambiguous


def test_an_unspecified_source_refuses_to_choose_between_two_events(
    db: object, investor: str
) -> None:
    """THE FAIL-CLOSED CASE, and the reason match_unspecified returns a list.

    An interim and a special declared with one ex-date mean an UNSPECIFIED candidate could
    describe either. Attaching its agreement to one would promote that one to VERIFIED on
    evidence that may describe the other -- and VERIFIED is what the product shows. Doing
    nothing is correct, and being COUNTED is what stops it being silent.
    """
    de.upsert_declared_dividend(
        db, _nse(amount="1.50", kind=DividendKind.INTERIM), actor_uid=ACTOR)
    de.upsert_declared_dividend(
        db, _nse(amount="12.00", kind=DividendKind.SPECIAL), actor_uid=ACTOR)
    db.commit()

    assert de.upsert_declared_dividend(db, _yf(amount="1.50"), actor_uid=ACTOR) == (
        de.OUTCOME_AMBIGUOUS
    )
    db.commit()

    events = de.list_dividend_events(db, isins=[ISIN])
    assert len(events) == 2
    assert all(e.verification is Verification.DRAFT for e in events), "neither was promoted"
    assert all(e.corroborated_by is None for e in events)


def test_two_named_events_on_one_date_each_corroborate_independently(
    db: object, investor: str
) -> None:
    """Ambiguity is a property of the UNSPECIFIED candidate, not of the date.

    When both sources name the kind, an interim and a special sharing an ex-date resolve
    cleanly and separately.
    """
    de.upsert_declared_dividend(
        db, _nse(amount="1.50", kind=DividendKind.INTERIM), actor_uid=ACTOR)
    de.upsert_declared_dividend(
        db, _nse(amount="12.00", kind=DividendKind.SPECIAL), actor_uid=ACTOR)
    db.commit()

    other = "Accord Fintech"
    for amount, kind in (("1.50", DividendKind.INTERIM), ("12.00", DividendKind.SPECIAL)):
        de.upsert_declared_dividend(
            db,
            DividendEvent(
                isin=ISIN, ex_date=EX, amount_per_share=Decimal(amount), kind=kind,
                source=other, source_url="https://accordfintech.example/ca",
            ),
            actor_uid=ACTOR,
        )
    db.commit()

    events = de.list_dividend_events(db, isins=[ISIN])
    assert len(events) == 2
    assert all(e.verification is Verification.VERIFIED for e in events)


# ------------------------------------------------------------ the float/paise boundary


def test_a_float_sourced_amount_corroborates_a_clean_notice_amount(
    db: object, investor: str
) -> None:
    """End to end, the reason AMOUNT_QUANTUM exists.

    yfinance's 1.1 arrives as Decimal("1.100000") and the notice's as Decimal("1.10").
    Compared at paise -- the granularity dividends are actually declared at -- they are the
    same declaration. Compared exactly, every float-sourced corroboration would become a
    false DISPUTED.
    """
    de.upsert_declared_dividend(db, _nse(amount="1.10"), actor_uid=ACTOR)
    db.commit()
    assert de.upsert_declared_dividend(db, _yf(amount="1.100000"), actor_uid=ACTOR) == (
        de.OUTCOME_CORROBORATED
    )
    db.commit()
    assert de.list_dividend_events(db, isins=[ISIN])[0].verification is Verification.VERIFIED


def test_a_genuine_paisa_disagreement_is_still_a_conflict(db: object, investor: str) -> None:
    """Nothing real is hidden: a true disagreement is never smaller than a paisa."""
    de.upsert_declared_dividend(db, _nse(amount="1.10"), actor_uid=ACTOR)
    db.commit()
    assert de.upsert_declared_dividend(db, _yf(amount="1.11"), actor_uid=ACTOR) == (
        de.OUTCOME_CONFLICT
    )
    db.commit()
    assert de.list_dividend_events(db, isins=[ISIN])[0].verification is Verification.DISPUTED


# ------------------------------------------------------------------- the feed runners


class _FakeFeed:
    def __init__(self, payload: bytes):
        self._payload = payload

    def fetch(self, start: date, end: date) -> bytes:
        return self._payload


def _nse_payload(*subjects: str) -> bytes:
    return json.dumps([
        {
            "isin": ISIN, "symbol": "BLS", "exDate": "10-Jul-2025",
            "recDate": "11-Jul-2025", "subject": subject,
        }
        for subject in subjects
    ]).encode()


def test_the_nse_runner_lands_dividends_and_ignores_other_notices(
    db: object, investor: str
) -> None:
    result = de.refresh_dividend_feed(
        db, date(2025, 7, 1), date(2025, 7, 31),
        source=_FakeFeed(_nse_payload(
            "Interim Dividend - Rs 1.50 Per Share",
            "Bonus 1:1",
            "Annual General Meeting",
        )),
        actor_uid=ACTOR,
    )

    assert result["fetched"] == 1
    assert result[de.OUTCOME_INSERTED] == 1
    assert len(de.list_dividend_events(db, isins=[ISIN])) == 1


def test_the_nse_runner_is_idempotent(db: object, investor: str) -> None:
    payload = _nse_payload("Interim Dividend - Rs 1.50 Per Share")
    for _ in range(2):
        de.refresh_dividend_feed(
            db, date(2025, 7, 1), date(2025, 7, 31),
            source=_FakeFeed(payload), actor_uid=ACTOR,
        )
    assert len(de.list_dividend_events(db, isins=[ISIN])) == 1


def test_a_fetch_failure_is_reported_not_raised(db: object, investor: str) -> None:
    """A daily job logs and returns rather than propagating -- the same posture
    refresh_corporate_action_feed and _run_snapshots already take."""
    from app.ingest.corporate_action_feed import CorporateActionFeedFetchFailed

    class _Broken:
        def fetch(self, start: date, end: date) -> bytes:
            raise CorporateActionFeedFetchFailed("HTTP 403")

    result = de.refresh_dividend_feed(db, date(2025, 7, 1), date(2025, 7, 31), source=_Broken())
    assert result["fetched"] == 0
    assert "403" in result["error"]


def test_a_reshaped_payload_is_reported_not_raised(db: object, investor: str) -> None:
    result = de.refresh_dividend_feed(
        db, date(2025, 7, 1), date(2025, 7, 31), source=_FakeFeed(b"<html>403</html>")
    )
    assert result["fetched"] == 0
    assert "error" in result


def test_one_unusable_row_does_not_stop_the_others(db: object, investor: str) -> None:
    """Per-row commit is what makes log-and-continue actually isolate a bad row: without
    it, a later error would roll back every earlier row's successful work in the run."""
    payload = json.dumps([
        {"isin": ISIN, "symbol": "BLS", "exDate": "10-Jul-2025",
         "subject": "Interim Dividend - Rs 1.50 Per Share"},
        {"isin": "INE000000000", "symbol": "GHOST", "exDate": "11-Jul-2025",
         "subject": "Dividend - Rs 2 Per Share"},  # no security row -> FK rejects it
        {"isin": ISIN, "symbol": "BLS", "exDate": "12-Jul-2025",
         "subject": "Final Dividend - Rs 3 Per Share"},
    ]).encode()

    result = de.refresh_dividend_feed(
        db, date(2025, 7, 1), date(2025, 7, 31), source=_FakeFeed(payload), actor_uid=ACTOR
    )

    assert result["fetched"] == 3
    assert result["failed"] == 1
    assert result[de.OUTCOME_INSERTED] == 2
    assert len(de.list_dividend_events(db, isins=[ISIN])) == 2


class _FakeYf:
    def __init__(self, series: dict[date, float]):
        self._series = series

    def dividends(self, symbol: str) -> dict[date, float]:
        return dict(self._series)


def test_the_yfinance_runner_corroborates_what_the_notice_feed_found(
    db: object, investor: str
) -> None:
    """The two entry points composing, which is the actual Phase 1 deliverable: a dividend
    that reaches VERIFIED without any human step, because two separately-operated sources
    read the same fact."""
    de.refresh_dividend_feed(
        db, date(2025, 7, 1), date(2025, 7, 31),
        source=_FakeFeed(_nse_payload("Interim Dividend - Rs 1.50 Per Share")),
        actor_uid=ACTOR,
    )
    result = de.discover_dividends_from_yfinance(
        db, isins=[ISIN], source=_FakeYf({EX: 1.5}), actor_uid=ACTOR
    )

    assert result[de.OUTCOME_CORROBORATED] == 1
    event = de.list_dividend_events(db, isins=[ISIN])[0]
    assert event.verification is Verification.VERIFIED
    assert event.source == NSE
    assert event.corroborated_by == "Yahoo Finance (yfinance)"


def test_the_yfinance_runner_skips_an_isin_with_no_security_row(
    db: object, investor: str
) -> None:
    result = de.discover_dividends_from_yfinance(
        db, isins=["INE000000000"], source=_FakeYf({EX: 1.5}), actor_uid=ACTOR
    )
    assert result == {}


def test_a_yfinance_lookup_failure_is_recorded_per_isin(db: object, investor: str) -> None:
    class _Broken:
        def dividends(self, symbol: str) -> dict[date, float]:
            raise RuntimeError("Yahoo said no")

    result = de.discover_dividends_from_yfinance(
        db, isins=[ISIN], source=_Broken(), actor_uid=ACTOR)
    assert "Yahoo said no" in result["errors"][ISIN]


def test_neither_runner_writes_to_the_ledger(db: object, investor: str) -> None:
    """THE LOAD-BEARING NEGATIVE TEST OF PHASE 1.

    Both entry points can run, discover, corroborate and VERIFY, and the ledger must be
    untouched. A verified declaration is still only a declaration -- receipt is a separate
    question neither source answers.
    """
    de.refresh_dividend_feed(
        db, date(2025, 7, 1), date(2025, 7, 31),
        source=_FakeFeed(_nse_payload("Interim Dividend - Rs 1.50 Per Share")),
        actor_uid=ACTOR,
    )
    de.discover_dividends_from_yfinance(
        db, isins=[ISIN], source=_FakeYf({EX: 1.5}), actor_uid=ACTOR)
    db.commit()

    assert de.list_dividend_events(db, isins=[ISIN])[0].verification is Verification.VERIFIED
    with db.cursor() as cur:
        cur.execute('SELECT count(*) FROM "transaction"')
        assert cur.fetchone()[0] == 0
