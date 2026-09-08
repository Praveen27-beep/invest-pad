#!/usr/bin/env bash
# start.sh — start the full Trackr stack: Postgres → migrations → API → frontend
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$REPO_ROOT/trackr-backend"
FRONTEND_DIR="$REPO_ROOT/trackr-frontend"
VENV_DIR="$REPO_ROOT/.venv"
PID_DIR="$REPO_ROOT/.trackr-pids"
LOG_DIR="$REPO_ROOT/.trackr-logs"

# ── config (override via env) ─────────────────────────────────────────────────
DB_CONTAINER="${TRACKR_DB_CONTAINER:-trackr-postgres}"
DB_IMAGE="${TRACKR_DB_IMAGE:-postgres:16-alpine}"
# Auto-detect DB port: reuse existing container port if running, or fallback to 5433 if 5432 is bound
if [[ -z "${TRACKR_DB_PORT:-}" ]]; then
    if docker ps -a --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
        DB_PORT=$(docker inspect --format '{{(index (index .HostConfig.PortBindings "5432/tcp") 0).HostPort}}' "$DB_CONTAINER" 2>/dev/null || true)
    fi
    if [[ -z "${DB_PORT:-}" ]]; then
        if ss -tlnp 'sport = :5432' 2>/dev/null | grep -q LISTEN || lsof -i :5432 &>/dev/null; then
            DB_PORT=5433
        else
            DB_PORT=5432
        fi
    fi
else
    DB_PORT="$TRACKR_DB_PORT"
fi

DB_NAME="${TRACKR_DB_NAME:-portfolio}"
DB_USER="${TRACKR_DB_USER:-trackr}"
DB_PASS="${TRACKR_DB_PASS:-trackr_dev}"
# Auto-detect BACKEND port: fallback to 8001 if 8000 is already bound by another process
if [[ -z "${TRACKR_BACKEND_PORT:-}" ]]; then
    if ss -tlnp 'sport = :8000' 2>/dev/null | grep -q LISTEN || lsof -i :8000 &>/dev/null; then
        BACKEND_PORT=8001
    else
        BACKEND_PORT=8000
    fi
else
    BACKEND_PORT="$TRACKR_BACKEND_PORT"
fi

FRONTEND_PORT="${TRACKR_FRONTEND_PORT:-3000}"
RELOAD="${TRACKR_BACKEND_RELOAD:-true}"

export DATABASE_URL="postgresql://${DB_USER}:${DB_PASS}@localhost:${DB_PORT}/${DB_NAME}"

# ── colours ───────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    BOLD="\033[1m"; GREEN="\033[0;32m"; CYAN="\033[0;36m"
    RED="\033[0;31m"; YELLOW="\033[0;33m"; DIM="\033[2m"; R="\033[0m"
else
    BOLD="" GREEN="" CYAN="" RED="" YELLOW="" DIM="" R=""
fi

info()  { echo -e "${CYAN}${BOLD}[trackr]${R} $*"; }
ok()    { echo -e "${GREEN}${BOLD}[  ok  ]${R} $*"; }
warn()  { echo -e "${YELLOW}${BOLD}[ warn ]${R} $*"; }
die()   { echo -e "${RED}${BOLD}[ fail ]${R} $*" >&2; exit 1; }
step()  { echo -e "${DIM}         › $*${R}"; }
section(){ echo -e "\n${BOLD}${CYAN}━━━  $*  ━━━${R}"; }

mkdir -p "$PID_DIR" "$LOG_DIR"

# ─────────────────────────────────────────────────────────────────────────────
# PRE-FLIGHT
# ─────────────────────────────────────────────────────────────────────────────
section "Pre-flight"

[[ -f "$VENV_DIR/bin/activate" ]] || die ".venv not found — run: make install"
ok "venv present"

[[ -f "$BACKEND_DIR/.env" ]] || {
    warn "trackr-backend/.env not found — copying from .env.example"
    warn "Fill in PORTFOLIO_ENCRYPTION_KEY, PORTFOLIO_PAN_PEPPER, JWT_SECRET before using the API"
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
}
ok "backend .env present"

command -v docker &>/dev/null || die "docker not found on PATH"
docker info &>/dev/null       || die "Docker daemon is not running"
ok "Docker daemon reachable"

command -v node &>/dev/null || die "node not found on PATH"
command -v npm  &>/dev/null || die "npm not found on PATH"
ok "node/npm present"

# Load backend .env so assert_secrets can read the variables
# shellcheck disable=SC2046
export $(grep -v '^\s*#' "$BACKEND_DIR/.env" | grep -v '^\s*$' | xargs) 2>/dev/null || true

# Always ensure DATABASE_URL uses the target DB_PORT and credentials
export DATABASE_URL="postgresql://${DB_USER}:${DB_PASS}@localhost:${DB_PORT}/${DB_NAME}"

# Required secrets — the app refuses to start if any are missing; fail here with
# a clear message rather than letting uvicorn crash with a pydantic validation error.
missing=0
for var in DATABASE_URL PORTFOLIO_ENCRYPTION_KEY PORTFOLIO_PAN_PEPPER JWT_SECRET; do
    [[ -n "${!var:-}" ]] || { warn "Required env var $var is not set in trackr-backend/.env"; missing=1; }
done
[[ $missing -eq 0 ]] || die "Fill in the missing secrets above, then re-run ./start.sh"
ok "required secrets present"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — POSTGRES
# ─────────────────────────────────────────────────────────────────────────────
section "Step 1 — Postgres"

if docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
    ok "container '$DB_CONTAINER' is already running"
elif docker ps -a --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
    info "starting existing container '$DB_CONTAINER' …"
    docker start "$DB_CONTAINER" > /dev/null
else
    info "pulling $DB_IMAGE and creating container '$DB_CONTAINER' …"
    docker pull "$DB_IMAGE" --quiet
    docker run \
        --name "$DB_CONTAINER" --detach --restart unless-stopped \
        -p "${DB_PORT}:5432" \
        -v "trackr-postgres-data:/var/lib/postgresql/data" \
        -e "POSTGRES_DB=${DB_NAME}" \
        -e "POSTGRES_USER=${DB_USER}" \
        -e "POSTGRES_PASSWORD=${DB_PASS}" \
        -e "POSTGRES_INITDB_ARGS=--encoding=UTF8 --locale=C" \
        "$DB_IMAGE" > /dev/null
    ok "container created"
fi

step "waiting for Postgres to accept connections …"
elapsed=0
until docker exec "$DB_CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" &>/dev/null; do
    sleep 1; elapsed=$((elapsed+1))
    [[ $elapsed -lt 60 ]] || die "Postgres did not become ready after 60s — check: docker logs $DB_CONTAINER"
done
ok "Postgres ready (${elapsed}s)"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — MIGRATIONS
# ─────────────────────────────────────────────────────────────────────────────
section "Step 2 — Database migrations"

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

(cd "$BACKEND_DIR" && python - <<'PYEOF'
import sys, os, psycopg
from app.db.migrate import migrate
url = os.environ["DATABASE_URL"]
try:
    conn = psycopg.connect(url)
    applied = migrate(conn)
    conn.commit(); conn.close()
    if applied:
        print(f"  applied {len(applied)} migration(s):")
        for f in applied: print(f"    ✓ {f}")
    else:
        print("  schema is up to date — nothing to apply")
except Exception as exc:
    print(f"  FAILED: {exc}", file=sys.stderr); sys.exit(1)
PYEOF
)
ok "migrations complete"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — BACKEND (uvicorn)
# ─────────────────────────────────────────────────────────────────────────────
section "Step 3 — Backend"

# Kill any stale process that left a PID file but isn't actually running
if [[ -f "$PID_DIR/backend.pid" ]]; then
    old=$(cat "$PID_DIR/backend.pid")
    kill -0 "$old" 2>/dev/null || rm -f "$PID_DIR/backend.pid"
fi

if [[ -f "$PID_DIR/backend.pid" ]]; then
    ok "uvicorn already running (pid $(cat "$PID_DIR/backend.pid"))"
else
    reload_flag=""
    [[ "$RELOAD" == "true" ]] && reload_flag="--reload"

    (
        cd "$BACKEND_DIR"
        # shellcheck disable=SC2086
        if command -v setsid &>/dev/null; then
            exec setsid "$VENV_DIR/bin/uvicorn" app.main:app \
                --host 0.0.0.0 --port "$BACKEND_PORT" \
                --log-level info $reload_flag \
                </dev/null >> "$LOG_DIR/backend.log" 2>&1
        else
            exec "$VENV_DIR/bin/uvicorn" app.main:app \
                --host 0.0.0.0 --port "$BACKEND_PORT" \
                --log-level info $reload_flag \
                </dev/null >> "$LOG_DIR/backend.log" 2>&1
        fi
    ) &
    bpid=$!
    disown $bpid 2>/dev/null || true
    echo $bpid > "$PID_DIR/backend.pid"
    step "uvicorn PID $! → $LOG_DIR/backend.log"

    step "waiting for /health …"
    elapsed=0
    until curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" -o /dev/null 2>/dev/null; do
        sleep 1; elapsed=$((elapsed+1))
        [[ $elapsed -lt 60 ]] || die "uvicorn did not pass /health after 60s — check $LOG_DIR/backend.log"
    done
    ok "backend healthy (${elapsed}s)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3.5 — DAILY SNAPSHOTS
# ─────────────────────────────────────────────────────────────────────────────
section "Step 3.5 — Daily snapshots"

# TODAY ONLY, by default. This used to hardcode a start of 2024-01-01 on every single
# boot -- which is not the daily catch-up its own heading claims, it is the resumable
# HISTORICAL BACKFILL: ~660 trading days of bhavcopy walked, and one snapshot attempted
# per day per investor per advised_only flag. The ops endpoint it borrows from
# (app/routers/analytical.py::run_snapshots) defaults start and end to today for exactly
# this reason, calling that "the cheap daily catch-up".
#
# The backfill is still one command away, and it is still resumable, so it costs nothing
# to leave it out of the hot path:
#
#     TRACKR_SNAPSHOT_START=2024-01-01 ./start.sh
#
# Run it once after importing history; after that the daily catch-up keeps up on its own.
SNAPSHOT_START="${TRACKR_SNAPSHOT_START:-}"
if [[ -n "$SNAPSHOT_START" ]]; then
    step "historical backfill from $SNAPSHOT_START (resumable — safe to interrupt)"
else
    step "today's catch-up (set TRACKR_SNAPSHOT_START=YYYY-MM-DD for a historical backfill)"
fi

# `if (...)` rather than `(...) || warn` followed by an unconditional ok: printing an
# error and then "ok" on the next line is what made the old version of this step so
# confusing to read. One outcome, one line.
if (cd "$BACKEND_DIR" && SNAPSHOT_START="$SNAPSHOT_START" python - <<'PYEOF'
import sys, os, psycopg
from datetime import date
from app.prices.alerts import LoggingNotifier
from app.routers.analytical import _run_snapshots

url = os.environ["DATABASE_URL"]
raw_start = os.environ.get("SNAPSHOT_START", "").strip()
try:
    start = date.fromisoformat(raw_start) if raw_start else date.today()
except ValueError:
    print(f"  TRACKR_SNAPSHOT_START={raw_start!r} is not YYYY-MM-DD", file=sys.stderr)
    sys.exit(1)

try:
    conn = psycopg.connect(url)
    res = _run_snapshots(conn, start, date.today(), LoggingNotifier())
    conn.commit()
    conn.close()
except Exception as exc:
    # Snapshots are a stored convenience -- every figure in this product is still
    # derivable from the ledger on read without them -- so a failure here must not stop
    # the stack coming up. It is reported, not swallowed: the exit code below is what
    # turns it into a visible [warn] rather than a line nobody reads under an [ok].
    print(f"  snapshots step failed: {exc}", file=sys.stderr)
    sys.exit(1)

written = res.get("snapshots_written", 0)
fetched = res.get("price_dates_fetched", 0)
skipped = res.get("skipped_missing_price", []) or []
print(f"  snapshots written: {written}, price dates fetched: {fetched}")
if skipped:
    # One line naming the securities, not one traceback per skipped day. A snapshot that
    # cannot be priced is expected and handled (a missing price NEVER defaults to zero,
    # CLAUDE.md rule 4) -- but which securities, and how many days, is worth saying once.
    unpriced = sorted({i for s in skipped for i in (s.get("isins") or []) if i})
    print(f"  {len(skipped)} day(s) skipped for want of a price: {', '.join(unpriced)}")
PYEOF
); then
    ok "daily snapshots up to date"
else
    warn "snapshots step did not complete — see the message above."
    warn "The stack is still usable: every figure is derived from the ledger on read,"
    warn "so snapshots are a stored convenience, not a prerequisite."
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — FRONTEND (Next.js)
# ─────────────────────────────────────────────────────────────────────────────
section "Step 4 — Frontend"

# Ensure .env.local exists and sets NEXT_PUBLIC_API_BASE_URL to active BACKEND_PORT
if [[ ! -f "$FRONTEND_DIR/.env.local" ]]; then
    cp "$FRONTEND_DIR/.env.example" "$FRONTEND_DIR/.env.local"
fi
# Guarantee NEXT_PUBLIC_API_BASE_URL matches the backend port
if grep -q "NEXT_PUBLIC_API_BASE_URL=" "$FRONTEND_DIR/.env.local"; then
    sed -i.bak "s|NEXT_PUBLIC_API_BASE_URL=.*|NEXT_PUBLIC_API_BASE_URL=http://localhost:${BACKEND_PORT}|" "$FRONTEND_DIR/.env.local"
    rm -f "$FRONTEND_DIR/.env.local.bak"
else
    echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:${BACKEND_PORT}" >> "$FRONTEND_DIR/.env.local"
fi

# Install node_modules if needed
[[ -d "$FRONTEND_DIR/node_modules" ]] || {
    info "node_modules missing — running npm install …"
    (cd "$FRONTEND_DIR" && npm install --silent)
    ok "npm install done"
}

# Kill stale PID
if [[ -f "$PID_DIR/frontend.pid" ]]; then
    old=$(cat "$PID_DIR/frontend.pid")
    kill -0 "$old" 2>/dev/null || rm -f "$PID_DIR/frontend.pid"
fi

if [[ -f "$PID_DIR/frontend.pid" ]]; then
    ok "Next.js already running (pid $(cat "$PID_DIR/frontend.pid"))"
else
    (
        cd "$FRONTEND_DIR"
        if command -v setsid &>/dev/null; then
            exec setsid ./node_modules/.bin/next dev --port "$FRONTEND_PORT" --hostname 0.0.0.0 \
                </dev/null >> "$LOG_DIR/frontend.log" 2>&1
        else
            exec ./node_modules/.bin/next dev --port "$FRONTEND_PORT" --hostname 0.0.0.0 \
                </dev/null >> "$LOG_DIR/frontend.log" 2>&1
        fi
    ) &
    fpid=$!
    disown $fpid 2>/dev/null || true
    echo $fpid > "$PID_DIR/frontend.pid"
    step "Next.js PID $! → $LOG_DIR/frontend.log"

    step "waiting for Next.js to compile …"
    elapsed=0
    until curl -sf "http://localhost:${FRONTEND_PORT}" -o /dev/null 2>/dev/null; do
        sleep 1; elapsed=$((elapsed+1))
        [[ $elapsed -lt 120 ]] || die "Next.js did not respond after 120s — check $LOG_DIR/frontend.log"
    done
    ok "frontend ready (${elapsed}s)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# DONE
# ─────────────────────────────────────────────────────────────────────────────
section "Stack is up"
echo -e "  ${BOLD}Postgres${R}   localhost:${DB_PORT}   (container: ${DB_CONTAINER})"
echo -e "  ${BOLD}API${R}        http://localhost:${BACKEND_PORT}"
echo -e "  ${BOLD}API docs${R}   http://localhost:${BACKEND_PORT}/docs"
echo -e "  ${BOLD}App${R}        http://localhost:${FRONTEND_PORT}"
echo
echo -e "  ${DIM}Stop everything:  ./stop.sh${R}"
echo -e "  ${DIM}Backend log:      $LOG_DIR/backend.log${R}"
echo -e "  ${DIM}Frontend log:     $LOG_DIR/frontend.log${R}"
