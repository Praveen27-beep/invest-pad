"""DTOs for /investors/{id}/corporate-actions* -- verified corporate-action reference
data, and the matcher's /match "Apply" step (ENGINE_SPEC section 7's reconciliation,
turned into a staged transaction instead of only a text hint)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.reconcile import DeclaredHoldingIn


class CorporateActionIn(BaseModel):
    """Primitive facts off the exchange notice -- never a ratio string. Which fields
    are required depends on ``action_type``; ``app.engine.corporate_actions
    .CorporateAction.__post_init__`` is what actually enforces that and raises a 422
    for an incomplete record, not this schema."""

    isin: str = Field(pattern=r"^IN[A-Z0-9]{10}$")
    action_type: str = Field(description="BONUS | SPLIT | DEMERGER")
    ex_date: date

    # --- BONUS ---------------------------------------------------------------
    bonus_new: int | None = None
    bonus_for: int | None = None

    # --- SPLIT -----------------------------------------------------------------
    face_value_before: Decimal | None = None
    face_value_after: Decimal | None = None

    # --- DEMERGER: quantity leg only --------------------------------------------
    resulting_isin: str | None = Field(default=None, pattern=r"^IN[A-Z0-9]{10}$")
    demerger_new: int | None = None
    demerger_for: int | None = None

    # --- audit: mandatory for BONUS/SPLIT, the only automatic defence against an
    # inverted ratio ---------------------------------------------------------
    price_cum: Decimal | None = None
    price_ex: Decimal | None = None

    source: str
    source_url: str
    verification: str = "DRAFT"
    notes: str = ""


class CorporateActionOut(BaseModel):
    """Mirrors ``CorporateActionIn`` plus ``id``. Money/ratio fields cross as strings,
    same convention as every other decimal field in this API (``app.database.money``)."""

    id: str | None = None
    isin: str
    action_type: str
    ex_date: date
    bonus_new: int | None = None
    bonus_for: int | None = None
    face_value_before: str | None = None
    face_value_after: str | None = None
    resulting_isin: str | None = None
    demerger_new: int | None = None
    demerger_for: int | None = None
    price_cum: str | None = None
    price_ex: str | None = None
    source: str
    source_url: str
    verification: str
    notes: str = ""
    price_waived: bool = False
    price_waiver_reason: str = ""


class MatchCorporateActionsRequest(BaseModel):
    """Body for POST /investors/{id}/corporate-actions/match -- the MProfit "Apply"
    step. ``holdings`` is the same declared-quantity shape ``/reconcile`` already
    takes (CAS- or broker-declared), since matching runs reconciliation first."""

    account_id: str
    as_of: date | None = None
    holdings: list[DeclaredHoldingIn] = Field(default_factory=list)


class MatchCorporateActionsOut(BaseModel):
    """What got staged. Review and promotion happen through the existing
    /ingest/stage/{batch_id} endpoints -- this never applies anything silently."""

    batch_id: str
    parsed: int
    rejected: int
    notes: list[str] = Field(default_factory=list)


class DisputeCorporateActionIn(BaseModel):
    """Body for POST /ops/corporate-actions/{id}/dispute -- why a human rejected an
    Exceptions entry, kept on the row (never deleted) as the record of what was
    rejected and why."""

    reason: str = ""


class WaivePriceEvidenceIn(BaseModel):
    """Body for POST /ops/corporate-actions/{id}/waive-price-evidence -- why a human is
    accepting a BONUS/SPLIT whose ex_date predates this system's price archive without
    the usual cum/ex corroboration. See ``app.db.corporate_actions.waive_price_evidence``
    for what this does and does not bypass."""

    reason: str


class RefreshCorporateActionFeedOut(BaseModel):
    """Result of one automated feed run -- see
    ``app.db.corporate_actions.refresh_corporate_action_feed``."""

    fetched: int
    verified: int
    exceptions: int
    error: str | None = None


class DiscoverYfinanceOut(BaseModel):
    """Result of one yfinance discovery run -- see
    ``app.db.corporate_actions.discover_from_yfinance``."""

    isins_checked: int
    discovered: int
    verified: int
    exceptions: int
    #: Candidates already on file from another path (or a prior run) -- the two discovery
    #: sources agreeing, which is the system working rather than anything to act on.
    duplicates: int = 0
    errors: dict[str, str] = Field(default_factory=dict)
