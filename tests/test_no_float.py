"""Money is Decimal. The binary numeric type is banned from engine/.

CLAUDE.md states the rule bluntly and the MVP checklist enforces it with a bare
``grep -r "float" engine/``. This test is stricter than the Makefile's ``grep "float("``,
which only catches calls and would miss a bare type annotation.

Two checks, because they catch different mistakes:

1. the token nowhere in engine sources -- annotations, casts, imports, comments
2. no binary literals in the engine AST -- this is the one that matters, because
   ``Decimal(0.1)`` is syntactically innocent and quietly wrong

Consequence for anyone editing engine/: do not write the banned word even in a
docstring, including in a sentence forbidding its use. Say "Decimal only" instead.
"""

from __future__ import annotations

import ast
import re

import pytest

from tests.conftest import ENGINE

BANNED = "float"
BANNED_TOKEN = re.compile(rf"\b{BANNED}\b")

ENGINE_SOURCES = sorted(ENGINE.rglob("*.py"))
SOURCE_IDS = [str(p.relative_to(ENGINE)) for p in ENGINE_SOURCES]


def test_engine_has_sources() -> None:
    """Guard against the ban passing vacuously because nothing was scanned."""
    assert ENGINE_SOURCES, f"no Python sources found under {ENGINE}"


@pytest.mark.parametrize("path", ENGINE_SOURCES, ids=SOURCE_IDS)
def test_token_absent(path) -> None:
    source = path.read_text(encoding="utf-8")
    offenders = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in enumerate(source.splitlines(), start=1)
        if BANNED_TOKEN.search(line)
    ]
    assert not offenders, "banned numeric type in engine/:\n" + "\n".join(offenders)


@pytest.mark.parametrize("path", ENGINE_SOURCES, ids=SOURCE_IDS)
def test_no_binary_literals(path) -> None:
    """``Decimal(0.1)`` is not 0.1. Catch the literal before it reaches a Decimal."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders = [
        f"{path.name}:{node.lineno}: {node.value!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, float)
    ]
    assert not offenders, "binary numeric literal in engine/:\n" + "\n".join(offenders)


def test_makefile_grep_would_also_pass() -> None:
    """The blunt checklist grep and this test must agree.

    If this fails while the per-file checks pass, someone has weakened one of them.
    """
    combined = "\n".join(p.read_text(encoding="utf-8") for p in ENGINE_SOURCES)
    assert BANNED not in combined
