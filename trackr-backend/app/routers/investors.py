"""POST /investors, POST /investors/{id}/accounts -- onboarding.

Every other endpoint in this API takes an ``investor_id`` it assumes already exists.
Before this router, the only way one did was ``app.db.load_golden``'s one-fixture
seed -- an adviser had no way to onboard a second client without hand-writing SQL. See
docs/FULL_VISION_BACKEND_ROADMAP.md section A5.

Onboarding is authenticated and attributed: the creating login becomes
``investor.owner_user_id``, which is what every scoped read authorises against. An
investor created without an owner would be unreachable through the API.

All logic lives in ``app.db.repository``; these handlers only translate between the
wire shape and the repository calls, the same split ``app.routers.transactions`` uses.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user, require_owned_investor
from app.config import Settings, get_settings
from app.database import get_conn
from app.db import repository
from app.db.repository import create_account, create_investor
from app.ingest.addresses import forwarding_addresses
from app.schemas.investors import AccountIn, AccountOut, InvestorIn, InvestorOut

router = APIRouter(prefix="/investors", tags=["onboarding"])


@router.post("", response_model=InvestorOut, status_code=status.HTTP_201_CREATED)
def onboard_investor(
    body: InvestorIn,
    connection: Any = Depends(get_conn),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return create_investor(
        connection,
        code=body.code,
        display_name=body.display_name,
        family_group_id=body.family_group_id,
        pan=body.pan,
        onboarding_date=body.onboarding_date,
        owner_user_id=str(current_user["id"]),
        actor_uid=str(current_user["id"]),
    )


@router.get(
    "/{investor_id}/accounts",
    response_model=list[AccountOut],
    dependencies=[Depends(require_owned_investor)],
)
def list_accounts(
    investor_id: str,
    connection: Any = Depends(get_conn),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    """The investor's broker accounts -- what the Import screen's account selector
    offers, and what makes an already-onboarded account re-fetchable (until now the
    POST response was the only place an account ever appeared, so clients cached it in
    localStorage). Same shape as the POST response, forwarding addresses included."""
    code = repository.get_investor_code(connection, investor_id)
    if code is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no such investor: {investor_id}")
    accounts = repository.list_accounts(connection, investor_id)
    for account in accounts:
        account["forwarding_addresses"] = forwarding_addresses(
            settings.ingest_domain, code, account["broker"]
        )
        account["investor_id"] = investor_id
    return accounts


@router.post(
    "/{investor_id}/accounts",
    response_model=AccountOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_owned_investor)],
)
def onboard_account(
    investor_id: str,
    body: AccountIn,
    connection: Any = Depends(get_conn),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    account = create_account(
        connection,
        investor_id=investor_id,
        broker=body.broker,
        dp_id=body.dp_id,
        client_id=body.client_id,
        is_advised=body.is_advised,
        label=body.label,
    )
    investor_code = account.pop("investor_code")
    account["forwarding_addresses"] = forwarding_addresses(
        settings.ingest_domain, investor_code, account["broker"]
    )
    return account
