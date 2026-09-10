"""Where bhavcopy files come from.

The URL shapes live here, in one place, because they are the single most likely thing to
break -- an exchange reorganising its archive is not a rare event, and a pipe that silently
starts 404ing every day is worse than one that fails loudly on day one.
"""

from __future__ import annotations

import csv
import io
import ssl
import urllib.error
import urllib.request
import zipfile
from datetime import date
from functools import lru_cache
from typing import Protocol, runtime_checkable

NSE_URL = (
    "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
)
BSE_URL = (
    "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV"
)

#: The pre-2024 NSE archive -- a different URL, a different CSV shape (no UDiFF headers),
#: still genuinely free. See LegacyNseBhavcopySource for why this needs a warmed session
#: cookie where the current-format host does not.
LEGACY_NSE_URL = (
    "https://archives.nseindia.com/content/historical/EQUITIES/{d:%Y}/{mon}/"
    "cm{d:%d}{mon}{d:%Y}bhav.csv.zip"
)
LEGACY_NSE_WARMUP_URL = "https://www.nseindia.com/all-reports"

#: The date NSE_URL's exact filename scheme starts answering -- see
#: app.prices.pipe.NSE_BHAVCOPY_EARLIEST's docstring for how this was verified. Before
#: this, NseBhavcopySource goes to the legacy archive instead; on/after it, the 404 vs
#: 200 boundary is real news (a holiday), not a format problem, so nothing before this
#: date should ever be asked of the current-format URL.
NSE_CURRENT_FORMAT_SINCE = date(2024, 1, 1)

#: NSE returns 403 to anything that does not look like a browser.
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.nseindia.com/",
}

#: LEGACY_NSE_URL's host (archives.nseindia.com) 403s/503s BROWSER_HEADERS above even
#: with a Referer -- confirmed live. This fuller, more current header set plus an actual
#: warmed session cookie (LegacyNseBhavcopySource.fetch, not just a Referer string) is
#: what a real fetch of a real 17-Oct-2023 file needed to get past it.
LEGACY_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": LEGACY_NSE_WARMUP_URL,
}

TIMEOUT_SECONDS = 30


@lru_cache(maxsize=1)
def _ssl_context() -> ssl.SSLContext:
    """A context with an explicit CA bundle.

    Python does not use the macOS keychain and a fresh python.org install has no
    certificates at all, so urllib fails CERTIFICATE_VERIFY_FAILED on hosts where curl
    works fine. Containers have the same gap. Pointing at certifi makes the fetch behave
    identically everywhere.

    VERIFICATION IS NEVER DISABLED. Turning it off would "fix" this in one line and leave
    the pipe accepting any certificate for the rest of its life - on a feed that sets every
    price this system reports.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


class NotPublished(Exception):
    """No bhavcopy for that date.

    NOT a failure. Weekends and exchange holidays have no file, and treating their absence
    as an outage either floods a mailbox every Sunday or -- far worse -- trains whoever
    reads the alerts to ignore them, which is how a genuine multi-day outage goes unnoticed.
    """


class FetchFailed(Exception):
    """The file should exist and could not be retrieved. This one alerts."""


@runtime_checkable
class BhavcopySource(Protocol):
    exchange: str

    def fetch(self, on: date) -> bytes: ...


class HttpBhavcopySource:
    def __init__(self, exchange: str, url_template: str, opener=None):
        self.exchange = exchange
        self.url_template = url_template
        self._opener = opener or urllib.request.urlopen

    def url_for(self, on: date) -> str:
        return self.url_template.format(d=on)

    def fetch(self, on: date) -> bytes:
        request = urllib.request.Request(self.url_for(on), headers=BROWSER_HEADERS)
        try:
            with self._opener(request, timeout=TIMEOUT_SECONDS, context=_ssl_context()) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            # 404 is the exchange saying "no trading that day". Anything else is a problem
            # with the fetch itself: 403 means the anti-bot headers stopped working, 5xx
            # means their side is down. Those must be distinguishable.
            if exc.code == 404:
                raise NotPublished(f"{self.exchange}: nothing published for {on}") from exc
            raise FetchFailed(f"{self.exchange}: HTTP {exc.code} for {on}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FetchFailed(f"{self.exchange}: {type(exc).__name__} for {on}") from exc

        # BSE's "no trading that day" answer is not a 404 -- confirmed live, 2026-08-30
        # (a Sunday): HTTP 200, its own marketing homepage HTML. Treated as NotPublished,
        # the same as NSE's 404, rather than falling through to parse() where it would
        # raise BhavcopyFormatError and alert every single non-trading day -- exactly the
        # "trains whoever reads the alerts to ignore them" failure NotPublished's own
        # docstring warns about. A real UDiFF file, zipped or bare CSV, never starts with
        # an HTML doctype/tag, so this cannot mask an actual format break.
        if body.lstrip()[:20].lower().startswith((b"<!doctype html", b"<html")):
            raise NotPublished(f"{self.exchange}: nothing published for {on} (HTML response)")
        return body


#: Legacy archive columns -> the UDiFF names app.prices.udiff.parse already knows, so
#: that one parser stays the only bhavcopy parser -- see _to_udiff_csv.
_LEGACY_SYMBOL_COL = "SYMBOL"
_LEGACY_SERIES_COL = "SERIES"
_LEGACY_CLOSE_COL = "CLOSE"
_LEGACY_TIMESTAMP_COL = "TIMESTAMP"
_LEGACY_ISIN_COL = "ISIN"

#: Cash-segment equity series only -- same posture as udiff.EQUITY_INSTRUMENTS, just
#: keyed on the legacy file's own SERIES column instead of UDiFF's FinInstrmTp.
_LEGACY_EQUITY_SERIES = {"EQ", "BE"}

_LEGACY_MONTH_ABBREVIATIONS = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)


def _to_udiff_csv(legacy_text: str) -> bytes:
    """Re-shape a legacy ``cmDDMMMYYYYbhav`` row into UDiFF's column names, so
    ``app.prices.udiff.parse`` -- the one bhavcopy parser -- can read it unmodified.
    Only the columns that parser actually reads are produced; nothing here does its own
    Decimal/date validation; that happens exactly once, inside ``parse``, same as any
    other source.

    Confirmed against a real fetched file (17-Oct-2023): the legacy format DOES carry an
    ISIN column, contradicting ``app.prices.udiff``'s old module docstring, which this
    change corrects.
    """
    reader = csv.DictReader(io.StringIO(legacy_text))
    if reader.fieldnames is None:
        return b""
    columns = {(f or "").strip() for f in reader.fieldnames}
    missing = {_LEGACY_ISIN_COL, _LEGACY_CLOSE_COL, _LEGACY_TIMESTAMP_COL} - columns
    if missing:
        # Let the caller's udiff.parse raise BhavcopyFormatError with its own message --
        # an empty-but-headered UDiFF CSV reliably triggers that path.
        return b"ISIN,ClsPric,TradDt\n"

    out = io.StringIO()
    writer = csv.DictWriter(
        out,
        fieldnames=["ISIN", "TckrSymb", "SctySrs", "ClsPric", "TradDt", "FinInstrmTp"],
    )
    writer.writeheader()
    for raw in reader:
        series = (raw.get(_LEGACY_SERIES_COL) or "").strip().upper()
        if series not in _LEGACY_EQUITY_SERIES:
            continue
        timestamp = (raw.get(_LEGACY_TIMESTAMP_COL) or "").strip().upper()
        try:
            day_s, mon_s, year_s = timestamp.split("-")
            trad_dt = date(int(year_s), _LEGACY_MONTH_ABBREVIATIONS.index(mon_s) + 1, int(day_s))
        except (ValueError, IndexError):
            continue  # let udiff.parse's own per-row date guard handle anything malformed
        writer.writerow(
            {
                "ISIN": (raw.get(_LEGACY_ISIN_COL) or "").strip(),
                "TckrSymb": (raw.get(_LEGACY_SYMBOL_COL) or "").strip(),
                "SctySrs": series,
                "ClsPric": (raw.get(_LEGACY_CLOSE_COL) or "").strip(),
                "TradDt": trad_dt.isoformat(),
                "FinInstrmTp": "EQ",
            }
        )
    return out.getvalue().encode("utf-8")


def _legacy_opener():
    """A cookie-persisting opener -- the one thing that actually mattered. The plain
    ``urllib.request.urlopen`` HttpBhavcopySource uses (a fresh, cookie-less request
    every call) 403s/503s against archives.nseindia.com even with LEGACY_BROWSER_HEADERS;
    only a warmed session cookie, carried across the warmup and the real request via the
    SAME opener, got a real 200. Confirmed live."""
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=_ssl_context()),
        urllib.request.HTTPCookieProcessor(),
    )


class LegacyNseBhavcopySource:
    """The pre-2024 NSE archive -- see LEGACY_NSE_URL and NSE_CURRENT_FORMAT_SINCE.
    Never constructed directly by a caller; NseBhavcopySource picks this over the
    current-format HttpBhavcopySource by date."""

    exchange = "NSE"

    def __init__(self, opener_factory=None):
        self._opener_factory = opener_factory or _legacy_opener

    def url_for(self, on: date) -> str:
        return LEGACY_NSE_URL.format(d=on, mon=_LEGACY_MONTH_ABBREVIATIONS[on.month - 1])

    def fetch(self, on: date) -> bytes:
        opener = self._opener_factory()
        try:
            warmup = urllib.request.Request(LEGACY_NSE_WARMUP_URL, headers=LEGACY_BROWSER_HEADERS)
            opener.open(warmup, timeout=TIMEOUT_SECONDS).close()

            request = urllib.request.Request(self.url_for(on), headers=LEGACY_BROWSER_HEADERS)
            with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise NotPublished(f"NSE (legacy archive): nothing published for {on}") from exc
            raise FetchFailed(f"NSE (legacy archive): HTTP {exc.code} for {on}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FetchFailed(f"NSE (legacy archive): {type(exc).__name__} for {on}") from exc

        if body[:2] != b"PK":
            # Same "got an HTML page back, not a real file" guard HttpBhavcopySource
            # applies to BSE -- an unexpected redirect/login page must not silently
            # parse as zero rows.
            raise NotPublished(
                f"NSE (legacy archive): nothing published for {on} (non-zip response)"
            )
        archive = zipfile.ZipFile(io.BytesIO(body))
        legacy_text = archive.read(archive.namelist()[0]).decode("utf-8", "replace")
        return _to_udiff_csv(legacy_text)


class NseBhavcopySource:
    """NSE bhavcopy, current format on/after NSE_CURRENT_FORMAT_SINCE, the legacy
    archive before it -- one BhavcopySource, so fetch_day and every other caller stays
    unaware two different URL shapes and two different CSV layouts are behind it.
    ``fetch`` always returns UDiFF-shaped bytes either way; app.prices.udiff.parse
    remains the only bhavcopy parser."""

    exchange = "NSE"

    def __init__(
        self,
        current: HttpBhavcopySource | None = None,
        legacy: LegacyNseBhavcopySource | None = None,
    ):
        self._current = current or HttpBhavcopySource("NSE", NSE_URL)
        self._legacy = legacy or LegacyNseBhavcopySource()

    def fetch(self, on: date) -> bytes:
        if on < NSE_CURRENT_FORMAT_SINCE:
            return self._legacy.fetch(on)
        return self._current.fetch(on)


def nse_source(opener=None) -> NseBhavcopySource:
    return NseBhavcopySource(current=HttpBhavcopySource("NSE", NSE_URL, opener))


def bse_source(opener=None) -> HttpBhavcopySource:
    return HttpBhavcopySource("BSE", BSE_URL, opener)
