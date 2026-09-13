"""The guards that decide whether a declared dividend may be projected from.

These are the dividend analogue of test_corporate_actions.py's guard cases, and the
interesting difference is WHAT corroborates what. A bonus is checked against a physically
separate observation -- the traded close. A dividend cannot be: its ex-date price move is
inside daily noise, so the substitute is a second source reading the same fact. These
tests pin that substitute's limits as carefully as its successes, because an overclaimed
guard is worse than an absent one.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.engine.corporate_actions import Verification
from app.engine.dividend_events import (
    MAX_PLAUSIBLE_YIELD,
    DividendEvent,
    DividendKind,
    check_amount_plausible,
    check_cross_sourced,
    check_sourced,
    check_verified,
    screen,
)

NSE = "NSE corporate filings"
YF = "Yahoo Finance (yfinance)"


def _event(**overrides: object) -> DividendEvent:
    """A fully corroborated, verified interim dividend -- the shape that passes everything."""
    base: dict[str, object] = {
        "isin": "INE002A01018",
        "ex_date": date(2025, 7, 10),
        "amount_per_share": Decimal("1.50"),
        "kind": DividendKind.INTERIM,
        "source": NSE,
        "source_url": "https://www.nseindia.com/companies-listing/corporate-filings-actions",
        "corroborated_by": YF,
        "corroborated_url": "https://finance.yahoo.com/quote/RELIANCE.NS",
        "verification": Verification.VERIFIED,
    }
    base.update(overrides)
    return DividendEvent(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- sourcing


def test_an_event_without_provenance_is_rejected() -> None:
    failure = check_sourced(_event(source="", source_url=""))
    assert failure is not None
    assert failure.code == "UNSOURCED"


def test_sourcing_passes_on_any_non_empty_strings() -> None:
    """Pinned deliberately to document the guard's WEAKNESS, not its strength.

    check_sourced tests two strings are non-empty and nothing more -- exactly as weak as
    its corporate-action twin. It is recorded here so nobody later reads a passing
    check_sourced as evidence a dividend is trustworthy; check_cross_sourced is what
    actually gates verification.
    """
    assert check_sourced(_event(source="x", source_url="y")) is None


# ------------------------------------------------------------------ cross-sourcing


def test_a_single_sourced_dividend_is_not_projectable() -> None:
    """The normal resting state of a freshly discovered dividend, and not a failure.

    One feed has seen it. It stays DRAFT until a second agrees or a human reads the
    company's filing.
    """
    failure = check_cross_sourced(_event(corroborated_by=None, corroborated_url=None))
    assert failure is not None
    assert failure.code == "UNCORROBORATED"


def test_a_source_cannot_corroborate_itself() -> None:
    """Two reads of one feed are one observation.

    This is the precise mistake the guard exists to prevent: a second run of the NSE feed
    must not look like independent confirmation of the first run.
    """
    failure = check_cross_sourced(_event(corroborated_by=NSE, corroborated_url="https://nse"))
    assert failure is not None
    assert failure.code == "SELF_CORROBORATED"


def test_a_half_filled_corroboration_does_not_count() -> None:
    """A corroborating source with no URL is an assertion nobody can re-check."""
    assert check_cross_sourced(_event(corroborated_url=None)).code == "UNCORROBORATED"
    assert check_cross_sourced(_event(corroborated_by=None)).code == "UNCORROBORATED"


def test_two_distinct_sources_agreeing_passes() -> None:
    assert check_cross_sourced(_event()) is None


# -------------------------------------------------------------------- plausibility


def test_a_hundredfold_unit_error_is_caught() -> None:
    """The realistic parse failure: "Rs 1.50 Per Share" read as 150.

    On a 200-rupee share that implies a 75% yield. This is the error class the guard is
    calibrated for -- a misplaced decimal point, not a generous payout.
    """
    failure = check_amount_plausible(_event(amount_per_share=Decimal("150")), Decimal("200"))
    assert failure is not None
    assert failure.code == "AMOUNT_IMPLAUSIBLE"


def test_an_ordinary_dividend_is_plausible() -> None:
    assert check_amount_plausible(_event(), Decimal("1400")) is None


def test_a_generous_special_dividend_still_passes() -> None:
    """The ceiling sits far above any ordinary yield on purpose.

    A company distributing asset-sale proceeds can legitimately pay a large fraction of
    its price. Rejecting that would quarantine real events to catch nothing extra -- the
    guard is aimed at 100x errors, and a 40% yield is below the ceiling by design.
    """
    assert check_amount_plausible(_event(amount_per_share=Decimal("40")), Decimal("100")) is None


def test_plausibility_passes_when_no_close_is_available() -> None:
    """Unlike a bonus, a dividend is not withheld for want of a price.

    NO_PRICE_EVIDENCE quarantines a bonus because the price IS the evidence there. Here it
    never was, so requiring one would quarantine most of the historic archive for no gain.
    """
    assert check_amount_plausible(_event(), None) is None
    assert check_amount_plausible(_event(), Decimal("0")) is None


def test_a_non_positive_amount_is_rejected_before_any_price_lookup() -> None:
    assert check_amount_plausible(_event(amount_per_share=Decimal("0")), None).code == "BAD_AMOUNT"
    assert check_amount_plausible(_event(amount_per_share=Decimal("-1")), None).code == "BAD_AMOUNT"


def test_the_plausibility_ceiling_is_where_the_constant_says() -> None:
    """Pins the boundary so a later change to MAX_PLAUSIBLE_YIELD is a deliberate act."""
    close = Decimal("100")
    at_ceiling = _event(amount_per_share=MAX_PLAUSIBLE_YIELD * close)
    just_over = _event(amount_per_share=(MAX_PLAUSIBLE_YIELD * close) + Decimal("0.01"))
    assert check_amount_plausible(at_ceiling, close) is None
    assert check_amount_plausible(just_over, close) is not None


# ------------------------------------------------------------------- verification


def test_a_draft_event_is_not_projectable() -> None:
    assert check_verified(_event(verification=Verification.DRAFT)).code == "UNVERIFIED"


def test_a_disputed_event_is_not_projectable() -> None:
    assert check_verified(_event(verification=Verification.DISPUTED)).code == "UNVERIFIED"


# -------------------------------------------------------------------------- screen


def test_screen_separates_safe_events_from_quarantined_ones() -> None:
    good = _event()
    draft = _event(ex_date=date(2025, 8, 1), verification=Verification.DRAFT)
    lonely = _event(ex_date=date(2025, 9, 1), corroborated_by=None, corroborated_url=None)

    safe, failures = screen([good, draft, lonely])

    assert safe == [good]
    assert {f.code for f in failures} == {"UNVERIFIED", "UNCORROBORATED"}


def test_screen_reports_one_failure_per_event() -> None:
    """An event that trips several guards is reported once.

    A second opinion on an already-quarantined record tells a reader nothing they can act
    on, and the count of failures is read as a count of problems.
    """
    hopeless = _event(source="", source_url="", verification=Verification.DRAFT,
                      corroborated_by=None, corroborated_url=None)
    safe, failures = screen([hopeless])
    assert safe == []
    assert len(failures) == 1
    assert failures[0].code == "UNSOURCED"


def test_screen_uses_closes_for_plausibility_when_given() -> None:
    bad_unit = _event(amount_per_share=Decimal("150"))
    safe, failures = screen([bad_unit], closes={(bad_unit.isin, bad_unit.ex_date): Decimal("200")})
    assert safe == []
    assert failures[0].code == "AMOUNT_IMPLAUSIBLE"


def test_screen_without_closes_still_applies_the_other_guards() -> None:
    safe, failures = screen([_event()])
    assert safe and not failures


# -------------------------------------------------------------------------- identity


def test_event_identity_excludes_the_amount() -> None:
    """A corrected amount is the SAME event with a better number.

    If the amount were part of identity, a correction would insert a second row and leave
    two contradictory claims about one fact with nothing able to choose between them --
    the failure security_alias's single-row primary key was designed to prevent.
    """
    original = _event(amount_per_share=Decimal("1.50"))
    corrected = _event(amount_per_share=Decimal("1.75"))
    assert original.dedup_key == corrected.dedup_key


def test_event_identity_includes_the_kind() -> None:
    """An interim and a special dividend can share an ex-date and are two real events.

    Without the kind in the key, a special declared alongside an interim is silently lost.
    """
    interim = _event(kind=DividendKind.INTERIM)
    special = _event(kind=DividendKind.SPECIAL)
    assert interim.dedup_key != special.dedup_key


def test_unspecified_is_a_real_kind_not_an_absence() -> None:
    """It means "this source did not say", and it has to be orderable and comparable
    because it participates in the table's uniqueness."""
    assert DividendKind("UNSPECIFIED") is DividendKind.UNSPECIFIED
    assert _event(kind=DividendKind.UNSPECIFIED).dedup_key[2] == DividendKind.UNSPECIFIED


def test_a_dividend_event_carries_no_quantity_and_no_total() -> None:
    """The type itself refuses to hold a projection.

    Multiplying by a holder's quantity is what turns a declaration into an expectation,
    and that must happen on read, never in storage. Pinned so a later "convenience" field
    cannot quietly make this table investor-specific.
    """
    fields = set(DividendEvent.__dataclass_fields__)
    assert not fields & {"quantity", "eligible_quantity", "total", "gross", "amount"}


def test_dividend_events_reuse_the_one_verification_vocabulary() -> None:
    """Not a parallel enum: the same Verification corporate_action and security_alias use.

    Two three-state enums pretending to be one standard of evidence is how a system ends
    up with two.
    """
    from app.engine import corporate_actions, dividend_events

    assert dividend_events.Verification is corporate_actions.Verification


def test_price_consistency_is_not_reachable_for_a_dividend() -> None:
    """The load-bearing negative test for this whole design.

    check_price_consistency returns None -- i.e. PASSES -- for anything that is not BONUS
    or SPLIT. That is why DIVIDEND was kept out of CorpActionType: as a member of that
    enum it would have inherited apply_known_actions_for_account's auto-apply path with
    this guard silently passing, leaving "somebody typed a URL" as the only real check.
    This test documents the vacuum rather than relying on a comment to.
    """
    from app.engine.corporate_actions import (
        CorpActionType,
        CorporateAction,
        check_price_consistency,
    )

    demerger = CorporateAction(
        isin="INE002A01018",
        action_type=CorpActionType.DEMERGER,
        ex_date=date(2025, 7, 10),
        source="x",
        source_url="y",
        verification=Verification.VERIFIED,
        resulting_isin="INE002A01026",
        demerger_new=1,
        demerger_for=1,
    )
    assert check_price_consistency(demerger) is None
    assert "DIVIDEND" not in {t.value for t in CorpActionType}


@pytest.mark.parametrize("kind", list(DividendKind))
def test_every_kind_round_trips_through_its_value(kind: DividendKind) -> None:
    assert DividendKind(kind.value) is kind
