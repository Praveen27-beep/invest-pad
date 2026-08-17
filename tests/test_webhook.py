"""app/ingest/webhook.py -- the pieces that don't touch a database connection.

``parse_to_address`` and ``PDF_PASSWORD_CASE`` are pure. Everything else in this module
(``resolve_investor``, ``resolve_account``, ``adapter_for``, ``handle_inbound_email``)
takes a real ``conn`` and is out of scope for this suite -- it belongs in a
``pytest.mark.db`` file this session was not asked to add.
"""

from __future__ import annotations

import pytest
from app.ingest.webhook import (
    PDF_PASSWORD_CASE,
    RoutedAddress,
    UnroutableAddressError,
    parse_to_address,
)

# --- parse_to_address ---------------------------------------------------------------


def test_parses_the_three_hyphen_separated_segments() -> None:
    assert parse_to_address("c001-zerodha-contractnote@ingest.example.com") == RoutedAddress(
        investor_code="c001", broker="zerodha", doctype="contractnote"
    )


def test_lowercases_and_strips_each_segment() -> None:
    routed = parse_to_address(" C001 - ZERODHA -ContractNote@ingest.example.com")
    assert routed == RoutedAddress(investor_code="c001", broker="zerodha", doctype="contractnote")


def test_missing_at_sign_still_parses_from_the_whole_string() -> None:
    """``to.split("@", 1)[0]`` on a string with no ``@`` returns the whole string --
    documenting the behaviour rather than assuming a webhook payload's ``to`` always
    contains one."""
    assert parse_to_address("c001-zerodha-contractnote") == RoutedAddress(
        investor_code="c001", broker="zerodha", doctype="contractnote"
    )


def test_rejects_too_few_segments() -> None:
    with pytest.raises(UnroutableAddressError):
        parse_to_address("c001-zerodha@ingest.example.com")


def test_rejects_too_many_segments() -> None:
    with pytest.raises(UnroutableAddressError):
        parse_to_address("c001-zerodha-contractnote-extra@ingest.example.com")


def test_rejects_an_empty_segment() -> None:
    with pytest.raises(UnroutableAddressError):
        parse_to_address("c001--contractnote@ingest.example.com")


def test_rejects_a_local_part_with_no_hyphens_at_all() -> None:
    with pytest.raises(UnroutableAddressError):
        parse_to_address("notroutable@ingest.example.com")


def test_error_message_names_the_offending_address() -> None:
    with pytest.raises(UnroutableAddressError, match=r"bad-address@ingest\.example\.com"):
        parse_to_address("bad-address@ingest.example.com")


# --- PDF_PASSWORD_CASE ----------------------------------------------------------------


def test_zerodha_and_groww_uppercase_the_pan() -> None:
    assert PDF_PASSWORD_CASE["zerodha"]("abcde1234f") == "ABCDE1234F"
    assert PDF_PASSWORD_CASE["groww"]("abcde1234f") == "ABCDE1234F"


def test_upstox_lowercases_the_pan() -> None:
    assert PDF_PASSWORD_CASE["upstox"]("ABCDE1234F") == "abcde1234f"


def test_only_the_three_documented_brokers_have_a_case_rule() -> None:
    """A broker missing here isn't a bug -- ``_pdf_password`` treats absence as 'no
    documented password rule' and falls back to an empty password -- but pinning the
    exact set means a silent fourth entry doesn't slip in unnoticed."""
    assert set(PDF_PASSWORD_CASE) == {"zerodha", "groww", "upstox"}


def test_an_undocumented_broker_is_absent_rather_than_defaulted() -> None:
    assert PDF_PASSWORD_CASE.get("unknownbroker") is None
