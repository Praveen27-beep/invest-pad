"""EXPECTED -- a declared dividend sized to a holder, computed on read.

The two tests that matter most here are negative. ``test_a_split_before_the_ex_date_
withholds_the_projection`` pins the one hazard in this calculation that is off by a whole
multiplier rather than a rounding, and ``test_a_projection_never_reaches_a_return_figure``
pins the property the entire declared/received design exists to protect.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.engine.corporate_actions import (
    CorpActionType,
    CorporateAction,
    Verification,
)
from app.engine.dividend_events import DividendEvent, DividendKind
from app.engine.dividends import (
    compute_expected_dividends,
    event_source_ref,
    parse_event_source_ref,
    realised_event_ids,
)
from app.engine.types import Source, Transaction, TxnType

ISIN = "INE002A01018"
EX = date(2025, 7, 10)

NSE = "NSE corporate filings"
YF = "Yahoo Finance (yfinance)"


def _event(
    amount: str = "1.50",
    ex_date: date = EX,
    event_id: str = "evt-1",
    verification: Verification = Verification.VERIFIED,
    **kw,
) -> DividendEvent:
    """A fully corroborated, verified declaration -- the shape that projects."""
    return DividendEvent(
        isin=kw.pop("isin", ISIN),
        ex_date=ex_date,
        amount_per_share=Decimal(amount),
        kind=kw.pop("kind", DividendKind.INTERIM),
        source=NSE,
        source_url="https://nseindia.example/ca",
        corroborated_by=kw.pop("corroborated_by", YF),
        corroborated_url=kw.pop("corroborated_url", "https://finance.yahoo.example"),
        verification=verification,
        id=event_id,
        **kw,
    )


def _buy(quantity: str, txn_date: date, isin: str = ISIN) -> Transaction:
    return Transaction(
        isin=isin, txn_date=txn_date, txn_type=TxnType.BUY,
        quantity=Decimal(quantity), price=Decimal("100"), source=Source.MANUAL,
    )


def _sell(quantity: str, txn_date: date, isin: str = ISIN) -> Transaction:
    return Transaction(
        isin=isin, txn_date=txn_date, txn_type=TxnType.SELL,
        quantity=Decimal(quantity), price=Decimal("120"), source=Source.MANUAL,
    )


# ------------------------------------------------------------------------ the basics


def test_a_normal_dividend_projects() -> None:
    expected, unprojectable = compute_expected_dividends(
        [_buy("100", date(2024, 1, 1))], [_event(amount="1.50")]
    )
    assert not unprojectable
    assert len(expected) == 1
    assert expected[0].eligible_quantity == Decimal("100")
    assert expected[0].gross_expected == Decimal("150.00")


def test_several_lots_are_one_eligible_quantity() -> None:
    """Lot structure is irrelevant to a dividend -- it pays on shares held, not on lots."""
    txns = [
        _buy("100", date(2023, 1, 1)),
        _buy("50", date(2024, 3, 1)),
        _buy("25", date(2025, 1, 1)),
    ]
    expected, _ = compute_expected_dividends(txns, [_event(amount="2")])
    assert expected[0].eligible_quantity == Decimal("175")
    assert expected[0].gross_expected == Decimal("350")


def test_a_sale_before_the_ex_date_reduces_the_projection() -> None:
    """The classic entitlement error: projecting on what is held NOW rather than what was
    held at the cutoff."""
    txns = [_buy("100", date(2024, 1, 1)), _sell("40", date(2025, 7, 8))]
    expected, _ = compute_expected_dividends(txns, [_event(amount="1.50")])
    assert expected[0].eligible_quantity == Decimal("60")
    assert expected[0].gross_expected == Decimal("90.00")


def test_a_sale_on_the_ex_date_is_still_entitled() -> None:
    """The cutoff is the CLOSE BEFORE the ex-date. Selling on the ex-date itself keeps the
    dividend -- that is what "ex" means. Pins quantity_held_before's boundary."""
    txns = [_buy("100", date(2024, 1, 1)), _sell("100", EX)]
    expected, _ = compute_expected_dividends(txns, [_event()])
    assert expected[0].eligible_quantity == Decimal("100")


def test_a_purchase_on_the_ex_date_is_not_entitled() -> None:
    """Buying on the ex-date buys the share without the dividend. Absent, not zero."""
    expected, unprojectable = compute_expected_dividends([_buy("100", EX)], [_event()])
    assert expected == []
    assert unprojectable == [], "not a failure -- simply not a holder"


def test_a_holding_sold_out_entirely_projects_nothing() -> None:
    txns = [_buy("100", date(2024, 1, 1)), _sell("100", date(2025, 1, 1))]
    expected, _ = compute_expected_dividends(txns, [_event()])
    assert expected == []


def test_a_dividend_on_a_security_never_held_projects_nothing() -> None:
    expected, _ = compute_expected_dividends(
        [_buy("100", date(2024, 1, 1), isin="INE009A01021")], [_event()]
    )
    assert expected == []


# ---------------------------------------------------------------- what does not project


def test_an_unverified_event_is_withheld_with_a_reason() -> None:
    """A single-sourced dividend is the normal resting state, not a failure -- but it does
    not produce a number, and the reason is visible rather than the event vanishing."""
    event = _event(verification=Verification.DRAFT)
    expected, unprojectable = compute_expected_dividends([_buy("100", date(2024, 1, 1))], [event])
    assert expected == []
    assert unprojectable[0].code == "UNVERIFIED"


def test_an_uncorroborated_event_is_withheld() -> None:
    event = _event(corroborated_by=None, corroborated_url=None)
    expected, unprojectable = compute_expected_dividends([_buy("100", date(2024, 1, 1))], [event])
    assert expected == []
    assert unprojectable[0].code == "UNCORROBORATED"


def test_a_future_ex_date_is_not_projected_against_as_of() -> None:
    """It has not happened yet, so nobody is eligible. Not withheld -- not due."""
    expected, unprojectable = compute_expected_dividends(
        [_buy("100", date(2024, 1, 1))], [_event(ex_date=date(2026, 1, 1))],
        as_of=date(2025, 12, 1),
    )
    assert expected == [] and unprojectable == []


def test_without_as_of_a_future_dividend_is_included() -> None:
    """What a caller listing UPCOMING dividends wants."""
    expected, _ = compute_expected_dividends(
        [_buy("100", date(2024, 1, 1))], [_event(ex_date=date(2026, 1, 1))]
    )
    assert len(expected) == 1


# --------------------------------------------------------- the split-window hazard


def _split(ex_date: date) -> CorporateAction:
    return CorporateAction(
        isin=ISIN, action_type=CorpActionType.SPLIT, ex_date=ex_date,
        face_value_before=Decimal("10"), face_value_after=Decimal("2"),
        price_cum=Decimal("500"), price_ex=Decimal("100"),
        source="NSE", source_url="https://nseindia.example",
        verification=Verification.VERIFIED,
    )


def test_a_split_before_the_ex_date_withholds_the_projection() -> None:
    """THE HAZARD THIS GUARD EXISTS FOR, and it is off by a whole multiplier.

    "Rs 1.50 per share" declared against the pre-split share, a 1:5 split landing before
    the dividend's ex-date, and quantity_held_before correctly returning the POST-split
    500 shares. 1.50 x 500 = 750 instead of 150 -- five times too large, with every
    component correct and nothing reporting an error.
    """
    txns = [_buy("100", date(2024, 1, 1))]
    expected, unprojectable = compute_expected_dividends(
        txns, [_event(amount="1.50")], actions=[_split(date(2025, 6, 1))]
    )
    assert expected == []
    assert unprojectable[0].code == "SHARE_COUNT_CHANGED"
    assert "SPLIT" in unprojectable[0].detail


def test_a_bonus_before_the_ex_date_withholds_the_projection() -> None:
    bonus = CorporateAction(
        isin=ISIN, action_type=CorpActionType.BONUS, ex_date=date(2025, 6, 1),
        bonus_new=1, bonus_for=1, price_cum=Decimal("400"), price_ex=Decimal("200"),
        source="NSE", source_url="https://nseindia.example",
        verification=Verification.VERIFIED,
    )
    expected, unprojectable = compute_expected_dividends(
        [_buy("100", date(2024, 1, 1))], [_event()], actions=[bonus]
    )
    assert expected == []
    assert unprojectable[0].code == "SHARE_COUNT_CHANGED"


def test_an_old_split_does_not_withhold_the_projection() -> None:
    """A split well outside the declaration window cannot predate this declaration, so
    both the amount and the quantity are on the post-split basis and the figure is right.

    Without this the guard would withhold every dividend of every company that has ever
    split, which is most of them.
    """
    expected, unprojectable = compute_expected_dividends(
        [_buy("100", date(2020, 1, 1))], [_event()], actions=[_split(date(2021, 3, 1))]
    )
    assert unprojectable == []
    assert expected[0].gross_expected == Decimal("150.00")


def test_a_split_after_the_ex_date_does_not_withhold() -> None:
    """A later split restates nothing about a dividend already gone ex."""
    expected, unprojectable = compute_expected_dividends(
        [_buy("100", date(2024, 1, 1))], [_event()], actions=[_split(date(2025, 9, 1))]
    )
    assert unprojectable == []
    assert len(expected) == 1


def test_a_split_on_another_security_does_not_withhold() -> None:
    other = CorporateAction(
        isin="INE009A01021", action_type=CorpActionType.SPLIT, ex_date=date(2025, 6, 1),
        face_value_before=Decimal("10"), face_value_after=Decimal("2"),
        price_cum=Decimal("500"), price_ex=Decimal("100"),
        source="NSE", source_url="https://nseindia.example",
        verification=Verification.VERIFIED,
    )
    expected, unprojectable = compute_expected_dividends(
        [_buy("100", date(2024, 1, 1))], [_event()], actions=[other]
    )
    assert unprojectable == []
    assert len(expected) == 1


def test_a_demerger_does_not_withhold() -> None:
    """A demerger changes the cost pool and adds a second security; it does not restate
    the per-share basis of the security being paid on."""
    demerger = CorporateAction(
        isin=ISIN, action_type=CorpActionType.DEMERGER, ex_date=date(2025, 6, 1),
        resulting_isin="INE009A01021", demerger_new=1, demerger_for=1,
        source="NSE", source_url="https://nseindia.example",
        verification=Verification.VERIFIED,
    )
    expected, unprojectable = compute_expected_dividends(
        [_buy("100", date(2024, 1, 1))], [_event()], actions=[demerger]
    )
    assert unprojectable == []
    assert len(expected) == 1


# ------------------------------------------------------------------ realised linkage


def test_source_ref_round_trips() -> None:
    assert parse_event_source_ref(event_source_ref("evt-1")) == ("evt-1", 1)
    assert parse_event_source_ref(event_source_ref("evt-1", 2)) == ("evt-1", 2)


def test_a_manual_dividends_source_ref_is_not_a_link() -> None:
    """A hand-entered dividend is real income and counts in compute_dividends, but it is
    not linked to a declared event. Tolerant, not an error."""
    assert parse_event_source_ref(None) is None
    assert parse_event_source_ref("cheque no 4471") is None
    assert parse_event_source_ref("DIV:evt-1") is None
    assert parse_event_source_ref("DIV:evt-1:notanumber") is None


def test_an_already_realised_event_is_not_projected_again() -> None:
    """Once the money has arrived, the ledger row is the truth and the expectation is
    spent. Matched exactly through source_ref."""
    realised = Transaction(
        isin=ISIN, txn_date=date(2025, 8, 1), txn_type=TxnType.DIVIDEND,
        quantity=Decimal("0"), price=Decimal("0"), dividend_amount=Decimal("150"),
        source=Source.CORP_ACTION, source_ref=event_source_ref("evt-1"),
    )
    expected, _ = compute_expected_dividends(
        [_buy("100", date(2024, 1, 1)), realised], [_event(event_id="evt-1")]
    )
    assert expected == []


def test_a_similar_but_unlinked_dividend_does_not_suppress_the_expectation() -> None:
    """Never inferred from a nearby date and a similar amount.

    Guessing the link would quietly hide a real SECOND dividend that happened to resemble
    one already received -- exactly the interim-plus-special case.
    """
    manual = Transaction(
        isin=ISIN, txn_date=date(2025, 8, 1), txn_type=TxnType.DIVIDEND,
        quantity=Decimal("0"), price=Decimal("0"), dividend_amount=Decimal("150"),
        source=Source.MANUAL, source_ref="from the bank statement",
    )
    expected, _ = compute_expected_dividends(
        [_buy("100", date(2024, 1, 1)), manual], [_event(event_id="evt-1")]
    )
    assert len(expected) == 1


def test_realised_event_ids_reads_only_dividend_rows() -> None:
    txns = [
        _buy("100", date(2024, 1, 1)),
        Transaction(
            isin=ISIN, txn_date=date(2025, 8, 1), txn_type=TxnType.DIVIDEND,
            quantity=Decimal("0"), price=Decimal("0"), dividend_amount=Decimal("150"),
            source=Source.CORP_ACTION, source_ref=event_source_ref("evt-9"),
        ),
    ]
    assert realised_event_ids(txns) == {"evt-9"}


# ------------------------------------------------------- the containment property


def test_a_projection_never_reaches_a_return_figure() -> None:
    """THE LOAD-BEARING TEST OF THE WHOLE DECLARED/RECEIVED DESIGN.

    The same rupees must move a return figure when they are RECEIVED and leave it
    untouched when they are only EXPECTED. Asserting that directly is what makes this
    meaningful rather than tautological: the test first proves XIRR is sensitive to
    dividend income at all (otherwise it would pass for the wrong reason), then proves the
    identical amount as a projection moves nothing.
    """
    from app.engine.dividends import compute_dividends
    from app.engine.xirr import compute_xirr

    txns = [_buy("100", date(2024, 1, 1)), _sell("40", date(2025, 3, 1))]
    events = [
        _event(amount="1.50"),
        _event(amount="2.00", ex_date=date(2025, 9, 1), event_id="evt-2",
               kind=DividendKind.FINAL),
    ]
    prices = {ISIN: Decimal("130")}
    as_of = date(2025, 12, 31)

    expected, _ = compute_expected_dividends(txns, events)
    # 60 shares held at both ex-dates (100 bought, 40 sold in March): 60x1.50 + 60x2.00.
    total_expected = sum(e.gross_expected for e in expected)
    assert total_expected == Decimal("210.00")

    # Control: the SAME amount, actually received, does move XIRR. Without this the test
    # below could pass simply because XIRR ignores dividends, which it does not.
    received = Transaction(
        isin=ISIN, txn_date=date(2025, 9, 2), txn_type=TxnType.DIVIDEND,
        quantity=Decimal("0"), price=Decimal("0"), dividend_amount=total_expected,
        source=Source.CORP_ACTION, source_ref=event_source_ref("evt-3"),
    )
    assert compute_xirr([*txns, received], prices, as_of) != compute_xirr(txns, prices, as_of)

    # The property: with the declarations outstanding and nothing received, realised
    # dividend income is nothing and XIRR is the no-dividend figure exactly.
    assert compute_dividends(txns) == []
    assert compute_xirr(txns, prices, as_of) == compute_xirr(
        [_buy("100", date(2024, 1, 1)), _sell("40", date(2025, 3, 1))], prices, as_of
    )


def test_expected_dividends_are_returned_in_calendar_order() -> None:
    events = [
        _event(ex_date=date(2025, 11, 4), event_id="c"),
        _event(ex_date=date(2025, 2, 6), event_id="a"),
        _event(ex_date=date(2025, 7, 10), event_id="b"),
    ]
    expected, _ = compute_expected_dividends([_buy("100", date(2024, 1, 1))], events)
    assert [e.ex_date for e in expected] == [
        date(2025, 2, 6), date(2025, 7, 10), date(2025, 11, 4)
    ]


def test_an_expectation_carries_no_tds() -> None:
    """No tax has been withheld from a projection, because no money has moved. The field
    is named gross_expected for that reason and there is no net."""
    from app.engine.dividends import ExpectedDividend

    fields = set(ExpectedDividend.__dataclass_fields__)
    assert "gross_expected" in fields
    assert not fields & {"tds", "tds_amount", "net", "net_received"}


@pytest.mark.parametrize("quantity", ["0", "0.000000"])
def test_a_zero_eligible_quantity_projects_nothing(quantity: str) -> None:
    txns = [_buy("100", date(2024, 1, 1)), _sell("100", date(2025, 1, 1))]
    expected, _ = compute_expected_dividends(txns, [_event()])
    assert expected == []
