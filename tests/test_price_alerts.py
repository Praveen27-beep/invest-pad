"""Price-pipe alert delivery -- docs/FULL_VISION_BACKEND_ROADMAP.md A8.

BUILD_PLAN's MVP definition of done requires "failure alerts by email". These tests
exercise the real send codepath (smtplib) against a fake SMTP server, since sending an
actual email is not practical in this environment -- there is no real mail server to
send to, and nothing here should perform real outbound network I/O. Actual end-to-end
delivery to a live inbox has NOT been verified; what IS verified is that fetch_day's
real failure path constructs and hands off a correctly-addressed, correctly-worded
message to smtplib exactly as a real send would, and that a broken SMTP server can never
crash the price pipe.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest
from app.config import Settings
from app.prices.alerts import EmailNotifier, LoggingNotifier, get_notifier
from app.prices.pipe import fetch_day
from app.prices.sources import FetchFailed

#: Settings() requires these four regardless of SMTP -- see tests/test_config.py.
BASE_SETTINGS = {
    "database_url": "postgresql://localhost/test",
    "portfolio_encryption_key": "test-encryption-key",
    "portfolio_pan_pepper": "test-pan-pepper",
    "jwt_secret": "test-jwt-secret",
    # app/config.py's _validate_ingest_domain only accepts the dev placeholder domain
    # under DEBUG -- this suite is exactly that dev context.
    "debug": True,
}


class FakeSource:
    """A source whose fetch() always fails -- enough to drive fetch_day's alert path
    without needing real bhavcopy fixture bytes for a second, succeeding exchange."""

    def __init__(self, exchange: str, error: Exception):
        self.exchange = exchange
        self._error = error

    def fetch(self, on: date) -> bytes:
        raise self._error


@pytest.fixture
def fake_smtp(monkeypatch):
    """Replaces smtplib.SMTP with an in-memory fake and returns the list of instances
    it constructs, each recording whatever the real client would have done."""
    instances: list[_FakeSMTPClient] = []

    class _FakeSMTPClient:
        def __init__(self, host, port, timeout=None):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.started_tls = False
            self.login_call = None
            self.sent: list = []
            instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def starttls(self):
            self.started_tls = True

        def login(self, username, password):
            self.login_call = (username, password)

        def send_message(self, message):
            self.sent.append(message)

    monkeypatch.setattr("smtplib.SMTP", _FakeSMTPClient)
    return instances


# --- EmailNotifier, in isolation -------------------------------------------------


def test_email_notifier_sends_a_correctly_addressed_message(fake_smtp) -> None:
    notifier = EmailNotifier(
        host="smtp.example.com",
        port=587,
        use_tls=True,
        from_address="alerts@trackr.example",
        recipient="ops@trackr.example",
        username="alerts@trackr.example",
        password="hunter2",
    )

    notifier.notify(
        subject="NSE bhavcopy unavailable for 2026-08-16",
        detail="NSE: HTTP 403",
        context={"exchange": "NSE", "date": "2026-08-16"},
    )

    assert len(fake_smtp) == 1
    client = fake_smtp[0]
    assert (client.host, client.port) == ("smtp.example.com", 587)
    assert client.started_tls is True
    assert client.login_call == ("alerts@trackr.example", "hunter2")

    assert len(client.sent) == 1
    message = client.sent[0]
    assert message["From"] == "alerts@trackr.example"
    assert message["To"] == "ops@trackr.example"
    assert message["Subject"] == "[Trackr] NSE bhavcopy unavailable for 2026-08-16"
    body = message.get_content()
    assert "NSE: HTTP 403" in body
    assert "exchange: NSE" in body
    assert "date: 2026-08-16" in body


def test_email_notifier_skips_auth_without_credentials(fake_smtp) -> None:
    notifier = EmailNotifier(
        host="smtp.example.com", port=25, use_tls=False,
        from_address="a@x.example", recipient="b@x.example",
    )
    notifier.notify("subject", "detail", {})
    client = fake_smtp[0]
    assert client.started_tls is False
    assert client.login_call is None


def test_email_notifier_strips_header_injection_attempts(fake_smtp) -> None:
    """subject/detail ultimately come from a fetch error message -- never trust it not
    to contain a newline that could smuggle extra headers into the email."""
    notifier = EmailNotifier(
        host="smtp.example.com", port=587, use_tls=False,
        from_address="a@x.example", recipient="b@x.example",
    )
    notifier.notify("bad subject\r\nBcc: attacker@evil.example", "detail", {})
    message = fake_smtp[0].sent[0]
    subject = str(message["Subject"])
    assert "\r" not in subject
    assert "\n" not in subject


@pytest.mark.parametrize("missing", ["host", "from_address", "recipient"])
def test_email_notifier_requires_host_from_address_and_recipient(missing: str) -> None:
    kwargs = {
        "host": "smtp.example.com", "port": 587, "use_tls": True,
        "from_address": "a@x.example", "recipient": "b@x.example",
    }
    kwargs[missing] = ""
    with pytest.raises(ValueError):
        EmailNotifier(**kwargs)


def test_email_notifier_does_not_raise_when_smtp_itself_fails(monkeypatch, caplog) -> None:
    """A broken mail server must not crash the price pipe -- see the module docstring.
    This is the property that lets the pipe still store prices from the exchange that
    DID answer even when alert delivery is down."""
    class ExplodingSMTP:
        def __init__(self, *args, **kwargs):
            raise OSError("connection refused")

    monkeypatch.setattr("smtplib.SMTP", ExplodingSMTP)
    notifier = EmailNotifier(
        host="smtp.example.com", port=587, use_tls=True,
        from_address="a@x.example", recipient="b@x.example",
    )

    with caplog.at_level(logging.ERROR, logger="prices"):
        notifier.notify("subject", "detail", {})  # must not raise

    assert "FAILED TO SEND" in caplog.text


# --- get_notifier: Settings -> Notifier selection --------------------------------


def test_get_notifier_returns_email_notifier_when_smtp_is_configured() -> None:
    settings = Settings(
        _env_file=None,
        smtp_host="smtp.example.com",
        smtp_from_address="alerts@trackr.example",
        smtp_alert_recipient="ops@trackr.example",
        **BASE_SETTINGS,
    )
    assert isinstance(get_notifier(settings), EmailNotifier)


def test_get_notifier_falls_back_to_logging_when_smtp_is_unconfigured(caplog) -> None:
    settings = Settings(_env_file=None, **BASE_SETTINGS)

    with caplog.at_level(logging.WARNING, logger="prices"):
        notifier = get_notifier(settings)

    assert isinstance(notifier, LoggingNotifier)
    assert "SMTP not configured" in caplog.text


# --- end-to-end: a real fetch_day failure reaches the email codepath -------------


def test_a_forced_exchange_failure_reaches_the_email_notifier(fake_smtp) -> None:
    """The actual gate this ticket closes: fetch_day's real failure path (not a test
    double standing in for it) constructs and hands a message to smtplib on a genuine
    fetch failure, with the failing exchange and error message intact."""
    notifier = EmailNotifier(
        host="smtp.example.com", port=587, use_tls=True,
        from_address="alerts@trackr.example", recipient="ops@trackr.example",
    )
    on = date(2026, 8, 16)

    result = fetch_day(
        on,
        sources=[FakeSource("NSE", FetchFailed("NSE: HTTP 403"))],
        notifier=notifier,
    )

    assert "NSE" in result.failures
    assert len(fake_smtp) == 1
    message = fake_smtp[0].sent[0]
    assert message["Subject"] == "[Trackr] NSE bhavcopy unavailable for 2026-08-16"
    body = message.get_content()
    assert "NSE: HTTP 403" in body
    assert "exchange: NSE" in body
    assert "date: 2026-08-16" in body
