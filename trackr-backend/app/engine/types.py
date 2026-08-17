"""Core object shapes for the engine.

These dataclasses mirror ``schema/*.schema.json`` field for field. That correspondence
is not a convention to be remembered -- ``tests/test_types_match_schema.py`` asserts it
on every run and fails if the two ever drift.

Money and quantity are ``Decimal``, always. Binary approximations lose paise, and a
reconciliation that is off by paise takes days to track down. Rates (XIRR, CAGR, ratios)
are ``Decimal`` here too; they cross the JSON boundary as numbers, converted via ``str``.

Nothing in this module reaches upward into the adapter or web layers, or into any
framework. The engine is pure functions over plain data, which is what makes the
fixtures runnable with zero infrastructure and a port to another language a mechanical
exercise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

ZERO = Decimal("0")


class TxnType(StrEnum):
    """Every ledger event. Quantity and cash effects are tabulated in DATA_MODEL.md.

    The three groups that matter to the cost pool:
      - acquiring for cash: BUY, IPO_ALLOT, TRANSFER_IN  -> quantity up, pool up
      - disposing:          SELL, TRANSFER_OUT, BUYBACK  -> quantity down, pool down
                                                            PROPORTIONALLY
      - free shares:        BONUS, SPLIT_ADJ, DEMERGER_IN -> quantity up, pool UNCHANGED

    That third group is the whole mechanism by which cost basis self-corrects after a
    corporate action. No ratio arithmetic is needed anywhere in the code.
    """

    BUY = "BUY"
    SELL = "SELL"
    BONUS = "BONUS"
    SPLIT_ADJ = "SPLIT_ADJ"
    DEMERGER_IN = "DEMERGER_IN"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    IPO_ALLOT = "IPO_ALLOT"
    BUYBACK = "BUYBACK"
    DIVIDEND = "DIVIDEND"


#: Acquisitions that move cash out and add to the cost pool.
ACQUIRING_TYPES = frozenset({TxnType.BUY, TxnType.IPO_ALLOT, TxnType.TRANSFER_IN})

#: Disposals that move cash in and remove cost from the pool proportionally.
DISPOSING_TYPES = frozenset({TxnType.SELL, TxnType.TRANSFER_OUT, TxnType.BUYBACK})

#: Free shares. Quantity rises, the cost pool does not move, the average falls.
FREE_SHARE_TYPES = frozenset({TxnType.BONUS, TxnType.SPLIT_ADJ, TxnType.DEMERGER_IN})


class Source(StrEnum):
    """Which adapter produced a row.

    Recorded for forensics and import summaries. The engine must never branch on it --
    that boundary is what lets a new adapter be added in layer 1 without touching
    layers 2 to 4.
    """

    MANUAL = "MANUAL"
    CSV = "CSV"
    TRADEBOOK = "TRADEBOOK"
    CONTRACT_NOTE = "CONTRACT_NOTE"
    EMAIL = "EMAIL"
    CORP_ACTION = "CORP_ACTION"


class Term(StrEnum):
    """Holding-period classification for a realised gain."""

    SHORT = "SHORT"
    LONG = "LONG"


class Exchange(StrEnum):
    NSE = "NSE"
    BSE = "BSE"
    BOTH = "BOTH"


class AssetClass(StrEnum):
    """All 30 codes from ``schema/asset_classes.json``.

    Seeded in full so the enum never needs a migration. Phase 1 BUILDS EXACTLY ONE: EQ.
    This list is an extension point, not a to-do list.
    """

    EQ = "EQ"
    MF_EQUITY = "MF_EQUITY"
    MF_DEBT = "MF_DEBT"
    SIF = "SIF"
    BND = "BND"
    NCD = "NCD"
    SGB = "SGB"
    FD = "FD"
    BNK = "BNK"
    CD = "CD"
    LN = "LN"
    PPF_EPF = "PPF_EPF"
    NPS_ULIP = "NPS_ULIP"
    INS = "INS"
    PO = "PO"
    REIT = "REIT"
    INVIT = "INVIT"
    GLD = "GLD"
    SLV = "SLV"
    JWL = "JWL"
    PR = "PR"
    ART = "ART"
    AIF = "AIF"
    PE = "PE"
    PMS = "PMS"
    US_EQ = "US_EQ"
    INTL_PE = "INTL_PE"
    STOCK_FNO = "STOCK_FNO"
    OTHER_FNO = "OTHER_FNO"
    CRYPTO = "CRYPTO"


@dataclass(frozen=True, slots=True)
class Transaction:
    """One ledger row. The only thing in this system that is written.

    APPEND-ONLY. There is no correct way to edit one of these. A mistake is fixed by
    appending a reversing row and then the correct row, which is what keeps every
    number reproducible by replaying the ledger.

    ``quantity`` is always positive; direction comes from ``txn_type``.
    """

    isin: str
    txn_date: date
    txn_type: TxnType
    quantity: Decimal
    price: Decimal
    charges: Decimal = ZERO
    dividend_amount: Decimal = ZERO
    id: str | None = None
    account_id: str | None = None
    source: Source | None = None
    source_ref: str | None = None
    dedupe_key: str | None = None
    raw_payload: dict[str, Any] | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Holding:
    """A current position. DERIVED, NEVER STORED -- recomputed on every read.

    ``avg_cost`` is ``invested / quantity``. Because a disposal removes cost
    proportionally, selling never moves it: a sale changes what you own, not what the
    shares you kept cost you.
    """

    isin: str
    quantity: Decimal
    avg_cost: Decimal
    invested: Decimal
    symbol: str | None = None
    last_price: Decimal | None = None
    market_value: Decimal | None = None
    unrealised: Decimal | None = None
    unrealised_pct: Decimal | None = None
    weight_pct: Decimal | None = None
    first_buy_date: date | None = None
    cost_estimated: bool = False
    # ENGINE_SPEC section 5: cagr = (end_value / start_value)^(365.25/days) - 1, valid
    # only as a single-lump-sum approximation. For a position built from several buys,
    # start_value is the current weighted-average `invested` cost pool and start_date is
    # `first_buy_date` -- the earliest acquisition -- treating the whole blended cost as
    # if it had all been put in on that first date. None whenever days, invested, or a
    # price is unavailable; never defaulted to zero. Computed in engine/valuation.py
    # alongside market_value, since it needs a price and an as_of date, neither of which
    # compute_holdings has.
    cagr: Decimal | None = None
    # FIFO cost of the surviving lots, alongside the weighted-average headline. The two
    # differ only where a position has been partly sold, and then they differ a lot: on
    # KDL-SM in the golden fixture, by 8,144.32. Brokers report FIFO; ENGINE_SPEC section 1
    # displays weighted average. Carrying both is what lets a portfolio be reconciled
    # against a broker statement without either number being wrong.
    fifo_cost: Decimal | None = None
    fifo_avg: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Lot:
    """One open FIFO lot. DERIVED, NEVER STORED.

    Runs alongside weighted-average cost: the average is what the dashboard shows, the
    lots are what tax computation needs.
    """

    isin: str
    open_date: date
    quantity_open: Decimal
    cost_per_unit: Decimal


@dataclass(frozen=True, slots=True)
class Realised:
    """A slice of a disposal matched against ONE lot. DERIVED, NEVER STORED.

    A sell spanning two lots produces two of these, which is exactly what the FIFO case
    in the fixtures asserts.
    """

    quantity: Decimal
    proceeds: Decimal
    cost: Decimal
    gain: Decimal
    term: Term
    isin: str | None = None
    sell_date: date | None = None
    holding_days: int | None = None


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Portfolio totals as at one date.

    A persisted snapshot is a cache of a derivation, never a source of truth. It must
    always stay recomputable from the ledger.
    """

    as_of: date
    invested: Decimal
    market_value: Decimal
    unrealised: Decimal | None = None
    realised_to_date: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Discrepancy:
    """One mismatch between computed holdings and a declared quantity.

    A hypothesis for a human to confirm -- never an instruction to auto-correct the
    ledger.
    """

    isin: str
    computed_qty: Decimal
    declared_qty: Decimal
    difference: Decimal
    ratio: Decimal | None = None
    likely_cause: str | None = None


@dataclass(frozen=True, slots=True)
class Benchmark:
    """Cash-flow-replicated index return.

    Answers "what if I had bought the index on exactly the days I bought stocks".
    Comparing portfolio XIRR against a headline index CAGR is not a valid comparison
    and must not be shown.
    """

    name: str
    xirr: Decimal | None = None
    terminal_value: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Performance:
    """The performance response.

    BOTH XIRR VARIANTS ARE MANDATORY TOGETHER. They answer different questions, and the
    gap between them is itself the insight. Reporting one alone leaves a choice about
    which number flatters the portfolio; that choice should not exist.
    """

    as_of: date
    # Deliberately WITHOUT defaults: you cannot construct a Performance without
    # supplying both variants. The "never report one alone" rule is structural here,
    # not a convention someone has to remember. Either may still be None -- the solver
    # legitimately fails sometimes -- but the caller must say so explicitly.
    xirr_all: Decimal | None
    xirr_holdings: Decimal | None
    # FY-to-date variant, WITHOUT a default for the same reason: the caller must always
    # state it, even as None when no 1-April price exists for a held ISIN -- see
    # compute_fy_xirr's docstring, which forbids a substitute for that missing price.
    fy_xirr: Decimal | None
    absolute_return: Decimal | None = None
    cagr: Decimal | None = None
    invested: Decimal | None = None
    market_value: Decimal | None = None
    unrealised: Decimal | None = None
    realised_to_date: Decimal | None = None
    benchmark: Benchmark | None = None
    # Adviser-onboarding variant: money-weighted return since investor.onboarding_date
    # (docs/DATA_MODEL.md), resolved the same honest way fy_xirr is -- see
    # app.routers.analytical._period_xirr. period_start echoes back the date actually
    # used so a caller never has to guess which onboarding_date backed the percentage.
    period_xirr: Decimal | None = None
    period_start: date | None = None
    warning: str | None = None


@dataclass(frozen=True, slots=True)
class ImportSummary:
    """Result of appending rows to the ledger.

    Duplicates are SKIPPED and COUNTED, never treated as errors -- re-importing a file
    must be a no-op, and the caller still needs an honest summary to display.
    """

    inserted: int = 0
    skipped_duplicates: int = 0
    rejected: list[dict[str, Any]] = field(default_factory=list)
