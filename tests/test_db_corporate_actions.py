"""Verified corporate actions against a real database -- two paths to the same ledger
write. The MANUAL one: reconcile -> match -> stage -> review -> promote, proving a
batch this feature stages is indistinguishable from one a file upload produces
(app.db.imports.promote_batch, reused unchanged). The AUTOMATIC one:
apply_known_actions_for_account/_investor, which skips staging and review entirely for
an action that already cleared every guard -- see that function's own docstring for the
safety argument. Both write through the identical Transaction shape and the identical
source_ref format, so they recognise and no-op against each other's work.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import psycopg
import pytest
from app.db import corporate_actions as ca_db
from app.db import repository
from app.engine.corporate_actions import CorpActionType, CorporateAction, Verification
from app.engine.holdings import compute_holdings
from app.engine.types import Source, Transaction, TxnType

pytestmark = pytest.mark.db

ISIN = "INE153T01027"  # seeded by the ``investor`` fixture (symbol BLS)
ACTOR = "22222222-2222-2222-2222-222222222222"


def _bonus(ex_date: date = date(2024, 6, 1)) -> CorporateAction:
    """A clean 1:1 bonus -- 1 new share for every 1 held, multiplier 2 -- with a price
    move that exactly corroborates it (400 -> 200)."""
    return CorporateAction(
        isin=ISIN, action_type=CorpActionType.BONUS, ex_date=ex_date,
        bonus_new=1, bonus_for=1,
        price_cum=Decimal(400), price_ex=Decimal(200),
        source="BSE notice", source_url="https://example.invalid/bonus",
        verification=Verification.VERIFIED,
    )


def _buy(account_id: str, qty: str = "100") -> Transaction:
    return Transaction(
        isin=ISIN, txn_date=date(2024, 1, 10), txn_type=TxnType.BUY,
        quantity=Decimal(qty), price=Decimal("200.50"), account_id=account_id,
        source=Source.TRADEBOOK,
    )


def test_add_corporate_action_round_trips(db: object, investor: str) -> None:
    action_id = ca_db.add_corporate_action(db, _bonus(), actor_uid=ACTOR)
    db.commit()

    [stored] = ca_db.list_corporate_actions(db, [ISIN])
    assert stored.id == action_id
    assert stored.isin == ISIN
    assert stored.multiplier() == 2
    assert stored.verification is Verification.VERIFIED


def test_adding_the_same_notice_twice_is_rejected(db: object, investor: str) -> None:
    ca_db.add_corporate_action(db, _bonus(), actor_uid=ACTOR)
    db.commit()
    with pytest.raises(psycopg.errors.UniqueViolation):
        ca_db.add_corporate_action(db, _bonus(), actor_uid=ACTOR)
    db.rollback()


def test_adding_a_verified_action_closes_the_gap_immediately_no_manual_step(
    db: object, investor: str
) -> None:
    """The end-to-end path this feature exists for, now automatic: buy first, THEN a
    verified bonus notice lands on file later (exactly the KAMAHOLD/GENSOL shape --
    ledger already has the trade, the corporate action reference data arrives after).
    ``add_corporate_action`` itself closes the gap via its retroactive sweep -- no
    staging, no review, no promote click."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    repository.save_transactions(db, [_buy(account_id)])
    ca_db.add_corporate_action(db, _bonus(), actor_uid=ACTOR)
    db.commit()

    transactions = repository.load_transactions(db, investor_id=investor)
    bonus_rows = [t for t in transactions if t.txn_type is TxnType.BONUS]
    assert len(bonus_rows) == 1
    assert bonus_rows[0].quantity == Decimal(100)
    assert bonus_rows[0].source is Source.CORP_ACTION

    [holding] = [h for h in compute_holdings(transactions) if h.isin == ISIN]
    assert holding.quantity == Decimal(200)
    assert holding.invested == Decimal("20050.00")  # cost pool unchanged by the bonus

    # The OLD manual path, run afterwards against the same declared holdings, must
    # agree there is nothing left to do -- reconcile() sees computed == declared and
    # reports no discrepancy at all, not a redundant match.
    staged = ca_db.stage_corporate_actions(
        db, investor_id=investor, account_id=account_id,
        declared_holdings={ISIN: Decimal(200)}, actor_uid=ACTOR,
    )
    assert staged["parsed"] == 0
    assert staged["rejected"] == 0


def test_restaging_before_promotion_returns_the_same_batch(
    db: object, investor: str
) -> None:
    """Idempotent the way a file re-upload is: nothing changed since the first call, so
    this must not create a second batch sitting alongside the first.

    Uses a discrepancy the automatic sweep does NOT already cover -- the bonus notice
    is added before any purchase exists, so ``add_corporate_action``'s retroactive
    sweep finds no eligible account yet and the gap is still open for
    ``stage_corporate_actions`` to find, same as a corporate action whose ledger-side
    purchase arrives later.
    """
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    ca_db.add_corporate_action(db, _bonus(), actor_uid=ACTOR)
    repository.save_transactions(db, [_buy(account_id)])
    db.commit()

    first = ca_db.stage_corporate_actions(
        db, investor_id=investor, account_id=account_id,
        declared_holdings={ISIN: Decimal(200)}, actor_uid=ACTOR,
    )
    second = ca_db.stage_corporate_actions(
        db, investor_id=investor, account_id=account_id,
        declared_holdings={ISIN: Decimal(200)}, actor_uid=ACTOR,
    )
    db.commit()
    assert first["batch_id"] == second["batch_id"]


def test_apply_known_actions_applies_directly_without_staging_review_or_promote(
    db: object, investor: str
) -> None:
    """The automated path this whole module exists for: no declared-holdings statement,
    no batch, no review, no promote click -- a VERIFIED, price-corroborated action on
    file is applied to an eligible account's own ledger directly.

    The action is added BEFORE the purchase exists, so ``add_corporate_action``'s own
    retroactive sweep has nothing to apply yet -- this isolates
    ``apply_known_actions_for_account`` itself as the thing under test, exercised the
    way a fresh import (``promote_batch``'s own sweep) would trigger it."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    ca_db.add_corporate_action(db, _bonus(), actor_uid=ACTOR)
    repository.save_transactions(db, [_buy(account_id)])
    db.commit()

    summary = ca_db.apply_known_actions_for_account(db, account_id, actor_uid=ACTOR)
    db.commit()
    assert summary.inserted == 1

    transactions = repository.load_transactions(db, investor_id=investor)
    bonus_rows = [t for t in transactions if t.txn_type is TxnType.BONUS]
    assert len(bonus_rows) == 1
    assert bonus_rows[0].quantity == Decimal(100)
    assert bonus_rows[0].source is Source.CORP_ACTION

    [holding] = [h for h in compute_holdings(transactions) if h.isin == ISIN]
    assert holding.quantity == Decimal(200)
    assert holding.invested == Decimal("20050.00")  # cost pool unchanged by the bonus


def test_apply_known_actions_is_idempotent(db: object, investor: str) -> None:
    """Running the sweep twice (the shape a background job or a second import would
    take) must not double-credit the bonus."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    ca_db.add_corporate_action(db, _bonus(), actor_uid=ACTOR)
    repository.save_transactions(db, [_buy(account_id)])
    db.commit()

    first = ca_db.apply_known_actions_for_account(db, account_id, actor_uid=ACTOR)
    db.commit()
    second = ca_db.apply_known_actions_for_account(db, account_id, actor_uid=ACTOR)
    db.commit()

    assert first.inserted == 1
    assert second.inserted == 0

    transactions = repository.load_transactions(db, investor_id=investor)
    assert len([t for t in transactions if t.txn_type is TxnType.BONUS]) == 1


def test_apply_known_actions_recognises_a_prior_application_with_different_source_text(
    db: object, investor: str
) -> None:
    """A bonus applied earlier by hand (or by an older version of this table's source
    text) must not be re-applied just because ``source_ref`` does not match byte for
    byte -- the check is (isin, ex_date, txn_type), not the exact string."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    ca_db.add_corporate_action(db, _bonus(), actor_uid=ACTOR)
    repository.save_transactions(db, [_buy(account_id)])
    db.commit()

    # Simulate an earlier, differently-worded application of the SAME event.
    repository.save_transactions(
        db,
        [
            Transaction(
                isin=ISIN, txn_date=date(2024, 6, 1), txn_type=TxnType.BONUS,
                quantity=Decimal(100), price=Decimal(0), account_id=account_id,
                source=Source.CORP_ACTION,
                source_ref="a hand-typed note about the same bonus, worded differently",
            )
        ],
    )
    db.commit()

    summary = ca_db.apply_known_actions_for_account(db, account_id, actor_uid=ACTOR)
    db.commit()
    assert summary.inserted == 0

    transactions = repository.load_transactions(db, investor_id=investor)
    assert len([t for t in transactions if t.txn_type is TxnType.BONUS]) == 1


def test_apply_known_actions_skips_an_account_that_never_held_it(
    db: object, investor: str
) -> None:
    """A VERIFIED action on file for an ISIN this account has never bought must not
    credit a bonus to a position that does not exist -- not a holder of record."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    ca_db.add_corporate_action(db, _bonus(), actor_uid=ACTOR)
    db.commit()

    summary = ca_db.apply_known_actions_for_account(db, account_id, actor_uid=ACTOR)
    db.commit()
    assert summary.inserted == 0


def test_apply_known_actions_skips_an_unverified_notice(db: object, investor: str) -> None:
    """A DRAFT notice must never be auto-applied, same guard ``screen()`` already gives
    the staged/reviewed path."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    repository.save_transactions(db, [_buy(account_id)])
    draft = CorporateAction(
        isin=ISIN, action_type=CorpActionType.BONUS, ex_date=date(2024, 6, 1),
        bonus_new=1, bonus_for=1, price_cum=Decimal(400), price_ex=Decimal(200),
        source="BSE notice", source_url="https://example.invalid/bonus",
        verification=Verification.DRAFT,
    )
    ca_db.add_corporate_action(db, draft, actor_uid=ACTOR)
    db.commit()

    summary = ca_db.apply_known_actions_for_account(db, account_id, actor_uid=ACTOR)
    db.commit()
    assert summary.inserted == 0


def test_apply_known_actions_for_investor_covers_every_account(
    db: object, investor: str
) -> None:
    """The investor-level wrapper sweeps every account under the investor, not just
    one -- holdings are computed per account, so eligibility is too."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    ca_db.add_corporate_action(db, _bonus(), actor_uid=ACTOR)
    repository.save_transactions(db, [_buy(account_id)])
    db.commit()

    summary = ca_db.apply_known_actions_for_investor(db, investor, actor_uid=ACTOR)
    db.commit()
    assert summary.inserted == 1


def test_unverified_notice_is_quarantined_all_the_way_through(
    db: object, investor: str
) -> None:
    """A DRAFT notice on file must not be matched -- the discrepancy stages as a
    Rejection carrying reconcile()'s own text hint, same as no notice at all."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    repository.save_transactions(db, [_buy(account_id)])
    draft = CorporateAction(
        isin=ISIN, action_type=CorpActionType.BONUS, ex_date=date(2024, 6, 1),
        bonus_new=1, bonus_for=1, price_cum=Decimal(400), price_ex=Decimal(200),
        source="BSE notice", source_url="https://example.invalid/bonus",
        verification=Verification.DRAFT,
    )
    ca_db.add_corporate_action(db, draft, actor_uid=ACTOR)
    db.commit()

    staged = ca_db.stage_corporate_actions(
        db, investor_id=investor, account_id=account_id,
        declared_holdings={ISIN: Decimal(200)}, actor_uid=ACTOR,
    )
    db.commit()
    assert staged["parsed"] == 0
    assert staged["rejected"] == 1


# ---------------------------------------------------------------------------
# refresh_corporate_action_feed(): automated ingestion, the third path
# ---------------------------------------------------------------------------


class _FakeFeedSource:
    """Injects a fixed payload instead of hitting NSE -- the same ``opener``-injection
    pattern every other source in this codebase uses for tests
    (``app.prices.sources.HttpBhavcopySource``, etc.), one level up since this Protocol
    is ``fetch(start, end)`` rather than ``fetch(on)``."""

    def __init__(self, payload: bytes):
        self._payload = payload

    def fetch(self, start: date, end: date) -> bytes:
        return self._payload


def _feed_payload(*records: dict) -> bytes:
    import json

    return json.dumps(list(records)).encode()


def _set_price(conn: object, isin: str, on: date, close: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO price (isin, price_date, close, source) VALUES (%s, %s, %s, 'TEST')",
            (isin, on, Decimal(close)),
        )


def test_refresh_feed_auto_verifies_a_clean_bonus_with_no_human_step(
    db: object, investor: str
) -> None:
    """The end-to-end automated path: a real-shaped NSE notice in, corroborating
    bhavcopy prices already stored, VERIFIED out with no staging and no promote --
    same acceptance bar as the manual and direct-apply paths above."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    repository.save_transactions(db, [_buy(account_id)])
    ex_date = date(2024, 6, 1)
    _set_price(db, ISIN, date(2024, 5, 31), "400")  # cum
    _set_price(db, ISIN, ex_date, "200")  # ex -- exactly corroborates a 1:1 bonus
    db.commit()

    source = _FakeFeedSource(_feed_payload({
        "isin": ISIN, "symbol": "BLS", "exDate": "01-Jun-2024", "subject": "Bonus 1:1",
    }))
    result = ca_db.refresh_corporate_action_feed(
        db, date(2024, 5, 25), date(2024, 6, 5), source=source, actor_uid=ACTOR
    )
    db.commit()

    assert result == {"fetched": 1, "verified": 1, "exceptions": 0}
    transactions = repository.load_transactions(db, investor_id=investor)
    bonus_rows = [t for t in transactions if t.txn_type is TxnType.BONUS]
    assert len(bonus_rows) == 1
    assert bonus_rows[0].quantity == Decimal(100)
    [stored] = ca_db.list_corporate_actions(db, [ISIN])
    assert stored.verification is Verification.VERIFIED


def test_refresh_feed_lands_in_exceptions_without_price_evidence(
    db: object, investor: str
) -> None:
    """No bhavcopy stored yet for the cum/ex dates -- NO_PRICE_EVIDENCE, same guard the
    manual path already enforces. Lands in Exceptions, does not touch the ledger."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    repository.save_transactions(db, [_buy(account_id)])
    db.commit()

    source = _FakeFeedSource(_feed_payload({
        "isin": ISIN, "symbol": "BLS", "exDate": "01-Jun-2024", "subject": "Bonus 1:1",
    }))
    result = ca_db.refresh_corporate_action_feed(
        db, date(2024, 5, 25), date(2024, 6, 5), source=source, actor_uid=ACTOR
    )
    db.commit()

    assert result == {"fetched": 1, "verified": 0, "exceptions": 1}
    transactions = repository.load_transactions(db, investor_id=investor)
    assert [t for t in transactions if t.txn_type is TxnType.BONUS] == []
    [pending] = ca_db.list_pending_corporate_actions(db)
    assert pending.isin == ISIN
    assert pending.verification is Verification.DRAFT
    assert "NO_PRICE_EVIDENCE" in pending.notes


def test_refresh_feed_self_corrects_once_price_evidence_arrives(
    db: object, investor: str
) -> None:
    """The self-correcting retry, the specific behaviour this plan changed after
    review: an Exceptions entry left over from a run with no price evidence promotes
    itself to VERIFIED on a LATER run, once bhavcopy catches up -- no human call
    in between, no brand-new notice needed to re-trigger it."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    repository.save_transactions(db, [_buy(account_id)])
    db.commit()

    source = _FakeFeedSource(_feed_payload({
        "isin": ISIN, "symbol": "BLS", "exDate": "01-Jun-2024", "subject": "Bonus 1:1",
    }))
    first = ca_db.refresh_corporate_action_feed(
        db, date(2024, 5, 25), date(2024, 6, 5), source=source, actor_uid=ACTOR
    )
    db.commit()
    assert first["exceptions"] == 1

    # Bhavcopy catches up. A run over a DIFFERENT window that never mentions this ISIN
    # at all still retries it -- the retry sweep covers every pending row, not just
    # ISINs the current fetch happens to touch.
    _set_price(db, ISIN, date(2024, 5, 31), "400")
    _set_price(db, ISIN, date(2024, 6, 1), "200")
    db.commit()

    empty_source = _FakeFeedSource(_feed_payload())
    second = ca_db.refresh_corporate_action_feed(
        db, date(2025, 1, 1), date(2025, 1, 2), source=empty_source, actor_uid=ACTOR
    )
    db.commit()

    assert second == {"fetched": 0, "verified": 1, "exceptions": 0}
    transactions = repository.load_transactions(db, investor_id=investor)
    assert len([t for t in transactions if t.txn_type is TxnType.BONUS]) == 1
    [stored] = ca_db.list_corporate_actions(db, [ISIN])
    assert stored.verification is Verification.VERIFIED


def test_disputed_row_is_never_retried(db: object, investor: str) -> None:
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    repository.save_transactions(db, [_buy(account_id)])
    db.commit()

    source = _FakeFeedSource(_feed_payload({
        "isin": ISIN, "symbol": "BLS", "exDate": "01-Jun-2024", "subject": "Bonus 1:1",
    }))
    ca_db.refresh_corporate_action_feed(
        db, date(2024, 5, 25), date(2024, 6, 5), source=source, actor_uid=ACTOR
    )
    db.commit()
    [pending] = ca_db.list_pending_corporate_actions(db)

    ca_db.dispute_corporate_action(db, pending.id, actor_uid=ACTOR, reason="wrong ISIN mapping")
    db.commit()
    assert ca_db.list_pending_corporate_actions(db) == []

    _set_price(db, ISIN, date(2024, 5, 31), "400")
    _set_price(db, ISIN, date(2024, 6, 1), "200")
    db.commit()
    empty_source = _FakeFeedSource(_feed_payload())
    result = ca_db.refresh_corporate_action_feed(
        db, date(2025, 1, 1), date(2025, 1, 2), source=empty_source, actor_uid=ACTOR
    )
    db.commit()

    assert result == {"fetched": 0, "verified": 0, "exceptions": 0}
    transactions = repository.load_transactions(db, investor_id=investor)
    assert [t for t in transactions if t.txn_type is TxnType.BONUS] == []


def test_verify_corporate_action_promotes_and_sweeps(db: object, investor: str) -> None:
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    repository.save_transactions(db, [_buy(account_id)])
    draft = CorporateAction(
        isin=ISIN, action_type=CorpActionType.BONUS, ex_date=date(2024, 6, 1),
        bonus_new=1, bonus_for=1, price_cum=Decimal(400), price_ex=Decimal(200),
        source="BSE notice", source_url="https://example.invalid/bonus",
        verification=Verification.DRAFT,
    )
    action_id = ca_db.add_corporate_action(db, draft, actor_uid=ACTOR)
    db.commit()
    before = repository.load_transactions(db, investor_id=investor)
    assert [t for t in before if t.txn_type is TxnType.BONUS] == []  # still DRAFT, nothing applied

    ca_db.verify_corporate_action(db, action_id, actor_uid=ACTOR)
    db.commit()

    transactions = repository.load_transactions(db, investor_id=investor)
    assert len([t for t in transactions if t.txn_type is TxnType.BONUS]) == 1
    [stored] = ca_db.list_corporate_actions(db, [ISIN])
    assert stored.verification is Verification.VERIFIED


# ---------------------------------------------------------------------------
# discover_from_yfinance(): the second free candidate source, for the historical
# gap the live NSE notices feed structurally cannot reach
# ---------------------------------------------------------------------------


class _FakeYfinanceSource:
    """Same injection posture as _FakeFeedSource above -- no network, and no dependency
    on Yahoo's own answer still being the same tomorrow."""

    def __init__(self, splits: dict[date, float]):
        self._splits = splits

    def splits(self, symbol: str) -> dict[date, float]:
        return self._splits


def test_yfinance_discovery_auto_verifies_against_real_price_evidence(
    db: object, investor: str
) -> None:
    """The whole point: a historical action nobody researched by hand, discovered and
    applied with no human step -- but only because stored bhavcopy corroborates it."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    repository.save_transactions(db, [_buy(account_id)])
    ex_date = date(2024, 6, 1)
    _set_price(db, ISIN, date(2024, 5, 31), "400")  # cum
    _set_price(db, ISIN, ex_date, "200")  # ex -- exactly corroborates a 1:1 bonus
    db.commit()

    result = ca_db.discover_from_yfinance(
        db, isins=[ISIN], source=_FakeYfinanceSource({ex_date: 2.0}), actor_uid=ACTOR
    )
    db.commit()

    assert result["discovered"] == 1
    assert result["verified"] == 1
    assert result["exceptions"] == 0

    [stored] = ca_db.list_corporate_actions(db, [ISIN])
    assert stored.verification is Verification.VERIFIED
    assert stored.multiplier() == 2
    assert "yfinance" in stored.source.lower()

    transactions = repository.load_transactions(db, investor_id=investor)
    bonus_rows = [t for t in transactions if t.txn_type is TxnType.BONUS]
    assert len(bonus_rows) == 1
    assert bonus_rows[0].quantity == Decimal(100)


def test_yfinance_discovery_lands_in_exceptions_without_price_evidence(
    db: object, investor: str
) -> None:
    """Yahoo saying so is NOT enough on its own -- the same NO_PRICE_EVIDENCE guard the
    NSE-notices path enforces applies here unchanged, never relaxed for a second source."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    repository.save_transactions(db, [_buy(account_id)])
    db.commit()

    result = ca_db.discover_from_yfinance(
        db, isins=[ISIN], source=_FakeYfinanceSource({date(2024, 6, 1): 2.0}), actor_uid=ACTOR
    )
    db.commit()

    assert result["verified"] == 0
    assert result["exceptions"] == 1
    [stored] = ca_db.list_corporate_actions(db, [ISIN])
    assert stored.verification is Verification.DRAFT
    assert "NO_PRICE_EVIDENCE" in stored.notes

    transactions = repository.load_transactions(db, investor_id=investor)
    assert [t for t in transactions if t.txn_type is TxnType.BONUS] == []


def test_yfinance_discovery_is_rejected_when_the_price_move_contradicts_the_factor(
    db: object, investor: str
) -> None:
    """A wrong factor from Yahoo must not credit shares. The price move is the
    independent check that catches it -- 400 -> 200 is a 2x move, not the 5x a 5.0
    factor claims."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    repository.save_transactions(db, [_buy(account_id)])
    ex_date = date(2024, 6, 1)
    _set_price(db, ISIN, date(2024, 5, 31), "400")
    _set_price(db, ISIN, ex_date, "200")
    db.commit()

    result = ca_db.discover_from_yfinance(
        db, isins=[ISIN], source=_FakeYfinanceSource({ex_date: 5.0}), actor_uid=ACTOR
    )
    db.commit()

    assert result["verified"] == 0
    assert result["exceptions"] == 1
    [stored] = ca_db.list_corporate_actions(db, [ISIN])
    assert stored.verification is Verification.DRAFT
    assert "RATIO_CONTRADICTS_PRICE" in stored.notes


def test_yfinance_discovery_is_idempotent_against_an_action_already_on_file(
    db: object, investor: str
) -> None:
    """The NSE feed and this source will often find the same event. The second one to
    arrive must be a benign no-op, not a duplicate credit."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    repository.save_transactions(db, [_buy(account_id)])
    ex_date = date(2024, 6, 1)
    _set_price(db, ISIN, date(2024, 5, 31), "400")
    _set_price(db, ISIN, ex_date, "200")
    ca_db.add_corporate_action(db, _bonus(ex_date), actor_uid=ACTOR)
    db.commit()

    result = ca_db.discover_from_yfinance(
        db, isins=[ISIN], source=_FakeYfinanceSource({ex_date: 2.0}), actor_uid=ACTOR
    )
    db.commit()

    assert len(ca_db.list_corporate_actions(db, [ISIN])) == 1
    transactions = repository.load_transactions(db, investor_id=investor)
    assert len([t for t in transactions if t.txn_type is TxnType.BONUS]) == 1
    assert result["discovered"] == 1  # it was looked at...
    assert result["duplicates"] == 1  # ...recognised as already on file...
    assert result["verified"] == 0  # ...and NOT counted as work this run did.


def test_yfinance_discovery_skips_an_isin_with_no_security_row(db: object, investor: str) -> None:
    """No symbol to query with, and add_corporate_action's FK to security would reject
    it anyway -- skipped before spending a network call, never a crash."""
    result = ca_db.discover_from_yfinance(
        db, isins=["INE000000001"], source=_FakeYfinanceSource({date(2024, 6, 1): 2.0})
    )
    assert result["discovered"] == 0
    assert result["errors"] == {}
