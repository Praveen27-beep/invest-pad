"""The golden fixture: a real portfolio with independently verified answers.

Provenance matters here. These numbers are not invented test data -- they came from a
working Excel implementation covering real trades (Oct-2022 to Aug-2026), reconciled
against the broker's own holdings export and against two consecutive CDSL CAS statements,
then verified a second time in Python.

THIS IS THE ACCEPTANCE TEST. Nothing above Session 4 should be built on a red result.

NOT IN THE REPOSITORY. ``fixtures/golden_portfolio.json`` is one investor's actual trading
history -- every trade, date, quantity and price they have made -- along with their demat
identifiers. It belongs in object storage with a retention policy, not in git history where
it cannot be erased on request. The whole module skips without it, the same way the
tradebook and contract-note tests skip without their source documents.

To run these, put the file at ``fixtures/golden_portfolio.json`` locally. It is gitignored.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from app.engine.holdings import compute_holdings
from app.engine.valuation import value_holdings
from app.engine.xirr import compute_xirr, compute_xirr_holdings

from tests.conftest import FIXTURES, dec, load_json, to_date, to_transaction

GOLDEN_PATH = FIXTURES / "golden_portfolio.json"

pytestmark = pytest.mark.skipif(
    not GOLDEN_PATH.exists(),
    reason="golden_portfolio.json is local-only (real client data); see the module docstring",
)

GOLDEN: dict[str, Any] = load_json(GOLDEN_PATH) if GOLDEN_PATH.exists() else {"expected": {}}
EXPECTED: dict[str, Any] = GOLDEN["expected"]


@pytest.fixture(scope="module")
def transactions() -> list[Any]:
    return [to_transaction(r) for r in GOLDEN["transactions"]]


@pytest.fixture(scope="module")
def prices() -> dict[str, Decimal]:
    return {k: dec(v) for k, v in GOLDEN["prices"].items()}


def test_fixture_shape() -> None:
    """The fixture is internally consistent before anything is asserted about the engine.

    Counts are read from the fixture rather than hardcoded: the ledger is anchored at
    31-03-2025 for ISINs whose pre-2025 corporate-action history could not be recovered
    (see the `_ledger_anchor` key), so the transaction count is a property of the fixture,
    not a constant.
    """
    assert len(GOLDEN["transactions"]) == EXPECTED["transaction_count"]
    assert len({t["isin"] for t in GOLDEN["transactions"]}) == EXPECTED["securities_traded"]


def test_ledger_anchor_is_declared() -> None:
    """An anchored ledger must say so, in the fixture itself.

    xirr_all over this ledger is a period return bounded at the anchor date, not a
    since-inception return. Silence here is how that distinction gets lost.
    """
    anchor = GOLDEN["_ledger_anchor"]
    assert anchor["anchor_date"] == "2025-03-31"
    assert anchor["anchored_isins"]
    reconciling = [
        t for t in GOLDEN["transactions"] if str(t.get("source_ref", "")).startswith("CAS-ANCHOR")
    ]
    assert len(reconciling) == anchor["reconciling_entries_added"]
    for row in reconciling:
        assert "cost_estimated" in row["raw_payload"]


PAISE = Decimal("0.01")


def test_invested_is_the_weighted_average_total(transactions: list[Any]) -> None:
    """The headline. Weighted average, as ENGINE_SPEC section 1 displays it.

    This is NOT the broker's number, and that is correct rather than a defect -- see
    test_fifo_reproduces_the_broker_statement below.
    """
    holdings = compute_holdings(transactions, to_date(GOLDEN["as_of"]))
    total = sum((h.invested for h in holdings), Decimal("0")).quantize(PAISE)
    assert abs(total - dec(EXPECTED["invested"])) <= PAISE


def test_fifo_reproduces_the_broker_statement(transactions: list[Any]) -> None:
    """The other convention, against the real Zerodha holdings statement.

    This is what resolved the KDL-SM mystery: the 8144.32 "discrepancy" was never missing
    data, missing charges, or a corporate action. It was FIFO versus weighted average.
    Independently corroborated -- FIFO cost-of-goods-sold on the 1650 KDL shares sold comes
    to 280582.50, exactly the "Buy Value" the FY2026-27 P&L reports for those sales.
    """
    holdings = compute_holdings(transactions, to_date(GOLDEN["as_of"]))
    broker = {h["isin"]: dec(h["invested"]) for h in EXPECTED["holdings"]}

    for isin in ("INE0O4R01018", "INE0Q9301021", "INE933S01016"):
        holding = next(h for h in holdings if h.isin == isin)
        assert holding.fifo_cost.quantize(PAISE) == broker[isin], (
            f"{isin}: FIFO must reproduce the broker statement exactly"
        )

    total = sum((h.fifo_cost for h in holdings), Decimal("0")).quantize(PAISE)
    assert total == dec(EXPECTED["invested_broker_fifo"]), (
        "the FIFO total must reproduce the broker holdings statement exactly"
    )


def test_the_conventions_diverge_only_on_a_partly_sold_position(
    transactions: list[Any],
) -> None:
    """Which is exactly why this stayed invisible for several sessions.

    Across the whole portfolio the two conventions disagree on ONE holding. A position
    that was never partly sold has the same cost either way, so 19 of 20 matched and the
    gap looked like a bug in one security rather than a difference in method.
    """
    holdings = compute_holdings(transactions, to_date(GOLDEN["as_of"]))
    diverged = {
        h.isin for h in holdings if h.fifo_cost.quantize(PAISE) != h.invested.quantize(PAISE)
    }
    assert diverged == {"INE0O4R01018"}, "KDL-SM, and nothing else"

    kdl = next(h for h in holdings if h.isin == "INE0O4R01018")
    gap = kdl.fifo_cost.quantize(PAISE) - kdl.invested.quantize(PAISE)
    assert gap == Decimal("8144.32"), "the gap that took three sessions to explain"
    assert kdl.avg_cost < kdl.fifo_avg, "its earliest lots were the cheapest"


def test_both_conventions_are_always_populated(transactions: list[Any]) -> None:
    """Neither is optional. A holding carrying only one of them cannot be reconciled."""
    holdings = compute_holdings(transactions, to_date(GOLDEN["as_of"]))
    assert all(h.fifo_cost is not None and h.fifo_avg is not None for h in holdings)
    assert all(h.invested is not None and h.avg_cost is not None for h in holdings)


def test_no_synthetic_correction_rows_remain_for_kdl(dummy=None) -> None:
    """They papered over a convention gap, not missing data, and are gone.

    Kept as a test so nobody reintroduces one to "fix" a difference that is not an error.
    """
    corrections = [
        t for t in GOLDEN["transactions"]
        if str(t.get("source_ref", "")).startswith("COST-CORRECTION")
        and t["isin"] == "INE0O4R01018"
    ]
    assert corrections == []


def test_estimated_cost_is_flagged() -> None:
    """The doubt must be visible, not merely stored.

    An estimated cost that reaches a user unlabelled is worse than no figure at all: it
    reads as fact. Exactly the two corrected positions carry the flag, and no others.
    """
    holdings = compute_holdings(
        [to_transaction(r) for r in GOLDEN["transactions"]], to_date(GOLDEN["as_of"])
    )
    flagged = {h.isin for h in holdings if h.cost_estimated}
    assert flagged == {"INE0Q9301021"}, (
        "IGIL only. KDL-SM's flag went with its correction rows once FIFO explained it."
    )

    verified = [h for h in holdings if not h.cost_estimated]
    assert len(verified) == 19

    # LIQUIDBEES cost really is zero -- dividend units -- so it is verified, not estimated.
    liquidbees = next(h for h in holdings if h.isin == "INF732E01037")
    assert liquidbees.invested == Decimal("0")
    assert liquidbees.cost_estimated is False


def test_market_value(transactions: list[Any], prices: dict[str, Decimal]) -> None:
    """Valuation is a separate step: compute_holdings takes no prices, by design.

    Compared at paise. Carried further, the total is 1360575.41988 -- LIQUIDBEES holds
    0.012 units at 999.99 -- which is what the broker's own holdings statement also
    reports, as 1360575.4199. The fixture states the 2dp presentation of the same number.
    """
    holdings = value_holdings(compute_holdings(transactions, to_date(GOLDEN["as_of"])), prices)
    total = sum((h.market_value for h in holdings), Decimal("0")).quantize(PAISE)
    assert total == dec(EXPECTED["market_value"])


def test_securities_held(transactions: list[Any]) -> None:
    """20 of the 44 traded securities are still open. Closed positions are excluded."""
    holdings = compute_holdings(transactions, to_date(GOLDEN["as_of"]))
    assert len(holdings) == EXPECTED["securities_held"]


def test_xirr_all(transactions: list[Any], prices: dict[str, Decimal]) -> None:
    result = compute_xirr(transactions, prices, to_date(GOLDEN["as_of"]))
    assert result is not None
    tolerance = dec(EXPECTED["xirr_tolerance"])
    assert abs(Decimal(str(result)) - dec(EXPECTED["xirr_all"])) <= tolerance


def test_xirr_holdings(transactions: list[Any], prices: dict[str, Decimal]) -> None:
    result = compute_xirr_holdings(transactions, prices, to_date(GOLDEN["as_of"]))
    assert result is not None
    tolerance = dec(EXPECTED["xirr_tolerance"])
    assert abs(Decimal(str(result)) - dec(EXPECTED["xirr_holdings"])) <= tolerance


def test_both_xirrs_differ_in_the_documented_direction(
    transactions: list[Any], prices: dict[str, Decimal]
) -> None:
    """The live book is WORSE than the all-in number, and that gap is the insight.

    Sold positions outperformed retained ones here -- the opposite of the usual
    sell-the-losers bias. It is also the reason both variants must always be shown
    together: presenting either alone is a choice about which number flatters.
    """
    as_of = to_date(GOLDEN["as_of"])
    all_txns = compute_xirr(transactions, prices, as_of)
    held_only = compute_xirr_holdings(transactions, prices, as_of)
    assert held_only < all_txns
