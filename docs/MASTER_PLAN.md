# Trackr+ — Master Plan

> **Review 2026-10-18:** historical plan, not current implementation/release status.
> Discussion-derived additions below are **PROPOSED**, pending explicit decisions;
> they do not amend financial invariants, authorize implementation or clear release gates.
> The repository's implemented contracts/invariants take precedence over historical instructions.

> **Read `ARCHITECTURE_INVARIANTS.md` first.** This document is subordinate to it.
> If anything here conflicts with an established invariant, stop and flag the conflict
> rather than improvising.

Companion documents: `WORKSPACE_SPEC.md` (what the product is),
`AGENT_PIPELINE.md` (how it gets built), `INVESTI_TEARDOWN.md` (what to take from the
closest comparable product, and where we diverge).

---

## 0. What this is

**Trackr+ is a product, not an internal tool.** It exists independently of Mei Capital
and is intended for outside users.

Two layers, one system:

- **The engine** answers *what do I own and what is it worth*.
- **The workspace** answers *what did I believe, why, and is it still true*.

One database, one auth model, one deterministic-vs-LLM boundary.

### Proposed positioning

Customer message: **Your research. Your thinking. Your AI.**

**Invest-pad: an AI Investment Studio for Indian equities** — company research, sourced
analysis and investor-owned memory beside the existing Trackr+ ledger. The value is
continuity from evidence to thesis to decision to later review, not model access alone.
Studio positioning does not remove the existing discipline or non-advisory constraints.

### Proposed deployment, privacy and operating requirements

- **Deployment:** reuse one versioned codebase/schema contract for retail and institutional
  backends; separate databases, object stores/indexes, secrets, queues and audit boundaries.
  No shared private corpus or cross-deployment fallback. Topology remains undecided below.
- **Institutional access:** map organisation roles and investor permissions onto existing
  ownership/RLS checks; enforce the same scope in retrieval, workers, caches and downloads.
  Define SSO, residency and dedicated-environment requirements before enterprise claims.
- **Data ownership:** investor/client content stays under its owner's control; no model
  training, cross-client memory or support access without explicit approved authority.
  Define export, revocation, deletion across derived artifacts/backups and legal holds.
- **Security evidence:** least-privilege service identities, encryption/key rotation,
  time-limited document access, redacted audit events, restore and cross-tenant denial tests.
  An institutional security claim requires tested controls; this list is not certification.
- **Costs/reliability:** per-run and per-tenant admission limits for tokens, steps, retries,
  concurrency, spend and deadline. Record provider/model/price versions and actual usage;
  reserve retry exposure and label unknown billing. Reuse existing job budgets/leases.
  Meter retained storage, extraction/OCR/indexing and AI inference separately; include failed
  runs, support and infrastructure in unit economics. No pricing or quota is approved here.
- **Defensibility:** evaluate cited-answer correctness, retrieval of the investor's prior
  reasoning, repeat use and cost per accepted research result. Model choice, generic reports
  and possession of private data are not evidence of a moat; portability remains required.
  Track weekly returning researchers and sessions reusing prior theses/decisions; exports
  preserve document/citation relationships and versions, rather than creating lock-in.

Reuse anchors in repository `46b904e` (source-inspected, not runtime-verified):
`app/db/workspace_context.py` / migration 045 (ownership/RLS),
`app/db/butler_notebook.py` (memory), `app/storage/base.py` /
`app/research/documents.py` (private documents/extraction), `app/db/hosted_jobs.py`
(bounded execution); paths are under `trackr-backend/`.

### Unresolved decisions / conflicts

Existing rules remain in force until an explicit decision records scope and acceptance tests.

| ID | Conflict or missing decision |
|---|---|
| D1 | Mandatory question/own-answer ritual vs open-ended research chat; define when each applies. |
| D2 | Atomic linked notes/writing-centred UX vs long-form editor and Investi-style Explorer/chat; folders remain secondary pending a storage decision. |
| D3 | One-database baseline vs separate retail/institutional deployments; decide shared references, identity boundary and institutional role model without forking the engine. |
| D4 | Append-only history vs erasure/retention/legal holds; approve category-specific rules, backup expiry and provider retention/training terms. |
| D5 | Historical `user_id on every table` wording vs existing investor ownership/RLS and shared reference data; reuse current scope, not a blanket column migration. |
| D6 | Browser-owned model execution vs configured hosted jobs; approve execution/disclosure policy, cost payer, quotas and service targets. |
| D7 | Document volume/latency and retrieval-quality targets, measured before choosing new storage/search infrastructure or embeddings. |

`Phase 0/current` and unchecked tasks below are historical sequencing, not fresh status.
A public landing/demo or successful frontend build does not clear private-research gates.

### User staging

| Stage | Who | Status |
|---|---|---|
| **MVP** | Parasu only, testing his own research workflow | Now |
| **Alpha** | A small number of invited outside users | Soon |
| **Beta / public** | Open signup | Later |

This staging is the most important thing in this document, because **almost everything
in §6 must be true before Alpha, not before Beta.** Being user #1 is a testing stage,
not a licence to defer the things that are expensive to retrofit.

---

## 1. Constraints (non-negotiable)

| Constraint | Meaning in practice |
|---|---|
| **Code simplicity is priority #1** | Ahead of feature completeness. Always. |
| **Fewest files** | A new file requires justification. Prefer extending. |
| **React / Next.js** | Confirmed. Supersedes the earlier server-rendered decision. |
| **Deterministic code owns truth** | The LLM never computes a number, date, quantity, or trigger state. |
| **Apple-clean UX** | One primary action per screen. No visible plumbing. No settings sprawl. |
| **Opinionated by design** | See `INVESTI_TEARDOWN.md` §2. The discipline is the product. |

### The "fewest files" rule, concretely

The codebase has already produced three orphaned components (`AllocationDonut.tsx` and
two CAS components) through the component-per-widget habit. In React terms:

- Colocate. A feature is one file until it demonstrably needs two.
- A component that is not imported anywhere is deleted in the commit that orphans it.
- No abstraction layer for a single implementation.
- No "framework" where a function would do.

---

## 2. Phase 0 — Finish the engine

**Nothing in the workspace starts until this closes.**

### Outstanding from the documentation audit

- [ ] Commit the audit work in four separate commits (docs/invariants; `udiff.py`
      legacy-ISIN correction + the test that pinned the wrong message; waiver gate
      rewrite + 7 tests; donut deletion + `groupBy` default fix).
- [ ] Resolve the two CAS orphans. One does not typecheck. Determine whether they are
      superseded (delete) or half-finished (finish or stash). Do not delete blind —
      CAS ingestion is the chosen ingestion path.
- [ ] Persist the price waiver reason as a **structured enum**, not free text:
      `price_absent_confirmed` | `below_backfill_floor`. Below-floor waivers rest on a
      constant the invariants doc says may be lowered with a verified fetch. When the
      floor moves, those waivers must be findable and re-auditable.
- [ ] Independent review of the waiver gate logic. Written and tested by the same author
      in the same session. Route through `financial-auditor`. See `AGENT_PIPELINE.md` §5.
- [ ] Unresolved data-truth items: **GUJTHEM (Aug 2024), SOUTHBANK, SULA.** These change
      user-facing numbers. They outrank every UI item in this document.

### Remaining engine sessions

Sessions 6–12: price pipe, API, dashboard, Gmail automation.

### Forward-compatibility decisions that must be made NOW

Cheap today, expensive after the engine ships. All five exist because outside users are
coming.

1. **`user_id` on every table from day one.** It holds exactly one value during MVP. A
   single-tenant schema retrofitted to multi-tenant is a migration with a correctness
   risk attached; a column that is always `1` costs nothing.
2. **Tenant isolation enforced at the query layer, not the route layer.** Even with one
   user. Isolation added later is isolation that was never tested against the queries
   written before it existed.
3. **Provenance on every externally fetched fact.** `source`, `source_type`,
   `source_url`, `publication_date`, `period`, `retrieved_at`. Record it in the price
   pipe *now* — retrofitting provenance is impossible, because the information is gone.
4. **Append-only storage for anything a human writes.** Notes, theses, decisions are
   never updated in place. The existing `engine/ledger` pattern (`seq bigserial`,
   explicit `ORDER BY (txn_date, seq)`) is the model. Extend it; do not build a parallel
   store.
5. **A single `entity` reference.** Notes, theses, monitors and holdings all point at the
   same company identity, resolved through the existing ISIN alias machinery. Two
   identity systems is the bug that never ends.

---

## 3. Phase 1 — Workspace core

See `WORKSPACE_SPEC.md` §3–§5.

- Notes (atomic, linked, date-stamped, append-only)
- The question ritual (write questions before research, answer after)
- The thesis ledger (thesis, anti-thesis, exit conditions, conviction changes)

**Why first:** this is the part whose absence is felt daily. Notion notes decay because
nothing brings them back. Skills, chat and Monitor are all worthless until a corpus of
the user's own writing exists to work against.

**Ship test:** you stop opening Notion.

---

## 4. Phase 2 — Skills and chat

AI grounded in the Phase 1 corpus. See `WORKSPACE_SPEC.md` §6–§7.

Start with **two** skills:

1. **Forensic accounting** — Financial Shenanigans, Beneish M-Score, cash-flow
   shenanigans. First because you have the expertise to detect when the output is wrong,
   which is the only reliable way to evaluate a skill. It is also the sharpest
   divergence from the comparable product, which builds around fundamentals rather than
   earnings quality.
2. **Thesis validation** — separate facts from assumptions, define counterarguments and
   invalidation conditions.

Phase 2b, one at a time, each only after the previous is genuinely used: financial
statement analysis · earnings analysis · initiating coverage · comparable companies ·
catalyst calendar · due-diligence checklist.

**Ship test:** you stop pasting company documents into other AI tools.

---

## 5. Phase 3–4 — Research tool layer and Monitor

See `WORKSPACE_SPEC.md` §8–§9.

**Phase 3** — a minimum tool layer. Trackr+'s own context first (thesis, exit plan,
decision history, position state, open questions, notes), because that is free, already
yours, and the only part no competitor has. Deterministic calculators second. External
data third, and only what §5.1 permits.

**Phase 4** — Monitor: scheduled re-execution of a research skill against a stored
thesis. Not a price alert. Each run immutable and independently auditable.

### 5.1 The data licensing gate

**Blocks Phase 3. Also blocks Alpha for anything already shipped.**

Every external source needs a written verdict before a tool is built against it:
NSE/BSE announcements, annual reports, results, investor presentations, concall
transcripts, shareholding patterns, corporate actions, news.

```
source
what the terms of use actually say   fetched, dated, with URL
personal use permitted?
commercial redistribution permitted?
attribution required?
rate limits / technical restrictions
verdict: USE / USE-WITH-LIMITS / DO-NOT-USE / NEEDS-LICENCE
```

Two things make this non-optional:

- The bhavcopy work already established the principle: **a public archive is not a
  redistribution licence.** The same logic applies here, one level up.
- Personal research and a commercial product are **different legal questions**. Verdicts
  recorded during MVP must state which one they answer, so nobody later mistakes
  "fine for my own use" for clearance to ship.

> Verify each source's terms at the source and date the check. Do not rely on what any
> document — including this one — believes the terms to be.

---

## 6. The Alpha gate

**Everything here must be true before the first outside user has an account.** Not
before public launch. Before user #2.

### Corporate structure — start this first, it has the longest lead time

**Trackr+ must sit in a separate legal entity from Mei Capital.**

The comparable product does exactly this: Investi is a product of Ombra, Inc. The
software company and the operator's other activities are structurally distinct.

The reason here is sharper. You hold SEBI Investment Adviser registration INA000022279.
A software product that tells a stranger *"your exit condition has triggered"*, operated
by a registered Investment Adviser, invites a question you do not want to answer
argumentatively. A clean corporate separation makes the answer structural.

- [ ] Separate entity incorporated, with its own bank account, contracts and branding
- [ ] Written position on the RIA's interest in the software entity, confirmed against
      the actual SEBI regulations by a lawyer — not inferred from any document
- [ ] No shared infrastructure, client data, or branding between the two
- [ ] Decide now whether Mei Capital clients may use Trackr+, because the answer changes
      the compliance picture materially

**Lead time: months. Start before Phase 1, not after Phase 4.**

### Technical

- [ ] Tenant isolation tested with queries that specifically attempt cross-user reads
- [ ] Authorization on every user-context tool
- [ ] Field-level encryption on personal and holdings data
- [ ] Audit log covering every read of user data
- [ ] Consent capture and withdrawal
- [ ] Data deletion on disconnect, and on account closure

### Legal — drafted with a lawyer, benchmarked against real published terms

- [ ] Terms of Use
- [ ] Privacy Policy + DPDP Act 2023 notice (data fiduciary obligations, consent,
      grievance officer, breach notification)
- [ ] Risk disclaimer
- [ ] **Non-advisory boundary statement** — the critical one

The boundary statement must say plainly: this is a research and information tool, not a
licensed investment firm, broker or adviser; its output is general information generated
by AI, not a personal recommendation; it can be wrong; verify independently. The product
design already enforces this (process not picks, no buy/sell, AI as Socratic mirror).
The document makes it legible to a regulator.

Benchmark against MProfit, Kalpi, and Investi's published terms. **Read their actual
documents; do not infer them.**

### The intermediate case

Before outside users, there is a nearer situation: **you use Trackr+ for your own
research, and that research informs advice given to a Mei Capital client.** SEBI IA
regulations impose record-keeping obligations on advice and its basis. Confirm whether
workspace notes and thesis history fall inside that perimeter — because if they do, the
retention and audit requirements attach immediately, at MVP scale, with no launch
involved.

---

## 7. Deliberately not being built

Recorded so nobody builds them by accident:

- Buy / sell / hold recommendations, price targets, or conviction scores
- Net worth tracking, budgeting, expense management
- A user-visible MCP or tool marketplace
- Generic watchlist news digests (thesis-linked monitors only)
- Folder-first organisation as the primary structure — folders are what made Notion decay
- Social or community features
- Mobile apps (Phase 1–4 are desktop; research is a desk activity)
- Broker API integration (Kite Connect rejected: daily token expiry, order capability)
- Any write-capable AI tool. The AI proposes as a diff you approve; it never mutates.

---

## 8. Sequencing

```
Phase 0   Engine complete + forward-compat decisions        ← current
          ├─ parallel: entity incorporation (§6)            ← start now, long lead time
          └─ parallel: data licensing verdicts (§5.1)
Phase 1   Notes, question ritual, thesis ledger
Phase 2   Forensic + thesis-validation skills, grounded chat
Phase 2b  Remaining skills, one at a time
Phase 3   Tool layer                     [BLOCKED BY §5.1]
          ═══ ALPHA GATE §6 ═══          [first outside user]
Phase 4   Monitor
```

Each phase ships and is used for at least two weeks before the next begins. A phase that
isn't used was a wrong phase, and finding that out is cheaper than building the next one
on top of it.

The Alpha gate sits where it does because the workspace becomes genuinely useful to
someone else around Phase 3 — and the entity and legal work must already be finished by
then, not starting.
