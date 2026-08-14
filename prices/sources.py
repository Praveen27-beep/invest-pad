"""Where bhavcopy files come from.

The URL shapes live here, in one place, because they are the single most likely thing to
break -- an exchange reorganising its archive is not a rare event, and a pipe that silently
starts 404ing every day is worse than one that fails loudly on day one.
"""

from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from datetime import date
from functools import lru_cache
from typing import Protocol, runtime_checkable

NSE_URL = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
)
BSE_URL = (
    "https://www.bseindia.com/download/BhavCopy/Equity/"
    "BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV"
)

#: NSE returns 403 to anything that does not look like a browser.
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.nseindia.com/",
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
                return response.read()
        except urllib.error.HTTPError as exc:
            # 404 is the exchange saying "no trading that day". Anything else is a problem
            # with the fetch itself: 403 means the anti-bot headers stopped working, 5xx
            # means their side is down. Those must be distinguishable.
            if exc.code == 404:
                raise NotPublished(f"{self.exchange}: nothing published for {on}") from exc
            raise FetchFailed(f"{self.exchange}: HTTP {exc.code} for {on}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FetchFailed(f"{self.exchange}: {type(exc).__name__} for {on}") from exc


def nse_source(opener=None) -> HttpBhavcopySource:
    return HttpBhavcopySource("NSE", NSE_URL, opener)


def bse_source(opener=None) -> HttpBhavcopySource:
    return HttpBhavcopySource("BSE", BSE_URL, opener)
