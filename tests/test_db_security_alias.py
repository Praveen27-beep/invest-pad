"""app/db/security_alias.py -- one security, many ISINs over time.

These are the contract, not incidental coverage. The governing rule is that an alias is
an IDENTITY ASSERTION, NEVER AN INFERENCE: the structural checks may reject an unsafe
alias but can never create one, and only verified evidence changes a number. Each test
below pins one half of that.

The first test is the reason the whole design exists. Modelling an identifier change as a
TRANSFER_OUT/TRANSFER_IN pair would have been simpler and would have quietly restarted
every holding period, turning long-term gains short-term -- the exact class of bug MProfit
has shipped fixes for. Normalising at the read boundary instead means the acquisition date
cannot move, and this test is what holds that.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import psycopg
import pytest
from app.db import repository
from app.db import security_alias as alias_db
from app.db.security_alias import SecurityAlias, SecurityAliasError
from app.engine.corporate_actions import Verification
from app.engine.holdings import compute_holdings
from app.engine.lots import compute_lots
from app.engine.types import Source, Transaction, TxnType

pytestmark = pytest.mark.db

# Two real ISINs for the same issuer (INE411D), differing only in the security code at
# characters 8-9 -- the SKMEGGPROD identifier change this feature was built for.
OLD = "INE411D01015"
NEW = "INE411D01023"
#: A different issuer entirely -- the merger case, which must never enter this way.
OTHER_ISSUER = "INE153T01027"
ACTOR = "22222222-2222-2222-2222-222222222222"


def _seed_securities(db, *isins: str) -> None:
    with db.cursor() as cur:
        for isin in isins:
            cur.execute(
                "INSERT INTO security (isin) VALUES (%s) ON CONFLICT (isin) DO NOTHING",
                (isin,),
            )


def _alias(old: str = OLD, new: str = NEW, **kw) -> SecurityAlias:
    return SecurityAlias(
        old_isin=old,
        current_isin=new,
        effective_date=kw.pop("effective_date", date(2026, 1, 9)),
        source=kw.pop("source", "NSDL ISIN change notice"),
        source_url=kw.pop("source_url", "https://example.invalid/isin-change"),
        verification=kw.pop("verification", Verification.VERIFIED),
        **kw,
    )


def _txn(isin: str, txn_type: str, qty: str, price: str, day: str, account_id: str):
    return Transaction(
        isin=isin,
        txn_date=date.fromisoformat(day),
        txn_type=TxnType(txn_type),
        quantity=Decimal(qty),
        price=Decimal(price),
        account_id=account_id,
        source=Source.CONTRACT_NOTE,
    )


# --- 1. the regression this design exists to prevent ------------------------------


def test_the_acquisition_date_survives_an_isin_change(db, investor) -> None:
    """A buy under the retired ISIN keeps its ORIGINAL open_date after aliasing.

    If this ever fails, a long-term holding has silently become short-term and the tax
    engine is wrong -- which is precisely what a synthetic TRANSFER_OUT/TRANSFER_IN pair
    would have done.
    """
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(db, [_txn(OLD, "BUY", "10", "100", "2021-03-01", account_id)])
    alias_db.add_alias(db, _alias(), actor_uid=ACTOR)
    db.commit()

    transactions = repository.load_transactions(db, account_id=account_id)
    [lot] = [lot for lot in compute_lots(transactions, date(2026, 9, 11)) if lot.isin == NEW]

    assert lot.open_date == date(2021, 3, 1), "the identifier moved; the purchase did not"


# --- 2. one economic position -----------------------------------------------------


def test_old_and_new_become_one_position(db, investor) -> None:
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "1", "194.06", "2025-04-25", account_id),
            _txn(NEW, "BUY", "10", "232.35", "2026-06-02", account_id),
        ],
    )
    alias_db.add_alias(db, _alias(), actor_uid=ACTOR)
    db.commit()

    holdings = compute_holdings(
        repository.load_transactions(db, account_id=account_id), date(2026, 9, 11)
    )
    assert [h.isin for h in holdings] == [NEW], "two identities, one security"
    assert holdings[0].quantity == Decimal("11")
    # One cost pool, both halves in it. Rule B (app.engine.holdings) rounds the average
    # to 4dp once at emission, so a merged pool re-rounds ONE average where there were
    # two -- landing within that precision of the sum, not bit-identical to it. Demanding
    # exact equality here would be demanding that arithmetic not happen.
    assert abs(holdings[0].invested - (Decimal("194.06") + Decimal("2323.50"))) <= Decimal(
        "0.001"
    )


# --- 3. DRAFT is inert ------------------------------------------------------------


def test_a_draft_alias_has_no_effect(db, investor) -> None:
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "1", "194.06", "2025-04-25", account_id),
            _txn(NEW, "BUY", "10", "232.35", "2026-06-02", account_id),
        ],
    )
    alias_db.add_alias(db, _alias(verification=Verification.DRAFT), actor_uid=ACTOR)
    db.commit()

    holdings = compute_holdings(
        repository.load_transactions(db, account_id=account_id), date(2026, 9, 11)
    )
    assert sorted(h.isin for h in holdings) == [OLD, NEW], "unverified changes nothing"


def test_verifying_a_draft_alias_then_applies_it(db, investor) -> None:
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(db, [_txn(OLD, "BUY", "1", "194.06", "2025-04-25", account_id)])
    alias_db.add_alias(db, _alias(verification=Verification.DRAFT), actor_uid=ACTOR)
    db.commit()

    alias_db.verify_alias(db, OLD, actor_uid=ACTOR)
    db.commit()

    holdings = compute_holdings(
        repository.load_transactions(db, account_id=account_id), date(2026, 9, 11)
    )
    assert [h.isin for h in holdings] == [NEW]


# --- 4 & 5. structural gates reject, but never vouch ------------------------------


def test_an_alias_cannot_merge_two_different_issuers(db, investor) -> None:
    """A different issuer is a MERGER -- its own cost allocation and tax treatment. It
    must not be smuggled in as an identity change."""
    _seed_securities(db, OLD, OTHER_ISSUER)
    with pytest.raises(SecurityAliasError, match="merger or amalgamation"):
        alias_db.add_alias(db, _alias(new=OTHER_ISSUER))
    db.rollback()


def test_an_equity_cannot_alias_onto_a_fund(db, investor) -> None:
    """Characters 1-3 carry the instrument type: INE equity, INF mutual fund."""
    fund = "INF411D01015"
    _seed_securities(db, OLD, fund)
    with pytest.raises(SecurityAliasError):
        alias_db.add_alias(db, _alias(new=fund))
    db.rollback()


def test_an_isin_cannot_alias_to_itself(db, investor) -> None:
    _seed_securities(db, OLD)
    with pytest.raises(SecurityAliasError, match="itself"):
        alias_db.add_alias(db, _alias(new=OLD))
    db.rollback()


def test_an_alias_needs_a_source(db, investor) -> None:
    """Structural checks passing is not evidence. Something must vouch for the identity."""
    _seed_securities(db, OLD, NEW)
    with pytest.raises(SecurityAliasError, match="source"):
        alias_db.add_alias(db, _alias(source="", source_url=""))
    db.rollback()


def test_same_issuer_alone_never_creates_an_alias(db, investor) -> None:
    """The heart of "necessary, not sufficient": two same-issuer ISINs that the detector
    has NOT been told to link stay two separate securities. Nothing infers the identity
    from the shared issuer code."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "1", "194.06", "2025-04-25", account_id),
            _txn(NEW, "BUY", "10", "232.35", "2026-06-02", account_id),
        ],
    )
    db.commit()

    holdings = compute_holdings(
        repository.load_transactions(db, account_id=account_id), date(2026, 9, 11)
    )
    assert sorted(h.isin for h in holdings) == [OLD, NEW]


# --- 6. canonical and cycle-safe --------------------------------------------------


def test_a_chain_resolves_to_its_terminal_isin(db, investor) -> None:
    """A -> B -> C must resolve to C, never to a half-resolved B."""
    third = "INE411D01031"
    _seed_securities(db, OLD, NEW, third)
    alias_db.add_alias(db, _alias(old=OLD, new=NEW))
    alias_db.add_alias(db, _alias(old=NEW, new=third))
    db.commit()

    assert alias_db.verified_map(db)[OLD] == third


def test_a_cycle_is_refused(db, investor) -> None:
    """A -> B -> A would make "what is this security now?" unanswerable."""
    _seed_securities(db, OLD, NEW)
    alias_db.add_alias(db, _alias(old=OLD, new=NEW))
    db.commit()

    with pytest.raises(SecurityAliasError, match="cycle"):
        alias_db.add_alias(db, _alias(old=NEW, new=OLD))
    db.rollback()


def test_the_same_isin_cannot_be_superseded_twice(db, investor) -> None:
    """Two rows for one old_isin would be two contradictory claims about one fact."""
    third = "INE411D01031"
    _seed_securities(db, OLD, NEW, third)
    alias_db.add_alias(db, _alias(old=OLD, new=NEW))
    db.commit()

    with pytest.raises(psycopg.errors.UniqueViolation):
        alias_db.add_alias(db, _alias(old=OLD, new=third))
    db.rollback()


# --- 7. post-alias reconciliation quarantines a bad alias -------------------------


def test_reconciliation_passes_for_a_clean_alias(db, investor) -> None:
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "1", "194.06", "2025-04-25", account_id),
            _txn(NEW, "BUY", "10", "232.35", "2026-06-02", account_id),
        ],
    )
    alias_db.add_alias(db, _alias())
    db.commit()

    result = alias_db.reconcile_after_alias(db, account_id, OLD, NEW, date(2026, 9, 11))
    assert result.ok, result.failures


def test_an_alias_that_cannot_reconcile_is_reported_not_applied_silently(
    db, investor
) -> None:
    """Merging two identities must not manufacture a holding that cannot exist. Here the
    combined ledger still disposes more than it ever acquired -- the signature of a
    missing quantity-changing corporate action, which has to be entered first."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "10", "100", "2024-01-10", account_id),
            _txn(NEW, "SELL", "400", "250", "2025-03-18", account_id),
        ],
    )
    alias_db.add_alias(db, _alias())
    db.commit()

    result = alias_db.reconcile_after_alias(db, account_id, OLD, NEW, date(2026, 9, 11))
    assert not result.ok
    assert any("corporate action" in f for f in result.failures), result.failures


def test_quarantine_disables_the_alias_without_deleting_it(db, investor) -> None:
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(db, [_txn(OLD, "BUY", "1", "194.06", "2025-04-25", account_id)])
    alias_db.add_alias(db, _alias())
    db.commit()

    alias_db.quarantine_alias(db, OLD, "reconciliation failed in a test", actor_uid=ACTOR)
    db.commit()

    assert OLD not in alias_db.verified_map(db), "a quarantined alias is inert"
    [stored] = alias_db.list_aliases(db)
    assert stored.verification is Verification.DISPUTED
    assert "QUARANTINED" in stored.notes, "the record of what was tried survives"
    # And it stays inert -- a verify must not silently resurrect a rejected identity.
    alias_db.verify_alias(db, OLD, actor_uid=ACTOR)
    db.commit()
    assert OLD not in alias_db.verified_map(db)


# --- 8. detection may infer; resolution may not -----------------------------------


def test_detection_flags_the_isin_change_shape(db, investor) -> None:
    """The GUJTHEM signature: one ISIN stranding a position while a same-issuer sibling
    disposes of what it never acquired."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "65", "700", "2022-10-19", account_id),
            _txn(NEW, "SELL", "487", "254.75", "2025-03-18", account_id),
        ],
    )
    db.commit()

    [candidate] = alias_db.detect_candidates(db, investor_id=investor)
    assert candidate.old_isin == OLD
    assert candidate.current_isin == NEW
    assert candidate.dangling_quantity == Decimal("65")
    assert candidate.unexplained_disposal == Decimal("487")
    assert "unverified" in candidate.reason


def test_detection_does_not_flag_a_plain_missing_trade(db, investor) -> None:
    """SULA and SOUTHBANK's real shape: a single ISIN short of buy history, with no
    sibling identity anywhere. Pinned so a later change cannot quietly start "fixing"
    missing trades by inventing an identity for them."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OTHER_ISSUER)
    repository.save_transactions(
        db,
        [
            _txn(OTHER_ISSUER, "BUY", "23", "490", "2023-08-31", account_id),
            _txn(OTHER_ISSUER, "SELL", "65", "484", "2024-09-10", account_id),
        ],
    )
    db.commit()

    assert alias_db.detect_candidates(db, investor_id=investor) == []


def test_detection_never_writes_an_alias(db, investor) -> None:
    """The whole point of the rule. A candidate is a hypothesis; the table stays empty
    until something with evidence acts on it."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "65", "700", "2022-10-19", account_id),
            _txn(NEW, "SELL", "487", "254.75", "2025-03-18", account_id),
        ],
    )
    db.commit()

    assert alias_db.detect_candidates(db, investor_id=investor)
    assert alias_db.list_aliases(db) == []
    assert alias_db.verified_map(db) == {}


def test_detection_flags_the_quiet_shape_once_and_in_the_right_direction(
    db, investor
) -> None:
    """Two identities BOTH holding a position contradict nothing, so no screen breaks and
    nobody would look -- yet the holding is silently split in two (SKMEGGPROD's shape).
    The pair is symmetric, so direction comes from which identifier stopped trading
    first, and it must be reported once, not both ways round."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "1", "194.06", "2025-04-25", account_id),
            _txn(NEW, "BUY", "10", "232.35", "2026-06-02", account_id),
        ],
    )
    db.commit()

    candidates = alias_db.detect_candidates(db, investor_id=investor)
    assert len(candidates) == 1, "reported once, not in both directions"
    assert candidates[0].old_isin == OLD, "the retired one stopped trading first"
    assert candidates[0].current_isin == NEW


def test_an_already_aliased_pair_is_not_re_flagged(db, investor) -> None:
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "1", "194.06", "2025-04-25", account_id),
            _txn(NEW, "BUY", "10", "232.35", "2026-06-02", account_id),
        ],
    )
    alias_db.add_alias(db, _alias())
    db.commit()

    assert alias_db.detect_candidates(db, investor_id=investor) == []


# --- 9. price evidence spans identifiers ------------------------------------------


def test_price_evidence_follows_an_alias_across_an_isin_change(db, investor) -> None:
    """A split that CHANGES the ISIN puts cum and ex on different identifiers: the old
    one trades up to the change, the new one from it. Without following the alias the cum
    lookup finds nothing and the guard rejects a perfectly good ratio for a reason that
    has nothing to do with the ratio.

    Real numbers, from the SKMEGGPROD change this was built for: 344.05 on the last day
    of the old ISIN, 159.90 on the first day of the new one, against an expected x2.
    """
    from app.db.corporate_actions import _price_evidence

    _seed_securities(db, OLD, NEW)
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO price (isin, price_date, close, source) VALUES (%s,%s,%s,'TEST')",
            (OLD, date(2026, 1, 9), Decimal("344.05")),
        )
        cur.execute(
            "INSERT INTO price (isin, price_date, close, source) VALUES (%s,%s,%s,'TEST')",
            (NEW, date(2026, 1, 12), Decimal("159.90")),
        )
    alias_db.add_alias(db, _alias(effective_date=date(2026, 1, 12)))
    db.commit()

    cum, ex = _price_evidence(db, NEW, date(2026, 1, 12))
    assert cum == Decimal("344.05"), "cum came from the retired identifier"
    assert ex == Decimal("159.90")


def test_price_evidence_does_not_follow_a_draft_alias(db, investor) -> None:
    """Unverified changes nothing, here as everywhere else."""
    from app.db.corporate_actions import _price_evidence

    _seed_securities(db, OLD, NEW)
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO price (isin, price_date, close, source) VALUES (%s,%s,%s,'TEST')",
            (OLD, date(2026, 1, 9), Decimal("344.05")),
        )
    alias_db.add_alias(db, _alias(verification=Verification.DRAFT))
    db.commit()

    cum, _ex = _price_evidence(db, NEW, date(2026, 1, 12))
    assert cum is None


# --- 10. automated promotion: reconcile_after_alias, wired up ---------------------


def test_promotion_verifies_an_alias_with_no_affected_accounts(db, investor) -> None:
    """The common case: an ISIN change for a company nothing in this ledger holds.
    Vacuously safe -- nothing exists for the alias to break."""
    _seed_securities(db, OLD, NEW)
    alias_db.add_alias(db, _alias(verification=Verification.DRAFT))
    db.commit()

    summary = alias_db.promote_draft_aliases(db, as_of=date(2026, 9, 20))

    assert summary.verified == 1
    assert summary.quarantined == 0
    assert OLD in alias_db.verified_map(db)


def test_promotion_verifies_a_clean_split(db, investor) -> None:
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "1", "194.06", "2025-04-25", account_id),
            _txn(NEW, "BUY", "10", "232.35", "2026-06-02", account_id),
        ],
    )
    alias_db.add_alias(db, _alias(verification=Verification.DRAFT))
    db.commit()

    summary = alias_db.promote_draft_aliases(db, as_of=date(2026, 9, 20))

    assert summary.verified == 1
    holdings = compute_holdings(
        repository.load_transactions(db, account_id=account_id), date(2026, 9, 20)
    )
    assert [h.isin for h in holdings] == [NEW]


def test_promotion_quarantines_an_alias_missing_its_corporate_action(db, investor) -> None:
    """The GUJTHEM shape again, but reached through the automated path this time: 65
    held cannot cover 487 sold until a split is on file, so promotion must not verify."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "65", "700", "2022-10-19", account_id),
            _txn(NEW, "SELL", "487", "254.75", "2025-03-18", account_id),
        ],
    )
    alias_db.add_alias(db, _alias(verification=Verification.DRAFT))
    db.commit()

    summary = alias_db.promote_draft_aliases(db, as_of=date(2026, 9, 20))

    assert summary.verified == 0
    assert summary.quarantined == 1
    assert OLD not in alias_db.verified_map(db)
    [stored] = alias_db.list_aliases(db)
    assert stored.verification is Verification.DISPUTED
    assert "corporate action" in stored.notes
    assert account_id in stored.notes, "the notes name which account failed"


def test_promotion_quarantines_if_any_one_of_several_accounts_fails(db, investor) -> None:
    """Two accounts hold the same aliased ISIN pair; one reconciles cleanly, the other
    does not. The alias is GLOBAL -- verification must not partially apply."""
    account_a = os.environ["_TEST_ACCOUNT_ID"]
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO account (investor_id, broker, is_advised) "
            "VALUES (%s, 'ZERODHA', true) RETURNING id",
            (investor,),
        )
        account_b = str(cur.fetchone()[0])
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "1", "194.06", "2025-04-25", account_a),
            _txn(NEW, "BUY", "10", "232.35", "2026-06-02", account_a),
            _txn(OLD, "BUY", "65", "700", "2022-10-19", account_b),
            _txn(NEW, "SELL", "487", "254.75", "2025-03-18", account_b),
        ],
    )
    alias_db.add_alias(db, _alias(verification=Verification.DRAFT))
    db.commit()

    summary = alias_db.promote_draft_aliases(db, as_of=date(2026, 9, 20))

    assert summary.verified == 0
    assert summary.quarantined == 1
    assert OLD not in alias_db.verified_map(db)
    # Account A's own clean reconcile must not leak through as a partial verification.
    holdings_a = compute_holdings(
        repository.load_transactions(db, account_id=account_a), date(2026, 9, 20)
    )
    assert sorted(h.isin for h in holdings_a) == [OLD, NEW], "still unverified for A too"


def test_promotion_leaves_draft_when_reconcile_raises_rather_than_quarantining(
    db, investor, monkeypatch
) -> None:
    """An unrelated exception is not evidence the identity claim is wrong. Quarantining
    on it would be a one-way door -- verify_alias refuses to un-quarantine a DISPUTED
    row -- so an inconclusive round must leave the alias exactly as it found it."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db, [_txn(OLD, "BUY", "1", "194.06", "2025-04-25", account_id)]
    )
    alias_db.add_alias(db, _alias(verification=Verification.DRAFT))
    db.commit()

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated transient failure")

    monkeypatch.setattr(alias_db, "reconcile_after_alias", _boom)

    summary = alias_db.promote_draft_aliases(db, as_of=date(2026, 9, 20))

    assert summary.verified == 0
    assert summary.quarantined == 0
    assert summary.inconclusive == 1
    [stored] = alias_db.list_aliases(db)
    assert stored.verification is Verification.DRAFT, "untouched, not quarantined"


def test_promotion_is_idempotent_on_an_already_quarantined_alias(db, investor) -> None:
    """Re-running the job must not re-examine a row that is no longer DRAFT."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "65", "700", "2022-10-19", account_id),
            _txn(NEW, "SELL", "487", "254.75", "2025-03-18", account_id),
        ],
    )
    alias_db.add_alias(db, _alias(verification=Verification.DRAFT))
    db.commit()

    first = alias_db.promote_draft_aliases(db, as_of=date(2026, 9, 20))
    assert first.quarantined == 1

    second = alias_db.promote_draft_aliases(db, as_of=date(2026, 9, 20))
    assert second.verified == 0
    assert second.quarantined == 0
    assert second.inconclusive == 0
    [stored] = alias_db.list_aliases(db)
    assert stored.verification is Verification.DISPUTED, "still disputed, not re-verified"


def test_promotion_scope_includes_hand_entered_drafts(db, investor) -> None:
    """No special-casing by origin -- a DRAFT written directly via add_alias gets the
    same automated treatment as one a feed created."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "1", "194.06", "2025-04-25", account_id),
            _txn(NEW, "BUY", "10", "232.35", "2026-06-02", account_id),
        ],
    )
    alias_db.add_alias(
        db,
        _alias(
            verification=Verification.DRAFT,
            source="Hand-entered by ops",
            source_url="https://example.invalid/manual",
        ),
    )
    db.commit()

    summary = alias_db.promote_draft_aliases(db, as_of=date(2026, 9, 20))
    assert summary.verified == 1


def test_quarantine_notes_name_broker_and_investor_code_not_just_a_uuid(db, investor) -> None:
    """The usability gap surfaced reviewing this feature: a raw UUID in notes forces a
    second lookup before a human can act. broker/investor.code must lead, with the UUID
    kept alongside for an exact match rather than replaced by it."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    _seed_securities(db, OLD, NEW)
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "65", "700", "2022-10-19", account_id),
            _txn(NEW, "SELL", "487", "254.75", "2025-03-18", account_id),
        ],
    )
    alias_db.add_alias(db, _alias(verification=Verification.DRAFT))
    db.commit()

    alias_db.promote_draft_aliases(db, as_of=date(2026, 9, 20))

    [stored] = alias_db.list_aliases(db)
    assert "ZERODHA/C001" in stored.notes, stored.notes
    assert account_id in stored.notes, "the exact UUID stays available too"
