"""Per-account inbound-forwarding addresses -- app/routers/investors.py surfaces these
on ``AccountOut`` so a client has something to paste into a Gmail filter instead of
docs/INGESTION.md prose nobody can act on. See docs/INGESTION.md "Adapter 3 -- Gmail
forwarding".

Derived, never stored: CLAUDE.md's "everything is derived" discipline applies here too
-- INGEST_DOMAIN + the investor's code + the account's broker is enough to reconstruct
every address on every read, so no address is ever written to a row.
"""

from __future__ import annotations

from app.ingest.webhook import _ADAPTER_FACTORIES


def forwarding_addresses(domain: str, investor_code: str, broker: str) -> list[str]:
    """One address per ``(broker, doctype)`` pair with a real adapter in
    ``app.ingest.webhook._ADAPTER_FACTORIES`` -- read from that registry rather than a
    separately hand-listed set of doctypes, so the two cannot drift apart.

    A broker with no adapter yet (or misspelled) yields an empty list -- CLAUDE.md:
    never invent parsing logic for a source the codebase doesn't handle, so this never
    fabricates an address for a doctype nothing here can parse.
    """
    code = investor_code.strip().lower()
    broker_key = broker.strip().lower()
    return sorted(
        f"{code}-{registered_broker}-{doctype}@{domain}"
        for registered_broker, doctype in _ADAPTER_FACTORIES
        if registered_broker == broker_key
    )
