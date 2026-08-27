"""build_itr_capital_gains -- docs/TAX_ENGINE.md, docs/FEATURE_BACKLOG.md Phase 3.

Hand-computed per CLAUDE.md's "tests are the specification" rule. Sl.No. labels in
comments refer to CBDT's AY 2026-27 ITR-2 Schedule CG (see
app/engine/itr_capital_gains.py's module docstring for the exact source).

Worked scenario:

  STCG u/s 111A (item A2(i)), two realised lots on the same or different ISINs,
  aggregated (unlike Schedule 112A, s.111A STCG reporting is NOT scrip-wise):
    lot 1: 50 units, cost 5,000 (100/unit), proceeds 6,500 (130/unit)
    lot 2: 30 units, cost 4,500 (150/unit), proceeds 4,200 (140/unit) -- a loss
    A2ia  (full value of consideration) = 6,500 + 4,200          = 10,700
    A2ibi (cost of acquisition)         = 5,000 + 4,500          =  9,500
    A2ibiv (total deductions)           = 9,500 + 0 + 0          =  9,500
    A2ic  (balance)                     = 10,700 - 9,500         =  1,200
    A2id  (loss disallowed 94(7)/94(8)) = 0 (not implemented, see module docstring)
    A2ie  (net STCG)                    = 1,200 + 0              =  1,200

  LTCG u/s 112A (item B3), reusing the same BE+AE scenario
  test_schedule_112a.py already hand-verifies (total_ltcg = 5,000 + 6,000 = 11,000):
    B3a (= Schedule112AReport.total_ltcg) = 11,000
    B3b (54F deduction, not implemented)  = 0
    B3c (net LTCG)                        = 11,000 - 0 = 11,000

  Total capital gains (Trackr-Plus-scoped C) = A2ie + B3c = 1,200 + 11,000 = 12,200
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.engine.itr_capital_gains import build_itr_capital_gains
from app.engine.schedule_112a import build_schedule_112a
from app.engine.types import Realised, Term

BE_ISIN = "INE001A01036"
AE_ISIN = "INE002B02044"
SELL_DATE = date(2025, 6, 1)


def _stcg_realised(
    isin: str,
    quantity: str,
    cost: str,
    proceeds: str,
    cost_stt: str = "0",
    proceeds_stt: str = "0",
) -> Realised:
    q, c, p = Decimal(quantity), Decimal(cost), Decimal(proceeds)
    return Realised(
        quantity=q,
        proceeds=p,
        cost=c,
        gain=p - c,
        term=Term.SHORT,
        isin=isin,
        sell_date=SELL_DATE,
        holding_days=90,
        cost_stt=Decimal(cost_stt),
        proceeds_stt=Decimal(proceeds_stt),
    )


def _ltcg_realised(isin: str, quantity: str, cost: str, proceeds: str, open_date: date) -> Realised:
    q, c, p = Decimal(quantity), Decimal(cost), Decimal(proceeds)
    return Realised(
        quantity=q,
        proceeds=p,
        cost=c,
        gain=p - c,
        term=Term.LONG,
        isin=isin,
        sell_date=SELL_DATE,
        holding_days=(SELL_DATE - open_date).days,
    )


def _schedule_112a_fixture():
    # Same BE/AE scenario as test_schedule_112a.py: total_ltcg == 11,000.
    be = _ltcg_realised("INE009X01011", "100", "10000", "20000", open_date=date(2016, 3, 1))
    ae = _ltcg_realised(AE_ISIN, "200", "10000", "16000", open_date=date(2021, 4, 1))
    return build_schedule_112a(
        ltcg_realised=[be, ae],
        fmv_31jan2018={"INE009X01011": Decimal("150")},
        scrip_names={"INE009X01011": "ORIGINAL CO LTD"},
    )


def test_stcg_and_ltcg_sections_hand_verified() -> None:
    stcg_lots = [
        _stcg_realised(BE_ISIN, "50", "5000", "6500"),
        _stcg_realised(BE_ISIN, "30", "4500", "4200"),
    ]
    report = build_itr_capital_gains(
        stcg_realised=stcg_lots,
        schedule_112a=_schedule_112a_fixture(),
    )

    assert report.a2i_full_value_of_consideration == Decimal("10700")
    assert report.a2i_cost_of_acquisition == Decimal("9500")
    assert report.a2i_cost_of_improvement == Decimal("0")
    assert report.a2i_expenditure_on_transfer == Decimal("0")
    assert report.a2i_total_deductions == Decimal("9500")
    assert report.a2i_balance == Decimal("1200")
    assert report.a2i_loss_disallowed_94_7_94_8 == Decimal("0")
    assert report.a2i_stcg == Decimal("1200")

    assert report.b3a_ltcg_112a == Decimal("11000")
    assert report.b3b_deduction_54f == Decimal("0")
    assert report.b3c_ltcg == Decimal("11000")

    assert report.total_capital_gains == Decimal("12200")


def test_stt_is_excluded_from_stcg_cost_and_consideration() -> None:
    """STT baked into `cost`/`proceeds` must not reach A2ia/A2ibi -- Income Tax Act
    Section 48. Lot 1 gets buy-side STT 50 and sell-side STT 65 layered on top of its
    raw cost/proceeds; once excluded via app.engine.realised.tax_cost/tax_proceeds, the
    reported STCG section must come out identical to
    test_stcg_and_ltcg_sections_hand_verified()'s own (STT-free) figures."""
    stcg_lots = [
        _stcg_realised(BE_ISIN, "50", "5050", "6435", cost_stt="50", proceeds_stt="65"),
        _stcg_realised(BE_ISIN, "30", "4500", "4200"),
    ]
    report = build_itr_capital_gains(
        stcg_realised=stcg_lots,
        schedule_112a=_schedule_112a_fixture(),
    )

    assert report.a2i_full_value_of_consideration == Decimal("10700")
    assert report.a2i_cost_of_acquisition == Decimal("9500")
    assert report.a2i_total_deductions == Decimal("9500")
    assert report.a2i_balance == Decimal("1200")
    assert report.a2i_stcg == Decimal("1200")


def test_b3a_equals_schedule_112a_total_ltcg_exactly() -> None:
    """B3a is not re-derived -- it must be the literal Schedule112AReport.total_ltcg
    the CBDT workbook's own B3a formula reads (see module docstring)."""
    schedule_112a = _schedule_112a_fixture()
    report = build_itr_capital_gains(stcg_realised=[], schedule_112a=schedule_112a)
    assert report.b3a_ltcg_112a == schedule_112a.total_ltcg


def test_empty_stcg_produces_zeroed_a2_section() -> None:
    report = build_itr_capital_gains(stcg_realised=[], schedule_112a=_schedule_112a_fixture())
    assert report.a2i_full_value_of_consideration == Decimal("0")
    assert report.a2i_stcg == Decimal("0")
    assert report.total_capital_gains == report.b3c_ltcg


def test_long_term_lot_raises_instead_of_being_silently_included() -> None:
    long_term_lot = _ltcg_realised(BE_ISIN, "10", "1000", "1500", open_date=date(2020, 1, 1))
    with pytest.raises(ValueError, match="SHORT-term"):
        build_itr_capital_gains(
            stcg_realised=[long_term_lot],
            schedule_112a=_schedule_112a_fixture(),
        )
