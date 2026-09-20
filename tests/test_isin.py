"""ISO 6166 validation, and the fixture helper everything else should build ISINs with.

READ THE FIRST TEST BEFORE ADDING ANYTHING HERE. ``make_isin`` computes a check digit
with the same code under test, so a fixture built by it passes validation *by
construction* -- if ``check_digit`` were wrong, the helper would generate consistently
wrong ISINs and every test built on it would still be green. That circularity is broken
by exactly one thing: the four independently published control vectors in
``test_control_vectors``. They are external truth. If that test fails, nothing else in
this file means anything, which is why it comes first and why the vectors must not be
replaced with generated values.

No real issuer's ISIN appears in this file. Fixtures are generated from reserved-looking
bodies so that no test asserts anything about a real company.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
from app.isin import (
    MAX_RAW_LENGTH,
    NON_SECURITY_LABELS,
    Classification,
    Outcome,
    Reason,
    check_digit,
    classify,
    expand,
    has_valid_check_digit,
    normalize,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

#: Published ISINs whose check digits are documented in the ISO 6166 literature and in
#: every independent implementation. Not generated, not from our data, not Indian --
#: their whole value is being outside this system.
CONTROL_VECTORS = ("US0378331005", "AU0000XVGZA3", "GB0002634946", "US30231G1022")


def make_isin(body: str) -> str:
    """An 11-character body plus its correct check digit. Build every fixture with this.

    Use a body that cannot collide with a real security. ``INE000...`` and ``INE999...``
    are what the existing suite already uses for synthetic values.
    """
    return body + str(check_digit(body))


# --------------------------------------------------------------------------------------
# 0. The control vectors. Everything below depends on this passing.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("isin", CONTROL_VECTORS)
def test_control_vectors_pass(isin: str) -> None:
    """Independently published valid ISINs must validate."""
    assert has_valid_check_digit(isin), isin


@pytest.mark.parametrize("isin", CONTROL_VECTORS)
def test_control_vectors_agree_with_generator(isin: str) -> None:
    """``check_digit`` must reproduce each control vector's published final character.

    This is the test that makes ``make_isin`` trustworthy: the generator and the external
    truth have to agree, not merely the generator and the validator.
    """
    assert str(check_digit(isin[:11])) == isin[11], isin


def test_control_vectors_reject_single_character_damage() -> None:
    """A validator that accepts everything would pass the tests above. It must not.

    Every single-digit substitution in the check-digit position must fail, for all four
    vectors -- nine failures each, no exceptions.
    """
    for isin in CONTROL_VECTORS:
        for digit in "0123456789":
            if digit == isin[11]:
                continue
            assert not has_valid_check_digit(isin[:11] + digit), isin[:11] + digit


def test_expansion_is_letter_to_number_not_ordinal() -> None:
    """A=10 ... Z=35, digits untouched. The classic bug is doubling before expanding."""
    assert expand("AZ") == "1035"
    assert expand("US037833100") == "3028037833100"
    assert expand("0123456789") == "0123456789"


def test_check_digit_rejects_wrong_length_body() -> None:
    with pytest.raises(ValueError):
        check_digit("TOOSHORT")


# --------------------------------------------------------------------------------------
# 1. Malformed inputs. None raise; each returns the correct outcome and reason.
# --------------------------------------------------------------------------------------

VALID_SYNTHETIC = make_isin("INE000A0101")


@pytest.mark.parametrize(
    ("raw", "outcome", "reason"),
    [
        # Well-formed, after normalisation that has real work to do.
        (VALID_SYNTHETIC, Outcome.VALID, None),
        (f"  {VALID_SYNTHETIC.lower()}  ", Outcome.VALID, None),
        (f"{VALID_SYNTHETIC[:7]} {VALID_SYNTHETIC[7:]}", Outcome.VALID, None),
        (f"\u200b{VALID_SYNTHETIC}\ufeff", Outcome.VALID, None),
        (f"\u00a0{VALID_SYNTHETIC}\u00a0", Outcome.VALID, None),
        # Absent identifier, no label to explain it -- the case that must NOT be cash.
        ("", Outcome.QUARANTINE, Reason.MISSING_IDENTIFIER),
        ("   ", Outcome.QUARANTINE, Reason.MISSING_IDENTIFIER),
        ("\u200b", Outcome.QUARANTINE, Reason.MISSING_IDENTIFIER),
        # Not a string.
        (None, Outcome.QUARANTINE, Reason.NOT_A_STRING),
        (12345, Outcome.QUARANTINE, Reason.NOT_A_STRING),
        (b"INE000A01012", Outcome.QUARANTINE, Reason.NOT_A_STRING),
        # Wrong shape.
        ("INE000A0101", Outcome.QUARANTINE, Reason.SHAPE),  # 11 chars
        ("INE000A010123", Outcome.QUARANTINE, Reason.SHAPE),  # 13 chars
        ("INE000A0101A", Outcome.QUARANTINE, Reason.SHAPE),  # letter check digit
        ("1NE000A01012", Outcome.QUARANTINE, Reason.SHAPE),  # digit in country code
        ("INE000-A01012", Outcome.QUARANTINE, Reason.SHAPE),  # punctuation
        ("TREPS", Outcome.QUARANTINE, Reason.SHAPE),  # label in the ISIN column
        ("Net Receivables", Outcome.QUARANTINE, Reason.SHAPE),
        # Right shape, wrong check digit.
        ("IN9999999999", Outcome.QUARANTINE, Reason.CHECKSUM),
        ("INE000A01011", Outcome.QUARANTINE, Reason.CHECKSUM),
        # Over-long: a misaligned column, rejected before any pattern runs.
        ("X" * (MAX_RAW_LENGTH + 1), Outcome.QUARANTINE, Reason.TOO_LONG),
    ],
)
def test_classify_outcomes(raw: object, outcome: Outcome, reason: Reason | None) -> None:
    result = classify(raw)
    assert result.outcome is outcome, (raw, result)
    assert result.reason is reason, (raw, result)


def test_the_spec_fixture_that_was_wrong_is_still_wrong() -> None:
    """A guard against the specific failure this work started from.

    The ISIN resolution spec used ``INE238A01028`` as its *known-good* control. It fails
    ISO 6166 -- the correct final digit for that body is 6. The danger was never the
    fixture itself: it is that a valid-looking fixture failing validation invites someone
    to weaken the validator. Pinned here so that if anyone ever does, this test names the
    reason out loud instead of a distant suite going red.
    """
    assert check_digit("INE238A0102") == 6
    assert classify("INE238A01028").reason is Reason.CHECKSUM
    assert classify("INE238A01026").outcome is Outcome.VALID


def test_checksum_and_shape_are_distinguished() -> None:
    """The two failures need different handling, so they must not collapse into one.

    A CHECKSUM value is shape-valid and may match dirty-but-real reference data, so a
    caller is entitled to look it up before discarding it. A SHAPE value cannot key
    anything at all. Callers branch on this, so the distinction is load-bearing.
    """
    assert classify("IN9999999999").normalized == "IN9999999999"
    assert classify("TREPS").normalized == "TREPS"
    assert classify("TREPS").reason is Reason.SHAPE


def test_raw_is_preserved_so_extraction_damage_stays_visible() -> None:
    """A reviewer must be able to see what arrived, not only the cleaned-up form."""
    result = classify("  ine000a\u200b0101x  ")
    assert result.raw == "  ine000a\u200b0101x  "
    assert result.normalized == "INE000A0101X"


def test_classification_rejects_an_inconsistent_verdict() -> None:
    """The reason/outcome invariant is enforced, not merely documented."""
    with pytest.raises(ValueError):
        Classification(Outcome.VALID, "x", "X", Reason.SHAPE)
    with pytest.raises(ValueError):
        Classification(Outcome.QUARANTINE, "x", "X", None)


# --------------------------------------------------------------------------------------
# 8. A blank ISIN is only cash when the label says so.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("label", sorted(NON_SECURITY_LABELS))
def test_blank_isin_with_a_non_security_label_is_not_quarantined(label: str) -> None:
    result = classify("", label=label)
    assert result.outcome is Outcome.NON_SECURITY
    assert result.reason is None


@pytest.mark.parametrize(
    "label",
    [
        "Some Equity Scheme - Growth",
        "ACME INDUSTRIES LIMITED",
        "Partly Paid Rights",
        "",
        "Unrecognised Broker Wording",
    ],
)
def test_blank_isin_without_a_non_security_label_quarantines(label: str) -> None:
    """The misclassification that silently deletes a holding.

    A row whose identifier went missing is a security awaiting review, not a cash line.
    Defaulting an unrecognised label to NON_SECURITY is how it disappears from holdings
    with no error anywhere.
    """
    result = classify("", label=label)
    assert result.outcome is Outcome.QUARANTINE
    assert result.reason is Reason.MISSING_IDENTIFIER


def test_label_is_matched_case_and_whitespace_insensitively() -> None:
    assert classify("", label="  net   receivables ").outcome is Outcome.NON_SECURITY
    assert classify("", label="TrEpS").outcome is Outcome.NON_SECURITY


def test_a_label_never_supplies_an_identifier() -> None:
    """A non-security label on a row that DOES carry a valid ISIN does not override it,
    and a label never invents an identifier for a row that has none."""
    assert classify(VALID_SYNTHETIC, label="TREPS").outcome is Outcome.VALID
    assert classify("", label="TREPS").normalized == ""


# --------------------------------------------------------------------------------------
# 15. Fuzz. Mutations of valid ISINs, not random strings.
# --------------------------------------------------------------------------------------

_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -\u200b\u00a0\t"


def test_fuzz_single_character_mutations_of_valid_isins() -> None:
    """10,000 mutations of *valid* ISINs. Zero exceptions, and every verdict coherent.

    Mutating valid values is the point. Random 12-character strings almost all fail the
    shape check, so they exercise one branch ten thousand times and prove nothing about
    the rest.
    """
    rng = random.Random(20260920)
    bodies = [f"INE{rng.randrange(1000):03d}{chr(65 + rng.randrange(26))}0101" for _ in range(50)]
    valid = [make_isin(b) for b in bodies]

    for _ in range(10_000):
        base = rng.choice(valid)
        position = rng.randrange(len(base))
        mutated = base[:position] + rng.choice(_ALPHABET) + base[position + 1 :]
        result = classify(mutated)
        # No exception is the headline assertion; coherence is what makes it meaningful.
        assert isinstance(result, Classification)
        assert (result.reason is None) is (result.outcome is not Outcome.QUARANTINE)
        if result.outcome is Outcome.VALID:
            assert has_valid_check_digit(result.normalized)


def test_fuzz_hostile_inputs_never_raise() -> None:
    """Non-strings, length bombs, unicode and control characters all get a verdict."""
    hostile: list[object] = [
        None, b"", b"INE000A01012", 0, -1, 12345, 1.5, [], {}, set(), object(),
        "", " ", "\t\n", "\u200b" * 100, "\u00a0",
        "X" * 10_000, "INE000A01012" * 500,
        "\x00INE000A01012", "INE000A01012\x00", "\N{SNOWMAN}" * 12,
        "İNE000A01012",  # dotted capital I: upper()/lower() are not symmetric here
        "ine000a01012\N{ZERO WIDTH JOINER}",
        "INE000A01012\N{RIGHT-TO-LEFT OVERRIDE}",
    ]
    for value in hostile:
        result = classify(value)
        assert isinstance(result, Classification)
        assert (result.reason is None) is (result.outcome is not Outcome.QUARANTINE)


def test_normalize_never_raises_on_any_string() -> None:
    rng = random.Random(11)
    for _ in range(2_000):
        raw = "".join(chr(rng.randrange(0x11000)) for _ in range(rng.randrange(0, 20)))
        assert isinstance(normalize(raw), str)


# --------------------------------------------------------------------------------------
# The regression gate: the committed fixtures must not contain a damaged ISIN.
# --------------------------------------------------------------------------------------


def test_golden_portfolio_isins_are_all_well_formed() -> None:
    """Every ISIN in the acceptance fixture passes ISO 6166.

    This is what makes it safe to enforce the check digit in ingestion later: the
    fixture that defines correctness does not depend on an invalid identifier. Measured,
    not assumed -- at the time of writing all 37 distinct ISINs across its 240 ledger
    rows pass.
    """
    golden = json.loads((FIXTURES / "golden_portfolio.json").read_text(encoding="utf-8"))
    isins = sorted({t["isin"] for t in golden["transactions"] if t.get("isin")})
    assert isins, "fixture carries no ISINs -- the assertion below would be vacuous"
    damaged = [i for i in isins if classify(i).outcome is not Outcome.VALID]
    assert not damaged, f"golden_portfolio.json contains invalid ISINs: {damaged}"
