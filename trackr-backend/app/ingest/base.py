"""The adapter contract.

Every adapter has the same job: turn one source into candidate ``Transaction`` rows and
stop. It does not value anything, does not compute holdings, and -- importantly -- does not
write to the ledger. Staging and promotion are separate steps in ``db/imports.py``.

VALIDATION-FIRST. A row that cannot be parsed is rejected WITH ITS ROW NUMBER and the rest
still import. One malformed line in a 115-row export must not cost the other 114, and a
person fixing it needs to be told which line to look at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from app.engine.types import Transaction

#: A cleanly parsed structured row. Nothing was inferred.
CONFIDENCE_CERTAIN = Decimal("1.0")

#: Something was derived rather than read -- a charge apportioned across a multi-line
#: contract note, an ISIN resolved from a ticker. Still importable, worth a human's eye.
CONFIDENCE_DERIVED = Decimal("0.8")

#: Structurally sound but semantically doubtful. Should not promote without review.
CONFIDENCE_UNCERTAIN = Decimal("0.5")

#: Rows at or below this are surfaced by ``review_batch`` for explicit attention.
REVIEW_THRESHOLD = Decimal("0.9")


@dataclass(frozen=True, slots=True)
class StagedRow:
    """A candidate transaction, not yet in the ledger.

    ``confidence`` looks redundant for a tradebook, where everything is structured and
    scores 1.0. It exists so the contract-note parser -- where confidence genuinely varies
    -- slots into this same staging flow rather than inventing a second one, and so a human
    reviewing any batch reads one consistent signal.
    """

    row_number: int
    transaction: Transaction
    confidence: Decimal = CONFIDENCE_CERTAIN
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Rejection:
    """A row that could not be parsed. Carries the row number so it can be found."""

    row_number: int
    reason: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParseResult:
    rows: list[StagedRow] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def parsed(self) -> int:
        return len(self.rows)

    @property
    def rejected(self) -> int:
        return len(self.rejections)


@runtime_checkable
class Adapter(Protocol):
    """Layer 1. Produces candidate rows; never touches the ledger."""

    name: str

    def parse(self, content: bytes, account_id: str, filename: str = "") -> ParseResult:
        ...
