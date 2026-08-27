"""Holdings -- docs/ENGINE_SPEC.md sections 1 and 2.

Weighted-average cost. FIFO lots run alongside in ``engine/lots.py`` for tax purposes;
the two answer different questions and are deliberately not derived from each other.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.engine.errors import DemergerAdjustmentError, NegativeHoldingError
from app.engine.ledger import ordered
from app.engine.lots import compute_lots
from app.engine.types import (
    ACQUIRING_TYPES,
    DISPOSING_TYPES,
    FREE_SHARE_TYPES,
    ZERO,
    Holding,
    Transaction,
    TxnType,
)

#: A price older than this many days is not a current price. Carrying one forward
#: silently and labelling it "current" is worse than admitting the price is missing.
MAX_PRICE_STALENESS_DAYS = 5

#: Average cost is carried to 4 decimal places. Not an arbitrary choice: it is the
#: precision the depository and broker holdings statements themselves report, so a
#: portfolio reconciled against one of those has to agree at the same precision.
AVG_COST_PLACES = Decimal("0.0001")


def _rounded_pool(pool: Decimal, quantity: Decimal) -> Decimal:
    """Re-express a cost pool as (average rounded to 4dp) x quantity -- Rule B.

    Returns the pool unchanged when the position is closed, since there is no average
    to round and dividing would raise.
    """
    if quantity <= ZERO:
        return pool
    return (pool / quantity).quantize(AVG_COST_PLACES, rounding=ROUND_HALF_UP) * quantity


def compute_holdings(
    transactions: list[Transaction], as_of: date | None = None
) -> list[Holding]:
    """Replay the ledger into current positions.

    Positions at or below zero quantity are closed and excluded from the output.

    The cost-pool rules, which are the whole of this function:

    ==========================================  ==========  =========================
    txn_type                                    quantity    cost pool
    ==========================================  ==========  =========================
    BUY, IPO_ALLOT, TRANSFER_IN                 +qty        + (qty * price) + charges
    SELL, TRANSFER_OUT, BUYBACK                 -qty        - pool * (qty / held)
    BONUS, SPLIT_ADJ, DEMERGER_IN               +qty        unchanged
    DEMERGER_COST_OUT                           0           - cost_transfer
    DEMERGER_COST_IN                            0           + cost_transfer
    DIVIDEND                                    0           unchanged
    ==========================================  ==========  =========================

    ``DEMERGER_COST_OUT``/``DEMERGER_COST_IN`` are the later, paired correction to
    ``DEMERGER_IN``'s zero-cost placeholder above, once a scheme document's cost ratio
    is known -- see ENGINE_SPEC section 11 and ``engine/demerger.py``.

    ``avg_cost = pool / quantity``.

    A disposal removes cost PROPORTIONALLY, which is why selling never moves the average:
    a sale changes what you own, not what the shares you kept cost you. Free shares raise
    quantity and leave the pool alone, which is the mechanism that automatically corrects
    cost basis after a corporate action -- no ratio arithmetic anywhere.

    Precision -- RULE B. The cost pool is carried at full precision through the replay,
    and the average is rounded to 4 decimal places ONCE, when the holding is emitted;
    ``invested`` is then derived as ``avg_cost * quantity``.

    Where the rounding happens matters, and was settled by measurement rather than
    preference. Rounding at every acquisition instead reproduces only 16 of the golden
    fixture's 20 invested values; rounding once at presentation reproduces 18, and
    matches the broker holdings statement's own 4dp average for every one of them.
    Per-event rounding accumulates its own error across a long replay -- 25 acquisitions
    means 25 roundings, each feeding the next -- which is exactly what those two
    regressions were.

    Four decimal places is not arbitrary: it is the precision the depository and broker
    statements report, so a portfolio reconciled against one has to agree there.

    Price-derived fields (``last_price``, ``market_value``, ``unrealised``,
    ``unrealised_pct``, ``weight_pct``) are left unset. Prices are a separate pipe;
    valuation is section 2 and lives in ``engine/valuation.py``.

    Raises:
        NegativeHoldingError: a disposal exceeds the quantity held. That means buy
            history is missing, not that the investor is short.
    """
    quantities: dict[str, Decimal] = {}
    pools: dict[str, Decimal] = {}
    first_buy: dict[str, date] = {}
    estimated: dict[str, bool] = {}

    for txn in ordered(transactions, as_of):
        isin = txn.isin
        held = quantities.get(isin, ZERO)
        pool = pools.get(isin, ZERO)

        if txn.txn_type in ACQUIRING_TYPES:
            quantity = held + txn.quantity
            quantities[isin] = quantity
            # Full precision here; Rule B rounds once at emission. See the docstring for
            # why rounding at each acquisition instead costs two of the golden values.
            pools[isin] = pool + txn.quantity * txn.price + txn.charges
            first_buy.setdefault(isin, txn.txn_date)
            # Sticky, and deliberately so: once an estimated cost is averaged into the
            # pool there is no way to separate the estimated rupees from the verified
            # ones, so the whole position inherits the doubt.
            if (txn.raw_payload or {}).get("cost_estimated"):
                estimated[isin] = True

        elif txn.txn_type in DISPOSING_TYPES:
            if txn.quantity > held:
                raise NegativeHoldingError(isin, held - txn.quantity)
            if txn.quantity > ZERO:
                # Multiply before dividing, and divide by the quantity held BEFORE this
                # row. One division instead of a division followed by a multiplication
                # keeps materially less error out of a 324-row replay.
                pools[isin] = pool - (pool * txn.quantity / held)
                quantities[isin] = held - txn.quantity

        elif txn.txn_type in FREE_SHARE_TYPES:
            # Quantity rises, the pool does not move -- so the average falls, and is
            # re-expressed at 4dp for the same reason as an acquisition. The POOL is
            # what must stay put here; that is the invariant the bonus case checks.
            quantities[isin] = held + txn.quantity
            pools.setdefault(isin, ZERO)

        elif txn.txn_type is TxnType.DEMERGER_COST_OUT:
            # ENGINE_SPEC section 11. Quantity is untouched -- a demerger's cost ratio
            # moves cost basis, not shares. Requires a current position: this row
            # correcting DEMERGER_IN's zero-cost placeholder with nothing to correct
            # means the paired DEMERGER_IN/BUY history is missing or mis-ordered.
            if held <= ZERO:
                raise DemergerAdjustmentError(isin)
            pools[isin] = pool - txn.cost_transfer

        elif txn.txn_type is TxnType.DEMERGER_COST_IN:
            # The other half of the same pair, on the demerged security. Must follow the
            # DEMERGER_IN row that created this position -- see ENGINE_SPEC section 11's
            # ordering note.
            if held <= ZERO:
                raise DemergerAdjustmentError(isin)
            pools[isin] = pool + txn.cost_transfer

        # DIVIDEND moves neither quantity nor pool. It is a cash event, and shows up in
        # the XIRR series rather than here.

    # FIFO cost, computed alongside rather than instead. Same ledger, same ordering, a
    # different question: `invested` answers "what did the shares I still hold cost me on
    # average", fifo_cost answers "which specific lots survived and what did THOSE cost".
    # They coincide unless a position has been partly sold. See ENGINE_SPEC section 1.
    fifo: dict[str, Decimal] = {}
    for lot in compute_lots(transactions, as_of):
        fifo[lot.isin] = fifo.get(lot.isin, ZERO) + lot.quantity_open * lot.cost_per_unit

    holdings = []
    for isin in sorted(quantities):
        quantity = quantities[isin]
        if quantity <= ZERO:
            continue
        pool = pools.get(isin, ZERO)
        avg_cost = (pool / quantity).quantize(AVG_COST_PLACES, rounding=ROUND_HALF_UP)
        # Rule B applies to BOTH conventions, or they are not comparable. Without it the
        # two differ even for a position that was never sold -- purely because one is a
        # 4dp-average presentation and the other a raw lot sum -- which would bury the
        # real difference (partial disposals) under rounding noise.
        raw_fifo = fifo.get(isin)
        fifo_avg = (
            (raw_fifo / quantity).quantize(AVG_COST_PLACES, rounding=ROUND_HALF_UP)
            if raw_fifo is not None and quantity > ZERO
            else None
        )
        fifo_cost = fifo_avg * quantity if fifo_avg is not None else None
        holdings.append(
            Holding(
                isin=isin,
                quantity=quantity,
                avg_cost=avg_cost,
                invested=avg_cost * quantity,
                first_buy_date=first_buy.get(isin),
                cost_estimated=estimated.get(isin, False),
                fifo_cost=fifo_cost,
                fifo_avg=fifo_avg,
            )
        )
    return holdings
