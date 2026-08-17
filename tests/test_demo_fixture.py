"""fixtures/demo_portfolio.json: replayed through the real engine, no database required.

Not the golden-fixture acceptance test (that is test_golden_portfolio.py, pinning
numbers independently verified against a real broker statement) -- this is a sanity
check on the DEMO fixture, which is authored by hand rather than reconciled against
anything external. Its job is to catch an authoring mistake (an oversell, a duplicate
row, a stray ISIN, a security nobody ever bought) before it reaches
app/db/seed_demo.py, using the same replay every seeded database gets.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from app.db.seed_demo import _account_id
from app.engine.dedupe import make_dedupe_key
from app.engine.holdings import compute_holdings
from app.engine.lots import compute_lots
from app.engine.realised import compute_realised
from app.engine.types import Term, TxnType

from tests.conftest import FIXTURES, load_json, to_transaction

FIXTURE: dict[str, Any] = load_json(FIXTURES / "demo_portfolio.json")
ISIN_RE = re.compile(r"^IN[A-Z0-9]{10}$")


@pytest.fixture(scope="module")
def account_ids() -> dict[str, str]:
    code = FIXTURE["investor"]["code"]
    return {a["key"]: _account_id(code, a["key"]) for a in FIXTURE["accounts"]}


@pytest.fixture(scope="module")
def transactions(account_ids: dict[str, str]) -> list[Any]:
    rows = []
    for row in FIXTURE["transactions"]:
        row = dict(row)
        row["account_id"] = account_ids[row["account"]]
        rows.append(row)
    return [to_transaction(r) for r in rows]


def test_every_transaction_references_a_known_security_and_account() -> None:
    isins = {s["isin"] for s in FIXTURE["securities"]}
    keys = {a["key"] for a in FIXTURE["accounts"]}
    for row in FIXTURE["transactions"]:
        assert row["isin"] in isins, row["isin"]
        assert row["account"] in keys, row["account"]


def test_isins_match_the_schema_pattern() -> None:
    for security in FIXTURE["securities"]:
        assert ISIN_RE.match(security["isin"]), security["isin"]


def test_accounts_include_both_advised_and_self_directed() -> None:
    """So the "Advised accounts only" filter has something to show either way."""
    advised = {a["is_advised"] for a in FIXTURE["accounts"]}
    assert advised == {True, False}


def test_dedupe_keys_are_unique_within_the_fixture(transactions: list[Any]) -> None:
    """A collision here means two authored rows are indistinguishable to
    save_transactions -- the second would silently vanish as a "duplicate" of the
    first on every seed run, and the fixture would quietly seed fewer rows than it
    appears to contain."""
    keys = [make_dedupe_key(t) for t in transactions]
    assert len(keys) == len(set(keys))


def test_replays_cleanly_through_the_real_engine(transactions: list[Any]) -> None:
    """No NegativeHoldingError, no malformed lot consumption -- the same replay
    seed_demo.py's price anchor and every /holdings, /lots and /realised call perform."""
    assert compute_holdings(transactions)
    assert compute_lots(transactions)
    assert compute_realised(transactions)


def test_every_security_has_an_open_holding(transactions: list[Any]) -> None:
    """So no row in the Holdings table is ever missing -- every seeded security is
    still held, not merely mentioned in the transaction ledger."""
    held = {h.isin for h in compute_holdings(transactions)}
    isins = {s["isin"] for s in FIXTURE["securities"]}
    assert held == isins


def test_dataset_exercises_both_holding_terms(transactions: list[Any]) -> None:
    """STCG and LTCG both need a worked example for the realised-history screen."""
    terms = {r.term for r in compute_realised(transactions)}
    assert terms == {Term.SHORT, Term.LONG}


def test_dataset_exercises_corporate_actions_and_dividends() -> None:
    """A bonus and a split so cost-basis self-correction is visible, dividends so the
    cash-flow and recent-ledger views aren't buy/sell rows exclusively."""
    types = {row["txn_type"] for row in FIXTURE["transactions"]}
    assert TxnType.BONUS.value in types
    assert TxnType.SPLIT_ADJ.value in types
    assert TxnType.DIVIDEND.value in types
