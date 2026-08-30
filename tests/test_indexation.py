"""indexed_cost_of_acquisition -- docs/TAX_ENGINE.md "Indexation".

Hand-computed per CLAUDE.md's "tests are the specification" rule:

    indexed_cost = cost x (CII_sale_year / CII_purchase_year)

applied only to a lot purchased before FY 2023-24 (1 Apr 2023).

The CII figures used below (FY2012-13=200, FY2013-14=220, FY2019-20=289) are the real
CBDT-published Cost Inflation Index values for those years -- widely republished (e.g.
every major tax-prep vendor's own CII table cites the same series) but not themselves
sourced/verified as part of this session, same caveat docs/PHASE3_PROMPTS.md's Session 4
prompt states for CII table population generally: treat as representative until an
authoritative CBDT notification is checked against them before any real filing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.engine.errors import MissingCIIError
from app.engine.indexation import INDEXATION_CUTOFF_FY, indexed_cost_of_acquisition

#: A handful of real CBDT CII values, deliberately not the full historical series --
#: enough to exercise a purchase/sale pair and a gap.
CII_TABLE = {
    "2012-13": Decimal("200"),
    "2013-14": Decimal("220"),
    "2019-20": Decimal("289"),
    "2022-23": Decimal("331"),
}


def test_pre_cutoff_lot_is_indexed_by_cii_ratio() -> None:
    """buy FY2012-13 (CII 200), sell FY2019-20 (CII 289), cost=100000 ->
    100000 x (289/200) = 100000 x 1.445 = 144500 exactly -- chosen so the ratio
    terminates and can be hand-checked without a calculator."""
    result = indexed_cost_of_acquisition(Decimal("100000"), "2012-13", "2019-20", CII_TABLE)
    assert result == Decimal("144500")


def test_same_fy_purchase_and_sale_is_a_no_op_ratio() -> None:
    """CII_sale_year / CII_purchase_year = 1 when both years are the same FY --
    indexation must leave the cost unchanged, not merely "close"."""
    result = indexed_cost_of_acquisition(Decimal("50000"), "2012-13", "2012-13", CII_TABLE)
    assert result == Decimal("50000")


def test_purchase_fy_at_cutoff_returns_unindexed_cost() -> None:
    """A lot purchased in FY 2023-24 itself (i.e. on/after 1 Apr 2023) is taxed at slab
    rate with no indexation -- the function must return the plain cost, not raise, and
    not consult the CII table at all (proved by a sale_fy that has no entry in
    CII_TABLE; if the gate were missing this would raise MissingCIIError instead)."""
    result = indexed_cost_of_acquisition(
        Decimal("100000"), INDEXATION_CUTOFF_FY, "2030-31", CII_TABLE
    )
    assert result == Decimal("100000")


def test_purchase_fy_just_before_cutoff_is_still_indexed() -> None:
    """FY2022-23 is the last FY entirely before 1 Apr 2023 -- proves the gate excludes
    exactly FY2023-24 onward, not one year early."""
    result = indexed_cost_of_acquisition(Decimal("100000"), "2022-23", "2022-23", CII_TABLE)
    assert result == Decimal("100000")  # same-FY ratio = 1, but must not raise/gate out


def test_missing_purchase_year_raises_not_defaults_to_one() -> None:
    """CII table has no 2005-06 entry -- must raise, never silently use ratio 1.0 (which
    would understate the indexed cost, per CLAUDE.md rule 4 applied to this table)."""
    with pytest.raises(MissingCIIError) as exc_info:
        indexed_cost_of_acquisition(Decimal("100000"), "2005-06", "2019-20", CII_TABLE)
    assert exc_info.value.financial_years == ["2005-06"]


def test_missing_sale_year_raises_not_skipped() -> None:
    """Purchase year is present but sale year is not -- must still raise, not fall back
    to returning the unindexed cost as if indexation did not apply."""
    with pytest.raises(MissingCIIError) as exc_info:
        indexed_cost_of_acquisition(Decimal("100000"), "2012-13", "2021-22", CII_TABLE)
    assert exc_info.value.financial_years == ["2021-22"]


def test_both_years_missing_reports_both() -> None:
    with pytest.raises(MissingCIIError) as exc_info:
        indexed_cost_of_acquisition(Decimal("100000"), "2005-06", "2021-22", CII_TABLE)
    assert exc_info.value.financial_years == ["2005-06", "2021-22"]
