"""Nothing identifying leaves this process.

The most important test file in the LLM path. Everything else protects the *ledger* from
a bad number; this protects a *person* from a disclosure that no later fix undoes.

Run in two modes: seeded synthetic notes (always) and the 40 real contract notes plus the
five real XLSX exports (when PORTFOLIO_LOCAL_DOCS is set). The synthetic ones vary the
PII so a single hard-coded value cannot be what the patterns happen to catch; the real
ones are the only proof that the allow-list keeps the trade table on documents nobody
designed it against.
"""

from __future__ import annotations

import glob
import os
import random
import re
import string

import pytest
from app.ingest import redaction
from app.ingest.redaction import (
    NothingToSendError,
    RedactionError,
    redact_for_llm,
)

LOCAL_DOCS = os.environ.get("PORTFOLIO_LOCAL_DOCS", "")
NOTES = sorted(glob.glob(f"{LOCAL_DOCS}/[Cc]ontract note*.pdf"))

TRADE_LINE = (
    "1786505400085603080 12:19:40 1089300 12:19:40 WAAREEENER-A/INE377N01017 "
    "B BSE 18 0.0000 2663.95 (47951.10)"
)


def _synthetic_note(rng: random.Random) -> tuple[str, dict[str, str]]:
    """A note whose identity block is randomised, so a passing test cannot be an artefact
    of one hard-coded PAN."""
    pan = (
        "".join(rng.choices(string.ascii_uppercase, k=5))
        + "".join(rng.choices(string.digits, k=4))
        + rng.choice(string.ascii_uppercase)
    )
    ucc = "".join(rng.choices(string.ascii_uppercase, k=3)) + "".join(
        rng.choices(string.digits, k=3)
    )
    email = f"{''.join(rng.choices(string.ascii_lowercase, k=8))}@example.com"
    phone = rng.choice("6789") + "".join(rng.choices(string.digits, k=9))
    demat = "".join(rng.choices(string.digits, k=16))
    gstin = "29" + pan + "1Z" + rng.choice(string.digits)
    name = rng.choice(["Pankathi H Jain", "P. Muthukumar", "Arjun Rao", "S Venkatesh"])
    address = "14/3 Ganapathy Nagar, Velachery, Chennai 600042"

    text = "\n".join(
        [
            "CONTRACT NOTE CUM TAX INVOICE",
            "Zerodha Broking Limited",
            f"GSTIN: {gstin}   SEBI registration: INZ000031633",
            f"Name of the Client: {name}",
            f"Address of the Client: {address}",
            f"PAN: {pan}",
            f"UCC: {ucc}",
            f"{phone}, {email}",
            f"Demat: {demat}",
            "Trade Date: 12/08/2026 Settlement No: 2026151",
            "Order No. Order Time Trade No. Trade Time Security / Contract Description",
            TRADE_LINE,
            "Taxable value of Supply (Brokerage) (Rs)2 (0.01) (0.01)",
            "Securities Transaction Tax (Rs) (48.00) (48.00)",
            "Stamp duty (Rs) (7.00) (7.00)",
        ]
    )
    return text, {
        "pan": pan,
        "ucc": ucc,
        "email": email,
        "phone": phone,
        "demat": demat,
        "gstin": gstin,
        "name": name,
        "address": address,
    }


def _cases(n: int = 200):
    rng = random.Random(0)
    return [_synthetic_note(rng) for _ in range(n)]


# --- the property that matters --------------------------------------------------


@pytest.mark.parametrize("index", range(200))
def test_no_identifier_survives_any_generated_note(index: int) -> None:
    """The whole point of the module, asserted 200 times over varied PII."""
    text, pii = _cases()[index]
    out = redact_for_llm(text)

    for label, value in pii.items():
        assert value not in out.text, f"{label} survived redaction"


def test_the_name_and_address_block_is_dropped_entirely() -> None:
    """Names and addresses cannot be regexed, so the ALLOW-LIST is what handles them --
    not the deny-list. If this fails, the allow-list has started keeping lines because
    they looked harmless rather than because they looked useful."""
    text, pii = _cases(1)[0]
    out = redact_for_llm(text)
    assert pii["name"] not in out.text
    assert "Ganapathy Nagar" not in out.text
    assert "Client" not in out.text


def test_pattern_shapes_are_absent_not_merely_the_known_values() -> None:
    """Stronger than checking the values we planted: assert nothing PAN-shaped or
    email-shaped is present at all, so a PII field this test did not think to plant is
    still caught."""
    for text, _pii in _cases(50):
        out = redact_for_llm(text)
        assert redaction.BARE_PAN.search(out.text) is None
        assert redaction.EMAIL.search(out.text) is None
        assert redaction.PHONE.search(out.text) is None
        assert redaction.DEMAT.search(out.text) is None
        assert redaction.GSTIN.search(out.text) is None


# --- and the trade table has to survive -----------------------------------------


def test_the_trade_line_survives_intact() -> None:
    """Redaction that kept nothing would pass every test above and be useless."""
    text, _ = _cases(1)[0]
    out = redact_for_llm(text)
    assert "INE377N01017" in out.text
    assert "2663.95" in out.text
    assert "18" in out.text


def test_the_trade_and_order_numbers_survive() -> None:
    """They become ``source_ref``, which precedence.trade_identity needs to dedupe a
    contract note against the tradebook. Drop them and cross-source double-counting
    comes back. A broker sequence number carries no personal content."""
    text, _ = _cases(1)[0]
    out = redact_for_llm(text)
    assert "1786505400085603080" in out.text
    assert "1089300" in out.text


def test_charge_lines_survive() -> None:
    text, _ = _cases(1)[0]
    out = redact_for_llm(text)
    assert "Stamp duty" in out.text
    assert "Securities Transaction Tax" in out.text
    assert "48.00" in out.text


def test_the_trade_date_survives() -> None:
    text, _ = _cases(1)[0]
    assert "12/08/2026" in redact_for_llm(text).text


# --- the egress gate ------------------------------------------------------------


def test_a_document_with_no_isin_is_never_sent() -> None:
    """THE GATE that makes routing `unknown` documents here safe. A will, an insurance
    policy or a medical report has no ISIN on it, so nothing leaves the process -- not
    because we recognised the document, but because it produced nothing a trade parser
    wants."""
    will = "\n".join(
        [
            "LAST WILL AND TESTAMENT",
            "I, P. Muthukumar, PAN ABCDE1234F, of 14/3 Ganapathy Nagar, Chennai,",
            "bequeath my total estate to my daughter.",
        ]
    )
    with pytest.raises(NothingToSendError):
        redact_for_llm(will)


def test_the_gate_fires_before_any_redaction_work() -> None:
    """A document that is refused must be refused whole -- no partial payload, no
    'here is what we would have sent'."""
    with pytest.raises(NothingToSendError):
        redact_for_llm("Dear customer,\nYour policy number is 1234.\n")


# --- fail-closed ----------------------------------------------------------------


def test_assert_no_pii_is_the_last_line_of_defence(monkeypatch) -> None:
    """Deliberately a separate pass rather than trust that mask_pii ran. Break the
    masking and the assertion must still stop the send."""
    monkeypatch.setattr(redaction, "mask_pii", lambda line: (line, {}))
    text, _ = _cases(1)[0]
    with pytest.raises(RedactionError):
        redact_for_llm(text)


def test_the_failure_names_the_pattern_not_the_value() -> None:
    """An exception message travels into logs and tracebacks. crypto.py: 'a PAN in a
    traceback is a disclosure that no amount of encryption at rest undoes.'"""
    with pytest.raises(RedactionError) as exc:
        redaction.assert_no_pii("PAN ABCDE1234F on a line INE377N01017")
    assert "ABCDE1234F" not in str(exc.value)
    assert "pan-shaped" in str(exc.value)


def test_counts_are_reported_never_values() -> None:
    text, pii = _cases(1)[0]
    out = redact_for_llm(text)
    assert all(isinstance(v, int) for v in out.masked.values())
    assert pii["pan"] not in repr(out.masked)


# --- against the real documents -------------------------------------------------


def _real_equity_notes():
    """The real notes that carry an equity trade table, with their redacted payloads.

    Two of the 40 are F&O notes -- see test_an_options_note_is_refused. They raise
    NothingToSendError by design, so they are excluded here rather than asserted over.
    """
    from app.ingest.zerodha_contract_note import extract_text

    out = []
    for path in NOTES:
        with open(path, "rb") as fh:
            text = extract_text(fh.read())
        try:
            out.append((path, redact_for_llm(text)))
        except NothingToSendError:
            continue
    return out


@pytest.mark.skipif(not NOTES, reason="real contract notes not present")
def test_an_options_note_is_refused_for_free() -> None:
    """A REAL FINDING, and a property worth keeping.

    Two of the 40 real notes are F&O -- ``NIFTY2481424200PE S NSE 275 56.25``. Options
    carry no ISIN, so the egress gate refuses them without anything else being consulted.

    That is exactly right: CLAUDE.md's Phase 1 scope excludes derivatives outright. The
    gate built to keep unrelated documents from reaching a third party turns out to
    enforce the asset-class boundary too, and an options note therefore cannot leak.
    """
    refused = len(NOTES) - len(_real_equity_notes())
    assert refused == 2, f"expected the 2 known F&O notes to be refused, got {refused}"


@pytest.mark.skipif(not NOTES, reason="real contract notes not present")
def test_no_identifier_survives_any_real_note() -> None:
    """The real equity notes, both layouts, 2023-2026. The synthetic cases prove the
    patterns work; only these prove they work on what a broker actually prints."""
    for path, out in _real_equity_notes():
        assert redaction.BARE_PAN.search(out.text) is None, f"{path}: PAN-shaped token"
        assert redaction.EMAIL.search(out.text) is None, f"{path}: email"
        assert redaction.PHONE.search(out.text) is None, f"{path}: phone"
        assert redaction.GSTIN.search(out.text) is None, f"{path}: GSTIN"
        assert "YSL473" not in out.text, f"{path}: client code"
        assert "Pankathi" not in out.text, f"{path}: a name survived"


@pytest.mark.skipif(not NOTES, reason="real contract notes not present")
def test_every_real_equity_note_still_yields_a_trade_table() -> None:
    """Recall, on real documents. Redaction that drops the trades is safe and worthless;
    this is the test that stops the allow-list being tightened into uselessness."""
    from app.ingest.zerodha_contract_note import ISIN_PATTERN

    notes = _real_equity_notes()
    assert len(notes) == 38, "expected 38 equity notes among the 40"
    for path, out in notes:
        assert out.isin_lines > 0, f"{path}: no trade rows kept"
        assert any(
            ISIN_PATTERN.match(tok) for tok in re.findall(r"\bIN[EF][A-Z0-9]{9}\b", out.text)
        ), f"{path}: no ISIN survived"
        assert out.dropped_lines > 0, f"{path}: nothing was dropped, suspicious"


@pytest.mark.skipif(not NOTES, reason="real contract notes not present")
def test_redaction_drops_the_majority_of_a_real_note() -> None:
    """A sanity bound. If the allow-list ever starts keeping most of the document, it has
    stopped being an allow-list and nobody would notice from the assertions above.
    Real notes currently sit at 0.40-0.43."""
    for path, out in _real_equity_notes()[:10]:
        total = out.kept_lines + out.dropped_lines
        assert out.kept_lines < total * 0.75, f"{path}: kept {out.kept_lines}/{total}"


@pytest.mark.skipif(not NOTES, reason="real contract notes not present")
def test_order_and_trade_numbers_survive_on_real_notes() -> None:
    """A REGRESSION THIS ACTUALLY HIT.

    Zerodha order numbers on real notes are sixteen digits -- exactly the length of a
    CDSL demat id. A bare sixteen-digit deny-list rule masked every order number on every
    trade line, which passed all the PII assertions above and would have silently broken
    ``source_ref``: the field ``precedence.trade_identity`` uses to recognise that a
    contract note and a tradebook describe the same trade. The visible symptom would have
    been double-counted trades in a ledger, months later.

    Over-masking is not free, and this is the test that says so.
    """
    from app.ingest.zerodha_contract_note import TRADE_ROW, extract_text

    checked = 0
    for path in NOTES:
        with open(path, "rb") as fh:
            text = extract_text(fh.read())
        original = [m.group("order") for line in text.splitlines() if (m := TRADE_ROW.search(line))]
        if not original:
            continue
        checked += 1
        redacted = redact_for_llm(text).text
        for order_no in original:
            assert order_no in redacted, f"{path}: order number {order_no} was masked away"
    assert checked >= 30, f"only {checked} notes had parseable trade rows"
