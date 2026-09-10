"""Verified corporate actions -- the bridge between app.engine.reconcile's text
hypothesis and an actual staged transaction. Hand-computed per CLAUDE.md's "tests are
the specification" rule.

KAMAHOLD is the canonical case this whole feature exists for: Kama Holdings' 4:1 bonus
is printed "4:1" by one provider and "1:4" by another, and a record that guesses wrong
is 5x off with no error raised -- see app.engine.corporate_actions' module docstring.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.engine.corporate_actions import (
    CorpActionType,
    CorporateAction,
    CorporateActionRatioError,
    Verification,
    explain,
    match_corporate_action,
    screen,
)
from app.engine.types import Discrepancy, Source, Transaction, TxnType
from app.ingest.corporate_action_matcher import stage_corporate_actions

KAMAHOLD = "INE411H01032"
ACCOUNT = "A"


def _bonus(
    bonus_new: int = 4,
    bonus_for: int = 1,
    price_cum: str = "16000",
    price_ex: str = "3200",
    verification: Verification = Verification.VERIFIED,
    ex_date: date = date(2023, 10, 17),
) -> CorporateAction:
    return CorporateAction(
        isin=KAMAHOLD,
        action_type=CorpActionType.BONUS,
        ex_date=ex_date,
        bonus_new=bonus_new,
        bonus_for=bonus_for,
        price_cum=Decimal(price_cum) if price_cum else None,
        price_ex=Decimal(price_ex) if price_ex else None,
        source="BSE notice",
        source_url="https://example.invalid/kamahold",
        verification=verification,
    )


# ---------------------------------------------------------------------------
# multiplier() and construction-time validation
# ---------------------------------------------------------------------------


def test_kamahold_4for1_bonus_multiplier_is_5():
    """1 share held + 4 new for every 1 held -> 5 held after, per 1 before."""
    assert _bonus().multiplier() == 5


def test_bonus_missing_counts_fails_at_construction():
    with pytest.raises(CorporateActionRatioError):
        CorporateAction(
            isin=KAMAHOLD, action_type=CorpActionType.BONUS, ex_date=date(2024, 1, 1),
            source="s", source_url="https://example.invalid/s",
        )


def test_reverse_split_is_rejected_not_silently_inverted():
    """face_value_before < face_value_after would be a consolidation, which this system
    does not represent (see app.engine.corporate_actions' module docstring) -- SPLIT
    must fail loudly here, not silently scale a position the wrong way."""
    with pytest.raises(CorporateActionRatioError):
        CorporateAction(
            isin=KAMAHOLD, action_type=CorpActionType.SPLIT, ex_date=date(2024, 1, 1),
            face_value_before=Decimal(2), face_value_after=Decimal(10),
            source="s", source_url="https://example.invalid/s",
        )


def test_demerger_needs_resulting_isin_and_share_ratio():
    with pytest.raises(CorporateActionRatioError):
        CorporateAction(
            isin=KAMAHOLD, action_type=CorpActionType.DEMERGER, ex_date=date(2024, 1, 1),
            demerger_new=1, demerger_for=2,
            source="s", source_url="https://example.invalid/s",
        )


# ---------------------------------------------------------------------------
# Guards: silent wrongness turned into loud failure
# ---------------------------------------------------------------------------


def test_inverted_bonus_ratio_is_caught_by_the_price_move():
    """The Kama bonus written the wrong way round: 1 new for every 4 held. The record
    parses, the arithmetic runs, and the answer is 5x wrong. Only the price evidence
    catches it."""
    bad = _bonus(bonus_new=1, bonus_for=4)
    safe, failures = screen([bad])
    assert safe == []
    assert failures[0].code == "RATIO_CONTRADICTS_PRICE"


def test_action_without_price_evidence_is_quarantined_not_matched():
    no_price = _bonus(price_cum="", price_ex="")
    safe, failures = screen([no_price])
    assert safe == []
    assert failures[0].code == "NO_PRICE_EVIDENCE"


def test_unverified_action_never_matches_a_discrepancy():
    draft = _bonus(verification=Verification.DRAFT)
    d = Discrepancy(
        isin=KAMAHOLD, computed_qty=Decimal(1), declared_qty=Decimal(5),
        difference=Decimal(4), ratio=Decimal(5),
    )
    assert match_corporate_action(d, [draft], Decimal(1)) is None


def test_duplicate_action_is_rejected():
    kw = dict(
        isin=KAMAHOLD, action_type=CorpActionType.BONUS, ex_date=date(2023, 10, 17),
        bonus_new=4, bonus_for=1, price_cum=Decimal(16000), price_ex=Decimal(3200),
        source="s", source_url="https://example.invalid/s", verification=Verification.VERIFIED,
    )
    safe, failures = screen([CorporateAction(**kw), CorporateAction(**kw)])
    assert safe == []
    assert any(f.code == "DUPLICATE" for f in failures)


# ---------------------------------------------------------------------------
# explain(): does a verified action account for a specific Discrepancy?
# ---------------------------------------------------------------------------


def test_kamahold_bonus_explains_the_discrepancy_with_4_additional_shares():
    d = Discrepancy(
        isin=KAMAHOLD, computed_qty=Decimal(1), declared_qty=Decimal(5),
        difference=Decimal(4), ratio=Decimal(5),
    )
    matched = explain(d, _bonus(), held_qty=Decimal(1))
    assert matched is not None
    assert matched.txn_type == "BONUS"
    assert matched.isin == KAMAHOLD
    assert matched.quantity == Decimal(4)


def test_split_explains_a_5x_discrepancy_on_a_larger_holding():
    split = CorporateAction(
        isin=KAMAHOLD, action_type=CorpActionType.SPLIT, ex_date=date(2024, 1, 1),
        face_value_before=Decimal(10), face_value_after=Decimal(2),
        price_cum=Decimal(1500), price_ex=Decimal(300),
        source="s", source_url="https://example.invalid/s", verification=Verification.VERIFIED,
    )
    d = Discrepancy(
        isin=KAMAHOLD, computed_qty=Decimal(100), declared_qty=Decimal(500),
        difference=Decimal(400), ratio=Decimal(5),
    )
    matched = explain(d, split, held_qty=Decimal(100))
    assert matched is not None
    assert matched.txn_type == "SPLIT_ADJ"
    assert matched.quantity == Decimal(400)


def test_wrong_isin_never_matches():
    d = Discrepancy(
        isin="INE000A01010", computed_qty=Decimal(1), declared_qty=Decimal(5),
        difference=Decimal(4), ratio=Decimal(5),
    )
    assert explain(d, _bonus(), held_qty=Decimal(1)) is None


def test_ratio_outside_tolerance_never_matches():
    """A real 1:1 bonus (multiplier 2) must not be mistaken for a 4:1 bonus (multiplier
    5) just because both are "big"."""
    d = Discrepancy(
        isin=KAMAHOLD, computed_qty=Decimal(1), declared_qty=Decimal(2),
        difference=Decimal(1), ratio=Decimal(2),
    )
    assert explain(d, _bonus(), held_qty=Decimal(1)) is None


def test_demerger_explains_a_zero_computed_discrepancy_on_the_resulting_isin():
    """A demerger's discrepancy shows up on the CHILD security, which the ledger has
    never seen -- computed_qty is always 0 there, never a ratio."""
    demerger = CorporateAction(
        isin=KAMAHOLD, action_type=CorpActionType.DEMERGER, ex_date=date(2024, 7, 1),
        resulting_isin="INE222A01011", demerger_new=1, demerger_for=2,
        source="scheme notice", source_url="https://example.invalid/d",
        verification=Verification.VERIFIED,
    )
    d = Discrepancy(
        isin="INE222A01011", computed_qty=Decimal(0), declared_qty=Decimal(50),
        difference=Decimal(50), ratio=None,
    )
    matched = explain(d, demerger, held_qty=Decimal(100))  # parent's held quantity
    assert matched is not None
    assert matched.txn_type == "DEMERGER_IN"
    assert matched.isin == "INE222A01011"
    assert matched.quantity == Decimal(50)


def test_demerger_does_not_match_an_unrelated_zero_quantity():
    """computed_qty = 0 is also the signature of a plain missed transfer-in -- a
    demerger on file for a DIFFERENT resulting security must not be matched to it."""
    demerger = CorporateAction(
        isin=KAMAHOLD, action_type=CorpActionType.DEMERGER, ex_date=date(2024, 7, 1),
        resulting_isin="INE222A01011", demerger_new=1, demerger_for=2,
        source="scheme notice", source_url="https://example.invalid/d",
        verification=Verification.VERIFIED,
    )
    d = Discrepancy(
        isin="INE999Z01099", computed_qty=Decimal(0), declared_qty=Decimal(50),
        difference=Decimal(50), ratio=None,
    )
    assert explain(d, demerger, held_qty=Decimal(100)) is None


# ---------------------------------------------------------------------------
# stage_corporate_actions(): the full reconcile -> match -> StagedRow path
# ---------------------------------------------------------------------------


def test_matched_discrepancy_stages_the_correct_bonus_transaction():
    trades = [
        Transaction(
            isin=KAMAHOLD, txn_date=date(2023, 1, 3), txn_type=TxnType.BUY,
            quantity=Decimal(1), price=Decimal("16169.45"), account_id=ACCOUNT,
            source=Source.TRADEBOOK,
        )
    ]
    declared = {KAMAHOLD: Decimal(5)}
    result = stage_corporate_actions(trades, declared, [_bonus()], ACCOUNT)

    assert result.rejected == 0
    assert len(result.rows) == 1
    staged = result.rows[0].transaction
    assert staged.txn_type is TxnType.BONUS
    assert staged.isin == KAMAHOLD
    assert staged.quantity == Decimal(4)
    assert staged.price == Decimal(0)
    assert staged.account_id == ACCOUNT
    assert staged.source is Source.CORP_ACTION


def test_unmatched_discrepancy_falls_back_to_the_existing_text_hint():
    """No verified action on file for this ISIN -- the existing reconcile() hypothesis
    survives unchanged as a Rejection, not a silent drop."""
    trades = [
        Transaction(
            isin=KAMAHOLD, txn_date=date(2023, 1, 3), txn_type=TxnType.BUY,
            quantity=Decimal(1), price=Decimal("16169.45"), account_id=ACCOUNT,
            source=Source.TRADEBOOK,
        )
    ]
    declared = {KAMAHOLD: Decimal(5)}
    result = stage_corporate_actions(trades, declared, [], ACCOUNT)

    assert result.rows == []
    assert len(result.rejections) == 1
    # Unchanged from today's reconcile() behaviour: a ratio of 5 reads as "1:5 split"
    # per RATIO_CAUSES -- this is the existing hint, not something this feature adds.
    assert "split" in result.rejections[0].reason.lower()


def test_quarantined_action_does_not_match_even_though_it_is_on_file():
    """An inverted-ratio record sitting in the reference table must not be trusted just
    because it exists -- screen() quarantines it before matching ever sees it."""
    trades = [
        Transaction(
            isin=KAMAHOLD, txn_date=date(2023, 1, 3), txn_type=TxnType.BUY,
            quantity=Decimal(1), price=Decimal("16169.45"), account_id=ACCOUNT,
            source=Source.TRADEBOOK,
        )
    ]
    declared = {KAMAHOLD: Decimal(5)}
    bad = _bonus(bonus_new=1, bonus_for=4)  # inverted
    result = stage_corporate_actions(trades, declared, [bad], ACCOUNT)

    assert result.rows == []
    assert len(result.rejections) == 1


def test_bonus_quantity_is_based_on_holding_at_the_ex_date_not_today():
    """Regression: a purchase made AFTER the bonus, unrelated to it, must not be
    multiplied by the bonus ratio too.

    1000 held before the 2023-10-17 bonus (1:1 -> multiplier 2, +1000 bonus shares is
    correct), then 1 more bought in 2024 for an unrelated reason. ``declared`` is the
    honest total: 1000 original + 1000 bonus + 1 later purchase = 2001.

    Using "quantity held as of today" (2001, pre-fix) instead of "quantity held the day
    before the ex-date" (1000) computes a bonus of 2001 x 1 = 2001 -- silently 1001
    shares too many, and the error is proportional to whatever was bought after the
    bonus, not a fixed, obviously-wrong number. The fix must stage exactly 1000.
    """
    bonus_1for1 = CorporateAction(
        isin=KAMAHOLD, action_type=CorpActionType.BONUS, ex_date=date(2023, 10, 17),
        bonus_new=1, bonus_for=1,
        price_cum=Decimal(2000), price_ex=Decimal(1000),
        source="BSE notice", source_url="https://example.invalid/1for1",
        verification=Verification.VERIFIED,
    )
    trades = [
        Transaction(
            isin=KAMAHOLD, txn_date=date(2023, 6, 1), txn_type=TxnType.BUY,
            quantity=Decimal(1000), price=Decimal("1900"), account_id=ACCOUNT,
            source=Source.TRADEBOOK,
        ),
        Transaction(
            isin=KAMAHOLD, txn_date=date(2024, 1, 1), txn_type=TxnType.BUY,
            quantity=Decimal(1), price=Decimal("950"), account_id=ACCOUNT,
            source=Source.TRADEBOOK,
        ),
    ]
    declared = {KAMAHOLD: Decimal(2001)}
    result = stage_corporate_actions(trades, declared, [bonus_1for1], ACCOUNT)

    assert len(result.rows) == 1
    staged = result.rows[0].transaction
    assert staged.txn_type is TxnType.BONUS
    assert staged.quantity == Decimal(1000)


def test_matching_is_not_blocked_by_an_unrelated_broken_isin():
    """Regression: an account with ANY unresolved NegativeHoldingError elsewhere must
    not stop the matcher from fixing a different, healthy ISIN's discrepancy -- fixing
    exactly that kind of gap is this feature's whole purpose. Before the fix, ``reconcile``
    (and the matcher's own ``held`` lookup) called the strict, unpartitioned
    ``compute_holdings``, which raised on the broken ISIN and aborted the entire call --
    so a single bad security anywhere in the account silently disabled corporate-action
    matching for every other security too."""
    broken_isin = "INE999Z01099"  # a disposal with no buy history at all -- always broken
    trades = [
        Transaction(
            isin=broken_isin, txn_date=date(2024, 1, 1), txn_type=TxnType.SELL,
            quantity=Decimal(5), price=Decimal(100), account_id=ACCOUNT,
            source=Source.TRADEBOOK,
        ),
        Transaction(
            isin=KAMAHOLD, txn_date=date(2023, 1, 3), txn_type=TxnType.BUY,
            quantity=Decimal(1), price=Decimal("16169.45"), account_id=ACCOUNT,
            source=Source.TRADEBOOK,
        ),
    ]
    declared = {KAMAHOLD: Decimal(5)}
    result = stage_corporate_actions(trades, declared, [_bonus()], ACCOUNT)

    assert len(result.rows) == 1
    staged = result.rows[0].transaction
    assert staged.isin == KAMAHOLD
    assert staged.quantity == Decimal(4)


def test_clean_reconciliation_stages_nothing():
    trades = [
        Transaction(
            isin=KAMAHOLD, txn_date=date(2023, 1, 3), txn_type=TxnType.BUY,
            quantity=Decimal(5), price=Decimal("16169.45"), account_id=ACCOUNT,
            source=Source.TRADEBOOK,
        )
    ]
    declared = {KAMAHOLD: Decimal(5)}
    result = stage_corporate_actions(trades, declared, [_bonus()], ACCOUNT)
    assert result.rows == []
    assert result.rejections == []
