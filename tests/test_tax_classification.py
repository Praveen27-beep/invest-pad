"""classify_term -- docs/TAX_ENGINE.md "Holding-period thresholds".

Hand-computed per CLAUDE.md's "tests are the specification" rule. Unlike
tests/test_lots.py's boundary test (which pins EQ's hardcoded 365-day default
inside engine/lots.py), these exercise the asset-class-aware generalisation in
engine/tax_classification.py -- the same holding_days classified differently
depending on which class's threshold is supplied is exactly what proves the
function is reading its threshold rather than hardcoding EQ's number.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.engine.errors import CapitalGainsNotApplicableError
from app.engine.tax_classification import classify_term, long_term_days_for
from app.engine.types import Realised, Term

from tests.conftest import SCHEMA, load_json

ASSET_CLASSES = load_json(SCHEMA / "asset_classes.json")["asset_classes"]


def _realised(holding_days: int, isin: str = "INE153T01027") -> Realised:
    return Realised(
        quantity=Decimal("1"),
        proceeds=Decimal("150"),
        cost=Decimal("100"),
        gain=Decimal("50"),
        term=Term.SHORT,  # placeholder from the FIFO replay; classify_term recomputes it
        isin=isin,
        holding_days=holding_days,
    )


def test_long_term_days_for_reads_the_schema_file() -> None:
    """Sanity check on the lookup itself, independent of classify_term."""
    assert long_term_days_for("EQ", ASSET_CLASSES) == 365
    assert long_term_days_for("MF_DEBT", ASSET_CLASSES) == 1095
    assert long_term_days_for("FD", ASSET_CLASSES) is None


def test_equity_boundary_365_days_is_short_366_is_long() -> None:
    """Day 365 vs day 366 for EQ -- the exact boundary ENGINE_SPEC section 3 states."""
    threshold = long_term_days_for("EQ", ASSET_CLASSES)
    assert classify_term(_realised(365), "EQ", threshold) is Term.SHORT
    assert classify_term(_realised(366), "EQ", threshold) is Term.LONG


def test_debt_mf_uses_1095_days_not_equitys_365() -> None:
    """400 days is LONG for equity but must stay SHORT for debt MF -- proves the
    function reads MF_DEBT's own threshold instead of falling back to 365."""
    threshold = long_term_days_for("MF_DEBT", ASSET_CLASSES)
    assert threshold == 1095
    assert classify_term(_realised(400), "MF_DEBT", threshold) is Term.SHORT
    assert classify_term(_realised(1096), "MF_DEBT", threshold) is Term.LONG


def test_asset_class_with_null_threshold_raises_instead_of_guessing() -> None:
    """FD's long_term_days is null -- interest income, not a capital gain. Must raise,
    never silently return SHORT or LONG."""
    threshold = long_term_days_for("FD", ASSET_CLASSES)
    assert threshold is None
    with pytest.raises(CapitalGainsNotApplicableError):
        classify_term(_realised(400), "FD", threshold)


def test_reit_threshold_is_read_from_data_not_hardcoded() -> None:
    """Budget 2024 cut REIT/InvIT from 36 months (1095 days) to 12 (365) --
    docs/TAX_ENGINE.md notes this explicitly, and schema/asset_classes.json already
    carries the post-budget value. REIT itself is out of Phase 1/2 scope and nothing
    here builds it; this only proves classify_term honours whatever long_term_days
    it is given, so a future session that hardcodes '1095 for REIT' (the pre-budget
    number) regresses this test instead of shipping silently wrong.
    """
    threshold = long_term_days_for("REIT", ASSET_CLASSES)
    assert threshold == 365

    # 400 days is long-term under the CURRENT 365-day rule, but would wrongly come
    # back SHORT under the old, pre-Budget-2024 1095-day rule -- a hardcoded 1095
    # anywhere in classify_term would flip this assertion.
    assert classify_term(_realised(400), "REIT", threshold) is Term.LONG


def test_unknown_asset_class_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        long_term_days_for("NOT_A_REAL_CODE", ASSET_CLASSES)
