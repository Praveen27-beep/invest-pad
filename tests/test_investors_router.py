"""POST /investors, POST /investors/{id}/accounts -- request validation, no database
needed.

``app.schemas.investors`` is the exact boundary FastAPI validates these request bodies
against, the same split ``tests/test_transactions_router.py`` and
``tests/test_reconcile_router.py`` use for their sibling POST endpoints.
"""

from __future__ import annotations

from app.schemas.investors import AccountIn, AccountOut, InvestorIn


def test_investor_requires_code_and_display_name() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        InvestorIn(display_name="Only a name")


def test_investor_family_group_id_and_pan_are_optional() -> None:
    body = InvestorIn(code="C002", display_name="A New Client")
    assert body.family_group_id is None
    assert body.pan is None


def test_investor_onboarding_date_is_optional() -> None:
    body = InvestorIn(code="C002", display_name="A New Client")
    assert body.onboarding_date is None


def test_investor_pan_is_accepted_on_create() -> None:
    """Per the reasonable default chosen for A5: PAN travels on the create-investor
    body rather than a separate call, one round trip."""
    body = InvestorIn(code="C002", display_name="A New Client", pan="AAAPZ1234C")
    assert body.pan == "AAAPZ1234C"


def test_account_requires_broker() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AccountIn()


def test_account_is_advised_defaults_to_true() -> None:
    """docs/DATA_MODEL.md: is_advised is the key flag distinguishing a client's own
    punting from the mandated advisory account -- true is the common case."""
    body = AccountIn(broker="ZERODHA")
    assert body.is_advised is True


def test_account_optional_fields_default_to_none() -> None:
    body = AccountIn(broker="GROWW")
    assert body.dp_id is None
    assert body.client_id is None
    assert body.label is None


def test_account_out_forwarding_addresses_defaults_to_empty() -> None:
    out = AccountOut(id="a1", investor_id="i1", broker="GROWW", is_advised=True)
    assert out.forwarding_addresses == []
