"""Refusing a document that belongs to somebody else.

The pure half -- reading identifiers off a page -- is tests/test_ingest_identity.py. This
is the half that needs a database: a PAN hash to compare against, an account with a client
code, and ``stage_batch`` proving that a refusal leaves nothing behind.

The scenario throughout is the one this exists for: an advisor runs several portfolios and
picks the destination account from a dropdown. Picking the wrong one is one click, and
without this check it silently writes one client's trades into another's ledger.
"""

from __future__ import annotations

import os

import pytest
from app.db import crypto, identity
from app.ingest.base import DocumentIdentity

pytestmark = pytest.mark.db

#: Structurally valid, and nobody's.
DOC_PAN = "BEXPD1234F"
OTHER_PAN = "AAAPZ9999Z"


def _set_pan(db, investor_id: str, pan: str) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO investor_secret (investor_id, pan_hash, pan_enc) VALUES (%s,%s,%s) "
            "ON CONFLICT (investor_id) DO UPDATE SET pan_hash = EXCLUDED.pan_hash, "
            "pan_enc = EXCLUDED.pan_enc",
            (investor_id, crypto.hash_pan(pan), crypto.encrypt(pan)),
        )
    db.commit()


def _set_client_id(db, account_id: str, client_id: str) -> None:
    with db.cursor() as cur:
        cur.execute("UPDATE account SET client_id = %s WHERE id = %s", (client_id, account_id))
    db.commit()


@pytest.fixture()
def account_id(investor: str) -> str:
    return os.environ["_TEST_ACCOUNT_ID"]


# --- the PAN check -------------------------------------------------------------


def test_a_matching_pan_passes_with_no_complaint(db, investor, account_id, crypto_env) -> None:
    _set_pan(db, investor, DOC_PAN)
    notes = identity.verify(db, DocumentIdentity(pan=DOC_PAN), investor, account_id)
    assert not any("NOT verified" in n for n in notes)


def test_another_investors_document_is_refused(db, investor, account_id, crypto_env) -> None:
    """THE POINT OF THE FEATURE. The advisor picked the wrong account."""
    _set_pan(db, investor, OTHER_PAN)
    with pytest.raises(identity.IdentityMismatchError) as exc:
        identity.verify(db, DocumentIdentity(pan=DOC_PAN), investor, account_id)
    assert exc.value.field == "PAN"


def test_the_refusal_message_never_contains_a_whole_pan(
    db, investor, account_id, crypto_env
) -> None:
    """A PAN in an error string outlives the request in logs and tracebacks, which is
    exactly what investor_secret exists to prevent."""
    _set_pan(db, investor, OTHER_PAN)
    with pytest.raises(identity.IdentityMismatchError) as exc:
        identity.verify(db, DocumentIdentity(pan=DOC_PAN), investor, account_id)
    message = str(exc.value)
    assert DOC_PAN not in message
    assert OTHER_PAN not in message
    assert crypto.redact_pan(DOC_PAN) in message


def test_pan_case_does_not_decide_the_outcome(db, investor, account_id, crypto_env) -> None:
    _set_pan(db, investor, DOC_PAN)
    identity.verify(db, DocumentIdentity(pan=DOC_PAN.lower()), investor, account_id)


def test_a_mid_rotation_investor_is_not_refused(db, investor, account_id, crypto_env) -> None:
    """docs/KEY_ROTATION.md section 4: during a pepper rotation a lookup must match
    ``pan_hash`` OR ``pan_hash_next``. Checking only the former would turn every
    legitimate contract note into a refusal for as long as the rotation runs.
    """
    # The row's live hash is under some *older* pepper this process cannot compute, and
    # the new hash -- the one hash_pan produces now -- sits in pan_hash_next.
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO investor_secret (investor_id, pan_hash, pan_enc, pan_hash_next) "
            "VALUES (%s,%s,%s,%s)",
            (investor, "hash-under-the-previous-pepper", crypto.encrypt(DOC_PAN),
             crypto.hash_pan(DOC_PAN)),
        )
    db.commit()
    notes = identity.verify(db, DocumentIdentity(pan=DOC_PAN), investor, account_id)
    assert not any("NOT verified" in n for n in notes)


# --- absence is a note, not a refusal ------------------------------------------


def test_an_investor_with_no_pan_on_file_is_flagged_not_refused(
    db, investor, account_id, crypto_env
) -> None:
    """Fail-closed would break every account onboarded without a PAN. The note is what
    makes it honest: the reviewer sees "not verified" before promoting, rather than
    silence they would read as "verified"."""
    notes = identity.verify(db, DocumentIdentity(pan=DOC_PAN), investor, account_id)
    assert any("no PAN on file" in n for n in notes)


def test_a_document_stating_nothing_is_flagged_not_refused(
    db, investor, account_id, crypto_env
) -> None:
    _set_pan(db, investor, DOC_PAN)
    notes = identity.verify(db, DocumentIdentity(), investor, account_id)
    assert any("states no PAN or client code" in n for n in notes)


def test_a_malformed_pan_on_the_page_is_flagged_not_refused(
    db, investor, account_id, crypto_env
) -> None:
    """An OCR or layout slip is not evidence the document belongs to someone else."""
    _set_pan(db, investor, DOC_PAN)
    notes = identity.verify(db, DocumentIdentity(pan="NOTAPAN"), investor, account_id)
    assert any("not structurally valid" in n for n in notes)


# --- the UCC check catches what PAN cannot -------------------------------------


def test_the_right_person_but_the_wrong_account_is_refused(
    db, investor, account_id, crypto_env
) -> None:
    """One person's two Zerodha accounts share a PAN, so the PAN check passes and the
    document still does not belong here. This is the case UCC exists for."""
    _set_pan(db, investor, DOC_PAN)
    _set_client_id(db, account_id, "ABC111")
    with pytest.raises(identity.IdentityMismatchError) as exc:
        identity.verify(
            db, DocumentIdentity(pan=DOC_PAN, client_code="YSL473"), investor, account_id
        )
    assert exc.value.field == "client code"


def test_a_matching_ucc_passes(db, investor, account_id, crypto_env) -> None:
    _set_pan(db, investor, DOC_PAN)
    _set_client_id(db, account_id, "ysl473")  # stored casing must not decide it
    notes = identity.verify(
        db, DocumentIdentity(pan=DOC_PAN, client_code="YSL473"), investor, account_id
    )
    assert not any("NOT verified" in n for n in notes)


def test_an_account_with_no_client_id_is_flagged_not_refused(
    db, investor, account_id, crypto_env
) -> None:
    _set_pan(db, investor, DOC_PAN)
    notes = identity.verify(
        db, DocumentIdentity(pan=DOC_PAN, client_code="YSL473"), investor, account_id
    )
    assert any("no client code on file" in n for n in notes)


# --- a refusal must leave nothing behind ---------------------------------------


#: One real-shaped note. The trade row is a single line on the page and stays one here --
#: split across two, TRADE_ROW stops matching and the fixture silently parses nothing.
NOTE_TEXT = (
    f"CONTRACT NOTE CUM TAX INVOICE\n"
    f"Zerodha Broking Limited\n"
    f"PAN: {DOC_PAN}\n"
    f"UCC: YSL473\n"
    f"Trade Date: 12/08/2026\n"
    f"Order No. Order Time Trade No. Trade Time Security / Contract Description Buy(B) /\n"
    f"1786505400085603080 12:19:40 1089300 12:19:40 WAAREEENER-A/INE377N01017 "
    f"B BSE 18 0.0000 2663.95 (47951.10)\n"
    f"Stamp duty (Rs) (7.00) (7.00)\n"
)


def test_stage_batch_refuses_and_writes_nothing(db, investor, account_id, crypto_env) -> None:
    """The refusal happens before store_document and before the import_batch insert, so
    another investor's note is never written into this investor's document store on its
    way to being turned away."""
    from app.db import imports
    from app.ingest.zerodha_contract_note import ZerodhaContractNoteAdapter

    _set_pan(db, investor, OTHER_PAN)

    with pytest.raises(identity.IdentityMismatchError):
        imports.stage_batch(
            db,
            ZerodhaContractNoteAdapter(),
            NOTE_TEXT.encode(),
            investor_id=investor,
            account_id=account_id,
            filename="contract note.pdf",
            doctype="CONTRACT_NOTE",
            content_type="application/pdf",
        )

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM import_batch")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM import_row")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM document")
        assert cur.fetchone()[0] == 0


def test_stage_batch_stages_the_matching_investors_note(
    db, investor, account_id, crypto_env
) -> None:
    from app.db import imports
    from app.ingest.zerodha_contract_note import ZerodhaContractNoteAdapter

    _set_pan(db, investor, DOC_PAN)
    result = imports.stage_batch(
        db,
        ZerodhaContractNoteAdapter(),
        NOTE_TEXT.encode(),
        investor_id=investor,
        account_id=account_id,
        filename="contract note.pdf",
        doctype="CONTRACT_NOTE",
        content_type="application/pdf",
    )
    assert result["parsed"] == 1


def test_an_adapter_without_identity_is_untouched(db, investor, account_id, crypto_env) -> None:
    """A tradebook CSV carries no PAN. The check must skip entirely rather than treat
    the absence of the method as an unverifiable document."""
    from app.db import imports
    from app.ingest.zerodha_tradebook import ZerodhaTradebookAdapter

    assert not hasattr(ZerodhaTradebookAdapter(), "identity")
    _set_pan(db, investor, OTHER_PAN)
    result = imports.stage_batch(
        db,
        ZerodhaTradebookAdapter(),
        b"symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,"
        b"price,trade_id,order_id,order_execution_time\n"
        b"BLS,INE153T01027,2024-01-10,NSE,EQ,EQ,buy,false,100.000000,200.500000,"
        b"12345,99001,2024-01-10T10:15:00\n",
        investor_id=investor,
        account_id=account_id,
        filename="tradebook.csv",
    )
    assert result["parsed"] == 1
    assert not any("identity" in n for n in result.get("notes", []))
