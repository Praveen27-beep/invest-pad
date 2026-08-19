"""The dataclasses in engine/types.py must mirror schema/*.schema.json exactly.

docs/BUILD_PLAN.md says the types are "generated from schema/*.schema.json". A real
generator (datamodel-code-generator, quicktype) would emit pydantic models and binary
numeric types, and would add a dependency to the one layer that must stay pure and
framework-free. So the dataclasses are written by hand -- and this test enforces the
guarantee generation would have given, failing the moment the two drift apart.

The schemas are the contract. Any language honouring them is a valid implementation of
this system, so the Python types do not get to quietly diverge from them.
"""

from __future__ import annotations

from dataclasses import MISSING, fields
from typing import Any

import pytest
from app.engine import types as engine_types

from tests.conftest import SCHEMA, load_json

#: dataclass name -> schema filename. Benchmark is nested inside performance.schema.json
#: and ImportSummary is an API response shape, so neither has a top-level schema file.
TYPE_TO_SCHEMA = {
    "Transaction": "transaction.schema.json",
    "Holding": "holding.schema.json",
    "Lot": "lot.schema.json",
    "Realised": "realised.schema.json",
    "Snapshot": "snapshot.schema.json",
    "Discrepancy": "discrepancy.schema.json",
    "Performance": "performance.schema.json",
    "DividendSummary": "dividend.schema.json",
}


def schema_for(filename: str) -> dict[str, Any]:
    return load_json(SCHEMA / filename)


@pytest.mark.parametrize(
    ("type_name", "schema_file"), TYPE_TO_SCHEMA.items(), ids=TYPE_TO_SCHEMA.keys()
)
def test_fields_match_schema_properties(type_name: str, schema_file: str) -> None:
    schema = schema_for(schema_file)
    dataclass_fields = {f.name for f in fields(getattr(engine_types, type_name))}
    schema_properties = set(schema["properties"])

    assert dataclass_fields == schema_properties, (
        f"{type_name} and {schema_file} disagree. "
        f"Only in dataclass: {sorted(dataclass_fields - schema_properties)}. "
        f"Only in schema: {sorted(schema_properties - dataclass_fields)}."
    )


@pytest.mark.parametrize(
    ("type_name", "schema_file"), TYPE_TO_SCHEMA.items(), ids=TYPE_TO_SCHEMA.keys()
)
def test_required_fields_have_no_defaults(type_name: str, schema_file: str) -> None:
    """A schema-required field must be mandatory in the constructor too.

    Otherwise a caller can silently omit something the contract says is always present.
    """
    schema = schema_for(schema_file)
    required = set(schema.get("required", []))

    mandatory = {
        f.name
        for f in fields(getattr(engine_types, type_name))
        if f.default is MISSING and f.default_factory is MISSING
    }

    assert mandatory == required, (
        f"{type_name}: constructor-mandatory {sorted(mandatory)} != "
        f"schema-required {sorted(required)}"
    )


def test_every_schema_file_is_covered() -> None:
    """A new schema file must not be added without a matching dataclass."""
    on_disk = {p.name for p in SCHEMA.glob("*.schema.json")}
    assert on_disk == set(TYPE_TO_SCHEMA.values())


def test_txn_type_enum_matches_schema() -> None:
    """All ten ledger event types, including the awkward ones."""
    schema = schema_for("transaction.schema.json")
    assert {t.value for t in engine_types.TxnType} == set(
        schema["properties"]["txn_type"]["enum"]
    )


def test_source_enum_matches_schema() -> None:
    schema = schema_for("transaction.schema.json")
    assert {s.value for s in engine_types.Source} == set(
        schema["properties"]["source"]["enum"]
    )


def test_all_thirty_asset_classes_are_seeded() -> None:
    """Seed all 30 codes so the enum never needs a migration. Build exactly one: EQ."""
    seeded = load_json(SCHEMA / "asset_classes.json")["asset_classes"]
    codes = {entry["code"] for entry in seeded}

    assert len(seeded) == 30
    assert {a.value for a in engine_types.AssetClass} == codes
    assert "EQ" in codes


def test_only_eq_is_phase_one() -> None:
    """Scope discipline, asserted rather than trusted.

    The 30-code list is an extension point, not a to-do list.
    """
    seeded = load_json(SCHEMA / "asset_classes.json")["asset_classes"]
    phase_one = {e["code"] for e in seeded if e.get("phase") == 1}
    assert phase_one == {"EQ"}
