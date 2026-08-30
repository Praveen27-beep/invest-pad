"""Shared fixture loading.

Everything numeric arrives from JSON as a STRING and is converted with
``Decimal(str(...))``. Never let a JSON number become a Decimal directly -- that is the
one conversion that silently reintroduces binary approximation error into a system built
to avoid it.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

pytest_plugins = ["tests.conftest_db"]


@pytest.fixture(autouse=True, scope="session")
def _disable_auth_rate_limiting() -> None:
    """Router tests drive a shared TestClient through /auth/register and /auth/login
    many times from the same fake client address -- slowapi's per-IP limiter would
    otherwise start rejecting the test suite itself rather than a real attacker. Off for
    the whole run; nothing here exercises the limiter's own behaviour."""
    from app.rate_limit import limiter

    limiter.enabled = False


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
SCHEMA = ROOT / "schema"
#: relocated to trackr-backend/app/engine -- see docs/structure_revamp_plan.md.
ENGINE = ROOT / "trackr-backend" / "app" / "engine"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def dec(value: Any) -> Decimal:
    """Convert to Decimal via str, so a JSON number cannot smuggle in an approximation."""
    return Decimal(str(value))


def to_date(value: str) -> date:
    return date.fromisoformat(value)


def to_transaction(row: dict[str, Any]) -> Any:
    """Build a Transaction from a fixture row.

    Imported lazily so that a failure inside the engine surfaces as a test failure with
    a case name attached, rather than as a collection error with no name at all.
    """
    from app.engine.types import Source, Transaction, TxnType

    return Transaction(
        isin=row["isin"],
        txn_date=to_date(row["txn_date"]),
        txn_type=TxnType(row["txn_type"]),
        quantity=dec(row["quantity"]),
        price=dec(row["price"]),
        charges=dec(row.get("charges", "0")),
        dividend_amount=dec(row.get("dividend_amount", "0")),
        account_id=row.get("account_id"),
        source=Source(row["source"]) if row.get("source") else None,
        source_ref=row.get("source_ref"),
        dedupe_key=row.get("dedupe_key"),
        raw_payload=row.get("raw_payload"),
    )


@pytest.fixture(scope="session")
def engine_cases() -> list[dict[str, Any]]:
    return load_json(FIXTURES / "engine_cases.json")["cases"]


@pytest.fixture(scope="session")
def golden() -> dict[str, Any]:
    return load_json(FIXTURES / "golden_portfolio.json")
