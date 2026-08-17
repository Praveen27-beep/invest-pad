"""Compliance scaffolding: consent, encryption, export, erasure, retention.

These are the DPDP and SEBI obligations expressed as behaviour rather than documentation.
The gate `COMPLIANCE.md` sets is that they work BEFORE client data lands, so every one of
them is tested against a real database here rather than asserted in prose.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest
from app.db import audit, consent, crypto, privacy, repository, retention
from app.engine.types import Source, Transaction, TxnType

pytestmark = pytest.mark.db

PAN = "AAAPZ1234C"


def txn(ref: str = "T1") -> Transaction:
    return Transaction(
        isin="INE153T01027",
        txn_date=date(2024, 1, 10),
        txn_type=TxnType.BUY,
        quantity=Decimal("100"),
        price=Decimal("200"),
        account_id=os.environ["_TEST_ACCOUNT_ID"],
        source=Source.TRADEBOOK,
        source_ref=ref,
    )


# --- encryption ----------------------------------------------------------------


def test_encryption_round_trips(crypto_env) -> None:
    assert crypto.decrypt(crypto.encrypt(PAN)) == PAN


def test_ciphertext_does_not_contain_the_plaintext(crypto_env) -> None:
    assert PAN.encode() not in crypto.encrypt(PAN)


def test_a_wrong_key_fails_loudly(crypto_env, monkeypatch) -> None:
    """Authenticated encryption: a wrong key raises rather than returning plausible junk."""
    from cryptography.fernet import InvalidToken

    ciphertext = crypto.encrypt(PAN)
    monkeypatch.setenv(crypto.ENCRYPTION_KEY_ENV, crypto.generate_key())
    with pytest.raises(InvalidToken):
        crypto.decrypt(ciphertext)


def test_missing_key_raises_rather_than_storing_plaintext(monkeypatch) -> None:
    """Silent degradation is how a column everyone believes is ciphertext turns out
    to be readable."""
    monkeypatch.delenv(crypto.ENCRYPTION_KEY_ENV, raising=False)
    with pytest.raises(crypto.EncryptionNotConfiguredError):
        crypto.encrypt(PAN)


def test_pan_hash_is_stable_and_peppered(crypto_env, monkeypatch) -> None:
    first = crypto.hash_pan(PAN)
    assert first == crypto.hash_pan(PAN.lower()), "normalised before hashing"

    monkeypatch.setenv(crypto.PAN_PEPPER_ENV, "a-different-pepper")
    assert crypto.hash_pan(PAN) != first, "the pepper must actually participate"


def test_missing_pepper_raises(crypto_env, monkeypatch) -> None:
    monkeypatch.delenv(crypto.PAN_PEPPER_ENV, raising=False)
    with pytest.raises(crypto.EncryptionNotConfiguredError):
        crypto.hash_pan(PAN)


def test_invalid_pan_is_rejected(crypto_env) -> None:
    with pytest.raises(crypto.InvalidPANError):
        crypto.normalise_pan("NOTAPAN123")


def test_redaction_keeps_correlation_without_disclosure() -> None:
    """First two and last two characters survive; the rest is masked.

    Enough to tell two log lines apart, or recognise the same PAN twice. Not enough to be
    one. Derived from PAN rather than hardcoded, so this test carries no identifier itself.
    """
    redacted = crypto.redact_pan(PAN)
    assert redacted == f"{PAN[:2]}{'X' * (len(PAN) - 4)}{PAN[-2:]}"
    assert PAN not in redacted
    assert redacted.count("X") == len(PAN) - 4
    assert crypto.redact_pan(PAN) == redacted, "stable, so two log lines can be matched"


def test_secrets_live_in_their_own_table(db, investor, crypto_env) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO investor_secret (investor_id, pan_hash, pan_enc) VALUES (%s,%s,%s)",
            (investor, crypto.hash_pan(PAN), crypto.encrypt(PAN)),
        )
        cur.execute("SELECT pan_enc FROM investor_secret WHERE investor_id = %s", (investor,))
        assert crypto.decrypt(cur.fetchone()[0]) == PAN

        # and not on the investor row itself
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'investor'"
        )
        assert "pan" not in {r[0] for r in cur.fetchall()}


# --- consent -------------------------------------------------------------------


def test_consent_gate_refuses_without_a_grant(db, investor) -> None:
    with pytest.raises(consent.ConsentMissingError):
        consent.require_consent(db, investor)


def test_consent_gate_passes_once_granted(db, investor) -> None:
    consent.record_consent(db, investor, notice_version="v1", evidence_ref="msg-1")
    consent.require_consent(db, investor)
    assert consent.has_live_consent(db, investor)


def test_withdrawal_takes_effect_immediately(db, investor) -> None:
    consent.record_consent(db, investor, notice_version="v1", evidence_ref="msg-1")
    assert consent.withdraw_consent(db, investor) == 1
    assert not consent.has_live_consent(db, investor)
    with pytest.raises(consent.ConsentMissingError):
        consent.require_consent(db, investor)


def test_regrant_is_a_new_row_not_an_edit(db, investor) -> None:
    """The history of what was agreed, and under which notice version, must survive."""
    consent.record_consent(db, investor, notice_version="v1", evidence_ref="msg-1")
    consent.withdraw_consent(db, investor)
    consent.record_consent(db, investor, notice_version="v2", evidence_ref="msg-2")

    with db.cursor() as cur:
        cur.execute(
            "SELECT notice_version, withdrawn_at FROM client_consent "
            "WHERE investor_id = %s ORDER BY consent_given_at",
            (investor,),
        )
        rows = cur.fetchall()
    assert [r[0] for r in rows] == ["v1", "v2"]
    assert rows[0][1] is not None and rows[1][1] is None


def test_consent_events_are_audited(db, investor) -> None:
    consent.record_consent(db, investor, notice_version="v1", evidence_ref="msg-1")
    consent.withdraw_consent(db, investor)
    with db.cursor() as cur:
        cur.execute("SELECT action FROM audit_log ORDER BY ts")
        actions = [r[0] for r in cur.fetchall()]
    assert audit.ACTION_CONSENT_GIVEN in actions
    assert audit.ACTION_CONSENT_WITHDRAWN in actions


# --- export --------------------------------------------------------------------


def test_export_returns_the_investors_data(db, investor) -> None:
    consent.record_consent(db, investor, notice_version="v1", evidence_ref="msg-1")
    repository.save_transactions(db, [txn("A"), txn("B")])

    export = privacy.export_investor(db, investor)
    assert export["investor"]["code"] == "C001"
    assert len(export["transactions"]) == 2
    assert len(export["accounts"]) == 1
    assert len(export["consents"]) == 1


def test_export_omits_identifiers_unless_asked(db, investor, crypto_env) -> None:
    """Decrypting identifiers nobody asked for widens the blast radius of the export file."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO investor_secret (investor_id, pan_hash, pan_enc) VALUES (%s,%s,%s)",
            (investor, crypto.hash_pan(PAN), crypto.encrypt(PAN)),
        )
    assert "identifiers" not in privacy.export_investor(db, investor)

    with_ids = privacy.export_investor(db, investor, include_identifiers=True)
    assert with_ids["identifiers"]["pan"] == PAN


def test_reading_identifiers_is_audited_as_an_access_event(db, investor, crypto_env) -> None:
    """DPDP treats access to personal data as something the principal may be told about."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO investor_secret (investor_id, pan_enc) VALUES (%s,%s)",
            (investor, crypto.encrypt(PAN)),
        )
    privacy.export_investor(db, investor, include_identifiers=True)
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_log WHERE action = %s",
                    (audit.ACTION_SECRET_READ,))
        assert cur.fetchone()[0] == 1


# --- erasure -------------------------------------------------------------------


def test_erasure_removes_everything_about_the_investor(db, investor) -> None:
    repository.save_transactions(db, [txn()])
    result = privacy.erase_investor(db, investor)
    assert result["investors"] == 1
    assert result["transactions"] == 1

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM investor WHERE id = %s", (investor,))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM transaction")
        assert cur.fetchone()[0] == 0


def test_erasure_is_refused_under_legal_hold(db, investor) -> None:
    """A cleanup must never quietly destroy evidence in a live dispute."""
    repository.save_transactions(db, [txn()])
    privacy.place_legal_hold(db, investor, reason="SEBI complaint 2026/114")

    with pytest.raises(privacy.LegalHoldError) as excinfo:
        privacy.erase_investor(db, investor)
    assert "SEBI complaint" in str(excinfo.value)

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM transaction")
        assert cur.fetchone()[0] == 1, "nothing deleted"


def test_erasure_proceeds_once_the_hold_is_released(db, investor) -> None:
    hold_id = privacy.place_legal_hold(db, investor, reason="dispute")
    privacy.release_legal_hold(db, hold_id)
    assert privacy.erase_investor(db, investor)["investors"] == 1


def test_the_audit_trail_survives_erasure(db, investor) -> None:
    """Erasing the evidence that you erased would defeat both regimes."""
    repository.save_transactions(db, [txn()])
    privacy.erase_investor(db, investor)

    with db.cursor() as cur:
        cur.execute("SELECT action FROM audit_log WHERE entity_id = %s", (investor,))
        actions = {r[0] for r in cur.fetchall()}
    assert audit.ACTION_ERASURE in actions


def test_erasure_authorisation_does_not_leak_past_its_transaction(db, investor) -> None:
    """SET LOCAL expires with the transaction; a later delete must be refused again."""
    import psycopg

    second = os.environ["_TEST_ACCOUNT_ID"]
    repository.save_transactions(db, [txn()])
    privacy.erase_investor(db, investor)
    db.commit()

    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO investor (code, display_name) VALUES ('C002','Two') RETURNING id"
        )
        other = str(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO account (id, investor_id, broker) VALUES (%s,%s,'ZERODHA')",
            (second, other),
        )
        cur.execute(
            "INSERT INTO transaction (account_id, isin, txn_date, txn_type, quantity, "
            "price, source, dedupe_key) VALUES (%s,'INE153T01027','2024-01-10','BUY',"
            "1,1,'MANUAL','later')",
            (second,),
        )
    db.commit()

    with db.cursor() as cur, pytest.raises(psycopg.errors.RestrictViolation):
        cur.execute("DELETE FROM transaction")
    db.rollback()


# --- retention -----------------------------------------------------------------


def test_retention_defaults_to_five_years(db) -> None:
    """SEBI Reg. 19 governs and exceeds DPDP's 1-year log minimum."""
    assert retention.retain_years(db, "audit_log") == 5
    assert retention.retain_years(db, "transaction") == 5
    assert retention.retain_years(db, "unknown_entity") == retention.DEFAULT_RETAIN_YEARS


def test_cutoff_is_five_years_back(db) -> None:
    assert retention.cutoff(db, "investor", date(2026, 8, 13)) == date(2021, 8, 13)


def test_recent_activity_is_not_due_for_deletion(db, investor) -> None:
    repository.save_transactions(db, [txn()])
    assert retention.due_for_deletion(db, date(2026, 8, 13)) == []


def test_old_records_become_due(db, investor) -> None:
    """Retention runs from the LAST interaction, not the first."""
    repository.save_transactions(db, [txn()])
    due = retention.due_for_deletion(db, date(2035, 1, 1))
    assert [d["code"] for d in due] == ["C001"]


def test_held_investors_are_never_due(db, investor) -> None:
    repository.save_transactions(db, [txn()])
    privacy.place_legal_hold(db, investor, reason="litigation")
    assert retention.due_for_deletion(db, date(2035, 1, 1)) == []


def test_due_for_deletion_only_reports(db, investor) -> None:
    """Automatic destruction on a timer should require a human to look at a list first."""
    repository.save_transactions(db, [txn()])
    retention.due_for_deletion(db, date(2035, 1, 1))
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM transaction")
        assert cur.fetchone()[0] == 1


def test_leap_day_cutoff_steps_back_not_forward(db) -> None:
    """A cutoff landing later than intended destroys something a day early."""
    assert retention.cutoff(db, "investor", date(2028, 2, 29)) == date(2023, 2, 28)
