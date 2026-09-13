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


# ===========================================================================
# DIVIDEND NOTICES -- the same payload, a separate parser, a separate row type.
#
# WHY A SEPARATE PARSE FUNCTION rather than another branch inside
# ``parse_corporate_action_feed``. A dividend is not a ``CorpActionType`` and must never
# become one: see migration 029's header for the full argument, the short version being
# that ``check_price_consistency`` passes vacuously for any non-BONUS/SPLIT type, so a
# DIVIDEND member of that enum would inherit ``apply_known_actions_for_account``'s
# auto-apply path with no real guard behind it. Keeping the row types apart means the two
# kinds of notice cannot be confused downstream by a missing ``if``, and the existing
# parser's behaviour is unchanged -- it still drops dividends, which is now correct rather
# than merely incomplete, because this function is what reads them.
#
# WHAT THIS PARSER REFUSES TO DO, and why each refusal is safer than the alternative. Same
# governing rule as the bonus/split parser: no candidate beats a wrong candidate, because
# nothing downstream can tell "this parser guessed" from "this parser read a real notice".
# ===========================================================================


@dataclass(frozen=True, slots=True)
class DividendFeedRow:
    """One dividend notice, structured but UNVERIFIED.

    Carries no quantity and no total: multiplying by a holder's position is what turns a
    declaration into an expectation, and that happens on read, never here.
    """

    isin: str
    symbol: str
    ex_date: date
    amount_per_share: Decimal
    kind: str  # a DividendKind value; kept as str so this module imports no engine enum
    record_date: date | None = None
    raw_subject: str = ""


#: The notice must actually be about a dividend. Word-bounded so "Dividends" matches but a
#: substring inside another word does not.
_DIVIDEND_RE = re.compile(r"\bdividend", re.IGNORECASE)

#: "Rs 1.50 Per Share", "Rs.1.50/-", "Re. 1 Per Share". The Rs/Re alternation is the same
#: Indian-English singular/plural distinction ``_SPLIT_RE`` already documents -- "Re." for
#: exactly one rupee, "Rs." otherwise -- and missing it would silently drop every Re. 1
#: dividend, which is a common declaration.
#:
#: A BARE NUMBER IS DELIBERATELY NOT MATCHED. Requiring the currency marker is what stops
#: this regex reading a ratio, a face value, a percentage or a year as an amount. It costs
#: the occasional real notice phrased without one; a false negative here produces no
#: candidate, which is recoverable, while a false positive produces a wrong rupee figure
#: attached to a real security.
_DIVIDEND_AMOUNT_RE = re.compile(r"\b(?:rs|re)\.?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)

#: Which kind the notice says it is. Matched independently so a subject naming two kinds
#: can be detected as ambiguous rather than silently resolved to whichever matched first.
_DIVIDEND_KINDS = (
    ("INTERIM", re.compile(r"\binterim\b", re.IGNORECASE)),
    ("FINAL", re.compile(r"\bfinal\b", re.IGNORECASE)),
    ("SPECIAL", re.compile(r"\bspecial\b", re.IGNORECASE)),
)


def parse_dividend_feed(payload: bytes) -> list[DividendFeedRow]:
    """NSE's ``corporates-corporateActions`` JSON into structured, unverified dividends.

    Reads the SAME payload ``parse_corporate_action_feed`` reads, so one fetch serves both
    and the anti-bot session warm-up is paid once.

    FOUR THINGS THIS REFUSES TO PARSE, each one a real shape in live NSE data:

    1. A PERCENTAGE DECLARATION -- "Dividend - 150%". Historically common, and it means
       150% OF FACE VALUE, not of price and not a rupee amount. Computing it needs the
       security's face value AT THAT TIME, which this feed does not carry and which a
       later split changes. Reading "150" as Rs 150 would be a 100x error on a Rs 1.50
       dividend. No candidate.
    2. MORE THAN ONE AMOUNT in one subject -- "Interim Dividend Rs 1.50 Per Share And
       Special Dividend Rs 2 Per Share". Both amounts and both kinds are present, but
       PAIRING them correctly is an inference about text order, and getting it backwards
       silently swaps a Rs 2 special with a Rs 1.50 interim. A known gap, not a silent
       one: no candidate, and the notice stays visible as unparsed.
    3. MORE THAN ONE KIND NAMED, for the same reason -- the kind could not be attributed.
    4. ANYTHING ``_DISQUALIFYING_TERMS`` CATCHES, reused unchanged. A preference-share or
       debenture "dividend" is a different instrument's income and must not land against
       an equity ISIN; a scheme of arrangement is not a plain dividend.

    ``recDate`` is read when present and ignored when absent or "-", which NSE sends for a
    date not yet fixed. It is never required: ``_REQUIRED_FIELDS`` deliberately does not
    include it, so a feed that stops sending it degrades to a missing display field rather
    than a format error that stops the run.

    Raises:
        CorporateActionFeedFormatError: same contract and same required fields as
            ``parse_corporate_action_feed`` -- the payload is not a JSON array of objects,
            or a row is missing a field every row has always carried.
    """
    import json

    try:
        records = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CorporateActionFeedFormatError(f"not valid JSON: {exc}") from exc
    if not isinstance(records, list):
        raise CorporateActionFeedFormatError(f"expected a JSON array, got {type(records).__name__}")

    out: list[DividendFeedRow] = []
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
        if not _DIVIDEND_RE.search(subject):
            continue  # not a dividend notice -- the bonus/split parser's business
        if not _is_plain_notice(subject):
            continue  # a qualifier changes what this is -- see _DISQUALIFYING_TERMS
        if "%" in subject:
            continue  # percentage of face value -- refusal 1 above

        ex_date = _parse_nse_date(str(record["exDate"]).strip())
        if ex_date is None:
            continue  # "-" is a real, routine value for a not-yet-fixed date

        amounts = _DIVIDEND_AMOUNT_RE.findall(subject)
        if len(amounts) != 1:
            continue  # none to read, or two that cannot be attributed -- refusal 2
        try:
            amount = Decimal(amounts[0])
        except InvalidOperation:
            continue
        if amount <= 0:
            continue  # a zero or negative declaration is not a dividend

        kinds = [name for name, pattern in _DIVIDEND_KINDS if pattern.search(subject)]
        if len(kinds) > 1:
            continue  # two kinds named, neither attributable -- refusal 3
        kind = kinds[0] if kinds else "UNSPECIFIED"

        record_date = _parse_nse_date(str(record.get("recDate", "")).strip())
        if record_date is not None and record_date < ex_date:
            # A record date before the ex-date cannot be true and in practice means the
            # fields were transposed. Drop the date rather than the notice: the ex-date is
            # what eligibility uses, and record_date is display only.
            record_date = None

        out.append(
            DividendFeedRow(
                isin=isin,
                symbol=symbol,
                ex_date=ex_date,
                amount_per_share=amount,
                kind=kind,
                record_date=record_date,
                raw_subject=subject,
            )
        )

    return out
