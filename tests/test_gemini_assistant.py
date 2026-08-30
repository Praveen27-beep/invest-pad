"""app.ai.gemini.generate_reply -- the "Ask AI" assistant's one HTTP call.

Mocks urllib.request.urlopen rather than hitting the real API: this is a unit test of
the request/response shape (role mapping, response parsing, error translation), not an
integration test of Gemini itself, and it must run without network access or a real key
(see pyproject.toml's `network` marker, which this deliberately does not need).
"""

from __future__ import annotations

import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest
from app.ai.gemini import AssistantError, ChatTurn, generate_reply


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _patch_urlopen(monkeypatch: pytest.MonkeyPatch, fn) -> None:
    monkeypatch.setattr("app.ai.gemini.urllib.request.urlopen", fn)


def test_success_extracts_text_and_maps_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_urlopen(request, timeout, context=None):
        captured["body"] = json.loads(request.data)
        captured["url"] = request.full_url
        return _FakeResponse({"candidates": [{"content": {"parts": [{"text": "Here's why."}]}}]})

    _patch_urlopen(monkeypatch, fake_urlopen)

    reply = generate_reply(
        "fake-key",
        "system prompt",
        [ChatTurn(role="user", content="why?"), ChatTurn(role="assistant", content="because")],
    )

    assert reply == "Here's why."
    assert captured["url"].endswith("?key=fake-key")
    assert captured["body"]["system_instruction"]["parts"][0]["text"] == "system prompt"
    # "assistant" -> "model" is Gemini's own vocabulary, not this app's.
    assert [c["role"] for c in captured["body"]["contents"]] == ["user", "model"]


def test_empty_turns_raises_without_a_network_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(*a, **k):
        raise AssertionError("must not call the network for an empty turn list")

    _patch_urlopen(monkeypatch, fake_urlopen)

    with pytest.raises(AssistantError):
        generate_reply("fake-key", "system prompt", [])


def test_http_error_is_wrapped_not_leaked(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout, context=None):
        raise HTTPError(
            request.full_url, 429, "quota exceeded", None, BytesIO(b'{"error":"quota"}')
        )

    _patch_urlopen(monkeypatch, fake_urlopen)

    with pytest.raises(AssistantError, match="429"):
        generate_reply("fake-key", "system prompt", [ChatTurn(role="user", content="hi")])


def test_network_error_is_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout, context=None):
        raise URLError("timed out")

    _patch_urlopen(monkeypatch, fake_urlopen)

    with pytest.raises(AssistantError):
        generate_reply("fake-key", "system prompt", [ChatTurn(role="user", content="hi")])


def test_safety_blocked_response_raises_instead_of_returning_empty_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout, context=None):
        return _FakeResponse({"candidates": [{"finishReason": "SAFETY", "content": {}}]})

    _patch_urlopen(monkeypatch, fake_urlopen)

    with pytest.raises(AssistantError, match="SAFETY"):
        generate_reply("fake-key", "system prompt", [ChatTurn(role="user", content="hi")])
