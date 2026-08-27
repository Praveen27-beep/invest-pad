"""build_schedule_112a -- docs/TAX_ENGINE.md, docs/FEATURE_BACKLOG.md Phase 3.

Hand-computed per CLAUDE.md's "tests are the specification" rule. Column numbers in
comments refer to CBDT's Schedule 112A CSV-upload instructions (see
app/engine/schedule_112a.py's module docstring for the exact source).

Worked scenario, matching TAX_ENGINE.md/ENGINE_SPEC.md's style of small realistic
numbers:

  BE row (INE001A01036, bought 2016 -- pre-cutoff):
    quantity 100, actual buy price 100/unit, FMV as on 31 Jan 2018 = 150/unit,
    sold at 200/unit.
    col 8 (actual cost)      = 100 * 100 = 10,000
    col 10/11 (FMV, total)   = 150, 100*150 = 15,000
    col 6 (sale value)       = 100 * 200 = 20,000
    col 9 (grandfathering floor) = lower(11, 6) = lower(15000, 20000) = 15,000
    col 7 (cost w/o indexation)  = higher(8, 9) = higher(10000, 15000) = 15,000
    col 13 (total deductions)    = 7 + 12(=0) = 15,000
    col 14 (balance/gain)        = 6 - 13 = 20,000 - 15,000 = 5,000

  AE row (INE002B02044, bought 2021 -- post-cutoff, no grandfathering):
    quantity 200, buy price 50/unit, sold at 80/unit.
    cost = 10,000, proceeds = 16,000, gain = 6,000 -- consolidated, not scrip-wise.

  Combined: total_ltcg = 5,000 + 6,000 = 11,000, under the 125,000 exemption, so the
  whole amount is exempt and taxable_ltcg is 0.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.engine.schedule_112a import (
    CONSOLIDATED_AE_ISIN,
    CONSOLIDATED_AE_NAME,
    SECTION_112A_EXEMPTION,
    build_schedule_112a,
)
from app.engine.types import Realised, Term

BE_ISIN = "INE001A01036"
AE_ISIN = "INE002B02044"
SELL_DATE = date(2025, 6, 1)


def _realised(
    isin: str,
    quantity: str,
    cost: str,
    proceeds: str,
    open_date: date,
    sell_date: date = SELL_DATE,
    cost_stt: str = "0",
    proceeds_stt: str = "0",
) -> Realised:
    q, c, p = Decimal(quantity), Decimal(cost), Decimal(proceeds)
    return Realised(
        quantity=q,
        proceeds=p,
        cost=c,
        gain=p - c,
        term=Term.LONG,
        isin=isin,
        sell_date=sell_date,
        holding_days=(sell_date - open_date).days,
        cost_stt=Decimal(cost_stt),
        proceeds_stt=Decimal(proceeds_stt),
    )


def _be_realised() -> Realised:
    # 100 units, bought 2016-03-01 @ 100/unit -> cost 10,000; sold @ 200/unit -> proceeds 20,000.
    return _realised(BE_ISIN, "100", "10000", "20000", open_date=date(2016, 3, 1))


def _ae_realised() -> Realised:
    # 200 units, bought 2021-04-01 @ 50/unit -> cost 10,000; sold @ 80/unit -> proceeds 16,000.
    return _realised(AE_ISIN, "200", "10000", "16000", open_date=date(2021, 4, 1))


def test_be_row_applies_grandfathering_floor_via_session_3() -> None:
    report = build_schedule_112a(
        ltcg_realised=[_be_realised()],
        fmv_31jan2018={BE_ISIN: Decimal("150")},
        scrip_names={BE_ISIN: "ORIGINAL CO LTD"},
    )
    assert len(report.rows) == 1
    row = report.rows[0]

    assert row.acquired_on_or_before_cutoff is True
    assert row.isin == BE_ISIN
    assert row.scrip_name == "ORIGINAL CO LTD"
    assert row.quantity == Decimal("100")
    assert row.sale_price_per_unit == Decimal("200")
    assert row.full_value_of_consideration == Decimal("20000")  # col 6
    assert row.cost_of_acquisition == Decimal("10000")  # col 8
    assert row.fmv_per_unit_31jan2018 == Decimal("150")  # col 10
    assert row.total_fmv_31jan2018 == Decimal("15000")  # col 11
    assert row.grandfathering_floor == Decimal("15000")  # col 9 = lower(11, 6)
    assert row.cost_of_acquisition_without_indexation == Decimal("15000")  # col 7 = higher(8, 9)
    assert row.expenditure_on_transfer == Decimal("0")  # col 12
    assert row.total_deductions == Decimal("15000")  # col 13 = 7 + 12
    assert row.balance == Decimal("5000")  # col 14 = 6 - 13


def test_stt_is_excluded_from_cost_of_acquisition_and_consideration() -> None:
    """STT baked into `cost`/`proceeds` (Phase 1's real-cash figures) must not reach
    Schedule 112A -- Income Tax Act Section 48. Buy-side STT 100 and sell-side STT 200
    are layered on top of _be_realised()'s own numbers; once excluded via
    app.engine.realised.tax_cost/tax_proceeds, every reported column must come out
    identical to _be_realised()'s own (STT-free) test above."""
    with_stt = _realised(
        BE_ISIN, "100", "10100", "19800", open_date=date(2016, 3, 1),
        cost_stt="100", proceeds_stt="200",
    )
    report = build_schedule_112a(
        ltcg_realised=[with_stt],
        fmv_31jan2018={BE_ISIN: Decimal("150")},
        scrip_names={BE_ISIN: "ORIGINAL CO LTD"},
    )
    row = report.rows[0]
    assert row.sale_price_per_unit == Decimal("200")
    assert row.full_value_of_consideration == Decimal("20000")  # col 6, sell-side STT added back
    assert row.cost_of_acquisition == Decimal("10000")  # col 8, buy-side STT excluded
    assert row.cost_of_acquisition_without_indexation == Decimal("15000")  # col 7 = higher(8, 9)
    assert row.balance == Decimal("5000")  # col 14 -- identical to _be_realised()'s own figure


def test_ae_row_is_consolidated_not_scrip_wise() -> None:
    report = build_schedule_112a(
        ltcg_realised=[_ae_realised()],
        fmv_31jan2018={},
        scrip_names={},
    )
    assert len(report.rows) == 1
    row = report.rows[0]

    assert row.acquired_on_or_before_cutoff is False
    assert row.isin == CONSOLIDATED_AE_ISIN
    assert row.scrip_name == CONSOLIDATED_AE_NAME
    assert row.quantity is None
    assert row.sale_price_per_unit is None
    assert row.grandfathering_floor is None
    assert row.fmv_per_unit_31jan2018 is None
    assert row.full_value_of_consideration == Decimal("16000")
    assert row.cost_of_acquisition_without_indexation == Decimal("10000")
    assert row.balance == Decimal("6000")


def test_multiple_ae_lots_merge_into_one_consolidated_row() -> None:
    """Two different ISINs, both post-cutoff -- CBDT's instructions want ONE row, not
    one per ISIN, since a real ISIN/name is never reported for 'AE' entries."""
    second_ae = _realised("INE003C03052", "50", "5000", "6000", open_date=date(2022, 1, 1))
    report = build_schedule_112a(
        ltcg_realised=[_ae_realised(), second_ae],
        fmv_31jan2018={},
        scrip_names={},
    )
    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.full_value_of_consideration == Decimal("16000") + Decimal("6000")
    assert row.balance == Decimal("6000") + Decimal("1000")


def test_total_ltcg_and_exemption_below_threshold_leaves_nothing_taxable() -> None:
    report = build_schedule_112a(
        ltcg_realised=[_be_realised(), _ae_realised()],
        fmv_31jan2018={BE_ISIN: Decimal("150")},
        scrip_names={BE_ISIN: "ORIGINAL CO LTD"},
    )
    assert report.total_ltcg == Decimal("11000")
    assert report.exemption_applied == Decimal("11000")
    assert report.taxable_ltcg == Decimal("0")


def test_total_ltcg_above_threshold_taxes_only_the_excess() -> None:
    """Scale the BE lot up to 3,000 units (same per-unit economics: gain/unit = 50) so
    its row alone contributes 150,000 -- combined with the AE row's 6,000, total_ltcg
    is 156,000, comfortably past the 125,000 exemption. Exemption is capped at the
    threshold itself; taxable_ltcg is exactly the excess."""
    big_be = _realised(BE_ISIN, "3000", "300000", "600000", open_date=date(2016, 3, 1))
    report = build_schedule_112a(
        ltcg_realised=[big_be, _ae_realised()],
        fmv_31jan2018={BE_ISIN: Decimal("150")},
        scrip_names={BE_ISIN: "ORIGINAL CO LTD"},
    )
    assert report.total_ltcg == Decimal("156000")
    assert report.exemption_applied == SECTION_112A_EXEMPTION
    assert report.taxable_ltcg == Decimal("31000")


def test_be_lot_with_no_fmv_sourced_falls_back_to_actual_cost() -> None:
    """No fmv_31jan2018 entry for the ISIN -- mirrors grandfathering.py's own
    'most lots won't have one' fallback: no grandfathering applied, col 7 = col 8,
    and the FMV-derived columns (9, 10, 11) stay None rather than guessed at 0."""
    report = build_schedule_112a(
        ltcg_realised=[_be_realised()],
        fmv_31jan2018={},
        scrip_names={BE_ISIN: "ORIGINAL CO LTD"},
    )
    row = report.rows[0]
    assert row.fmv_per_unit_31jan2018 is None
    assert row.total_fmv_31jan2018 is None
    assert row.grandfathering_floor is None
    assert row.cost_of_acquisition_without_indexation == row.cost_of_acquisition == Decimal("10000")
    assert row.balance == Decimal("10000")  # 20,000 - 10,000, no grandfathering benefit


def test_boundary_open_date_31_jan_2018_is_be_1_feb_2018_is_ae() -> None:
    """Exactly the grandfathering cutoff, reused unmodified from app.engine.grandfathering
    -- 31 Jan 2018 still qualifies as 'BE', 1 Feb 2018 is the first 'AE' day."""
    day_before = _realised(BE_ISIN, "10", "1000", "2000", open_date=date(2018, 1, 31))
    cutoff_day = _realised(BE_ISIN, "10", "1000", "2000", open_date=date(2018, 2, 1))

    be_report = build_schedule_112a(
        ltcg_realised=[day_before], fmv_31jan2018={}, scrip_names={BE_ISIN: "X"}
    )
    ae_report = build_schedule_112a(ltcg_realised=[cutoff_day], fmv_31jan2018={}, scrip_names={})

    assert be_report.rows[0].acquired_on_or_before_cutoff is True
    assert ae_report.rows[0].acquired_on_or_before_cutoff is False
    assert ae_report.rows[0].isin == CONSOLIDATED_AE_ISIN


def test_short_term_lot_raises_instead_of_being_silently_included() -> None:
    short = Realised(
        quantity=Decimal("10"),
        proceeds=Decimal("2000"),
        cost=Decimal("1000"),
        gain=Decimal("1000"),
        term=Term.SHORT,
        isin=AE_ISIN,
        sell_date=SELL_DATE,
        holding_days=100,
    )
    with pytest.raises(ValueError, match="LTCG-classified"):
        build_schedule_112a(ltcg_realised=[short], fmv_31jan2018={}, scrip_names={})


def test_be_lot_missing_scrip_name_raises() -> None:
    with pytest.raises(ValueError, match=BE_ISIN):
        build_schedule_112a(
            ltcg_realised=[_be_realised()], fmv_31jan2018={}, scrip_names={}
        )


def test_empty_input_produces_an_empty_report() -> None:
    report = build_schedule_112a(ltcg_realised=[], fmv_31jan2018={}, scrip_names={})
    assert report.rows == []
    assert report.total_ltcg == Decimal("0")
    assert report.exemption_applied == Decimal("0")
    assert report.taxable_ltcg == Decimal("0")


def test_net_loss_gets_no_exemption_and_zero_taxable() -> None:
    """A loss must not have an 'exemption' applied to it -- exemption_applied stays 0
    and taxable_ltcg floors at 0 rather than going negative."""
    loss = _realised(AE_ISIN, "100", "20000", "12000", open_date=date(2021, 1, 1))
    report = build_schedule_112a(ltcg_realised=[loss], fmv_31jan2018={}, scrip_names={})
    assert report.total_ltcg == Decimal("-8000")
    assert report.exemption_applied == Decimal("0")
    assert report.taxable_ltcg == Decimal("0")
