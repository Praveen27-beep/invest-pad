"""The Jev HTTP client. Entirely offline -- the opener is injected, never monkeypatched.

Mirrors tests/test_ai_groq.py's posture: no network, no key, no @pytest.mark needed.
"""

from __future__ import annotations

import json
import urllib.error
from decimal import Decimal

import pytest
from app.ai.jev import JevClient, JevResponseError, JevUnavailable

KEY = "ts_test_not_a_real_key"
MODEL = "jev-latest"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"

CRITERIA = {"billing": "Payments, invoicing, refunds", "technical": "Bugs, outages"}


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
    captured: dict = {}

    def opener(request, timeout=None, context=None):
        captured["request"] = request
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data)
        body = payload if isinstance(payload, str) else json.dumps(payload)
        return _Response(body.encode())

    opener.captured = captured  # type: ignore[attr-defined]
    return opener


def _answer(choice: str, confidence: float = 0.9, probabilities: dict | None = None) -> dict:
    return {
        "answers": {
            "choice": {
                "type": "choice",
                "choice": choice,
                "confidence": confidence,
                "probabilities": probabilities or {choice: confidence},
            }
        }
    }


def _choose(opener):
    return JevClient(KEY, MODEL, opener=opener).choose(
        {"subject": "hello"}, "which team?", CRITERIA
    )


# --- the request ----------------------------------------------------------------


def test_the_request_body_is_what_we_intend() -> None:
    opener = _opener_returning(_answer("technical"))
    _choose(opener)

    body = opener.captured["body"]
    assert body["model"] == MODEL
    assert body["state"] == {"subject": "hello"}
    assert body["questions"] == {
        "choice": {"type": "choice", "instructions": "which team?", "criteria": CRITERIA}
    }


def test_the_model_comes_from_the_constructor() -> None:
    opener = _opener_returning(_answer("technical"))
    JevClient(KEY, "jev-2", opener=opener).choose({}, "q", CRITERIA)
    assert opener.captured["body"]["model"] == "jev-2"


def test_the_key_travels_as_a_header_not_in_the_url() -> None:
    opener = _opener_returning(_answer("technical"))
    _choose(opener)

    request = opener.captured["request"]
    assert KEY not in request.full_url
    assert request.headers["Authorization"] == f"Bearer {KEY}"


def test_a_timeout_is_always_passed() -> None:
    opener = _opener_returning(_answer("technical"))
    _choose(opener)
    assert opener.captured["timeout"] == 15


# --- the answer -------------------------------------------------------------------


def test_a_choice_answer_carries_decimal_confidence_and_probabilities() -> None:
    opener = _opener_returning(
        _answer("technical", confidence=0.82, probabilities={"billing": 0.18, "technical": 0.82})
    )
    out = _choose(opener)

    assert out.choice == "technical"
    assert isinstance(out.confidence, Decimal)
    assert not isinstance(out.confidence, float)
    assert out.confidence == Decimal("0.82")
    assert out.probabilities == {"billing": Decimal("0.18"), "technical": Decimal("0.82")}


def test_a_whole_number_confidence_is_still_decimal() -> None:
    """A confidence of exactly 1 is legitimate and arrives as a bare JSON int, not a
    float -- parse_float=Decimal alone would not catch this."""
    opener = _opener_returning(_answer("technical", confidence=1, probabilities={"technical": 1}))
    out = _choose(opener)
    assert out.confidence == Decimal("1")
    assert out.probabilities["technical"] == Decimal("1")


# --- transport failures: JevUnavailable -------------------------------------------


@pytest.mark.parametrize("code", [429, 500, 401, 529])
def test_an_http_error_is_unavailable_not_a_response_error(code: int) -> None:
    def opener(request, timeout=None, context=None):
        raise urllib.error.HTTPError(ENDPOINT, code, "boom", {}, None)

    with pytest.raises(JevUnavailable):
        _choose(opener)


def test_an_http_error_never_leaks_the_key_or_the_body() -> None:
    def opener(request, timeout=None, context=None):
        raise urllib.error.HTTPError(ENDPOINT, 401, "Unauthorized", {}, None)

    with pytest.raises(JevUnavailable) as exc:
        _choose(opener)
    assert KEY not in str(exc.value)
    assert str(exc.value) == "Jev returned HTTP 401"


def test_an_unreachable_host_is_unavailable() -> None:
    def opener(request, timeout=None, context=None):
        raise urllib.error.URLError("no route to host")

    with pytest.raises(JevUnavailable, match="could not reach"):
        _choose(opener)


def test_a_timeout_is_unavailable() -> None:
    def opener(request, timeout=None, context=None):
        raise TimeoutError()

    with pytest.raises(JevUnavailable):
        _choose(opener)


# --- shape drift: JevResponseError ------------------------------------------------


def test_a_non_json_envelope_is_a_response_error() -> None:
    opener = _opener_returning("<html>502 Bad Gateway</html>")
    with pytest.raises(JevResponseError, match="not JSON"):
        _choose(opener)


def test_a_missing_answer_is_a_response_error() -> None:
    opener = _opener_returning({"answers": {}})
    with pytest.raises(JevResponseError, match="no answer"):
        _choose(opener)


def test_a_choice_outside_the_offered_criteria_is_a_response_error() -> None:
    """The model can only mean something we asked about -- an answer naming an option we
    never offered is drift, not a valid third choice."""
    opener = _opener_returning(_answer("sales"))
    with pytest.raises(JevResponseError, match="not one of the options offered"):
        _choose(opener)


def test_a_non_numeric_confidence_is_a_response_error() -> None:
    opener = _opener_returning(
        {"answers": {"choice": {"choice": "technical", "confidence": "high"}}}
    )
    with pytest.raises(JevResponseError, match="not a number"):
        _choose(opener)


def test_the_two_error_classes_are_distinct() -> None:
    assert not issubclass(JevResponseError, JevUnavailable)
    assert not issubclass(JevUnavailable, JevResponseError)
