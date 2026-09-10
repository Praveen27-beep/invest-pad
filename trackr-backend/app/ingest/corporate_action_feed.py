"""Where automated corporate-action notices come from -- NSE's own corporate-filings API.

INTERIM SOURCE, NOT THE PERMANENT ONE -- stated once here, loudly, because this is the
one thing about this module most likely to need replacing. There is no static, published
archive file for corporate actions the way ``app.prices.sources`` has for bhavcopy
(confirmed: no ``nsearchives.nseindia.com`` equivalent exists). What works is NSE's own
interactive site API (``www.nseindia.com/api/corporates-corporateActions``), which needs
a bootstrapped session cookie and a Referer header to get past its anti-bot layer --
confirmed live, 2026-09-10. That is a materially different risk/reliability profile from
bhavcopy's own published archive: NSE's Terms of Use restrict automated collection from
the interactive site specifically. Kept behind ``CorporateActionFeedSource`` (a
``Protocol``, same shape as ``app.prices.sources.BhavcopySource``) for exactly one
reason: so a licensed vendor (e.g. Accord Fintech, a confirmed authorised NSE/BSE
reseller) can replace ``NseCorporateActionFeedSource`` later without
``app.db.corporate_actions.refresh_corporate_action_feed`` or anything downstream of it
changing at all.

WHY THIS MODULE NEVER EMITS A VERIFIED ``CorporateAction``. Parsing NSE's free-text
``subject`` field ("Bonus 1:1", "Dividend - Rs 1.50 Per Share", "Sub-Division ...") is a
best-effort regex classification, not a read of a structured, guaranteed-correct field --
see ``docs/ENGINE_SPEC.md``'s "No ratio strings" note on why this codebase never trusts
notation like this at face value. This module's job stops at producing a structured,
UNVERIFIED candidate; ``app.db.corporate_actions.refresh_corporate_action_feed`` is what
runs the actual trust guards (``app.engine.corporate_actions.screen``, in particular
``check_price_consistency`` -- the real, independent-of-this-parser corroboration) before
anything is ever marked ``VERIFIED``.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, runtime_checkable

from app.engine.corporate_actions import CorpActionType
from app.prices.sources import BROWSER_HEADERS, TIMEOUT_SECONDS, _ssl_context

#: NSE's interactive corporate-filings page -- confirmed live, 2026-09-10, that the
#: underlying API 403s without a warmed session cookie AND this exact Referer.
NSE_HOMEPAGE_URL = "https://www.nseindia.com/"
NSE_CORP_ACTIONS_URL = (
    "https://www.nseindia.com/api/corporates-corporateActions"
    "?index=equities&from_date={start:%d-%m-%Y}&to_date={end:%d-%m-%Y}"
)
NSE_REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-actions"


class CorporateActionFeedFetchFailed(Exception):
    """The request should have worked and did not -- network error, non-200, or the
    anti-bot layer blocked it even after a session warm-up. Alerts."""


class CorporateActionFeedFormatError(Exception):
    """The response parsed as JSON but is missing a field every row of this feed has
    carried so far -- the clearest signal NSE reshaped the API under us. A row this
    parser cannot classify at all (see ``parse_corporate_action_feed``) is NOT this --
    that is the expected, routine case of a notice type this parser doesn't yet cover,
    handled by simply not producing a candidate for it."""


@runtime_checkable
class CorporateActionFeedSource(Protocol):
    def fetch(self, start: date, end: date) -> bytes: ...


class NseCorporateActionFeedSource:
    """INTERIM implementation -- see module docstring. Replace this class, not its
    caller, when a licensed feed is in place."""

    def __init__(self, opener: Any = None):
        self._opener = opener or urllib.request.urlopen

    def fetch(self, start: date, end: date) -> bytes:
        ctx = _ssl_context()
        # Warm a session cookie against the homepage first -- confirmed live that the
        # API 403s a cold request even with browser headers. The cookie jar is carried
        # via a shared urllib opener with a CookieProcessor when this runs for real;
        # tests inject their own ``opener`` and skip this entirely.
        try:
            warmup = urllib.request.Request(NSE_HOMEPAGE_URL, headers=BROWSER_HEADERS)
            self._opener(warmup, timeout=TIMEOUT_SECONDS, context=ctx).close()

            request = urllib.request.Request(
                NSE_CORP_ACTIONS_URL.format(start=start, end=end),
                headers={**BROWSER_HEADERS, "Referer": NSE_REFERER, "Accept": "application/json"},
            )
            with self._opener(request, timeout=TIMEOUT_SECONDS, context=ctx) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise CorporateActionFeedFetchFailed(f"NSE corporate actions: HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CorporateActionFeedFetchFailed(
                f"NSE corporate actions: {type(exc).__name__}"
            ) from exc


def nse_corporate_action_feed(opener: Any = None) -> NseCorporateActionFeedSource:
    return NseCorporateActionFeedSource(opener)


@dataclass(frozen=True, slots=True)
class FeedRow:
    """One notice, structured but UNVERIFIED -- the boundary this module stops at.

    ``price_cum``/``price_ex`` are never populated here: NSE's corporate-actions feed
    carries no price at all. ``app.db.corporate_actions.refresh_corporate_action_feed``
    looks those up from ``app.db.prices.prices_on_date`` before this can ever become a
    ``CorporateAction``.
    """

    isin: str
    symbol: str
    action_type: CorpActionType
    ex_date: date
    bonus_new: int | None = None
    bonus_for: int | None = None
    face_value_before: Decimal | None = None
    face_value_after: Decimal | None = None
    raw_subject: str = ""


_REQUIRED_FIELDS = {"isin", "symbol", "exDate", "subject"}

#: "Bonus 1:1", "Bonus Issue 2:1", "Bonus  1 : 3" -- whitespace-tolerant, case-insensitive.
_BONUS_RE = re.compile(r"bonus\D*?(\d+)\s*:\s*(\d+)", re.IGNORECASE)

#: "Sub-Division (Split) - From Rs.10/- To Rs.2/-" and equivalent phrasings NSE uses.
#: "Rs" vs "Re" is not a typo to normalise away: Indian English grammar uses "Re." only
#: for exactly the singular unit (Re. 1/-), "Rs." for everything else (Rs. 2/-, Rs.
#: 10/-) -- confirmed live, a real and common phrasing for splits down to face value 1
#: (7 of 15 real split/bonus notices in one three-month pull), silently missed entirely
#: before this alternation was added. A false negative here is safe (the notice simply
#: never becomes a candidate, never a wrong one) but was defeating the point of
#: automating the common case.
_SPLIT_RE = re.compile(
    r"(?:sub[- ]division|stock\s*split).*?rs?e?\.?\s*(\d+(?:\.\d+)?)\D+rs?e?\.?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

#: A real, confirmed false positive from live data: "Scheme Of Arrangement - Bonus
#: Ncrps 46:1" matches ``_BONUS_RE`` on its ratio but is NOT an equity bonus -- NCRPS is
#: Non-Convertible Redeemable Preference Shares, a different instrument entirely, issued
#: under a scheme of arrangement, not a plain bonus issue. Applying its ratio to this
#: ISIN's equity quantity would be a real, quantified wrong number, not a theoretical
#: risk. Any subject containing one of these is treated as unclassifiable -- consistent
#: with the "no candidate beats a wrong candidate" rule above -- rather than trusting a
#: bare ratio match. Not exhaustive; extend this list the next time a live pull surfaces
#: another qualifier that changes what the ratio actually means.
_DISQUALIFYING_TERMS = (
    "scheme of arrangement",
    "ncrps",
    "preference share",
    "debenture",
    "warrant",
    "partly paid",
    "demerger",
    "merger",
    "amalgamation",
)


def _is_plain_notice(subject: str) -> bool:
    lowered = subject.lower()
    return not any(term in lowered for term in _DISQUALIFYING_TERMS)


def _parse_nse_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw, "%d-%b-%Y").date()
    except (ValueError, TypeError):
        return None


def parse_corporate_action_feed(payload: bytes) -> list[FeedRow]:
    """NSE's ``corporates-corporateActions`` JSON array into structured, unverified rows.

    A notice type this parser doesn't recognise (dividends, rights, mergers, anything
    whose ``subject`` text doesn't match ``_BONUS_RE``/``_SPLIT_RE``) is simply NOT
    included in the result -- not an error. This parser's only job is "classify what it
    can classify with confidence"; ``docs/ENGINE_SPEC.md``'s "No ratio strings" rule
    means a low-confidence guess at an ambiguous notice is worse than no candidate at
    all, since ``refresh_corporate_action_feed`` has no way to distinguish "this parser
    guessed wrong" from "this parser correctly read a real 4:1 bonus".

    Raises:
        CorporateActionFeedFormatError: the payload isn't a JSON array of objects, or an
            object is missing a field every row has carried so far (``isin``, ``symbol``,
            ``exDate``, ``subject``) -- the shape NSE has always sent, not a value this
            parser is choosy about.
    """
    import json

    try:
        records = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CorporateActionFeedFormatError(f"not valid JSON: {exc}") from exc
    if not isinstance(records, list):
        raise CorporateActionFeedFormatError(f"expected a JSON array, got {type(records).__name__}")

    out: list[FeedRow] = []
    for i, record in enumerate(records):
        if not isinstance(record, dict) or not _REQUIRED_FIELDS <= set(record):
            raise CorporateActionFeedFormatError(
                f"row {i}: missing required field(s) {sorted(_REQUIRED_FIELDS - set(record))}"
            )
        isin = str(record["isin"]).strip()
        symbol = str(record["symbol"]).strip()
        subject = str(record["subject"]).strip()
        if not isin or not subject:
            continue  # blank rows are a known artefact of this feed, not a format break
        ex_date = _parse_nse_date(str(record["exDate"]).strip())
        if ex_date is None:
            continue  # "-" is a real, routine value NSE sends for a not-yet-fixed date

        if not _is_plain_notice(subject):
            continue  # a qualifier changes what the ratio means -- see _DISQUALIFYING_TERMS

        bonus_match = _BONUS_RE.search(subject)
        if bonus_match:
            out.append(
                FeedRow(
                    isin=isin, symbol=symbol, action_type=CorpActionType.BONUS, ex_date=ex_date,
                    bonus_new=int(bonus_match.group(1)), bonus_for=int(bonus_match.group(2)),
                    raw_subject=subject,
                )
            )
            continue

        split_match = _SPLIT_RE.search(subject)
        if split_match:
            try:
                before, after = Decimal(split_match.group(1)), Decimal(split_match.group(2))
            except InvalidOperation:
                continue
            out.append(
                FeedRow(
                    isin=isin, symbol=symbol, action_type=CorpActionType.SPLIT, ex_date=ex_date,
                    face_value_before=before, face_value_after=after, raw_subject=subject,
                )
            )
            continue

        # Anything else (dividend, rights, merger, demerger, buyback, AGM/EGM notices,
        # ...) is out of this parser's scope by design -- see the docstring above.

    return out
