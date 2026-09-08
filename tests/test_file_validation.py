"""app/ingest/file_validation.py -- the two-tier upload check.

The whole point of this module is that a filename is a claim and the bytes are the fact,
so almost every case here is a deliberate disagreement between the two: a contract note
called ``.csv``, a tradebook saved as a workbook, a ZIP called ``.xlsx``. The tests that
matter most are the ones where a naive extension check would have said yes.

Fixtures are synthesised, not sampled: real broker documents are one investor's financial
history and stay out of the repository (same convention as tests/test_zerodha_tradebook.py).
The PDFs below are hand-assembled minimal files -- five objects and an xref -- because the
only thing under test is which words appear on page one.
"""

from __future__ import annotations

import io
import zipfile

import openpyxl
import pytest
from app.ingest import file_validation as fv

# --- fixtures ------------------------------------------------------------------------

TRADEBOOK_HEADER = (
    "symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,"
    "trade_id,order_id,order_execution_time\n"
)
TRADEBOOK_ROW = (
    "BLS,INE153T01027,2024-01-10,NSE,EQ,EQ,buy,false,100.000000,200.500000,"
    "12345,99001,2024-01-10T10:15:00\n"
)
TRADEBOOK_CSV = (TRADEBOOK_HEADER + TRADEBOOK_ROW).encode()


def minimal_pdf(lines: list[str]) -> bytes:
    """A one-page PDF whose text is exactly ``lines``.

    Hand-built rather than produced by a writer library: nothing here needs fonts,
    compression or a real layout, and adding a PDF-writing dependency to run five
    assertions would be a poor trade.
    """
    text_ops = "BT /F1 12 Tf 40 760 Td 14 TL\n"
    for line in lines:
        text_ops += f"({line}) Tj T*\n"
    text_ops += "ET\n"
    stream = text_ops.encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


CONTRACT_NOTE_PDF = minimal_pdf(
    [
        "ZERODHA BROKING LIMITED",
        "TAX INVOICE cum CONTRACT NOTE",
        "Trade date: 10/01/2024",
    ]
)

CAS_PDF = minimal_pdf(
    [
        "NSDL CONSOLIDATED ACCOUNT STATEMENT",
        "Statement of holding as on 31-MAR-2024",
    ]
)


def workbook_bytes(sheets: dict[str, list[list[object]]]) -> bytes:
    book = openpyxl.Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(title=name)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


CONTRACT_NOTE_CLEAN_XLSX = workbook_bytes(
    {
        "Trades": [["ISIN", "Symbol", "Quantity"], ["INE153T01027", "BLS", 100]],
        "Charges & Net": [["Brokerage", 20]],
        "Note Details": [["Trade Date", "10-01-2024"]],
    }
)

CONTRACT_NOTE_BULK_XLSX = workbook_bytes(
    {
        "10-01-2024": [
            ["TAX INVOICE cum CONTRACT NOTE"],
            ["Order No.", "Trade No.", "Security/Contract Description"],
        ]
    }
)

TRADEBOOK_XLSX = workbook_bytes(
    {
        "Sheet1": [
            ["symbol", "isin", "trade_date", "trade_type", "quantity", "price", "trade_id"],
            ["BLS", "INE153T01027", "2024-01-10", "buy", 100, 200.5, 12345],
        ]
    }
)


# --- tier 1: the extension ------------------------------------------------------------


@pytest.mark.parametrize("name", ["tradebook.csv", "NOTE.XLSX", "note.pdf", "a.b.csv"])
def test_allowed_extensions_pass_tier_one(name: str) -> None:
    assert fv.check_extension(name) is None


@pytest.mark.parametrize("name", ["payload.exe", "notes.txt", "book.xls", "sheet.numbers"])
def test_other_extensions_fail_tier_one(name: str) -> None:
    message = fv.check_extension(name)
    assert message is not None
    assert "PDF, CSV or XLSX" in message


def test_no_extension_is_named_as_the_problem() -> None:
    assert "no file extension" in (fv.check_extension("tradebook") or "")


def test_tier_one_rejects_before_reading_bytes() -> None:
    """A valid tradebook named ``.txt`` still fails: tier 1 is about the claim, and the
    claim is what a browser and a mail gateway both act on."""
    verdict = fv.classify(TRADEBOOK_CSV, "tradebook.txt")
    assert verdict.ok is False
    assert verdict.document == fv.DOC_UNKNOWN


# --- tier 2a: container vs extension --------------------------------------------------


def test_container_is_read_from_magic_bytes() -> None:
    assert fv.sniff_container(CONTRACT_NOTE_PDF) == fv.CONTAINER_PDF
    assert fv.sniff_container(CONTRACT_NOTE_CLEAN_XLSX) == fv.CONTAINER_XLSX
    assert fv.sniff_container(TRADEBOOK_CSV) == fv.CONTAINER_TEXT
    assert fv.sniff_container(b"") == fv.CONTAINER_EMPTY
    assert fv.sniff_container(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest") == fv.CONTAINER_XLS


def test_a_zip_that_is_not_a_workbook_is_not_xlsx() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("statement.pdf", "not really")
    assert fv.sniff_container(buffer.getvalue()) == fv.CONTAINER_ZIP


def test_pdf_renamed_to_csv_is_caught() -> None:
    """The case in the brief: a contract note dropped into a tradebook slot. Tier 1 is
    silent about it -- only the bytes say so."""
    verdict = fv.classify(CONTRACT_NOTE_PDF, "tradebook-2024.csv")
    assert verdict.ok is False
    assert verdict.container == fv.CONTAINER_PDF
    assert "actually a PDF" in (verdict.reason or "")
    assert ".pdf" in (verdict.hint or "")


def test_csv_renamed_to_xlsx_is_caught() -> None:
    verdict = fv.classify(TRADEBOOK_CSV, "contract-note.xlsx")
    assert verdict.ok is False
    assert verdict.container == fv.CONTAINER_TEXT


def test_empty_file_says_so() -> None:
    verdict = fv.classify(b"", "tradebook.csv")
    assert verdict.ok is False
    assert "0 bytes" in (verdict.hint or "")


# --- tier 2b: which document is inside ------------------------------------------------


def test_tradebook_csv_is_recognised_and_routed() -> None:
    verdict = fv.classify(TRADEBOOK_CSV, "tradebook-2024-EQ.csv")
    assert verdict.ok is True
    assert verdict.document == fv.DOC_TRADEBOOK_CSV
    assert verdict.adapter == "zerodha_tradebook"


def test_tradebook_with_leading_junk_rows_still_recognised() -> None:
    """The header is not always on line 1 -- a tradebook pasted through Google Sheets
    carries a title block above it, which is why the adapter scans. This must agree."""
    padded = b"Zerodha Console export\n\n\n" + TRADEBOOK_CSV
    assert fv.classify(padded, "tradebook.csv").document == fv.DOC_TRADEBOOK_CSV


def test_csv_missing_one_column_names_the_column() -> None:
    """A near-miss header is the commonest real failure. Naming the gap turns a dead end
    into a fix, so the missing column must appear in the notes."""
    broken = TRADEBOOK_CSV.replace(b"trade_id,", b"tradeid,")
    verdict = fv.classify(broken, "tradebook.csv")
    assert verdict.ok is False
    assert any("trade_id" in note for note in verdict.notes)


def test_contract_note_pdf_is_recognised() -> None:
    verdict = fv.classify(CONTRACT_NOTE_PDF, "contract-note.pdf")
    assert verdict.ok is True
    assert verdict.document == fv.DOC_CONTRACT_NOTE_PDF
    assert verdict.adapter == "zerodha_contract_note"


def test_cas_pdf_is_recognised_and_refused_with_guidance() -> None:
    """CAS parsing is out of Phase 1 (CLAUDE.md). Recognising one well enough to say
    'this is a holding statement, we need trades' is the whole job."""
    verdict = fv.classify(CAS_PDF, "nsdl-cas.pdf")
    assert verdict.ok is False
    assert verdict.document == fv.DOC_CAS_PDF
    assert "holding statement" in (verdict.reason or "")
    assert "tradebook" in (verdict.hint or "").lower()


def test_cas_wins_over_the_contract_note_marker() -> None:
    """A CAS can quote the words 'contract note' in a transaction narration. Reading it
    as a note we can parse would be a confident wrong answer."""
    both = minimal_pdf(
        [
            "CONSOLIDATED ACCOUNT STATEMENT",
            "Narration: purchase per CONTRACT NOTE 123",
        ]
    )
    assert fv.classify(both, "statement.pdf").document == fv.DOC_CAS_PDF


def test_pdf_with_no_readable_text_is_not_guessed_at() -> None:
    verdict = fv.classify(minimal_pdf([]), "scan.pdf")
    assert verdict.ok is False
    assert any("scanned" in note for note in verdict.notes)


def test_clean_shape_contract_note_xlsx() -> None:
    verdict = fv.classify(CONTRACT_NOTE_CLEAN_XLSX, "ContractNote_2024.xlsx")
    assert verdict.ok is True
    assert verdict.adapter == "zerodha_contract_note_xlsx"


def test_bulk_shape_contract_note_xlsx() -> None:
    verdict = fv.classify(CONTRACT_NOTE_BULK_XLSX, "YSL473_2024.xlsx")
    assert verdict.ok is True
    assert verdict.adapter == "zerodha_contract_note_xlsx"


def test_tradebook_saved_as_workbook_is_refused_with_the_fix() -> None:
    """Right document, wrong container: there is no XLSX tradebook adapter, and telling
    someone to re-export as CSV is a one-click fix. A parse error would not be."""
    verdict = fv.classify(TRADEBOOK_XLSX, "tradebook.xlsx")
    assert verdict.ok is False
    assert verdict.document == fv.DOC_TRADEBOOK_XLSX
    assert "CSV" in (verdict.hint or "")


def test_unknown_workbook_is_refused_without_pretending() -> None:
    other = workbook_bytes({"Sheet1": [["Name", "Address"], ["A", "B"]]})
    verdict = fv.classify(other, "addresses.xlsx")
    assert verdict.ok is False
    assert verdict.document == fv.DOC_UNKNOWN


# --- the slot check -------------------------------------------------------------------


def test_right_file_in_the_wrong_slot_names_both() -> None:
    verdict = fv.classify(TRADEBOOK_CSV, "tradebook.csv")
    narrowed = fv.verdict_for_adapter(verdict, "zerodha_contract_note_xlsx")
    assert narrowed.ok is False
    assert "tradebook" in (narrowed.reason or "").lower()
    assert "contract note" in (narrowed.reason or "").lower()


def test_right_file_in_the_right_slot_passes_through_unchanged() -> None:
    verdict = fv.classify(TRADEBOOK_CSV, "tradebook.csv")
    assert fv.verdict_for_adapter(verdict, "zerodha_tradebook") is verdict


def test_an_already_failed_verdict_is_not_re_explained() -> None:
    """The slot is the lesser problem when the file itself is wrong -- the original
    reason survives rather than being overwritten by 'wrong slot'."""
    verdict = fv.classify(CAS_PDF, "cas.pdf")
    assert fv.verdict_for_adapter(verdict, "zerodha_tradebook") is verdict


# --- nothing here raises --------------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [b"", b"\x00\x01\x02\x03", b"%PDF-1.4 truncated", b"PK\x03\x04 not a zip"],
    ids=["empty", "binary", "truncated-pdf", "fake-zip"],
)
def test_malformed_input_produces_a_verdict_not_an_exception(content: bytes) -> None:
    for name in ("x.csv", "x.xlsx", "x.pdf"):
        verdict = fv.classify(content, name)
        assert verdict.ok is False
        assert verdict.reason


def test_summarise_counts_both_sides() -> None:
    verdicts = [
        fv.classify(TRADEBOOK_CSV, "good.csv"),
        fv.classify(CAS_PDF, "bad.pdf"),
    ]
    assert fv.summarise(verdicts) == {"ok": 1, "rejected": 1}
