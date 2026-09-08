"""app/ingest/addresses.py -- pure, no database needed. Reads directly from
app.ingest.webhook._ADAPTER_FACTORIES rather than a hand-listed doctype set, so these
tests double as a pin on that registry not silently drifting out of sync.
"""

from __future__ import annotations

import pytest
from app.ingest.addresses import (
    broker_has_forwarding,
    forwarding_addresses,
    forwarding_enabled,
)
from app.ingest.webhook import _ADAPTER_FACTORIES

#: A domain that could actually receive mail. Deliberately NOT the dev placeholder any
#: more: an address is only derived where inbound mail is possible, so a test using
#: ``ingest.example.com`` would now be asserting the empty case by accident rather than
#: the routing rule it means to check.
DOMAIN = "ingest.mei.capital"

#: The RFC 2606 name app/config.py defaults to outside production.
PLACEHOLDER = "ingest.example.com"


def test_zerodha_gets_one_address_per_registered_doctype() -> None:
    assert forwarding_addresses(DOMAIN, "c001", "zerodha") == [
        f"c001-zerodha-contractnote@{DOMAIN}"
    ]


def test_a_broker_with_no_adapter_gets_an_empty_list() -> None:
    """CLAUDE.md: never invent parsing logic for a source the codebase doesn't handle
    -- CDSL has no adapter yet, so no address is fabricated for it."""
    assert forwarding_addresses(DOMAIN, "c001", "cdsl") == []


def test_investor_code_and_broker_are_lowercased() -> None:
    assert forwarding_addresses(DOMAIN, "C001", "ZERODHA") == [
        f"c001-zerodha-contractnote@{DOMAIN}"
    ]


def test_every_adapter_factory_entry_produces_a_routable_address() -> None:
    """Round-trips every registered (broker, doctype) pair through
    parse_to_address so this test breaks the day a new adapter's address would not
    actually route -- e.g. a broker or doctype segment containing a hyphen."""
    from app.ingest.webhook import RoutedAddress, parse_to_address

    for broker, doctype in _ADAPTER_FACTORIES:
        (address,) = forwarding_addresses(DOMAIN, "c001", broker)
        assert parse_to_address(address) == RoutedAddress(
            investor_code="c001", broker=broker, doctype=doctype
        )


# --- No address at all where mail cannot arrive. docs/ONBOARDING_AS_IS_VS_TO_BE.md
# --- section 8, decision 2: the wizard used to hand every new user an address at an
# --- RFC 2606 reserved domain, with four steps telling them to paste it into Gmail.


def test_the_dev_placeholder_domain_yields_no_addresses() -> None:
    """The forwarding step, the Settings panel and the "email ✅" badge all read from
    this one function, so gating here switches the whole feature off together rather
    than leaving three places to remember."""
    assert forwarding_addresses(PLACEHOLDER, "c001", "zerodha") == []
    assert not broker_has_forwarding(PLACEHOLDER, "ZERODHA")


@pytest.mark.parametrize(
    "domain",
    [
        "",
        "   ",
        "localhost",
        "ingest.example.com",
        "mail.example.net",
        "ingest.example.org",
        "ingest.invalid",
        "ingest.test",
        "ingest.localhost",
        # No dot at all is not a domain that MX records can exist for.
        "ingest",
    ],
)
def test_unroutable_domains_are_refused(domain: str) -> None:
    assert not forwarding_enabled(domain)
    assert forwarding_addresses(domain, "c001", "zerodha") == []


@pytest.mark.parametrize("domain", ["ingest.mei.capital", "in.trackr.app", "MAIL.Example2.com"])
def test_a_real_domain_is_accepted(domain: str) -> None:
    """Case and a lookalike name that merely CONTAINS "example" must still route --
    the check is on reserved suffixes, not on the substring."""
    assert forwarding_enabled(domain)


def test_broker_has_forwarding_needs_both_a_domain_and_an_adapter() -> None:
    """The picker asks this before any account exists, so it cannot go through
    ``forwarding_addresses`` (which needs an investor code) -- but it must apply the
    identical rule, or the badge and the address would disagree."""
    assert broker_has_forwarding(DOMAIN, "ZERODHA")
    assert not broker_has_forwarding(DOMAIN, "GROWW")
    assert not broker_has_forwarding(PLACEHOLDER, "ZERODHA")
