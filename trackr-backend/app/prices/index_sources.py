"""Where NIFTY 50 TRI index levels come from -- docs/ENGINE_SPEC.md section 6.

A separate module from ``sources.py`` on purpose: bhavcopy is one GET per day returning a
CSV/ZIP; this is one POST for an entire date range returning JSON. Different shape,
different failure modes, but the same discipline -- the URL and payload shape live in one
place because an undocumented endpoint changing shape under us is the single most likely
way this silently stops working.

SENSEX has no equivalent here. BSE's own index archive is a JS-rendered page with no
reachable data endpoint, Asia Index (BSE/S&P's index calculator) has no documented API,
and third-party aggregators are not fit as a system-of-record source for a financial
product. ``app.routers.analytical`` rejects a ``SENSEX_TRI`` request explicitly (400)
rather than this module guessing at a source for it.

NIFTY 50 TRI ONLY -- never the plain price index. ``getTotalReturnIndexString`` and the
``TotalReturnsIndex`` field are the load-bearing names here: swapping either for a plain
index-value endpoint/field would silently understate every benchmark comparison (a price
index excludes dividends), which is exactly the failure ``tests/test_index_sources.py``
pins against.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.prices.sources import BROWSER_HEADERS, TIMEOUT_SECONDS, _ssl_context

NIFTY_TRI_URL = "https://www.niftyindices.com/Backpage.aspx/getTotalReturnIndexString"
NIFTY_TRI_REFERER = "https://www.niftyindices.com/reports/historical-data"
NIFTY_TRI_INDEX_NAME = "NIFTY50_TRI"

#: The endpoint's own request-payload spelling of the index, distinct from our storage
#: key (NIFTY_TRI_INDEX_NAME) -- kept apart so a typo in one can't silently become a typo
#: in the other.
_NIFTY_50_REQUEST_NAME = "NIFTY 50"

_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
#: Explicit month-name maps rather than strptime/strftime's "%b" -- that is locale-
#: dependent, and a server running under a non-English locale would silently send or
#: misparse dates without erroring.
_MONTH_TO_NUM = {m: i + 1 for i, m in enumerate(_MONTHS)}


def _format_request_date(d: date) -> str:
    """``date`` -> ``DD-Mon-YYYY``, the request payload's date format."""
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year:04d}"


def _parse_response_date(text: str) -> date:
    """``DD Mon YYYY`` -> ``date``, the response payload's date format (no separator
    dashes, unlike the request format)."""
    day_str, month_str, year_str = text.strip().split()
    month = _MONTH_TO_NUM.get(month_str)
    if month is None:
        raise ValueError(f"unrecognised month {month_str!r} in {text!r}")
    return date(int(year_str), month, int(day_str))


@dataclass(frozen=True, slots=True)
class IndexLevelRow:
    index_name: str
    level_date: date
    close: Decimal
    source: str


class IndexSourceFetchFailed(Exception):
    """The request should have worked and did not -- network error, non-200, or a
    response shape too broken to even attempt parsing. This one alerts, same posture as
    ``app.prices.sources.FetchFailed``."""


class IndexSourceFormatError(Exception):
    """The response parsed as JSON but not into the shape this endpoint has always
    returned -- the clearest signal the undocumented endpoint changed shape."""


class NiftyTriSource:
    """Fetches NIFTY 50 TRI levels for a date range in one call.

    Unlike ``HttpBhavcopySource`` (one file per day), this endpoint answers a whole
    range at once -- so ``fetch`` takes ``start``/``end`` rather than a single date.
    """

    index_name = NIFTY_TRI_INDEX_NAME

    def __init__(self, opener: Any = None):
        self._opener = opener or urllib.request.urlopen

    def fetch(self, start: date, end: date) -> bytes:
        cinfo = (
            f"{{'name':'{_NIFTY_50_REQUEST_NAME}',"
            f"'startDate':'{_format_request_date(start)}',"
            f"'endDate':'{_format_request_date(end)}',"
            f"'indexName':'{_NIFTY_50_REQUEST_NAME}'}}"
        )
        body = json.dumps({"cinfo": cinfo}).encode("utf-8")
        headers = {
            **BROWSER_HEADERS,
            "Content-Type": "application/json; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": NIFTY_TRI_REFERER,
        }
        request = urllib.request.Request(NIFTY_TRI_URL, data=body, headers=headers, method="POST")
        try:
            with self._opener(request, timeout=TIMEOUT_SECONDS, context=_ssl_context()) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise IndexSourceFetchFailed(f"NIFTY 50 TRI: HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise IndexSourceFetchFailed(f"NIFTY 50 TRI: {type(exc).__name__}") from exc


def parse_nifty_tri(payload: bytes) -> list[IndexLevelRow]:
    """Rows with a usable date and TRI close.

    The response double-encodes JSON (ASP.NET's ``[WebMethod]`` convention): the outer
    body is ``{"d": "<json-string>"}``, and ``d`` itself must be parsed again to reach
    the actual records.

    Raises:
        IndexSourceFormatError: either JSON layer fails to parse, the expected keys are
            absent, or -- deliberately checked, not just assumed -- the
            ``TotalReturnsIndex`` field itself is missing, which is exactly what a silent
            swap to a plain price-index endpoint would look like.
    """
    try:
        outer = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise IndexSourceFormatError(f"NIFTY 50 TRI: outer response is not JSON: {exc}") from exc

    if not isinstance(outer, dict) or "d" not in outer:
        raise IndexSourceFormatError("NIFTY 50 TRI: response missing the 'd' envelope")

    try:
        records = json.loads(outer["d"])
    except json.JSONDecodeError as exc:
        raise IndexSourceFormatError(f"NIFTY 50 TRI: 'd' payload is not JSON: {exc}") from exc

    if not isinstance(records, list):
        raise IndexSourceFormatError("NIFTY 50 TRI: 'd' payload is not a list of records")

    rows: list[IndexLevelRow] = []
    for record in records:
        if not isinstance(record, dict) or "TotalReturnsIndex" not in record:
            raise IndexSourceFormatError(
                "NIFTY 50 TRI: record missing 'TotalReturnsIndex' -- this endpoint must "
                "never be read from a plain price-index field"
            )
        try:
            close = Decimal(str(record["TotalReturnsIndex"]).strip())
            level_date = _parse_response_date(str(record.get("Date", "")))
        except (InvalidOperation, ValueError) as exc:
            raise IndexSourceFormatError(
                f"NIFTY 50 TRI: unparseable record {record!r}: {exc}"
            ) from exc
        rows.append(
            IndexLevelRow(
                index_name=NIFTY_TRI_INDEX_NAME,
                level_date=level_date,
                close=close,
                source="NIFTYINDICES_TRI",
            )
        )
    return rows


def nifty_tri_source(opener: Any = None) -> NiftyTriSource:
    return NiftyTriSource(opener)


def fetch_and_store(conn: Any, start: date, end: date, source: NiftyTriSource | None = None) -> int:
    """Fetch NIFTY 50 TRI for ``[start, end]`` and upsert. The one write path into
    ``index_level`` for this index -- mirrors ``app.prices.pipe.fetch_day`` +
    ``app.db.prices.upsert_prices`` composed together, just without a separate pipe
    module since there is exactly one caller today (``app.routers.analytical``'s
    ``_benchmark``).
    """
    from app.db.index_levels import upsert_index_levels

    source = source or nifty_tri_source()
    rows = parse_nifty_tri(source.fetch(start, end))
    return upsert_index_levels(conn, rows)
