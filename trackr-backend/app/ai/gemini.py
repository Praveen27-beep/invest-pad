"""Thin client for Google's Gemini API -- the in-app "Ask AI" assistant
(app/routers/assistant.py).

Plain ``urllib.request`` rather than a new SDK dependency: one POST, no streaming, no
auth flow beyond a query-string API key -- pulling in ``google-generativeai`` (and its
own dependency tree) for that would be the kind of premature abstraction CLAUDE.md
warns against. If this assistant ever needs streaming or function-calling, revisit then.

This module never touches the ledger, the engine, or any investor's actual transaction
data -- it only ever sees what the caller explicitly puts in ``messages``/``context``.
That boundary is enforced by the router, not here; this module is a dumb HTTP client.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
_DEFAULT_MODEL = "gemini-2.5-flash"
_TIMEOUT_SECONDS = 20

#: Gemini's roles are "user" and "model" -- this app's chat history uses "assistant"
#: like every other chat API, so the router-facing shape stays consistent and this is
#: the one place that translates.
_ROLE_TO_GEMINI = {"user": "user", "assistant": "model"}


class AssistantError(Exception):
    """The Gemini call failed -- bad key, quota, network, or an unparseable response.
    The router turns this into a 502 with a message that names none of the above, so a
    quota exhaustion doesn't leak API-key-shaped details to the browser."""


@dataclass
class ChatTurn:
    role: str  # "user" or "assistant"
    content: str


def generate_reply(
    api_key: str,
    system_prompt: str,
    turns: list[ChatTurn],
    model: str = _DEFAULT_MODEL,
) -> str:
    """One request/response round trip. No conversation state is kept here -- the
    caller (the frontend, via the router) resends the full turn history each time, the
    same statelessness as every other endpoint in this app."""
    if not turns:
        raise AssistantError("no message to send")

    body = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {"role": _ROLE_TO_GEMINI[t.role], "parts": [{"text": t.content}]} for t in turns
        ],
        "generationConfig": {
            # A chat reply, not an essay -- keeps latency and cost down for what is
            # meant to be a quick explain-this-error assistant, not a report writer.
            "maxOutputTokens": 1024,
            "temperature": 0.4,
        },
    }
    url = f"{_ENDPOINT.format(model=model)}?key={api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AssistantError(f"Gemini returned {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AssistantError(f"could not reach Gemini: {exc.reason}") from exc

    try:
        candidates = payload["candidates"]
        parts = candidates[0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError) as exc:
        # A candidate can come back empty on a safety block rather than an HTTP error --
        # surfaced as the same AssistantError so the router's fallback message covers it.
        finish_reason = None
        if payload.get("candidates"):
            finish_reason = payload["candidates"][0].get("finishReason")
        raise AssistantError(
            f"Gemini returned no usable reply (finishReason={finish_reason})"
        ) from exc
