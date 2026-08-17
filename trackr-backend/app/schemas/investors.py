"""DTOs for POST /investors and POST /investors/{id}/accounts -- onboarding.

Mirrors contracts/openapi.yaml's inline request/response schemas for these two paths
field for field, the same convention every other schemas/*.py file in this package
follows rather than a shared components/schemas section.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class InvestorIn(BaseModel):
    """POST /investors request body. ``pan`` is optional and write-only: if supplied,
    it is routed through ``app.db.repository.create_investor`` into ``app.db.crypto``
    and is never stored on ``investor`` or echoed back in ``InvestorOut`` -- CLAUDE.md's
    rule that PAN never lands on the investor row. No pattern is enforced here on
    purpose; ``app.db.crypto.normalise_pan`` is the one place that check lives, and its
    failure is what turns into this endpoint's 400.

    ``onboarding_date`` is when the advisory relationship with this client began -- it
    feeds ``compute_period_xirr``'s ``start_date`` (app.engine.xirr) via GET
    /investors/{id}/performance's ``period_xirr``. Optional and nullable: when unset,
    that metric is simply omitted, never guessed."""

    code: str
    display_name: str
    family_group_id: str | None = None
    pan: str | None = None
    onboarding_date: date | None = None


class InvestorOut(BaseModel):
    id: str
    code: str
    display_name: str
    family_group_id: str | None = None
    onboarding_date: date | None = None
    created_at: datetime


class AccountIn(BaseModel):
    """POST /investors/{id}/accounts request body."""

    broker: str
    dp_id: str | None = None
    client_id: str | None = None
    is_advised: bool = True
    label: str | None = None


class AccountOut(BaseModel):
    id: str
    investor_id: str
    broker: str
    dp_id: str | None = None
    client_id: str | None = None
    is_advised: bool
    label: str | None = None
    # One address per (broker, doctype) pair with a real adapter -- see
    # app.ingest.addresses.forwarding_addresses. Empty for a broker with no adapter
    # yet, never a fabricated address for one that doesn't exist.
    forwarding_addresses: list[str] = []
