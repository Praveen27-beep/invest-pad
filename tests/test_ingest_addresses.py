"""app/ingest/addresses.py -- pure, no database needed. Reads directly from
app.ingest.webhook._ADAPTER_FACTORIES rather than a hand-listed doctype set, so these
tests double as a pin on that registry not silently drifting out of sync.
"""

from __future__ import annotations

from app.ingest.addresses import forwarding_addresses
from app.ingest.webhook import _ADAPTER_FACTORIES

DOMAIN = "ingest.example.com"


def test_zerodha_gets_one_address_per_registered_doctype() -> None:
    assert forwarding_addresses(DOMAIN, "c001", "zerodha") == [
        "c001-zerodha-contractnote@ingest.example.com"
    ]


def test_a_broker_with_no_adapter_gets_an_empty_list() -> None:
    """CLAUDE.md: never invent parsing logic for a source the codebase doesn't handle
    -- CDSL has no adapter yet, so no address is fabricated for it."""
    assert forwarding_addresses(DOMAIN, "c001", "cdsl") == []


def test_investor_code_and_broker_are_lowercased() -> None:
    assert forwarding_addresses(DOMAIN, "C001", "ZERODHA") == [
        "c001-zerodha-contractnote@ingest.example.com"
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
