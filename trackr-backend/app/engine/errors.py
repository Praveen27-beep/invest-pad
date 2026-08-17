"""The error taxonomy from docs/ENGINE_SPEC.md section 9.

Each of these exists because the silent alternative is worse. Failing loudly on a
missing price is the difference between a wrong XIRR nobody notices and a red screen
naming the ISIN that needs attention.
"""

from __future__ import annotations


class EngineError(Exception):
    """Base for every error the engine raises."""


class MissingPriceError(EngineError):
    """A held ISIN has no usable price within the staleness window.

    RAISE. Never substitute zero, never carry a stale price forward silently. Valuing
    an unpriced holding at zero understates XIRR catastrophically, and a stale price
    shown as current is worse than no price at all.

    The ISINs are carried on the exception so the UI can name them rather than showing
    a generic failure.
    """

    def __init__(self, isins: list[str] | None = None, as_of: object = None) -> None:
        self.isins = sorted(isins or [])
        self.as_of = as_of
        detail = ", ".join(self.isins) if self.isins else "unknown ISIN"
        suffix = f" as at {as_of}" if as_of is not None else ""
        super().__init__(f"No usable price for: {detail}{suffix}")


class DuplicateTransactionError(EngineError):
    """A dedupe_key collision.

    Not a failure. The importer skips the row, counts it, and reports the count in the
    import summary. Email forwarding will deliver the same contract note twice; that is
    expected behaviour, not an exception path.
    """

    def __init__(self, dedupe_key: str | None = None) -> None:
        self.dedupe_key = dedupe_key
        super().__init__(f"Transaction already present: {dedupe_key}")


class UnparseableRowError(EngineError):
    """Ingestion could not map a source row to a Transaction.

    Reject THAT ROW with its row number and import the rest. One malformed line in a
    tradebook must not cost the user the other 323.
    """

    def __init__(self, row: int | None = None, reason: str = "") -> None:
        self.row = row
        self.reason = reason
        super().__init__(f"Row {row}: {reason}" if row is not None else reason)


class NegativeHoldingError(EngineError):
    """Disposals exceed acquisitions for an ISIN.

    Flag loudly: this means buy history is missing, not that the investor is short.
    The usual cause is a tradebook downloaded with a date filter -- Console caps each
    download at 365 days. The fix is one file per financial year, going back until a
    download returns empty.
    """

    def __init__(self, isin: str | None = None, quantity: object = None) -> None:
        self.isin = isin
        self.quantity = quantity
        super().__init__(
            f"Holding for {isin} went negative ({quantity}); buy history is incomplete"
        )
