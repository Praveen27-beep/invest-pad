"""app/ingest/corporate_action_yfinance.py -- the second free discovery source.

Offline by construction: every test injects a fake ``YfinanceSplitSource`` rather than
calling Yahoo, both because a test must not depend on the network and because Yahoo's
own answer for a given ticker is not a fixed thing to assert against -- its
incompleteness is precisely why this source is never trusted on its own (see the
module docstring).
"""

from __future__ import annotations

from datetime import date

from app.ingest.corporate_action_yfinance import (
    YFINANCE_SOURCE_NAME,
    YfinanceSplitSource,
    discover_candidates,
)


class _FakeYfinance:
    """Same injection pattern as tests/test_db_corporate_actions.py's _FakeFeedSource."""

    def __init__(self, splits: dict[date, float]):
        self._splits = splits
        self.asked: list[str] = []

    def splits(self, symbol: str) -> dict[date, float]:
        self.asked.append(symbol)
        return self._splits


def test_a_real_gensol_split_becomes_a_candidate() -> None:
    """The real, confirmed case this source exists for: yfinance returned exactly
    ``{2023-10-17: 3.0}`` for GENSOL live, and 3.0 is the multiplier of the 2:1 bonus
    this system already had on file from an independent source."""
    source = _FakeYfinance({date(2023, 10, 17): 3.0})

    [candidate] = discover_candidates(source, "INE06H201014", "GENSOL")

    assert candidate.ex_date == date(2023, 10, 17)
    assert candidate.bonus_new == 2
    assert candidate.bonus_for == 1
    assert candidate.isin == "INE06H201014"
    assert "GENSOL" in candidate.source_url


def test_the_candidates_multiplier_matches_yfinances_factor() -> None:
    """bonus_new/bonus_for is only a representation choice -- what must survive it is
    the multiplier, since that is what actually credits shares in the ledger."""
    from app.engine.corporate_actions import CorpActionType, CorporateAction

    source = _FakeYfinance({date(2023, 10, 17): 3.0})
    [candidate] = discover_candidates(source, "INE06H201014", "GENSOL")

    action = CorporateAction(
        isin=candidate.isin, action_type=CorpActionType.BONUS, ex_date=candidate.ex_date,
        bonus_new=candidate.bonus_new, bonus_for=candidate.bonus_for,
        source=YFINANCE_SOURCE_NAME, source_url=candidate.source_url,
    )
    assert action.multiplier() == 3


def test_a_reverse_split_is_skipped_not_guessed_at() -> None:
    """A factor below 1 is a consolidation -- app.engine.types' free-share group is
    additive-only and cannot represent it (see 023_corporate_actions.sql's CONSOLIDATION
    note). Skipped, never rounded into a bogus bonus."""
    source = _FakeYfinance({date(2024, 3, 1): 0.5})
    assert discover_candidates(source, "INE153T01027", "BLS") == []


def test_an_empty_history_produces_nothing() -> None:
    """The common case for the names Yahoo does not cover -- KAMAHOLD and GUJTHEM both
    came back empty live despite real, confirmed corporate actions. Not an error."""
    assert discover_candidates(_FakeYfinance({}), "INE411F01010", "KAMAHOLD") == []


def test_the_nse_suffix_is_added_by_the_real_source_not_the_caller() -> None:
    source = _FakeYfinance({})
    discover_candidates(source, "INE153T01027", "BLS")
    assert source.asked == ["BLS"], "the .NS suffix belongs to YfinanceSource.splits"


def test_the_real_source_satisfies_the_protocol() -> None:
    from app.ingest.corporate_action_yfinance import YfinanceSource

    assert isinstance(YfinanceSource(), YfinanceSplitSource)
