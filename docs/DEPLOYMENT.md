# Deployment

Both `trackr-backend/` and `trackr-frontend/` deploy to Vercel, as **two separate
Vercel projects from the same repository** (no repo split needed — set each project's
Root Directory when you import it). This decision, and why it changed from an earlier
Vercel-frontend/Hetzner-backend split, is recorded in the session that wrote this doc:
Vercel's Python runtime now runs FastAPI natively with Fluid compute (no more 10-second
Lambda-style ceiling), gives free automatic HTTPS, and Vercel Cron replaces what would
otherwise be a systemd unit for the two `/ops/*` jobs below. The one real trade-off is
Postgres connection handling under serverless concurrency — solved by picking a Postgres
host with a **built-in pooler**, not worked around in code.

If you outgrow this later, nothing here is a dead end: the engine and parsers stay
framework-free per `docs/ARCHITECTURE.md`, and `trackr-backend/` is a normal FastAPI app
that runs unmodified under `uvicorn` anywhere (a VPS, a container, whatever) if you ever
move it off Vercel.

## What you need before you start

- A **Vercel account**, with the repo importable (GitHub/GitLab/Bitbucket connection).
- A **pooled Postgres**. [Neon](https://neon.tech) is the most Vercel-native choice
  (has a direct Vercel marketplace integration and a free tier); Supabase works too.
  Whichever you pick, use its **pooled** connection string for `DATABASE_URL`, not the
  direct one — the direct URL is for one-off admin work (migrations), not for the app
  itself. Serverless functions open far more concurrent connections than one VPS process
  ever would; the pooler is what stops that from exhausting Postgres's connection limit.
- An **S3-compatible object store** for uploaded documents. [Cloudflare
  R2](https://developers.cloudflare.com/r2/) is the recommended target (zero egress
  fees, and `app/storage/s3.py` already speaks its API via boto3) — create one bucket
  and an access-key pair scoped to it. **This one is not deferrable.**
  `app/config.py`'s `_validate_storage_backend` refuses to construct `Settings` at all
  with `STORAGE_BACKEND=local` outside `DEBUG=true` — and because `get_settings()` is a
  dependency on nearly every route (auth included), a deploy with `DEBUG=false` and no
  S3 configured doesn't just break document upload, it 500s on *every* request,
  starting with login. That's deliberate: `local` writes to a real directory on disk,
  which doesn't exist on Vercel's read-only function filesystem, and the alternative
  was letting that surface as a random unhandled filesystem error on whoever's first
  upload attempt instead. Set up R2 before your first deploy, not after.
  Email-forwarding ingestion (Mailgun/Postmark/SendGrid + a real domain) is genuinely
  deferrable, though — see the last section.

## 1. Generate secrets

Run these once, locally, and save the output somewhere durable (a password manager) —
you'll paste each into Vercel's environment-variable settings in step 3.

```bash
cd trackr-backend
python3 -c "from app.db.crypto import generate_key; print(generate_key())"   # PORTFOLIO_ENCRYPTION_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"                 # PORTFOLIO_PAN_PEPPER
python3 -c "import secrets; print(secrets.token_urlsafe(32))"                 # JWT_SECRET
python3 -c "import secrets; print(secrets.token_urlsafe(32))"                 # OPS_API_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"                 # CRON_SECRET
```

Five distinct values. Never reuse one across two of these — `app/db/crypto.py`'s own
docstring explains why the encryption key and the PAN pepper specifically must differ
(so a partial compromise stays partial), and the same logic extends to not sharing
`JWT_SECRET` with anything else either.

## 2. Set up Postgres

1. Create the Neon (or Supabase) project. Copy the **pooled** connection string.
2. Run migrations against it from your machine — this only needs network access to the
   database, not a deployed backend:

   ```bash
   export DATABASE_URL="<your pooled connection string>"
   cd trackr-backend
   python3 - <<'PYEOF'
   import os, psycopg
   from app.db.migrate import migrate
   conn = psycopg.connect(os.environ["DATABASE_URL"])
   applied = migrate(conn)
   conn.commit(); conn.close()
   print(f"applied {len(applied)} migration(s)" if applied else "already up to date")
   PYEOF
   ```

   This is the same migration runner `start.sh` uses locally — see
   `trackr-backend/app/db/migrations/` for the individual files if you want to read what
   it's about to apply.

## 3. Deploy the backend

1. In Vercel, **Add New Project** → import this repo → set **Root Directory** to
   `trackr-backend`. Vercel auto-detects the FastAPI/Python framework from
   `pyproject.toml`; `[tool.vercel] entrypoint = "app.main:app"` in that file tells it
   exactly where the app object is, so nothing else to configure there.
2. Under **Environment Variables**, set every one of these (Production environment;
   add to Preview too if you want preview deployments to work against the same data —
   most alphas don't need that yet):

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | the pooled Postgres string from step 2 |
   | `PORTFOLIO_ENCRYPTION_KEY` | from step 1 |
   | `PORTFOLIO_PAN_PEPPER` | from step 1 |
   | `JWT_SECRET` | from step 1 |
   | `JWT_ALGORITHM` | `HS256` |
   | `JWT_EXPIRY_SECONDS` | `3600` |
   | `OPS_API_KEY` | from step 1 |
   | `CRON_SECRET` | from step 1 — **must be named exactly `CRON_SECRET`**, Vercel sends it automatically as `Authorization: Bearer <value>` on every cron-triggered request (see step 5) |
   | `CORS_ORIGINS` | placeholder for now, e.g. `http://localhost:3000` — you'll update this in step 6 once the frontend has a real URL |
   | `DEBUG` | `false` |
   | `STORAGE_BACKEND` | `s3` |
   | `PORTFOLIO_STORAGE_BUCKET` | your R2 bucket name |
   | `PORTFOLIO_STORAGE_ENDPOINT` | your R2 account's S3 API endpoint |
   | (R2 access key / secret) | however `app/storage/s3.py` reads boto3 credentials in your setup — typically `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, boto3's own standard env vars, not Trackr-specific ones |
   | `INGEST_DOMAIN` | leave as `ingest.example.com` (the dev placeholder) until you set up email forwarding — see the last section. `DEBUG=false` normally requires a real value here, but nothing calls the ingest-address code path until an account actually needs a forwarding address, so this is safe to defer |
| `GEMINI_API_KEY` | Ask-AI assistant. Unset = the assistant returns 503; the app still boots |
| `LLM_PARSING_ENABLED` | `false` unless the Groq DPA is signed — see docs/COMPLIANCE.md |
| `GROQ_API_KEY` | LLM document extraction. Unset (with the flag false) = the feature never runs |
| `GROQ_MODEL` | Defaults to `openai/gpt-oss-20b`; swappable without a code change |

3. Deploy. Vercel gives you a URL like `https://trackr-backend-yourname.vercel.app` —
   note it, the frontend needs it next. Confirm it's alive:

   ```bash
   curl https://trackr-backend-yourname.vercel.app/health
   ```

## 4. Deploy the frontend

1. **Add New Project** again, same repo, **Root Directory** = `trackr-frontend`. Vercel
   auto-detects Next.js.
2. Environment variables:

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_API_BASE_URL` | the backend URL from step 3 |
   | `NEXT_PUBLIC_INGEST_DOMAIN` | same value as the backend's `INGEST_DOMAIN` |

3. Deploy. You'll get a frontend URL like `https://trackr-plus-yourname.vercel.app`.

## 5. Wire the cron jobs

`trackr-backend/vercel.json` already declares both schedules:

```json
{
  "crons": [
    { "path": "/ops/cron/prices-refresh", "schedule": "30 10 * * *" },
    { "path": "/ops/cron/snapshots-run", "schedule": "0 11 * * *" }
  ]
}
```

`prices-refresh` does two jobs: bhavcopy for every held ISIN, and a trailing-window
refresh of the NIFTY TRI levels behind the dashboard's benchmark line. The second is
best-effort — its outcome comes back in the response as `index_levels_stored` and
`index_failures`, and a failure there never fails the run. A non-empty `index_failures`
on consecutive days means the index source has moved or started refusing requests, and
the symptom to expect is the benchmark line quietly disappearing from the chart while
every other figure stays correct.

Times are UTC (Vercel Cron is always UTC) — 10:30/11:00 UTC is roughly 4:00/4:30pm IST,
after NSE/BSE bhavcopy is normally published; adjust if you find it publishes later.
Nothing else to do here — the `CRON_SECRET` env var from step 3 is what Vercel signs
these requests with automatically, and `app/auth/ops.py::require_cron_secret` verifies
it. **If you're on Vercel's Hobby plan**, cron jobs run once per day only and at some
point within the scheduled hour, not the exact minute — both of these schedules already
fit that constraint.

You can trigger either job manually any time via the `POST` route instead (useful for a
backfill, or to test before waiting for the schedule):

```bash
curl -X POST https://trackr-backend-yourname.vercel.app/ops/prices/refresh \
  -H "X-Ops-Key: <your OPS_API_KEY>"
```

## 6. Close the loop: CORS

Now that the frontend has a real URL, go back to the backend project's environment
variables and set the real value:

```
CORS_ORIGINS=https://trackr-plus-yourname.vercel.app
```

Comma-separate multiple origins if you also want a custom domain to work
(`https://app.yourdomain.com,https://trackr-plus-yourname.vercel.app`). Redeploy the
backend for this to take effect (env var changes need a redeploy, they aren't picked up
live).

## 7. Smoke test

- Visit the frontend URL, register an account (`POST /auth/register` fires once you
  submit the form). Confirm you land on the dashboard, not stuck loading.
- Manually enter one transaction and confirm it shows up under holdings.
- Try the account CSV/XLSX import screen with a small real file.
- Hit `GET /ops/cron/prices-refresh` yourself with a bad `Authorization` header and
  confirm you get a `403`, not data — this is the one endpoint class that's easy to
  misconfigure into being wide open, worth checking explicitly once, live.
- Check Vercel's **Cron Jobs** tab (project Settings) the day after deploying to
  confirm both jobs actually ran and their logs look clean.

## Later: email-forwarding ingestion

This needs a real domain you control (for `INGEST_DOMAIN`) and an inbound-parse
provider (Mailgun, Postmark, or SendGrid — `app/ingest/webhook_providers.py` supports
all three). Set `INGEST_DOMAIN` to that domain, `INGEST_WEBHOOK_PROVIDER` to your
chosen provider's name, and that provider's specific secret
(`INGEST_MAILGUN_SIGNING_KEY` / `INGEST_POSTMARK_BASIC_AUTH_USER` +
`INGEST_POSTMARK_BASIC_AUTH_PASSWORD` / `INGEST_SENDGRID_SHARED_SECRET`). Point that
provider's inbound-parse webhook at `https://<your-backend>.vercel.app/ingest/email`.
See `docs/INGESTION.md` for the legal boundary this design depends on and why it's
file/email-based rather than credential-based in the first place.
