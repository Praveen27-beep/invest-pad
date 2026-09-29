#!/usr/bin/env bash
# stop.sh — stop the full Trackr stack gracefully (reverse startup order).
#
# Usage:
#   ./stop.sh        — stop frontend + backend (leave Postgres running)
#   ./stop.sh --db   — also stop the Postgres container
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="$REPO_ROOT/.trackr-pids"

DB_CONTAINER="${TRACKR_DB_CONTAINER:-trackr-postgres}"

# ── colours ───────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    BOLD="\033[1m"; GREEN="\033[0;32m"; CYAN="\033[0;36m"
    YELLOW="\033[0;33m"; DIM="\033[2m"; R="\033[0m"
else
    BOLD="" GREEN="" CYAN="" YELLOW="" DIM="" R=""
fi

ok()   { echo -e "${GREEN}${BOLD}[  ok  ]${R} $*"; }
warn() { echo -e "${YELLOW}${BOLD}[ warn ]${R} $*"; }
info() { echo -e "${CYAN}${BOLD}[trackr]${R} $*"; }
section(){ echo -e "\n${BOLD}${CYAN}━━━  $*  ━━━${R}"; }

STOP_DB=false
for arg in "$@"; do
    [[ "$arg" == "--db" || "$arg" == "--all" ]] && STOP_DB=true
done

stop_process() {
    local name="$1" label="$2"
    local pid_file="$PID_DIR/${name}.pid"

    if [[ ! -f "$pid_file" ]]; then
        warn "$label: no PID file found (already stopped?)"
        return
    fi

    local pid
    pid=$(cat "$pid_file")

    if ! kill -0 "$pid" 2>/dev/null; then
        warn "$label: process $pid is not running (cleaning up stale PID)"
        rm -f "$pid_file"
        return
    fi

    info "stopping $label (pid $pid) …"
    # Kill the whole process group so child workers don't orphan
    kill -TERM "-${pid}" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true

    local elapsed=0
    while kill -0 "$pid" 2>/dev/null && [[ $elapsed -lt 10 ]]; do
        sleep 1; elapsed=$((elapsed+1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        warn "$label did not exit in 10s — sending SIGKILL"
        kill -9 "$pid" 2>/dev/null || true
    fi

    rm -f "$pid_file"
    ok "$label stopped"
}

# ─────────────────────────────────────────────────────────────────────────────
# Stop in reverse startup order
# ─────────────────────────────────────────────────────────────────────────────
section "Stopping Trackr stack"

stop_process "frontend" "Next.js dev server"
stop_process "reference-worker" "reference reconciliation worker"
stop_process "backend"  "uvicorn (FastAPI)"

if [[ "$STOP_DB" == "true" ]]; then
    if command -v docker &>/dev/null && docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
        info "stopping Postgres container '$DB_CONTAINER' …"
        docker stop "$DB_CONTAINER" > /dev/null
        ok "Postgres stopped"
    else
        warn "Postgres container '$DB_CONTAINER' is not running"
    fi
else
    warn "Postgres left running (pass --db to stop it too)"
fi

section "Done"
echo -e "  ${DIM}Restart:  ./start.sh${R}"
