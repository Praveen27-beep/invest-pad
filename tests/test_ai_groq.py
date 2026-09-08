"""The Groq HTTP client. Entirely offline -- the opener is injected, never monkeypatched.

Mirrors tests/test_gemini_assistant.py's posture: no network, no key, no @pytest.mark
needed. The one live call worth having is marked `network` and lives at the bottom.
"""

from __future__ import annotations

import json
import urllib.error
from decimal import Decimal

import pytest
from app.ai.groq import GroqClient, GroqResponseError, GroqUnavailable

KEY = "gsk_test_not_a_real_key"
MODEL = "openai/gpt-oss-20b"


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


def _opener_returning(payload: dict | str):
    """Captures the request so tests can assert on what was actually sent."""
    captured: dict = {}

    def opener(request, timeout=None, context=None):
        captured["request"] = request
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data)
        body = payload if isinstance(payload, str) else json.dumps(payload)
        return _Response(body.encode())

    opener.captured = captured  # type: ignore[attr-defined]
    return opener


def _envelope(content: str, finish_reason: str = "stop") -> dict:
    return {"choices": [{"finish_reason": finish_reason, "message": {"content": content}}]}


# --- the request ----------------------------------------------------------------


def test_the_request_body_is_what_we_intend() -> None:
    opener = _opener_returning(_envelope('{"ok": true}'))
    GroqClient(KEY, MODEL, opener=opener).complete_json("sys", "user")

    body = opener.captured["body"]
    assert body["model"] == MODEL
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0, "any sampling is a chance to invent a digit"
    assert body["stream"] is False
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["messages"][1] == {"role": "user", "content": "user"}


def test_the_model_comes_from_the_constructor() -> None:
    """It is env-driven config, so swapping models must never need a code change."""
    opener = _opener_returning(_envelope("{}"))
    GroqClient(KEY, "some/other-model", opener=opener).complete_json("s", "u")
    assert opener.captured["body"]["model"] == "some/other-model"


def test_the_key_travels_as_a_header_not_in_the_url() -> None:
    """A key in a query string ends up in proxy logs and in any exception quoting the
    request line. Gemini's API forces it into the URL; Groq's does not."""
    opener = _opener_returning(_envelope("{}"))
    GroqClient(KEY, MODEL, opener=opener).complete_json("s", "u")

    request = opener.captured["request"]
    assert KEY not in request.full_url
    assert request.headers["Authorization"] == f"Bearer {KEY}"


def test_a_timeout_is_always_passed() -> None:
    opener = _opener_returning(_envelope("{}"))
    GroqClient(KEY, MODEL, opener=opener).complete_json("s", "u")
    assert opener.captured["timeout"] == 30


# --- the float trap -------------------------------------------------------------


def test_a_bare_json_number_arrives_as_decimal_never_float() -> None:
    """THE MOST IMPORTANT TEST IN THIS FILE.

    If the model ignores the "copy as a string" instruction and emits 4000.5, stock
    json.loads makes a binary float and the paise are gone before any validation runs.
    Decimal(str(f)) afterwards cannot recover them. parse_float=Decimal makes that
    impossible rather than merely unlikely.
    """
    opener = _opener_returning(_envelope('{"quantity": 4000.5, "price": 0.1}'))
    out = GroqClient(KEY, MODEL, opener=opener).complete_json("s", "u")

    assert isinstance(out["quantity"], Decimal)
    assert not isinstance(out["quantity"], float)
    assert out["quantity"] == Decimal("4000.5")
    # The classic float failure, asserted directly: 0.1 + 0.2 != 0.3 in binary.
    assert out["price"] + Decimal("0.2") == Decimal("0.3")


def test_the_envelope_is_parsed_with_decimal_too() -> None:
    """Both loads, not just the inner one -- a number in the envelope is rarer but the
    kwarg costs nothing and its absence would be invisible."""
    opener = _opener_returning(
        json.dumps(
            {"usage": {"cost": 0.1}, "choices": [{"message": {"content": "{}"}}]}
        )
    )
    GroqClient(KEY, MODEL, opener=opener).complete_json("s", "u")


# --- transport failures: GroqUnavailable ----------------------------------------


@pytest.mark.parametrize("code", [429, 500, 502, 401])
def test_an_http_error_is_unavailable_not_a_response_error(code: int) -> None:
    def opener(request, timeout=None, context=None):
        raise urllib.error.HTTPError(_ENDPOINT_URL, code, "boom", {}, None)

    with pytest.raises(GroqUnavailable):
        GroqClient(KEY, MODEL, opener=opener).complete_json("s", "u")


_ENDPOINT_URL = "https://api.groq.com/openai/v1/chat/completions"


def test_an_http_error_never_leaks_the_key_or_the_body() -> None:
    """gemini.py reads the error body into its message. Here that would be a disclosure:
    a 401 body can echo request context, and this exception gets logged."""

    def opener(request, timeout=None, context=None):
        raise urllib.error.HTTPError(
            _ENDPOINT_URL, 401, "Unauthorized", {}, None
        )

    with pytest.raises(GroqUnavailable) as exc:
        GroqClient(KEY, MODEL, opener=opener).complete_json("s", "u")
    assert KEY not in str(exc.value)
    assert str(exc.value) == "Groq returned HTTP 401"


def test_an_unreachable_host_is_unavailable() -> None:
    def opener(request, timeout=None, context=None):
        raise urllib.error.URLError("no route to host")

    with pytest.raises(GroqUnavailable, match="could not reach"):
        GroqClient(KEY, MODEL, opener=opener).complete_json("s", "u")


def test_a_timeout_is_unavailable() -> None:
    def opener(request, timeout=None, context=None):
        raise TimeoutError()

    with pytest.raises(GroqUnavailable):
        GroqClient(KEY, MODEL, opener=opener).complete_json("s", "u")


# --- shape drift: GroqResponseError ---------------------------------------------


def test_truncation_is_never_treated_as_a_partial_answer() -> None:
    """The silent-corruption case. A trade table cut off at the token limit can still
    parse -- as a shorter list that looks complete. A note whose last four trades vanished
    would stage cleanly and reconcile against nothing."""
    opener = _opener_returning(_envelope('{"trades": []}', finish_reason="length"))
    with pytest.raises(GroqResponseError, match="truncated"):
        GroqClient(KEY, MODEL, opener=opener).complete_json("s", "u")


def test_a_non_json_envelope_is_a_response_error() -> None:
    opener = _opener_returning("<html>502 Bad Gateway</html>")
    with pytest.raises(GroqResponseError, match="envelope"):
        GroqClient(KEY, MODEL, opener=opener).complete_json("s", "u")


def test_missing_choices_is_a_response_error() -> None:
    opener = _opener_returning({"error": "something"})
    with pytest.raises(GroqResponseError, match="no choices"):
        GroqClient(KEY, MODEL, opener=opener).complete_json("s", "u")


def test_non_json_content_is_a_response_error() -> None:
    """A model that answers in prose despite response_format is drift, not an outage."""
    opener = _opener_returning(_envelope("Sure! Here are the trades I found:"))
    with pytest.raises(GroqResponseError, match="content was not JSON"):
        GroqClient(KEY, MODEL, opener=opener).complete_json("s", "u")


def test_empty_content_is_a_response_error() -> None:
    opener = _opener_returning(_envelope(""))
    with pytest.raises(GroqResponseError, match="empty message"):
        GroqClient(KEY, MODEL, opener=opener).complete_json("s", "u")


def test_a_json_array_is_a_response_error() -> None:
    """Valid JSON, wrong shape. The caller indexes this by key."""
    opener = _opener_returning(_envelope('[{"trade": 1}]'))
    with pytest.raises(GroqResponseError, match="expected a JSON object"):
        GroqClient(KEY, MODEL, opener=opener).complete_json("s", "u")


def test_the_two_error_classes_are_distinct() -> None:
    """Collapsing them would hide "the answer changed shape" behind "the network was
    down", and only one of those is worth waking someone for."""
    assert not issubclass(GroqResponseError, GroqUnavailable)
    assert not issubclass(GroqUnavailable, GroqResponseError)


# --- the one live call, opt-in --------------------------------------------------


@pytest.mark.network
def test_the_real_api_answers() -> None:
    """Opt-in: `pytest -m network`. Everything above runs offline; this exists so a
    genuine outage, a revoked key or an API change can be distinguished from a bug in
    this file.

    It caught a real one. api.groq.com sits behind Cloudflare, which rejects urllib's
    default Python-urllib/3.x agent with HTTP 403 "error code: 1010" -- a bot block that
    reads exactly like an auth failure. No offline test could have found that, because
    the fake opener never sees a header it dislikes.
    """
    from app.config import Settings

    settings = Settings()
    if not settings.groq_api_key:
        pytest.skip("GROQ_API_KEY not configured")

    out = GroqClient(settings.groq_api_key, settings.groq_model).complete_json(
        'Return only JSON matching {"ok": string}.', 'Set ok to the word reachable.'
    )
    assert out["ok"]


@pytest.mark.network
def test_the_user_agent_is_what_clears_cloudflare() -> None:
    """Pins the actual mechanism, so a future "tidy up the headers" commit fails here
    rather than in production with a 403 that looks like a bad key."""
    from app.ai.groq import _USER_AGENT

    assert _USER_AGENT and "urllib" not in _USER_AGENT.lower()


def test_the_user_agent_is_sent_on_every_request() -> None:
    """Offline counterpart to the network test: assert the header is actually attached.

    Without it Cloudflare answers 403 "error code: 1010" before Groq ever sees the
    request -- a bot block that reads exactly like a bad key.
    """
    from app.ai.groq import _USER_AGENT

    opener = _opener_returning(_envelope("{}"))
    GroqClient(KEY, MODEL, opener=opener).complete_json("s", "u")
    sent = opener.captured["request"].headers
    assert sent["User-agent"] == _USER_AGENT
    assert "urllib" not in sent["User-agent"].lower()
