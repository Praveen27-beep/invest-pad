"""POST/GET /investors/{id}/corporate-actions, POST /investors/{id}/corporate-actions/match
-- verified corporate-action reference data, and the MProfit-style "Apply" step that
matches it against a reconciliation mismatch and stages the result.

Review, promote and discard are NOT duplicated here: a batch ``/match`` stages lands in
the same ``import_batch``/``import_row`` tables a file upload does, so the existing
``GET /ingest/stage/{batch_id}``, ``POST /ingest/stage/{batch_id}/promote`` and
``POST /ingest/stage/{batch_id}/discard`` endpoints (app/routers/ingest.py) handle it
unchanged. Nothing here writes to the ledger.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import assert_owned_investor, get_current_user, require_owned_investor
from app.auth.ops import require_cron_secret, require_ops_key
from app.database import get_conn, money
from app.db import corporate_actions as ca_db
from app.db import holdings as db_holdings
from app.db import repository
from app.engine.corporate_actions import (
    CorpActionType,
    CorporateAction,
    CorporateActionRatioError,
    Verification,
)
from app.schemas.corporate_actions import (
    CorporateActionIn,
    CorporateActionOut,
    DiscoverYfinanceOut,
    DisputeCorporateActionIn,
    MatchCorporateActionsOut,
    MatchCorporateActionsRequest,
    RefreshCorporateActionFeedOut,
    WaivePriceEvidenceIn,
)

router = APIRouter(prefix="/investors", tags=["ops"])

#: Separate from ``router`` above on purpose: everything below is global reference-data
#: administration (the ``corporate_action`` table, and the automated feed that
#: populates it), never scoped to one investor's own ledger the way
#: ``/investors/{id}/corporate-actions`` is -- see ``docs/DATA_MODEL.md``'s
#: ``corporate_action`` section. Gated by the same ``X-Ops-Key``/``CRON_SECRET`` shared
#: secrets ``app.routers.analytical``'s ``/ops/*`` routes use, not a user login, for the
#: identical reason: this mutates reference data that affects every investor at once.
ops_router = APIRouter(prefix="/ops/corporate-actions", tags=["ops"])


def _to_action(body: CorporateActionIn) -> CorporateAction:
    try:
        return CorporateAction(
            isin=body.isin,
            action_type=CorpActionType(body.action_type),
            ex_date=body.ex_date,
            source=body.source,
            source_url=body.source_url,
            verification=Verification(body.verification),
            bonus_new=body.bonus_new,
            bonus_for=body.bonus_for,
            face_value_before=body.face_value_before,
            face_value_after=body.face_value_after,
            resulting_isin=body.resulting_isin,
            demerger_new=body.demerger_new,
            demerger_for=body.demerger_for,
            price_cum=body.price_cum,
            price_ex=body.price_ex,
            notes=body.notes,
        )
    except (CorporateActionRatioError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


def _out(a: CorporateAction) -> dict[str, Any]:
    return {
        "id": a.id,
        "isin": a.isin,
        "action_type": a.action_type.value,
        "ex_date": a.ex_date,
        "bonus_new": a.bonus_new,
        "bonus_for": a.bonus_for,
        "face_value_before": money(a.face_value_before),
        "face_value_after": money(a.face_value_after),
        "resulting_isin": a.resulting_isin,
        "demerger_new": a.demerger_new,
        "demerger_for": a.demerger_for,
        "price_cum": money(a.price_cum),
        "price_ex": money(a.price_ex),
        "source": a.source,
        "source_url": a.source_url,
        "verification": a.verification.value,
        "notes": a.notes,
        "price_waived": a.price_waived,
        "price_waiver_reason": a.price_waiver_reason,
    }


@router.post(
    "/{investor_id}/corporate-actions",
    response_model=CorporateActionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_owned_investor)],
)
def add_corporate_action(
    investor_id: str,
    body: CorporateActionIn,
    conn: Any = Depends(get_conn),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Manual/bulk entry of one verified corporate action -- the same product shape as
    MProfit's Bulk Corporate Action form (security, date, action type, the primitive
    ratio facts). ``investor_id`` gates who may add a record; the record itself is
    security-wide reference data, not scoped to one investor's ledger."""
    action = _to_action(body)
    try:
        action_id = ca_db.add_corporate_action(conn, action, actor_uid=current_user["id"])
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{action.action_type.value} on {action.isin} dated {action.ex_date} "
            "is already on file",
        ) from exc
    return _out(replace(action, id=action_id))


@router.get(
    "/{investor_id}/corporate-actions",
    response_model=list[CorporateActionOut],
    dependencies=[Depends(require_owned_investor)],
)
def list_corporate_actions(
    investor_id: str,
    isin: str | None = Query(default=None),
    conn: Any = Depends(get_conn),
) -> list[dict[str, Any]]:
    """Every corporate action on file, optionally filtered to one ISIN. ``investor_id``
    gates access only -- see ``add_corporate_action``'s docstring."""
    actions = ca_db.list_corporate_actions(conn, [isin] if isin else None)
    return [_out(a) for a in actions]


@router.post(
    "/{investor_id}/corporate-actions/match",
    response_model=MatchCorporateActionsOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def match_corporate_actions(
    investor_id: str,
    body: MatchCorporateActionsRequest,
    conn: Any = Depends(get_conn),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """The "Apply" step: reconcile this account against ``body.holdings``, match any
    mismatch against verified corporate actions on file, and stage the result.

    Never applied silently. The caller reviews and promotes through the existing
    ``GET /ingest/stage/{batch_id}`` / ``POST /ingest/stage/{batch_id}/promote``
    endpoints, exactly as for a file upload -- see this module's docstring.

    ``body.holdings`` may be omitted, in which case the declared side comes from the
    account's own most recent CAS snapshot (``app.db.holdings.latest_snapshot``) instead
    of the caller having to carry those quantities around. That is what lets a screen
    that already knows something is wrong -- the skipped-holdings notice -- ask for a
    reconciliation with nothing but an account id.
    """
    assert_owned_investor(conn, current_user, investor_id)
    if not repository.account_belongs_to(conn, body.account_id, investor_id):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"no such account for this investor: {body.account_id}",
        )
    declared = {h.isin: h.quantity for h in body.holdings} or db_holdings.latest_snapshot(
        conn, body.account_id
    )
    if not declared:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "no declared holdings supplied and no CAS statement on file for this "
            "account -- import a CAS to reconcile against",
        )
    return ca_db.stage_corporate_actions(
        conn,
        investor_id=investor_id,
        account_id=body.account_id,
        declared_holdings=declared,
        actor_uid=current_user["id"],
        as_of=body.as_of,
    )


# ---------------------------------------------------------------------------
# Exceptions -- DRAFT rows the automated feed (or a manual entry) could not
# auto-verify. Expected to be short and rare, not a daily queue -- see
# docs/ENGINE_SPEC.md section 7's "Automated ingestion".
# ---------------------------------------------------------------------------


@ops_router.get(
    "/exceptions",
    response_model=list[CorporateActionOut],
    dependencies=[Depends(require_ops_key)],
)
def list_exceptions(conn: Any = Depends(get_conn)) -> list[dict[str, Any]]:
    """Every DRAFT row on file -- the one screen a human ever needs to look at for
    corporate actions the deterministic checks couldn't resolve on their own."""
    return [_out(a) for a in ca_db.list_pending_corporate_actions(conn)]


@ops_router.post(
    "/{action_id}/verify",
    response_model=CorporateActionOut,
    dependencies=[Depends(require_ops_key)],
)
def verify_exception(
    action_id: str,
    conn: Any = Depends(get_conn),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Promote one DRAFT row to VERIFIED by hand -- triggers the same retroactive
    sweep an automated auto-verify does. See ``app.db.corporate_actions.
    verify_corporate_action``."""
    ca_db.verify_corporate_action(conn, action_id, actor_uid=current_user["id"])
    action = ca_db.get_corporate_action(conn, action_id)
    if action is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no such corporate action: {action_id}")
    return _out(action)


@ops_router.post(
    "/{action_id}/waive-price-evidence",
    response_model=CorporateActionOut,
    dependencies=[Depends(require_ops_key)],
)
def waive_price_evidence(
    action_id: str,
    body: WaivePriceEvidenceIn,
    conn: Any = Depends(get_conn),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """A human accepting a BONUS/SPLIT whose ex_date predates this system's price
    archive, so the usual cum/ex corroboration will never be obtainable -- see
    ``app.db.corporate_actions.waive_price_evidence`` for exactly what this does and
    does not bypass. 422 if the row does not qualify (a recent-enough ex_date, no
    source, or an already-disputed row)."""
    try:
        ca_db.waive_price_evidence(conn, action_id, body.reason, actor_uid=current_user["id"])
    except ca_db.PriceEvidenceWaiverError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    action = ca_db.get_corporate_action(conn, action_id)
    if action is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no such corporate action: {action_id}")
    return _out(action)


@ops_router.post(
    "/{action_id}/dispute",
    response_model=CorporateActionOut,
    dependencies=[Depends(require_ops_key)],
)
def dispute_exception(
    action_id: str,
    body: DisputeCorporateActionIn,
    conn: Any = Depends(get_conn),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Reject a DRAFT row permanently -- it will never match a Discrepancy again and
    the automated feed's retry sweep will never re-attempt it. The row is never
    deleted: it stays as the record of what was rejected and why."""
    ca_db.dispute_corporate_action(
        conn, action_id, actor_uid=current_user["id"], reason=body.reason
    )
    action = ca_db.get_corporate_action(conn, action_id)
    if action is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no such corporate action: {action_id}")
    return _out(action)


# ---------------------------------------------------------------------------
# Automated feed -- mirrors app.routers.analytical's refresh_prices/refresh_prices_cron
# pair exactly: one private worker, an X-Ops-Key POST for a human or a non-Vercel
# scheduler, a CRON_SECRET GET for Vercel Cron specifically.
# ---------------------------------------------------------------------------


def _refresh_corporate_actions(conn: Any, start: date, end: date) -> dict[str, Any]:
    return ca_db.refresh_corporate_action_feed(conn, start, end, actor_uid=None)


@ops_router.post(
    "/refresh",
    response_model=RefreshCorporateActionFeedOut,
    dependencies=[Depends(require_ops_key)],
)
def refresh_corporate_actions(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    conn: Any = Depends(get_conn),
) -> dict[str, Any]:
    """``X-Ops-Key``-gated -- a human or a non-Vercel scheduler triggering a fetch
    directly, same posture as ``app.routers.analytical.refresh_prices``. Defaults to a
    2-day window ending today (yesterday's notices often still show ex-dates landing
    today), overridable for a backfill."""
    today = date.today()
    return _refresh_corporate_actions(conn, start or today - timedelta(days=1), end or today)


@ops_router.get(
    "/refresh-cron",
    response_model=RefreshCorporateActionFeedOut,
    dependencies=[Depends(require_cron_secret)],
)
def refresh_corporate_actions_cron(conn: Any = Depends(get_conn)) -> dict[str, Any]:
    """Same job, reachable by Vercel Cron specifically: GET, gated by ``CRON_SECRET``
    rather than ``X-Ops-Key``, since that is the only credential Vercel's scheduler
    sends and the only HTTP method it calls with. See docs/DEPLOYMENT.md."""
    today = date.today()
    return _refresh_corporate_actions(conn, today - timedelta(days=1), today)


# ---------------------------------------------------------------------------
# yfinance discovery -- a second, independent free candidate source. NOT a historical
# fallback: NSE's notices API does serve arbitrary historical windows (re-probed live
# 2026-09-26), and the month-by-month sweep in app.db.reference_sync.schedule is what
# actually reaches a years-deep gap. See app.ingest.corporate_action_yfinance's module
# docstring for the correction and what the remaining uncovered gap really is (BSE).
# ---------------------------------------------------------------------------


@ops_router.post(
    "/discover-yfinance",
    response_model=DiscoverYfinanceOut,
    dependencies=[Depends(require_ops_key)],
)
def discover_yfinance(
    isin: list[str] | None = Query(default=None),
    conn: Any = Depends(get_conn),
) -> dict[str, Any]:
    """``X-Ops-Key``-gated, same posture as ``refresh_corporate_actions`` above. Occasional
    -- run when onboarding turns up a gap the live feed can't explain, not on a daily
    cron (a ticker's split history does not change day to day). Defaults to every ISIN
    this system has ever held; pass one or more ``isin`` query params to target specific
    securities instead of paying for the full sweep."""
    return ca_db.discover_from_yfinance(conn, isins=isin)
