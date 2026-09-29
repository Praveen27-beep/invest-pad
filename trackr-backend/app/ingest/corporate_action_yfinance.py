"""A second, independent, FREE candidate source for historical BONUS/SPLIT discovery --
alongside ``app.ingest.corporate_action_feed``'s live NSE notices.

CORRECTED 2026-09-26. This module previously claimed NSE's notices API "has no historical
depth", generalised from one observation on 2026-09-10: a GUJTHEM notice absent from a
live query around its own ex-date. That generalisation is **false**, and the observation
had a different cause.

Re-probed live by sweeping ``nse_corporate_action_feed()`` from 2022-10-01 to 2026-09-25
in 60-day chunks: zero fetch errors, real rows throughout, including GENSOL's
``BONUS 2:1 ex 2023-10-17`` -- a notice nearly three years old. NSE's API serves
arbitrary historical windows; the real gap was that ``refresh_corporate_action_feed``
had only two callers and both passed a 2-day window. That is now closed by
``app.db.reference_sync.schedule``, which enqueues one month per task from an account's
earliest ``txn_date`` to today.

GUJTHEM was absent for a reason that has nothing to do with date depth: it is a **BSE**
scrip, so NSE never carried that event at all. The same sweep returned only dividends --
no bonus/split -- for GUJTHEM and KAMAHOLD across the whole range, and
``app.prices.sources``' own comment notes BSE's legacy archive "is the only place
GUJTHEM's (BSE scrip 506879) split evidence exists at all". The uncovered gap is an
EXCHANGE one, not a temporal one.

This module remains useful as an independent second opinion on NSE-listed securities,
and its untrusted-candidate posture below is unchanged. It is not, however, the answer to
BSE-only securities -- that needs a BSE source.

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
from decimal import Decimal
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

    def dividends(self, symbol: str) -> dict[date, float]:
        """Satisfies ``YfinanceDividendSource`` as well, so one injected fake can stand in
        for both in a test exactly as one real ``Ticker`` serves both here."""
        import yfinance  # imported here, not at module load, so this stays optional

        series = yfinance.Ticker(f"{symbol}.NS").dividends
        return {timestamp.date(): float(amount) for timestamp, amount in series.items()}


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


# ===========================================================================
# DIVIDENDS -- the historic-depth source, and the only one there is.
#
# ``Ticker.dividends`` is the parallel to ``Ticker.splits`` above and exists for the same
# structural reason: NSE's own notices API has no historical depth, so a freshly imported
# ledger going back years can never have its dividends discovered there no matter how the
# date window is chosen. This is the only free source with that depth.
#
# WHAT IT CARRIES, AND WHAT IT THEREFORE CANNOT SAY. An ex-date and an amount per share.
# No record date, no payment date, no kind (interim/final/special), no currency marker,
# and above all NO EVIDENCE OF PAYMENT TO ANY PARTICULAR HOLDER. Every candidate from here
# is a DECLARATION and nothing more; the distance from there to "this investor received
# this cash" is the whole subject of migration 029's header and docs/INGESTION.md's
# Adapter 6.
#
# WHY EVERY CANDIDATE IS UNSPECIFIED. The kind is genuinely absent from the data rather
# than merely hard to parse, so inferring it -- from the month, from a position in the
# year, from the size relative to previous payouts -- would be exactly the invention
# CLAUDE.md forbids. UNSPECIFIED is the honest value, and
# ``app.db.dividend_events.match_unspecified`` is what reconciles such a candidate against
# a classified NSE notice for the same ex-date instead of duplicating it.
#
# THE ADJUSTMENT TRAP, and why this asks for actions rather than the plain series. Yahoo
# serves dividend amounts SPLIT-ADJUSTED by default in some views: a Rs 10 dividend
# declared before a 1:10 split can come back as Rs 1, silently, with no marker. That is a
# 10x error indistinguishable from a real small dividend. It is also the same class of
# hazard as the split-window guard in the projection path -- an amount and a quantity on
# different bases -- and neither this module nor the caller can detect it from one number
# in isolation. What defends against it here is CROSS-SOURCING: the NSE notice carries the
# as-declared amount, and a disagreement lands the event in DISPUTED rather than being
# averaged or preferred away. A dividend seen ONLY by this source stays DRAFT and is never
# projected from, which is the fail-closed answer to a hazard that cannot be detected
# locally.
# ===========================================================================


@dataclass(frozen=True, slots=True)
class YfinanceDividendCandidate:
    """One declared dividend, UNVERIFIED -- this module's boundary, same as its split twin.

    ``kind`` is deliberately absent rather than defaulted here: the caller supplies
    ``UNSPECIFIED`` when it builds a ``DividendEvent``, so nothing in this module has to
    import an engine enum to say "the source did not tell me".
    """

    isin: str
    symbol: str
    ex_date: date
    amount_per_share: Decimal
    source_url: str


@runtime_checkable
class YfinanceDividendSource(Protocol):
    def dividends(self, symbol: str) -> dict[date, float]:
        """Every dividend yfinance has on file for ``symbol`` (an NSE ticker, no exchange
        suffix), keyed by ex-date, valued as the amount per share in rupees."""
        ...


def discover_dividend_candidates(
    source: YfinanceDividendSource, isin: str, symbol: str
) -> list[YfinanceDividendCandidate]:
    """Every dividend ``source`` has on file for ``symbol``, as unverified candidates.

    A non-positive amount is skipped rather than recorded: Yahoo occasionally carries a
    zero row for a cancelled or restated declaration, and a zero dividend is not a
    dividend. It is skipped silently for the same reason the split path skips an
    unrepresentable factor -- no candidate beats a wrong one.

    THE FLOAT BOUNDARY IS HERE, DELIBERATELY AND ONLY HERE. ``yfinance`` returns floats;
    this system's engine may not contain one (``make lint`` fails the build over it). The
    conversion goes through ``str`` rather than ``Decimal(float)`` because the latter
    preserves the binary representation error -- ``Decimal(1.1)`` is
    ``1.100000000000000088817841970012523233890533447265625``, which would then be
    compared for exact equality against the NSE notice's clean ``1.1`` during
    corroboration and would never match, silently turning every cross-source agreement
    into a DISPUTED conflict. Quantising to paise afterwards is what makes the two
    sources' readings comparable at all.
    """
    candidates = []
    for ex_date, amount in source.dividends(symbol).items():
        if amount is None or amount <= 0:
            continue
        as_decimal = Decimal(str(amount)).quantize(Decimal("0.000001"))
        if as_decimal <= 0:
            continue
        candidates.append(
            YfinanceDividendCandidate(
                isin=isin,
                symbol=symbol,
                ex_date=ex_date,
                amount_per_share=as_decimal,
                source_url=f"https://finance.yahoo.com/quote/{symbol}.NS/history",
            )
        )
    return candidates
