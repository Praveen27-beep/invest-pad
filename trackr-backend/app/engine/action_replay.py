"""Recalculate identified derived entitlements after late imports, without editing trades."""

from dataclasses import replace

from app.engine.corporate_actions import CorporateAction, free_share_effect, screen
from app.engine.holdings import quantity_held_before
from app.engine.types import ZERO, Source, Transaction, TxnType


def replay_derived_actions(
    transactions: list[Transaction], actions: list[CorporateAction]
) -> list[Transaction]:
    def generated(t):
        return t.source is Source.CORP_ACTION and (t.raw_payload or {}).get(
            "auto_corporate_action_id"
        )

    tagged = [t for t in transactions if generated(t)]
    if not tagged:
        return transactions
    safe, _ = screen(actions)
    by_id = {a.id: a for a in safe}
    rebuilt = [t for t in transactions if not generated(t)]
    for original in sorted(tagged, key=lambda t: t.txn_date):
        action = by_id.get(original.raw_payload["auto_corporate_action_id"])
        # A withdrawn/unverified derived event is not an authoritative transaction.
        if action is None:
            continue
        account_rows = [t for t in rebuilt if t.account_id == original.account_id]
        held = quantity_held_before(account_rows, action.isin, action.ex_date)
        if held <= ZERO:
            continue
        isin, kind, quantity = free_share_effect(action, held)
        if quantity > ZERO and quantity == quantity.to_integral_value():
            rebuilt.append(
                replace(
                    original,
                    isin=isin,
                    txn_date=action.ex_date,
                    txn_type=TxnType(kind),
                    quantity=quantity,
                )
            )
    return rebuilt
