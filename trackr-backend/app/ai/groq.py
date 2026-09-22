"""Thin client for Groq's chat-completions API -- the document structuring step
(app/ingest/llm_extract.py).

Plain ``urllib.request``, no SDK: one POST, no streaming, no auth flow beyond a bearer
token. Adding the ``groq`` package (or ``openai``, which would also work -- the endpoint
is OpenAI-compatible) buys nothing here and costs a dependency tree against a Vercel
bundle ceiling that ``pyproject.toml`` already flags as load-bearing.

This is a dumb HTTP client: it does not know what a contract note is, what a Decimal is,
or that a ledger exists. It takes a system prompt and a user string and returns whatever
JSON came back. Every judgement about whether that JSON is *true* happens elsewhere,
deterministically, with no network and no model -- ``app/ingest/llm_verify.py`` for
documents, ``app/narrative/verify.py`` for analytics prose.

NOW SERVING THREE CALLERS with three different payloads and three different permissions:
document extraction (``LLM_PARSING_ENABLED``), analytics narration and the in-app
assistant (both ``INSIGHT_GENERATION_ENABLED``).

The boundary this crosses, stated plainly
-----------------------------------------
``app/routers/assistant.py`` says of the other model in this codebase: *"this router
never queries the ledger, the engine, or any other investor data ... an LLM inventing a
portfolio number is exactly the failure mode CLAUDE.md rule 4 exists to prevent."* This
module is the inverse -- document text goes out, numbers come back.

That is survivable for exactly one reason: **nothing here is believed.** A value reaches
the ledger only after it has been found in the source document verbatim and reconciled
arithmetically. The model proposes; ``llm_verify`` disposes. If a future change makes any
value from this module trusted on its own, that reason is gone and this boundary should
move back.

**THAT CASE ARRIVED, AND THE REASON HELD.** ``app/narrative/`` and
``app/routers/assistant.py`` now send an investor's derived positions outbound -- a
change of kind from redacted document text. Nothing they receive is believed either: the
model cannot emit a number on the analytics path at all (every figure is rendered
server-side from a computed fact pack), every comparison it declares is recomputed by
``app/narrative/verify.py``, and on the conversational path every numeral in a reply
must appear in the facts the model was given or the reply is discarded. The permission
is a separate setting, ``insight_generation_enabled``, because the processing purpose is
different from document extraction.

What is sent is only ever what ``app/ingest/redaction.py`` produced -- never a raw
document, never a PDF.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from decimal import Decimal
from functools import lru_cache
from typing import Any

_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

#: A page of text in, a whole trade table out. Still bounded,
#: because a person is waiting on the upload request this sits inside.
_TIMEOUT_SECONDS = 30

#: Generous enough for a long note's table. Truncation is treated as corruption rather
#: than as a partial answer -- see ``complete_json``.
_MAX_OUTPUT_TOKENS = 8192

#: REQUIRED, not decoration. api.groq.com sits behind Cloudflare, which rejects
#: urllib's default ``Python-urllib/3.x`` agent with **HTTP 403 "error code: 1010"** --
#: a bot-protection block that looks exactly like an auth failure and sends you hunting
#: for a bad key. Any explicit agent clears it.
#:
#: Same class of problem as ``app/prices/sources.py``'s BROWSER_HEADERS, which exists
#: because NSE and BSE do the same thing. Unlike those, this one identifies the client
#: honestly rather than impersonating a browser: Groq has no reason to object to a named
#: API client, and pretending to be Chrome to an API we hold a key for would be a lie
#: with no purpose.
_USER_AGENT = "trackr-plus/1.0 (+https://github.com/trackr-plus)"


@lru_cache(maxsize=1)
def _ssl_context() -> ssl.SSLContext:
    """Same fix, same reason, as app/prices/sources.py: Python does
    not use the OS trust store, so a fresh install or a minimal container fails
    CERTIFICATE_VERIFY_FAILED against a host curl reaches fine. Verification is never
    disabled -- only the CA bundle is made explicit, via certifi."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


class GroqUnavailable(Exception):
    """Transport: unreachable, timed out, rate-limited, or a non-200.

    NOT a data problem. The caller degrades to exactly the behaviour it had before this
    feature existed -- the document simply does not get an LLM pass. Mirrors
    ``app.prices.sources.FetchFailed`` / ``IndexSourceFetchFailed``.
    """


class GroqResponseError(Exception):
    """HTTP 200, and the body is not the shape we asked for.

    Missing ``choices``, content that is not JSON, or a response cut off at the token
    limit. The model or the API drifted, and a human needs to look. Mirrors
    ``IndexSourceFormatError``, and is kept distinct from ``GroqUnavailable`` for the same
    reason that module keeps them apart: "the network was down" and "the answer changed
    shape" need different responses, and collapsing them hides the second behind the first.
    """


class GroqClient:
    """One model, one endpoint, one round trip.

    ``opener`` is injectable for the same reason ``app.prices.sources`` makes it
    injectable: every test in this repo runs offline, and a client that could only be
    tested by reaching Groq would not be tested.
    """

    def __init__(self, api_key: str, model: str, opener: Any = None) -> None:
        self._api_key = api_key
        self.model = model
        self._opener = opener or urllib.request.urlopen

    def complete_json(self, system_prompt: str, user_content: str) -> dict[str, Any]:
        """Send one prompt, return the parsed JSON object the model produced.

        Raises:
            GroqUnavailable: the request did not complete.
            GroqResponseError: it completed and the body is unusable.
        """
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            # Transcription, not writing. Any sampling at all is a chance to invent a
            # digit, and there is no upside here to a second-best token ever winning.
            "temperature": 0,
            "max_tokens": _MAX_OUTPUT_TOKENS,
            "stream": False,
        }
        request = urllib.request.Request(
            _ENDPOINT,
            data=json.dumps(body).encode("utf-8"),
            headers={
                # A header, not a query string. A key in a URL ends up in
                # proxy logs and in any exception that quotes the request line.
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
            method="POST",
        )

        try:
            with self._opener(
                request, timeout=_TIMEOUT_SECONDS, context=_ssl_context()
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            # The response body is deliberately NOT read into this message. A 401 or a
            # quota error can echo request context, and this exception is going to be
            # logged, and a body can echo request context -- that would be a disclosure.
            raise GroqUnavailable(f"Groq returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GroqUnavailable(f"could not reach Groq: {type(exc).__name__}") from exc

        return _parse(raw)


def _parse(raw: bytes) -> dict[str, Any]:
    """The response envelope -> the model's JSON object.

    ``parse_float=Decimal`` on BOTH loads is the single most important detail in this
    module. If the model emits ``"quantity": 4000.5`` as a bare JSON number instead of the
    string it was asked for, stock ``json.loads`` produces a **binary float, and the paise
    are gone before any of this project's code runs**. ``Decimal(str(f))`` afterwards
    cannot recover them. With this kwarg a float cannot exist in the process at all.

    (``llm_verify`` still REJECTS non-string numbers rather than accepting these. Both are
    needed: this one makes the damage impossible, that one makes the drift visible.)
    """
    try:
        payload = json.loads(raw, parse_float=Decimal)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GroqResponseError("Groq's response envelope was not JSON") from exc

    try:
        choice = payload["choices"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise GroqResponseError("Groq returned no choices") from exc

    # Truncation is the silent-corruption case, and the reason it gets its own check: a
    # JSON array cut off mid-way either fails to parse -- fine, caught below -- or parses
    # as a SHORTER TRADE LIST THAT LOOKS COMPLETE. A note whose last four trades vanished
    # would stage cleanly and reconcile against nothing.
    if choice.get("finish_reason") == "length":
        raise GroqResponseError(
            "Groq's response was truncated at the token limit; a partial table is not a "
            "partial answer"
        )

    content = (choice.get("message") or {}).get("content")
    if not content:
        raise GroqResponseError("Groq returned an empty message")

    try:
        parsed = json.loads(content, parse_float=Decimal)
    except (json.JSONDecodeError, TypeError) as exc:
        raise GroqResponseError("Groq's message content was not JSON") from exc

    if not isinstance(parsed, dict):
        raise GroqResponseError(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed
