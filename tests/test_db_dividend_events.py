"""The dividend_event reference table against a real database -- migration 029.

What is being pinned here is mostly NEGATIVE, and deliberately: the table's value is as
much in what it refuses as in what it stores. A dividend reaches VERIFIED only through two
distinct sources agreeing or a human reading the filing; an amount conflict becomes one
DISPUTED row rather than two competing rows; and an unspecified-kind candidate must find
the event it describes instead of duplicating it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import psycopg
import pytest
from app.db import dividend_events as de
from app.db.dividend_events import DividendEventDateError
from app.engine.corporate_actions import Verification
from app.engine.dividend_events import DividendEvent, DividendKind

pytestmark = pytest.mark.db

ISIN = "INE153T01027"  # seeded by the ``investor`` fixture (symbol BLS)
ACTOR = "22222222-2222-2222-2222-222222222222"

NSE = "NSE corporate filings"
NSE_URL = "https://www.nseindia.com/companies-listing/corporate-filings-actions"
YF = "Yahoo Finance (yfinance)"
YF_URL = "https://finance.yahoo.com/quote/BLS.NS"


def _declared(
    ex_date: date = date(2025, 7, 10),
    amount: str = "1.50",
    kind: DividendKind = DividendKind.INTERIM,
    **overrides: object,
) -> DividendEvent:
    """A single-sourced declaration, as a feed would first produce it: DRAFT, no
    corroboration yet."""
    base: dict[str, object] = {
        "isin": ISIN,
        "ex_date": ex_date,
        "amount_per_share": Decimal(amount),
        "kind": kind,
        "source": NSE,
        "source_url": NSE_URL,
        "verification": Verification.DRAFT,
    }
    base.update(overrides)
    return DividendEvent(**base)  # type: ignore[arg-type]


# ------------------------------------------------------------------ insert + read back


def test_a_declared_dividend_round_trips(db: object, investor: str) -> None:
    event_id = de.add_dividend_event(db, _declared(record_date=date(2025, 7, 11)), actor_uid=ACTOR)
    db.commit()

    stored = de.get_dividend_event(db, event_id)
    assert stored is not None
    assert stored.isin == ISIN
    assert stored.ex_date == date(2025, 7, 10)
    assert stored.record_date == date(2025, 7, 11)
    assert stored.amount_per_share == Decimal("1.50")
    assert stored.kind is DividendKind.INTERIM
    assert stored.verification is Verification.DRAFT
    assert stored.corroborated_by is None


def test_a_fresh_event_lands_draft_not_verified(db: object, investor: str) -> None:
    """The default is inert. A declaration nobody has corroborated changes no number."""
    de.add_dividend_event(db, _declared(), actor_uid=ACTOR)
    db.commit()
    assert len(de.list_pending_dividend_events(db)) == 1


def test_the_same_event_twice_is_refused_by_the_table(db: object, investor: str) -> None:
    de.add_dividend_event(db, _declared(), actor_uid=ACTOR)
    db.commit()
    with pytest.raises(psycopg.errors.UniqueViolation):
        de.add_dividend_event(db, _declared(amount="9.99"), actor_uid=ACTOR)
    db.rollback()


def test_an_interim_and_a_special_may_share_an_ex_date(db: object, investor: str) -> None:
    """The reason ``kind`` is in the uniqueness key.

    These are two real events. A key without the kind would silently lose the second.
    """
    de.add_dividend_event(db, _declared(kind=DividendKind.INTERIM, amount="1.50"), actor_uid=ACTOR)
    de.add_dividend_event(db, _declared(kind=DividendKind.SPECIAL, amount="12.00"), actor_uid=ACTOR)
    db.commit()

    events = de.list_dividend_events(db, isins=[ISIN])
    assert len(events) == 2
    assert {e.amount_per_share for e in events} == {Decimal("1.50"), Decimal("12.00")}


# ------------------------------------------------------------------------ date sanity


def test_a_record_date_before_the_ex_date_is_rejected(db: object, investor: str) -> None:
    """In practice a transposed or misread field, not an unusual timetable."""
    with pytest.raises(DividendEventDateError):
        de.add_dividend_event(db, _declared(record_date=date(2025, 7, 1)), actor_uid=ACTOR)


def test_a_payment_date_before_the_ex_date_is_rejected(db: object, investor: str) -> None:
    with pytest.raises(DividendEventDateError):
        de.add_dividend_event(db, _declared(payment_date=date(2025, 6, 1)), actor_uid=ACTOR)


def test_the_table_enforces_date_sanity_even_bypassing_python(db: object, investor: str) -> None:
    """Belt and braces, the same reasoning security_alias's same-issuer CHECK carries: the
    invariant must survive anything that writes here without going through this module."""
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO dividend_event (isin, ex_date, record_date, amount_per_share, "
                "source, source_url) VALUES (%s, %s, %s, %s, %s, %s)",
                (ISIN, date(2025, 7, 10), date(2025, 7, 1), Decimal("1.5"), NSE, NSE_URL),
            )
    db.rollback()


def test_a_non_positive_amount_is_refused_by_the_table(db: object, investor: str) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO dividend_event (isin, ex_date, amount_per_share, source, source_url) "
                "VALUES (%s, %s, %s, %s, %s)",
                (ISIN, date(2025, 7, 10), Decimal("0"), NSE, NSE_URL),
            )
    db.rollback()


def test_a_source_cannot_be_recorded_as_its_own_corroborator(db: object, investor: str) -> None:
    """Two reads of one feed are one observation -- enforced in SQL, not only in Python."""
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO dividend_event (isin, ex_date, amount_per_share, source, source_url, "
                "corroborated_by, corroborated_url) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (ISIN, date(2025, 7, 10), Decimal("1.5"), NSE, NSE_URL, NSE, NSE_URL),
            )
    db.rollback()


def test_a_corroborator_without_a_url_is_refused(db: object, investor: str) -> None:
    """An assertion nobody can re-check is not provenance."""
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO dividend_event (isin, ex_date, amount_per_share, source, source_url, "
                "corroborated_by) VALUES (%s,%s,%s,%s,%s,%s)",
                (ISIN, date(2025, 7, 10), Decimal("1.5"), NSE, NSE_URL, YF),
            )
    db.rollback()


# ------------------------------------------------------------------- corroboration


def test_a_second_source_agreeing_verifies_the_event(db: object, investor: str) -> None:
    event_id = de.add_dividend_event(db, _declared(), actor_uid=ACTOR)
    db.commit()

    state = de.corroborate_dividend_event(
        db, event_id, YF, YF_URL, Decimal("1.50"), actor_uid=ACTOR
    )
    db.commit()

    assert state is Verification.VERIFIED
    stored = de.get_dividend_event(db, event_id)
    assert stored.verification is Verification.VERIFIED
    assert stored.corroborated_by == YF
    assert stored.corroborated_url == YF_URL


def test_a_second_source_disagreeing_disputes_rather_than_duplicating(
    db: object, investor: str
) -> None:
    """One fact, two contradictory claims, and no basis here for choosing between them.

    Not a second row, not an average, not "prefer the newer" -- all three would be this
    module inventing a resolution it has no evidence for.
    """
    event_id = de.add_dividend_event(db, _declared(amount="1.50"), actor_uid=ACTOR)
    db.commit()

    state = de.corroborate_dividend_event(
        db, event_id, YF, YF_URL, Decimal("1.75"), actor_uid=ACTOR
    )
    db.commit()

    assert state is Verification.DISPUTED
    stored = de.get_dividend_event(db, event_id)
    assert stored.verification is Verification.DISPUTED
    assert stored.amount_per_share == Decimal("1.50"), "the original reading is not overwritten"
    assert "AMOUNT_CONFLICT" in stored.notes
    assert "1.75" in stored.notes and "1.50" in stored.notes
    assert len(de.list_dividend_events(db, isins=[ISIN])) == 1, "one event, not two"


def test_the_same_source_reporting_twice_does_not_verify(db: object, investor: str) -> None:
    event_id = de.add_dividend_event(db, _declared(), actor_uid=ACTOR)
    db.commit()

    state = de.corroborate_dividend_event(
        db, event_id, NSE, NSE_URL, Decimal("1.50"), actor_uid=ACTOR
    )
    db.commit()

    assert state is Verification.DRAFT
    assert de.get_dividend_event(db, event_id).corroborated_by is None


def test_corroboration_never_overturns_a_human_dispute(db: object, investor: str) -> None:
    """A human's explicit rejection is the one state automation does not revisit -- the
    same contract refresh_corporate_action_feed already honours for corporate actions."""
    event_id = de.add_dividend_event(db, _declared(), actor_uid=ACTOR)
    de.dispute_dividend_event(db, event_id, "company filing says no dividend", actor_uid=ACTOR)
    db.commit()

    state = de.corroborate_dividend_event(
        db, event_id, YF, YF_URL, Decimal("1.50"), actor_uid=ACTOR
    )
    db.commit()

    assert state is Verification.DISPUTED
    assert de.get_dividend_event(db, event_id).verification is Verification.DISPUTED


# ---------------------------------------------------------- the unspecified-kind rule


def test_an_unspecified_candidate_finds_a_single_existing_event(db: object, investor: str) -> None:
    """yfinance supplies no kind, so its candidate must match the NSE notice already on
    file rather than inserting a second row for the same real dividend."""
    de.add_dividend_event(db, _declared(kind=DividendKind.INTERIM), actor_uid=ACTOR)
    db.commit()

    matches = de.match_unspecified(db, ISIN, date(2025, 7, 10))
    assert len(matches) == 1
    assert matches[0].kind is DividendKind.INTERIM


def test_an_unspecified_candidate_on_a_clear_date_finds_nothing(db: object, investor: str) -> None:
    de.add_dividend_event(db, _declared(ex_date=date(2025, 7, 10)), actor_uid=ACTOR)
    db.commit()
    assert de.match_unspecified(db, ISIN, date(2025, 11, 4)) == []


def test_an_unspecified_candidate_sees_every_match_when_ambiguous(
    db: object, investor: str
) -> None:
    """The fail-closed branch.

    An interim and a special sharing an ex-date mean the caller cannot know which one an
    unspecified candidate describes. It must be able to SEE that there was more than one,
    which is why this returns a list rather than a single row -- attaching corroborating
    evidence to the wrong dividend would promote DRAFT to VERIFIED on false evidence,
    which is worse than leaving it uncorroborated.
    """
    de.add_dividend_event(db, _declared(kind=DividendKind.INTERIM, amount="1.50"), actor_uid=ACTOR)
    de.add_dividend_event(db, _declared(kind=DividendKind.SPECIAL, amount="12.00"), actor_uid=ACTOR)
    db.commit()

    matches = de.match_unspecified(db, ISIN, date(2025, 7, 10))
    assert len(matches) == 2


# ------------------------------------------------------------------ manual verification


def test_a_human_can_verify_a_single_sourced_event(db: object, investor: str) -> None:
    """The third, stronger path: a person can read the company's own filing, which is
    differently originated from two redistributors agreeing."""
    event_id = de.add_dividend_event(db, _declared(), actor_uid=ACTOR)
    db.commit()

    de.verify_dividend_event(db, event_id, actor_uid=ACTOR)
    db.commit()

    stored = de.get_dividend_event(db, event_id)
    assert stored.verification is Verification.VERIFIED
    assert stored.corroborated_by is None, "a human verified it; no second source was needed"


def test_verifying_an_already_verified_event_is_a_no_op(db: object, investor: str) -> None:
    event_id = de.add_dividend_event(db, _declared(verification=Verification.VERIFIED),
                                     actor_uid=ACTOR)
    db.commit()
    de.verify_dividend_event(db, event_id, actor_uid=ACTOR)
    db.commit()
    assert de.get_dividend_event(db, event_id).verification is Verification.VERIFIED


def test_verifying_a_dividend_writes_no_ledger_row(db: object, investor: str) -> None:
    """The load-bearing negative test of this phase.

    verify_corporate_action deliberately triggers a retroactive ledger sweep, because a
    verified bonus credits every holder of record unconditionally. A verified DIVIDEND
    declaration has no receipt behind it, so there is nothing to sweep -- and nothing in
    this module may quietly acquire a path to the ledger.
    """
    event_id = de.add_dividend_event(db, _declared(), actor_uid=ACTOR)
    db.commit()
    de.verify_dividend_event(db, event_id, actor_uid=ACTOR)
    db.commit()

    with db.cursor() as cur:
        cur.execute('SELECT count(*) FROM "transaction"')
        assert cur.fetchone()[0] == 0


def test_this_module_exposes_no_apply_function(db: object) -> None:
    """Pinned so the absence is recognised as the design rather than an omission.

    app.db.corporate_actions has apply_known_actions_for_account because eligibility is a
    bonus's only open question. A dividend's open question is RECEIPT, which no feed
    behind this table answers -- so there is no safe automatic path to the ledger to
    expose, and adding one would need the whole argument in migration 029 overturned.
    """
    assert not [name for name in dir(de) if name.startswith("apply")]


# ------------------------------------------------------------------------- listing


def test_events_are_listed_in_calendar_order(db: object, investor: str) -> None:
    de.add_dividend_event(db, _declared(ex_date=date(2025, 11, 4)), actor_uid=ACTOR)
    de.add_dividend_event(db, _declared(ex_date=date(2025, 2, 6)), actor_uid=ACTOR)
    de.add_dividend_event(db, _declared(ex_date=date(2025, 7, 10)), actor_uid=ACTOR)
    db.commit()

    events = de.list_dividend_events(db, isins=[ISIN])
    assert [e.ex_date for e in events] == [
        date(2025, 2, 6), date(2025, 7, 10), date(2025, 11, 4)
    ]


def test_events_can_be_filtered_by_ex_date_window(db: object, investor: str) -> None:
    for d in (date(2025, 2, 6), date(2025, 7, 10), date(2025, 11, 4)):
        de.add_dividend_event(db, _declared(ex_date=d), actor_uid=ACTOR)
    db.commit()

    window = de.list_dividend_events(
        db, isins=[ISIN], ex_date_from=date(2025, 6, 1), ex_date_to=date(2025, 12, 31)
    )
    assert [e.ex_date for e in window] == [date(2025, 7, 10), date(2025, 11, 4)]


def test_a_later_fetch_can_fill_a_missing_payment_date(db: object, investor: str) -> None:
    event_id = de.add_dividend_event(db, _declared(), actor_uid=ACTOR)
    db.commit()
    de.update_dividend_event_dates(db, event_id, payment_date=date(2025, 8, 1))
    db.commit()
    assert de.get_dividend_event(db, event_id).payment_date == date(2025, 8, 1)


def test_a_date_already_on_file_is_never_overwritten(db: object, investor: str) -> None:
    """A contradiction about a date is the same class of problem as one about an amount,
    and belongs in DISPUTED -- not in a last-writer-wins update nobody can see."""
    event_id = de.add_dividend_event(db, _declared(payment_date=date(2025, 8, 1)), actor_uid=ACTOR)
    db.commit()
    de.update_dividend_event_dates(db, event_id, payment_date=date(2025, 9, 9))
    db.commit()
    assert de.get_dividend_event(db, event_id).payment_date == date(2025, 8, 1)


def test_adding_an_event_is_audited(db: object, investor: str) -> None:
    event_id = de.add_dividend_event(db, _declared(), actor_uid=ACTOR)
    db.commit()
    with db.cursor() as cur:
        cur.execute(
            "SELECT action FROM audit_log WHERE entity_type = 'dividend_event' AND entity_id = %s",
            (event_id,),
        )
        assert [r[0] for r in cur.fetchall()] == ["DIVIDEND_EVENT_ADDED"]


# ---------------------------------------------------------------------------- TDS


def test_tds_round_trips_through_the_ledger(db: object, investor: str) -> None:
    import os

    from app.db import repository
    from app.engine.types import Source, Transaction, TxnType

    account_id = os.environ["_TEST_ACCOUNT_ID"]
    txn = Transaction(
        isin=ISIN, txn_date=date(2025, 8, 1), txn_type=TxnType.DIVIDEND,
        quantity=Decimal("0"), price=Decimal("0"),
        dividend_amount=Decimal("9000"), tds_amount=Decimal("1000"),
        source=Source.MANUAL, source_ref="advice-1", account_id=account_id,
    )
    repository.save_transactions(db, [txn])
    db.commit()

    stored = repository.load_transactions(db, account_id=account_id)[0]
    assert stored.dividend_amount == Decimal("9000.000000"), "net, as credited"
    assert stored.tds_amount == Decimal("1000.000000")
    assert stored.gross_dividend == Decimal("10000.000000")


def test_an_unrecorded_tds_stays_null_in_the_database(db: object, investor: str) -> None:
    """NOT coerced to zero on the way in or out. Unknown is the honest state for every
    dividend the feeds produce, because neither feed carries tax at all."""
    import os

    from app.db import repository
    from app.engine.types import Source, Transaction, TxnType

    account_id = os.environ["_TEST_ACCOUNT_ID"]
    repository.save_transactions(db, [Transaction(
        isin=ISIN, txn_date=date(2025, 8, 1), txn_type=TxnType.DIVIDEND,
        quantity=Decimal("0"), price=Decimal("0"), dividend_amount=Decimal("9000"),
        source=Source.MANUAL, source_ref="advice-2", account_id=account_id,
    )])
    db.commit()

    assert repository.load_transactions(db, account_id=account_id)[0].tds_amount is None
    with db.cursor() as cur:
        cur.execute('SELECT tds_amount FROM "transaction"')
        assert cur.fetchone()[0] is None


def test_a_negative_tds_is_refused_by_the_table(db: object, investor: str) -> None:
    import os

    account_id = os.environ["_TEST_ACCOUNT_ID"]
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.cursor() as cur:
            cur.execute(
                'INSERT INTO "transaction" (account_id, isin, txn_date, txn_type, quantity, '
                "price, dividend_amount, tds_amount, source, dedupe_key) "
                "VALUES (%s,%s,%s,'DIVIDEND',0,0,%s,%s,'MANUAL',%s)",
                (account_id, ISIN, date(2025, 8, 1), Decimal("9000"), Decimal("-1"), "k1"),
            )
    db.rollback()
