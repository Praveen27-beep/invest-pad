"""Inbound-parse webhook handler for ``POST /ingest/email``.

docs/INGESTION.md "Adapter 3 -- Gmail forwarding": routing is by the ``to`` address
alone, NEVER by sniffing content -- Zerodha alone sends at least four document types
from one sender address, so content sniffing misclassifies and address routing cannot.

This module resolves investor + account + adapter from the address, unlocks a
password-protected PDF per the documented per-broker rule, and stages the parse via
``app.db.imports.stage_batch`` -- which itself stores the raw bytes before parsing, per
"Where documents land". It does not parse anything itself and does not decide source
precedence: it is glue over modules that already exist and are already tested.

Nothing here writes to the ledger. Staging only -- promotion is a separate, authenticated
call (``app/routers/ingest.py``), per "Staging: why nothing auto-commits".
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from app.db import consent, crypto, imports
from app.ingest.base import Adapter
from app.ingest.zerodha_contract_note import ZerodhaContractNoteAdapter

#: broker -> the case transform applied to the investor's PAN to unlock a contract-note
#: PDF. docs/INGESTION.md "PDF password rules -- a real trap": a single hardcoded case
#: silently breaks the brokers that disagree, so this stays a per-broker lookup.
PDF_PASSWORD_CASE = {
    "zerodha": str.upper,
    "groww": str.upper,
    "upstox": str.lower,
}

#: (broker, doctype) -> adapter factory, taking the unlocked PDF password. Only
#: combinations with a real, tested parser are listed -- CLAUDE.md: never invent parsing
#: logic for a source the codebase does not yet handle. A combination absent here is a
#: named gap, not a guess.
_ADAPTER_FACTORIES: dict[tuple[str, str], Any] = {
    ("zerodha", "contractnote"): lambda password: ZerodhaContractNoteAdapter(password=password),
}


class UnroutableAddressError(ValueError):
    """The ``to`` address is not ``{investor_code}-{broker}-{doctype}@...``."""


class NoSuchInvestorError(LookupError):
    """No investor with this code."""


class NoMatchingAccountError(LookupError):
    """The investor has no account for this broker."""


class UnsupportedDocumentError(ValueError):
    """No adapter exists yet for this (broker, doctype) pair."""


@dataclass(frozen=True, slots=True)
class RoutedAddress:
    investor_code: str
    broker: str
    doctype: str


def parse_to_address(to: str) -> RoutedAddress:
    """``{investor_code}-{broker}-{doctype}@domain`` -> its three segments.

    Raises:
        UnroutableAddressError: the local part is not exactly three non-empty,
            hyphen-separated segments.
    """
    local = to.split("@", 1)[0]
    parts = local.split("-")
    if len(parts) != 3 or not all(parts):
        raise UnroutableAddressError(f"not a routable ingest address: {to!r}")
    code, broker, doctype = parts
    return RoutedAddress(code.strip().lower(), broker.strip().lower(), doctype.strip().lower())


def resolve_investor(conn: Any, investor_code: str) -> tuple[str, str]:
    """``(investor_id, investor_code)`` for the code in the address."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, code FROM investor WHERE lower(code) = %s", (investor_code,))
        row = cur.fetchone()
    if row is None:
        raise NoSuchInvestorError(investor_code)
    return str(row[0]), row[1]


def resolve_account(conn: Any, investor_id: str, broker: str) -> str:
    """The account this broker's documents belong to."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM account WHERE investor_id = %s AND lower(broker) = %s LIMIT 1",
            (investor_id, broker),
        )
        row = cur.fetchone()
    if row is None:
        raise NoMatchingAccountError(f"investor has no account for broker {broker!r}")
    return str(row[0])


def _pdf_password(conn: Any, investor_id: str, broker: str) -> str:
    """PAN, cased per broker. Empty string when no PAN is on file or the broker has no
    documented password rule -- unlocking then fails inside pdfplumber, which is the
    honest outcome. Guessing a password is worse than failing to open the file."""
    case = PDF_PASSWORD_CASE.get(broker)
    if case is None:
        return ""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pan_enc FROM investor_secret WHERE investor_id = %s", (investor_id,)
        )
        row = cur.fetchone()
    if row is None or row[0] is None:
        return ""
    return case(crypto.decrypt(row[0]))


def adapter_for(conn: Any, investor_id: str, broker: str, doctype: str) -> Adapter:
    factory = _ADAPTER_FACTORIES.get((broker, doctype))
    if factory is None:
        raise UnsupportedDocumentError(f"no adapter for broker={broker!r} doctype={doctype!r}")
    return factory(_pdf_password(conn, investor_id, broker))


def handle_inbound_email(
    conn: Any,
    store: Any,
    to: str,
    attachments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Stage every attachment on one inbound message. Returns one ``stage_batch`` result
    per attachment.

    All attachments on one message share a single connection (``app.database.get_conn``
    -- one per request), so letting ``DuplicateUploadError`` propagate out of this loop
    would roll back every attachment already staged ahead of it in the same message,
    including ones that were legitimately new. Each attachment is independent instead:
    a duplicate is caught right here and reported inline, alongside whatever else in
    the message staged cleanly.

    Raises:
        UnroutableAddressError, NoSuchInvestorError, NoMatchingAccountError,
        UnsupportedDocumentError: routing failed before anything was staged.
        ConsentMissingError: routing succeeded but this investor has no live consent --
            checked last, after routing/account/adapter resolution, so those errors
            keep naming the actual routing problem instead of being masked by a 403.
    """
    routed = parse_to_address(to)
    investor_id, investor_code = resolve_investor(conn, routed.investor_code)
    account_id = resolve_account(conn, investor_id, routed.broker)
    adapter = adapter_for(conn, investor_id, routed.broker, routed.doctype)
    consent.require_consent(conn, investor_id)

    results = []
    for attachment in attachments:
        content = base64.b64decode(attachment["content_b64"])
        try:
            result = imports.stage_batch(
                conn,
                adapter,
                content,
                investor_id=investor_id,
                account_id=account_id,
                filename=attachment.get("filename", ""),
                store=store,
                investor_code=investor_code,
                actor_uid=None,
            )
        except imports.DuplicateUploadError as exc:
            results.append(
                {
                    "batch_id": exc.batch_id,
                    "parsed": 0,
                    "rejected": 0,
                    "sha256": exc.sha256,
                    "document_id": None,
                    "notes": [f"skipped: identical file already staged as batch {exc.batch_id}"],
                }
            )
            continue
        results.append(result)
    return results
