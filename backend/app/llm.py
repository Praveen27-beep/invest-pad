"""Talking to a language model. One function, one wire format.

Every hosted or local model Invest-pad supports speaks the OpenAI-style
`/chat/completions` format, so there is one implementation. Keys are decrypted here, used
for one request, and never logged.
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal

import httpx
from cryptography.fernet import Fernet, InvalidToken

TEST_MODEL_URL = "test://extractive"


@dataclass(frozen=True)
class Model:
    label: str
    base_url: str
    model: str
    key: str
    price_in: Decimal      # USD per 1M tokens
    price_out: Decimal
    payer: str             # 'platform' or 'own'


class ModelError(Exception):
    """The model could not be reached or answered with an error. The message is safe to show."""


def encrypt(secret_key: str, value: str) -> str:
    return Fernet(secret_key.encode()).encrypt(value.encode()).decode() if value else ""


def decrypt(secret_key: str, ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return Fernet(secret_key.encode()).decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ModelError("The saved key for this model can no longer be read. Add the model again.") from None


def estimate_tokens(text: str) -> int:
    """A deliberately high estimate (about 3 characters per token) for the pre-flight cost check."""
    return len(text) // 3 + 1


def cost(model: Model, tokens_in: int, tokens_out: int) -> Decimal:
    return (model.price_in * tokens_in + model.price_out * tokens_out) / Decimal(1_000_000)


def complete(model: Model, system: str, user: str, max_tokens: int = 1200) -> tuple[str, int, int]:
    """Send one request. Returns (text, input tokens, output tokens)."""
    if model.base_url == TEST_MODEL_URL:
        text = _test_model(user)
        return text, estimate_tokens(system + user), estimate_tokens(text)
    try:
        response = httpx.post(
            model.base_url.rstrip("/") + "/chat/completions",
            headers={"authorization": f"Bearer {model.key}"} if model.key else {},
            json={"model": model.model, "max_tokens": max_tokens, "temperature": 0,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout=120)
    except httpx.HTTPError as exc:
        raise ModelError(f"Could not reach the model ({type(exc).__name__}).") from None
    if response.status_code in (401, 403):
        raise ModelError("The model rejected the key.")
    if response.status_code == 429:
        raise ModelError("The model provider is rate-limiting or out of credit.")
    if response.status_code >= 400:
        raise ModelError(f"The model answered with an error ({response.status_code}).")
    try:
        data = response.json()
        text = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage") or {}
    except (ValueError, KeyError, IndexError, TypeError):
        raise ModelError("The model's reply was not in the expected format.") from None
    return (text, int(usage.get("prompt_tokens") or estimate_tokens(system + user)),
            int(usage.get("completion_tokens") or estimate_tokens(text)))


def parse_json(text: str) -> dict:
    """Models wrap JSON in prose or code fences. Take the outermost object; {} if there is none."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------- the built-in test model
#
# Not an AI. It lets the whole pipeline run with no key and no cost: for a question it
# quotes the first sentence of the best-matching source; for a guardrail check it quotes
# the first rule. Used by the tests and by anyone trying the product before adding a key.

def _test_model(user: str) -> str:
    rules = re.search(r"<rules>\n(.*?)\n</rules>", user, re.DOTALL)
    if rules is not None:
        first = next((line.strip() for line in rules.group(1).splitlines() if line.strip()), "")
        flags = [{"rule": first, "question": "Does this decision fit that rule?"}] if first else []
        return json.dumps({"flags": flags})
    source = re.search(r'<source id="(S\d+)"[^>]*>\n(.*?)\n</source>', user, re.DOTALL)
    if source is None:
        return json.dumps({"outcome": "unknown", "missing": "No source was provided.", "claims": []})
    sentence = re.split(r"(?<=[.!?])\s", source.group(2).strip(), maxsplit=1)[0][:400]
    return json.dumps({"outcome": "answered", "claims": [
        {"text": f"The best-matching passage says: {sentence}", "source": source.group(1), "quote": sentence}]})
