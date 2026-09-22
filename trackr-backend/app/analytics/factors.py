"""Cross-sectional factor scores.

THE ONE RULE THAT MAKES THESE MEAN ANYTHING: a factor score is a PERCENTILE, and a
percentile without a stated population is a decoration. "Momentum 66/100" says nothing
until you know 66th out of what. Every score this module produces carries the universe it
was ranked against, and the caller puts that on screen next to the number.

Ranking a portfolio against only its own holdings is the specific failure this guards
against -- with fifteen positions every percentile is an artefact of the fifteen, and the
top holding is always in the 100th percentile of something.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analytics.series import TRADING_DAYS, daily_returns, mean, stdev

#: A factor needs at least this many ranked peers before a percentile is worth showing.
MIN_UNIVERSE = 8


@dataclass(frozen=True, slots=True)
class FactorScore:
    score: float | None
    universe: str
    universe_size: int
    #: Share of portfolio WEIGHT that had the inputs this factor needs. A score computed
    #: over 40% of the book is a different claim from one computed over all of it.
    coverage_pct: float


def percentile_rank(values: dict[str, float]) -> dict[str, float]:
    """Cross-sectional rank, 0-100, higher value = higher score.

    Callers pass inputs already oriented so that more is better -- negated leverage,
    negated volatility. Doing the orientation at the call site keeps this function from
    needing to know what any particular factor means.
    """
    clean = {k: v for k, v in values.items() if v is not None}
    if len(clean) < 2:
        return {}
    ordered = sorted(clean.items(), key=lambda kv: kv[1])
    n = len(ordered)
    return {k: round(100.0 * i / (n - 1), 1) for i, (k, _) in enumerate(ordered)}


def zscore(values: dict[str, float]) -> dict[str, float]:
    clean = {k: v for k, v in values.items() if v is not None}
    if len(clean) < 2:
        return dict.fromkeys(clean, 0.0)
    mu = mean(list(clean.values()))
    sd = stdev(list(clean.values())) or 1.0
    return {k: (v - mu) / sd for k, v in clean.items()}


def momentum_12_1(values: list[float]) -> float | None:
    """The standard 12-1 construction: twelve-month return SKIPPING the most recent month.

    The skip is not a refinement, it is the construction. Including the latest month mixes
    short-term reversal into a momentum signal and measures roughly the opposite thing at
    the margin.
    """
    if len(values) < TRADING_DAYS + 1:
        return None
    start = values[-(TRADING_DAYS + 1)]
    end = values[-22] if len(values) > 22 else values[-1]
    return (end / start - 1.0) if start > 0 else None


def risk_adjusted_momentum(values: list[float]) -> float | None:
    raw = momentum_12_1(values)
    if raw is None:
        return None
    sd = stdev(daily_returns(values))
    if not sd:
        return None
    return raw / sd


def combine(*maps: dict[str, float]) -> dict[str, float]:
    """Equal-weighted mean of whichever component z-scores a security actually has.

    Averaging what is present rather than requiring all of them is deliberate: demanding
    every input would drop a company for one missing ratio, and a quality score from two
    of three measures is far more useful than no score at all. How much was available is
    reported as coverage.
    """
    out: dict[str, float] = {}
    keys = {k for m in maps for k in m}
    for key in keys:
        parts = [m[key] for m in maps if key in m]
        if parts:
            out[key] = sum(parts) / len(parts)
    return out


def score_portfolio(
    holding_scores: dict[str, float],
    weights: dict[str, float],
    universe: str,
    universe_size: int,
) -> FactorScore:
    """Weight-weighted mean of the holdings that have a score.

    The denominator is the weight that HAD a score, not total weight -- otherwise a book
    where half the holdings are unscored silently reads as scoring zero on that half.
    """
    numerator = sum(weights.get(i, 0.0) * s for i, s in holding_scores.items() if i in weights)
    denominator = sum(weights.get(i, 0.0) for i in holding_scores if i in weights)
    total_weight = sum(weights.values()) or 1.0
    if denominator <= 0 or universe_size < MIN_UNIVERSE:
        return FactorScore(None, universe, universe_size, 0.0)
    return FactorScore(
        score=round(numerator / denominator, 1),
        universe=universe,
        universe_size=universe_size,
        coverage_pct=round(100.0 * denominator / total_weight, 1),
    )
