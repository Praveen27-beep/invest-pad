"""app/brokers.py -- the registry GET /brokers serves. Pure, no database needed.

The point of every test here is the same one: a broker entry may not claim a capability
the codebase does not have. docs/ONBOARDING_AS_IS_VS_TO_BE.md section 2, screen 2 --
"the badges are load-bearing and must not flatter" -- and CLAUDE.md's rule against
inventing parsing logic for a source nothing handles.
"""

from __future__ import annotations

import pytest
from app.brokers import BROKERS, describe, registry
from app.ingest.file_validation import LABELS, ROUTING
from app.ingest.webhook import PDF_PASSWORD_CASE

REAL_DOMAIN = "ingest.mei.capital"
PLACEHOLDER_DOMAIN = "ingest.example.com"


# --- The build-failing pin: no entry may name an adapter that does not exist ---------


def test_every_declared_adapter_is_a_real_registered_adapter() -> None:
    """The one assertion that makes the registry trustworthy.

    A typo, or an optimistic entry added because a parser is "nearly done", would
    otherwise reach the picker as a tick beside a broker whose files silently fail.
    ROUTING is the deterministic upload path's own table, so this compares the claim
    against the thing that would actually run.
    """
    known = {adapter for adapter, _route in ROUTING.values()}
    for broker in BROKERS:
        unknown = set(broker.adapters) - known
        assert not unknown, f"{broker.code} claims adapters that do not exist: {sorted(unknown)}"


def test_broker_codes_are_unique_and_uppercase() -> None:
    """``account.broker`` is free text and the wizard writes these codes into it
    verbatim, so two entries differing only by case would create two accounts nothing
    could tell apart."""
    codes = [b.code for b in BROKERS]
    assert codes == [c.upper() for c in codes]
    assert len(set(codes)) == len(codes)


def test_every_broker_says_where_its_files_come_from() -> None:
    """A broker with no adapters is still expected to work end to end via file upload,
    which is only true if the person can find the files. An entry with no console steps
    is an entry that cannot be acted on."""
    for broker in BROKERS:
        assert broker.console_steps, f"{broker.code} has no console steps"
        assert broker.name, f"{broker.code} has no display name"


# --- Derivation: capabilities are read from the real registries, never declared ------


def test_zerodha_reports_the_capabilities_it_actually_has() -> None:
    described = describe(next(b for b in BROKERS if b.code == "ZERODHA"), REAL_DOMAIN)

    assert described["parses_contract_notes"] is True
    assert described["parses_tradebooks"] is True
    assert described["forwarding"] is True
    assert described["pdf_password"] == "Your PAN, in capitals"
    # The labels are the same phrases a rejected upload uses, so the promise made in the
    # picker and the sentence shown on failure describe one file the same way.
    assert all(label in LABELS.values() for label in described["document_labels"])


def test_a_broker_with_no_adapter_claims_nothing() -> None:
    """"files ✅ / email —" is the honest row for Groww today, and an empty
    ``documents`` list is what makes the UI draw it that way."""
    described = describe(next(b for b in BROKERS if b.code == "GROWW"), REAL_DOMAIN)

    assert described["documents"] == []
    assert described["document_labels"] == []
    assert described["parses_contract_notes"] is False
    assert described["parses_tradebooks"] is False
    assert described["forwarding"] is False


def test_forwarding_is_false_for_everyone_without_a_mail_domain() -> None:
    """The deployment-wide half of the gate. On a dev box with the RFC 2606 placeholder
    even Zerodha -- the one broker with an email adapter -- offers no forwarding, which
    is what keeps a dead @ingest.example.com address off every screen."""
    assert all(not b["forwarding"] for b in registry(PLACEHOLDER_DOMAIN))


def test_the_pdf_password_rule_is_read_from_the_transform_it_describes() -> None:
    """docs/INGESTION.md calls per-broker PDF password casing "a real trap". A sentence
    kept in a second table beside PDF_PASSWORD_CASE would be the same trap one level up,
    so the sentence is derived by applying the transform."""
    described = {b["code"]: b for b in registry(REAL_DOMAIN)}

    assert described["UPSTOX"]["pdf_password"] == "Your PAN, in lower case"
    assert described["ZERODHA"]["pdf_password"] == "Your PAN, in capitals"
    # No documented rule is a thing to say, not a thing to guess.
    assert described["ANGELONE"]["pdf_password"] == ""


@pytest.mark.parametrize("broker", [b for b in BROKERS if b.code.lower() in PDF_PASSWORD_CASE])
def test_a_broker_with_a_password_rule_always_states_it(broker: object) -> None:
    assert describe(broker, REAL_DOMAIN)["pdf_password"]  # type: ignore[arg-type]


def test_the_registry_serialises_every_broker() -> None:
    served = registry(REAL_DOMAIN)
    assert len(served) == len(BROKERS)
    assert [b["code"] for b in served] == [b.code for b in BROKERS]
