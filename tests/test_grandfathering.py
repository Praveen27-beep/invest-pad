"""grandfathered_cost_of_acquisition -- docs/TAX_ENGINE.md "Grandfathering".

Hand-computed per CLAUDE.md's "tests are the specification" rule:

    cost_of_acquisition = max( actual_buy_price,
                               min( fmv_31jan2018, actual_sell_price ) )

applied only to a lot opened before 1 Feb 2018.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.engine.grandfathering import (
    GRANDFATHERING_CUTOFF_DATE,
    grandfathered_cost_of_acquisition,
)
from app.engine.types import Lot


def _lot(open_date: date, buy_price: str) -> Lot:
    return Lot(
        isin="INE002A01018",
        open_date=open_date,
        quantity_open=Decimal("10"),
        cost_per_unit=Decimal(buy_price),
    )


def test_pre_2018_lot_fmv_between_buy_and_sell_uses_fmv() -> None:
    """The formula's actual gate: buy=100, fmv=150, sell=200 ->
    max(100, min(150, 200)) = max(100, 150) = 150."""
    lot = _lot(date(2017, 6, 1), "100")
    result = grandfathered_cost_of_acquisition(lot, Decimal("150"), Decimal("200"))
    assert result == Decimal("150")


def test_pre_2018_lot_fmv_above_sell_price_is_capped_at_sell_price() -> None:
    """buy=100, fmv=300, sell=200 -> max(100, min(300, 200)) = max(100, 200) = 200.
    An investor cannot be deemed to have "acquired" above what they actually sold for."""
    lot = _lot(date(2017, 6, 1), "100")
    result = grandfathered_cost_of_acquisition(lot, Decimal("300"), Decimal("200"))
    assert result == Decimal("200")


def test_pre_2018_lot_fmv_below_buy_price_buy_price_wins() -> None:
    """buy=150, fmv=100, sell=200 -> max(150, min(100, 200)) = max(150, 100) = 150.
    Grandfathering only ever helps the taxpayer; it must never manufacture a gain by
    substituting a lower FMV for what was genuinely paid."""
    lot = _lot(date(2017, 6, 1), "150")
    result = grandfathered_cost_of_acquisition(lot, Decimal("100"), Decimal("200"))
    assert result == Decimal("150")


def test_post_2018_lot_formula_never_applies_even_with_an_fmv_supplied() -> None:
    """A lot opened after the cutoff must return its real buy price regardless of what
    fmv_31jan2018 is passed in -- proving the date gate is real, not merely that no FMV
    happened to be available. buy=100; fmv=500 supplied on purpose (would give 200 if
    the gate were missing) but the lot's own open_date rules it out entirely."""
    lot = _lot(date(2019, 1, 1), "100")
    result = grandfathered_cost_of_acquisition(lot, Decimal("500"), Decimal("200"))
    assert result == Decimal("100")


def test_boundary_31_jan_2018_qualifies_1_feb_2018_does_not() -> None:
    """Exactly the cutoff date itself: "before 1 Feb 2018" per docs/TAX_ENGINE.md means
    31 Jan 2018 is the last qualifying day and 1 Feb 2018 is the first day the formula
    no longer applies."""
    day_before = _lot(date(2018, 1, 31), "100")
    cutoff_day = _lot(GRANDFATHERING_CUTOFF_DATE, "100")

    assert grandfathered_cost_of_acquisition(
        day_before, Decimal("150"), Decimal("200")
    ) == Decimal("150")
    assert grandfathered_cost_of_acquisition(
        cutoff_day, Decimal("150"), Decimal("200")
    ) == Decimal("100")


def test_pre_2018_lot_with_no_fmv_sourced_uses_buy_price() -> None:
    """Most lots: fmv_31jan2018 is None because it was never sourced (or the security
    was listed after the cutoff and so never needed one) -- must fall back to the real
    buy price, never raise and never treat None as 0."""
    lot = _lot(date(2015, 3, 1), "100")
    result = grandfathered_cost_of_acquisition(lot, None, Decimal("200"))
    assert result == Decimal("100")
