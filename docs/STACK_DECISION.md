# Stack Decision

## Verdict: Django 5 + DRF + PostgreSQL

Your developer evaluated three stacks and reached this conclusion independently. Agreed,
and the reasoning is worth recording because it explains why the *contracts* matter more
than the stack.

## The evaluation

| Criterion | Django + Postgres | Firebase | Next.js + Supabase + FastAPI |
|---|---|---|---|
| FIFO lot matching, XIRR | Native. Same process, relational joins. | **Poor.** No joins, no cross-document aggregation. All math offloads to a Cloud Run Python service anyway. | Works, but across a network boundary |
| PDF parsing (CAS, contract notes) | In-process, no timeout ceiling | Function timeouts on large files; needs a Python container regardless | Separate service, same Python libs |
| Multi-tenant integrity | Real FKs and constraints | Security Rules; no referential integrity on a deep hierarchy | Postgres RLS — good |
| Deployment surface | **One service, one migration system, one test run** | Three (Firestore + Functions + Cloud Run) | Two |

Firebase's own blueprint says it plainly: the tax/report engine is "exactly the workload
Firestore is worst at," and adopting it means "running Option A's Python core hosted next
to Firebase." That is a correct self-diagnosis, and it decides the question.

## Why this matters less than it appears

The stack is **disposable**. The system is defined by `contracts/openapi.yaml`,
`schema/*.schema.json` and `fixtures/*.json`. Django is the reference implementation, not
the specification. If your developer prefers Go, Rails or Node, the migration path is
mechanical — generate types, generate stubs, port the fixtures.

What is *not* negotiable is the layer rule in `docs/ARCHITECTURE.md`: the engine stays
pure, `Decimal`-based, and free of framework imports. That is what keeps the stack
disposable in the first place.

## Cost meters — where surprise bills come from

Your developer's framing is good and worth keeping. For the Django/Postgres path:

| Meter | Typical size | Risk |
|---|---|---|
| Database storage | Tens of MB even at 10,000 transactions over 20 years | Negligible |
| File storage (PDFs) | 100 KB–2 MB each, hundreds a year | Low. Use R2 — no egress fees. Lifecycle-delete raw PDFs after the retention period. |
| Compute (web + worker) | The real driver | **An over-frequent scheduled job.** Price refresh once daily, not hourly. |

Indicative: **~$22–60/month** for a small advisory practice (web + worker + managed
Postgres + Redis + storage). Verify current pricing; set billing alerts on day one.

Note the Firebase path adds a fourth meter — **per-document reads** — which is the one
that produces genuinely shocking bills when a naive view fans out across a family's
holdings. Another reason to avoid it.

## What not to build

| Tempting | Why not |
|---|---|
| Microservices | 10 clients, 20 holdings. One process is correct. |
| Realtime listeners | Holdings change on trade days. Daily is the natural cadence. |
| A separate calc service | Splits the one thing that must be correct across a network boundary |
| An SPA before the engine works | The dashboard is the last 10% of the value |
