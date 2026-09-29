"""Reference status is investor-scoped; worker execution and errors are ops-only."""

from typing import Any

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_owned_investor
from app.auth.ops import require_cron_secret, require_ops_key
from app.config import Settings, get_settings
from app.database import get_conn
from app.db.reference_sync import status
from app.reference_worker import run_once

router = APIRouter(tags=["reference-sync"])


@router.get(
    "/investors/{investor_id}/reference-status", dependencies=[Depends(require_owned_investor)]
)
def reference_status(
    investor_id: str, conn: Any = Depends(get_conn), settings: Settings = Depends(get_settings)
) -> dict:
    return {**status(conn, investor_id), "enabled": settings.reference_sync_enabled}


@router.post("/ops/reference-sync/run", dependencies=[Depends(require_ops_key)])
def run(conn: Any = Depends(get_conn), settings: Settings = Depends(get_settings)) -> dict:
    return run_once(conn, settings, limit=1)


@router.get("/ops/reference-sync/run-cron", dependencies=[Depends(require_cron_secret)])
def cron(conn: Any = Depends(get_conn), settings: Settings = Depends(get_settings)) -> dict:
    return run_once(conn, settings, limit=1)


@router.get("/ops/reference-sync/status", dependencies=[Depends(require_ops_key)])
def operations(conn: Any = Depends(get_conn)) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT kind,state,count(*),max(updated_at) FROM reference_sync_task "
            "GROUP BY kind,state ORDER BY kind,state"
        )
        counts = [
            {"source": r[0], "state": r[1], "count": r[2], "updated_at": r[3]}
            for r in cur.fetchall()
        ]
        cur.execute(
            "SELECT kind,task_key,last_error,available_at FROM reference_sync_task "
            "WHERE state='retry' ORDER BY updated_at DESC LIMIT 30"
        )
        failures = [
            {"source": r[0], "key": r[1], "error": r[2], "retry_at": r[3]} for r in cur.fetchall()
        ]
    return {"tasks": counts, "failures": failures}
