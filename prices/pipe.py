"""The price pipe: fetch both exchanges, merge, report.

A separate pipe from ingestion, on a separate schedule. On a day with no trades the price
job still runs and the dashboard still moves; on a day with no prices, ingestion is
unaffected. Neither blocks the other, which is why they are not the same code path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from prices.alerts import LoggingNotifier, Notifier
from prices.sources import FetchFailed, NotPublished, bse_source, nse_source
from prices.udiff import BhavcopyFormatError, BhavcopyRow, parse

#: DATA_MODEL: NSE wins on conflict, for deeper liquidity. Order matters here and nowhere
#: else -- the first source to supply an ISIN is the one whose close is kept.
SOURCE_PRIORITY = ("NSE", "BSE")

SOURCE_LABEL = {"NSE": "NSE_BHAVCOPY", "BSE": "BSE_BHAVCOPY"}


@dataclass(frozen=True, slots=True)
class MergedPrice:
    isin: str
    price_date: date
    close: Decimal
    source: str
    also_quoted_by: tuple[str, ...] = ()


@dataclass
class PipeResult:
    price_date: date
    prices: list[MergedPrice] = field(default_factory=list)
    fetched: dict[str, int] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)
    not_published: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        """A run is a success only if BOTH exchanges answered.

        Deliberately strict. One feed alone still produces prices for most holdings, which
        is exactly what makes a half-failure dangerous: it looks fine until the one
        security that only lists on the missing exchange is valued at nothing.
        """
        return not self.failures

    @property
    def only_one_exchange(self) -> bool:
        return len(self.fetched) == 1 and bool(self.failures)


def merge(rows_by_exchange: dict[str, list[BhavcopyRow]]) -> list[MergedPrice]:
    """Merge on ISIN. NSE wins where both quote; a single-feed ISIN is used as-is.

    That last clause is the entire reason both exchanges are fetched. In this portfolio
    KALYANI-M (INE0N6U01018) appears only on BSE and KDL-SM (INE0O4R01018) only on NSE, so
    either single-exchange pipe loses a real holding -- a different one each way.
    """
    merged: dict[str, MergedPrice] = {}
    for exchange in SOURCE_PRIORITY:
        for row in rows_by_exchange.get(exchange, []):
            existing = merged.get(row.isin)
            if existing is None:
                merged[row.isin] = MergedPrice(
                    isin=row.isin, price_date=row.price_date, close=row.close,
                    source=SOURCE_LABEL.get(exchange, exchange),
                )
            else:
                # Kept so "which feed did this number come from?" stays answerable.
                merged[row.isin] = MergedPrice(
                    isin=existing.isin, price_date=existing.price_date,
                    close=existing.close, source=existing.source,
                    also_quoted_by=(*existing.also_quoted_by, exchange),
                )
    return sorted(merged.values(), key=lambda p: p.isin)


def fetch_day(
    on: date,
    sources: list[Any] | None = None,
    notifier: Notifier | None = None,
) -> PipeResult:
    """Fetch both exchanges for one date and merge.

    A missing file (weekend, holiday) is recorded and NOT alerted. A fetch that should have
    worked and did not IS alerted, on every failure path, without exception.
    """
    sources = sources if sources is not None else [nse_source(), bse_source()]
    notifier = notifier or LoggingNotifier()

    result = PipeResult(price_date=on)
    rows_by_exchange: dict[str, list[BhavcopyRow]] = {}

    for source in sources:
        try:
            rows = parse(source.fetch(on), source.exchange)
        except NotPublished:
            result.not_published.append(source.exchange)
            continue
        except (FetchFailed, BhavcopyFormatError) as exc:
            result.failures[source.exchange] = str(exc)
            notifier.notify(
                subject=f"{source.exchange} bhavcopy unavailable for {on}",
                detail=str(exc),
                context={"exchange": source.exchange, "date": on.isoformat()},
            )
            continue
        rows_by_exchange[source.exchange] = rows
        result.fetched[source.exchange] = len(rows)

    result.prices = merge(rows_by_exchange)

    if result.only_one_exchange:
        notifier.notify(
            subject=f"Only one exchange answered for {on}",
            detail=(
                "Prices were stored from a single feed. Any holding listed solely on the "
                "missing exchange has NO price today and will raise rather than be valued."
            ),
            context={"fetched": result.fetched, "failed": list(result.failures)},
        )
    return result


def trading_days(start: date, end: date) -> list[date]:
    """Weekdays in range. Exchange holidays still 404 and are handled as NotPublished.

    Not a holiday calendar: one would need maintaining every year, and getting it wrong
    means either missing a real trading day or alerting on a real holiday. Letting the
    exchange's own 404 be the answer is self-maintaining.
    """
    days, cursor = [], start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days
