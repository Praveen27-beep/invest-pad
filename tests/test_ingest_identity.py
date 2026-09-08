"""Reading a document's stated owner off the page.

The comparison against an account lives in ``app.db.identity`` and is tested against a
real database in tests/test_db_identity.py. This file is the pure half: text in,
identifiers out, no connection and no pepper.
"""

from __future__ import annotations

import glob
import os

import pytest
from app.ingest.base import DocumentIdentity
from app.ingest.zerodha_contract_note import ZerodhaContractNoteAdapter, parse_identity

#: Same switch tests/test_zerodha_contract_note.py uses -- real broker documents stay out
#: of the repository.
LOCAL_DOCS = os.environ.get("PORTFOLIO_LOCAL_DOCS", "")
NOTES = sorted(glob.glob(f"{LOCAL_DOCS}/[Cc]ontract note*.pdf"))

HEADER = """CONTRACT NOTE CUM TAX INVOICE
Zerodha Broking Limited
SEBI registration: INZ000031633
PAN: BEXPD1234F
UCC: YSL473
Trade Date: 12/08/2026
"""


def test_pan_and_ucc_are_read_from_the_header() -> None:
    identity = parse_identity(HEADER)
    assert identity.pan == "BEXPD1234F"
    assert identity.client_code == "YSL473"


def test_the_brokers_own_pan_inside_its_gstin_is_not_mistaken_for_the_clients() -> None:
    """THE TRAP THIS EXISTS FOR.

    A contract note is a note *cum tax invoice*, so it carries the broker's GSTIN -- and a
    GSTIN embeds a PAN. All 40 real notes contain exactly two PAN-shaped tokens. Matching
    the wrong one would "verify" every investor against Zerodha's own PAN, which passes
    universally and therefore checks nothing.
    """
    text = HEADER + "\nGSTIN: 29AABCZ1234M1ZK\n"
    assert parse_identity(text).pan == "BEXPD1234F"


def test_label_variants_all_parse() -> None:
    """Zerodha prints "PAN:"; the wording differs across brokers and note vintages."""
    for label in ("PAN: BEXPD1234F", "PAN No: BEXPD1234F", "PAN of Client : BEXPD1234F"):
        assert parse_identity(label).pan == "BEXPD1234F", label


def test_a_document_stating_nothing_yields_an_empty_identity() -> None:
    identity = parse_identity("CONTRACT NOTE\nTrade Date: 12/08/2026\n")
    assert identity.pan == ""
    assert identity.client_code == ""
    assert not identity, "an identity with nothing in it must be falsy"


def test_identity_is_falsy_only_when_wholly_empty() -> None:
    assert DocumentIdentity(pan="BEXPD1234F")
    assert DocumentIdentity(client_code="YSL473")
    assert not DocumentIdentity()


def test_lowercase_is_normalised_upward() -> None:
    """PAN casing varies by broker -- app.db.crypto.normalise_pan says so, and the hash
    is computed over the normalised form, so this must not depend on how it was printed."""
    assert parse_identity("pan: bexpd1234f\nucc: ysl473").pan == "BEXPD1234F"
    assert parse_identity("pan: bexpd1234f\nucc: ysl473").client_code == "YSL473"


def test_unreadable_bytes_yield_an_empty_identity_rather_than_raising() -> None:
    """``parse`` is called on the same bytes moments later and reports the real reason.
    Raising here would replace "could not read PDF" with an identity complaint."""
    assert not ZerodhaContractNoteAdapter().identity(b"\xff\xfe\x00garbage")


def test_the_adapter_satisfies_the_identifying_protocol() -> None:
    from app.ingest.base import IdentifyingAdapter

    assert isinstance(ZerodhaContractNoteAdapter(), IdentifyingAdapter)


# --- against the 40 real notes -------------------------------------------------


@pytest.mark.skipif(not NOTES, reason="real contract notes not present")
def test_every_real_note_states_a_pan_and_a_ucc() -> None:
    """Pinned because it is what makes the check worth having: identity is present on
    100% of real notes across both layouts and 2023-2026, so a missing one means the
    regex broke, not that the format varies.
    """
    adapter = ZerodhaContractNoteAdapter()
    pans, uccs = set(), set()
    for path in NOTES:
        with open(path, "rb") as fh:
            identity = adapter.identity(fh.read())
        assert identity.pan, f"{path}: no PAN found"
        assert identity.client_code, f"{path}: no UCC found"
        pans.add(identity.pan)
        uccs.add(identity.client_code)

    # One client's history: one PAN, one UCC. Two would mean the broker's own PAN leaked
    # into the result on some notes and not others.
    assert len(pans) == 1, "more than one PAN across one client's notes"
    assert uccs == {"YSL473"}


# --- the XLSX export states the same two identifiers ---------------------------

BULK_XLSX = sorted(glob.glob(f"{LOCAL_DOCS}/YSL473_*.xlsx"))


def _bulk_workbook_with(*header_rows: list) -> bytes:
    """A minimal bulk-shaped workbook -- just the header block ``identity`` reads."""
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "19-10-2022"
    ws.append(["CONTRACT NOTE CUM TAX INVOICE"])
    for row in header_rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_xlsx_identity_is_read_from_cells_split_across_columns() -> None:
    """The XLSX states "PAN of Client:" in one cell and the value in another, so the
    label and value are only adjacent once the row is flattened back into text."""
    from app.ingest.zerodha_contract_note_xlsx import ZerodhaContractNoteXlsxAdapter

    content = _bulk_workbook_with(
        ["PAN of Client:", None, "BEXPD1234F"],
        ["UCC of Client:", None, "YSL473"],
    )
    identity = ZerodhaContractNoteXlsxAdapter().identity(content)
    assert identity.pan == "BEXPD1234F"
    assert identity.client_code == "YSL473"


def test_the_ucc_footnote_is_not_mistaken_for_a_ucc() -> None:
    """Every real sheet also carries "*Trading / Back Office Code (If different from
    UCC)" -- a second occurrence of the word with no code after it."""
    from app.ingest.zerodha_contract_note_xlsx import ZerodhaContractNoteXlsxAdapter

    content = _bulk_workbook_with(
        ["UCC of Client:", None, "YSL473"],
        ["*Trading / Back Office Code (If different from UCC)"],
    )
    assert ZerodhaContractNoteXlsxAdapter().identity(content).client_code == "YSL473"


def test_an_unreadable_workbook_yields_an_empty_identity() -> None:
    from app.ingest.zerodha_contract_note_xlsx import ZerodhaContractNoteXlsxAdapter

    assert not ZerodhaContractNoteXlsxAdapter().identity(b"not a workbook at all")


@pytest.mark.skipif(not BULK_XLSX, reason="real xlsx exports not present")
def test_every_real_bulk_export_states_its_client() -> None:
    from app.ingest.zerodha_contract_note_xlsx import ZerodhaContractNoteXlsxAdapter

    adapter = ZerodhaContractNoteXlsxAdapter()
    for path in BULK_XLSX:
        with open(path, "rb") as fh:
            identity = adapter.identity(fh.read())
        assert identity.pan, f"{path}: no PAN"
        assert identity.client_code == "YSL473", f"{path}: unexpected UCC"


def test_a_word_merely_containing_pan_is_not_a_label() -> None:
    """Real notes name a compliance officer, "Pankathi H Jain". Without a word boundary
    the label matches inside that name, and the next PAN-shaped token on the line wins.
    """
    assert not parse_identity("Compliance officer: Pankathi H Jain BEXPD1234F").pan
    assert parse_identity("Compliance officer: Pankathi H Jain\nPAN: BEXPD1234F").pan
