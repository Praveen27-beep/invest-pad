"""A second, independent, FREE candidate source for historical BONUS/SPLIT discovery --
alongside ``app.ingest.corporate_action_feed``'s live NSE notices, and built for the gap
that feed structurally cannot close: NSE's own notices API has no historical depth
(confirmed live, 2026-09-10 -- a real ~10-month-old GUJTHEM bonus notice was absent from
a live query of NSE's own feed for a window around its own ex-date), so a freshly
imported, years-deep ledger gap can never be found there no matter how the date window
is chosen.

WHY THIS MODULE NEVER EMITS A VERIFIED CorporateAction -- same boundary
``corporate_action_feed.parse_corporate_action_feed`` holds. ``yfinance``'s
``Ticker.splits`` is demonstrably incomplete: tested against 5 real, independently
confirmed corporate actions this session, it returned GENSOL's exact ex-date and ratio,
and returned nothing at all for two others (KAMAHOLD, GUJTHEM) that definitely happened.
A candidate produced here is exactly as untrusted as one from the NSE notices parser
until ``app.db.corporate_actions.discover_from_yfinance`` runs it through the SAME
``check_sourced``/``check_price_consistency`` guards every other path already uses --
reused, never relaxed, never a second, weaker gate.

WHY EVERY CANDIDATE IS MODELLED AS BONUS, NEVER SPLIT. ``Ticker.splits`` gives one bare
number -- shares-after per share-before -- with no way to tell a real bonus issue from a
face-value split. That is the exact cross-provider ambiguity ``docs/ENGINE_SPEC.md``'s
"No ratio strings" note already describes for manually-sourced notices: KAMAHOLD's own
real action is called a "4:1 bonus" by one provider and a "5-for-1 split" by another,
same 5x effect. Modelling every candidate as BONUS (``bonus_new = round(factor) - 1``,
``bonus_for = 1``) is not a guess at which one it legally was -- it is choosing the
representation that produces the IDENTICAL ledger effect either way (see
``app.engine.holdings``'s free-share group: BONUS and a forward SPLIT both mean quantity
up, cost pool unchanged, by the same multiplier). A non-integer factor (e.g. a 3-for-2
split, factor 1.5) is deliberately not specially handled: it rounds to the nearest whole
bonus and is left for ``check_price_consistency``'s price-band guard to reject on the
next line, rather than this module silently mis-crediting a fractional share count.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

#: Recorded on every candidate this module produces, so a human reading the reference
#: table can see it did not come from a notice -- see corporate_actions.py's
#: _FEED_SOURCE_NAME for the equivalent on the NSE-notices path.
YFINANCE_SOURCE_NAME = "Yahoo Finance (yfinance)"


@dataclass(frozen=True, slots=True)
class YfinanceSplitCandidate:
    """One structured, UNVERIFIED candidate -- this module's job stops here; the real
    trust guards live in app.db.corporate_actions.discover_from_yfinance."""

    isin: str
    symbol: str
    ex_date: date
    bonus_new: int
    bonus_for: int
    source_url: str


@runtime_checkable
class YfinanceSplitSource(Protocol):
    def splits(self, symbol: str) -> dict[date, float]:
        """Every split/bonus adjustment yfinance has on file for ``symbol`` (an NSE
        ticker, no exchange suffix), keyed by ex-date, valued as the shares-after-per-
        share-before multiplier -- e.g. ``{date(2023, 10, 17): 3.0}`` for GENSOL's real
        2:1 bonus (confirmed live, matches this system's own on-file record exactly)."""
        ...


class YfinanceSource:
    """The real ``yfinance`` library, kept behind ``YfinanceSplitSource`` for the same
    reason ``CorporateActionFeedSource`` wraps the NSE notices fetch: a test can inject
    a fake with no real network call and no dependency on Yahoo's own data still saying
    the same thing tomorrow."""

    def splits(self, symbol: str) -> dict[date, float]:
        import yfinance  # imported here, not at module load, so this stays optional

        series = yfinance.Ticker(f"{symbol}.NS").splits
        return {timestamp.date(): float(factor) for timestamp, factor in series.items()}


def discover_candidates(
    source: YfinanceSplitSource, isin: str, symbol: str
) -> list[YfinanceSplitCandidate]:
    """Every split/bonus ``source`` has on file for ``symbol``, as unverified candidates
    for ``isin``. A factor that rounds down to zero or below (a reverse split, or a
    rounding artefact of a near-1.0 factor) is not representable as a BONUS and is
    skipped -- not guessed at."""
    candidates = []
    for ex_date, factor in source.splits(symbol).items():
        bonus_new = round(factor) - 1
        if bonus_new < 1:
            continue
        candidates.append(
            YfinanceSplitCandidate(
                isin=isin,
                symbol=symbol,
                ex_date=ex_date,
                bonus_new=bonus_new,
                bonus_for=1,
                source_url=f"https://finance.yahoo.com/quote/{symbol}.NS/history",
            )
        )
    return candidates
