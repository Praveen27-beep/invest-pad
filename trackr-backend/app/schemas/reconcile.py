"""DTOs for POST /investors/{id}/reconcile -- ENGINE_SPEC section 7,
schema/discrepancy.schema.json."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class DeclaredHoldingIn(BaseModel):
    """One CAS- or broker-declared quantity, per contracts/openapi.yaml's
    ``/investors/{id}/reconcile`` request body. ``quantity`` is never negative -- a
    depository or broker statement does not declare a short position."""

    isin: str = Field(pattern=r"^IN[A-Z0-9]{10}$")
    quantity: Decimal = Field(ge=0)


class ReconcileRequest(BaseModel):
    """The full request body. ``source`` is accepted per the contract but not yet
    consumed anywhere -- ``app.engine.reconcile.reconcile`` has no parameter for it, and
    CLAUDE.md forbids inventing financial logic that ENGINE_SPEC does not state."""

    as_of: date | None = None
    source: str | None = None
    holdings: list[DeclaredHoldingIn] = Field(default_factory=list)


class DiscrepancyOut(BaseModel):
    """Mirrors schema/discrepancy.schema.json field for field. ``computed_qty``,
    ``declared_qty`` and ``difference`` cross as strings, per that schema's ``decimal``
    ``$ref`` -- same convention as every other money/quantity field in this API."""

    isin: str
    computed_qty: str
    declared_qty: str
    difference: str
    ratio: float | None = None
    likely_cause: str | None = None
