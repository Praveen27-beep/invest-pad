# Trackr+ Workspace — Product Specification

> **Review delta 2026-10-18 — PROPOSED, not implemented/approved by this document.**
> Existing contracts and invariants remain binding. Resolve conflicts in
> `MASTER_PLAN.md` D1–D7 before implementation; the original sections remain the baseline.

> You are not being asked to build a generic AI agent framework. You are extending an
> existing investment commitment ledger. Before implementing anything, understand the
> existing architecture and preserve its invariants. Prefer simple, composable
> primitives over framework-heavy abstractions. If an existing abstraction can support
> the requirement, extend it rather than introducing a parallel system. If a proposed
> implementation conflicts with an existing invariant, stop and flag the conflict
> rather than improvising.

---

## 1. The problem

Research currently happens across seven places:

| Where | For what |
|---|---|
| Multiple AI tools | Research, and separately, skills like forensic accounting |
| Screener | Watchlist status, latest updates on portfolio companies |
| Broker | Portfolio and index performance |
| Notion | Thousands of words across multiple documents per company |
| Google Sheets | Pre-research checklist |
| Paper notebook | Questions, written by hand before research |
| Nowhere | Going back to any of it |

The failure is not that the research is hard. It is that **the research does not
return**. A Notion document is written once and decays. A question in a notebook is
answered once and lost. Nothing brings prior thinking back at the moment it matters.

So the product is not a research tool. It is a **retrieval and return** system:
everything written once, in your own words, resurfaced against what you previously
committed to.

The design debt this pays off is described in *How to Take Smart Notes* (Ahrens) and
*Building a Second Brain* (Forte): notes only compound if they are atomic, linked, and
re-encountered. A folder of long documents is an archive. A second brain is a network
that talks back.

---

## 2. What this must never do

Structural, not stylistic. These are as binding as the engine's financial invariants.

The system must never:

- Issue a buy, sell, or hold recommendation, a price target, or a conviction score
- Rewrite or soften a thesis because new evidence contradicts it
- Modify an exit condition, a trigger, or any historical record
- Create an investment decision on the user's behalf
- Invent financial data, sources, or corporate events
- Infer a corporate action from price/quantity arithmetic
- Silently reconcile contradictory sources
- Calculate a number that deterministic code can calculate
- Convert uncertainty into confidence

When evidence is insufficient, **`UNKNOWN` is the correct output**, not a hedge.

The AI proposes an observation. It never changes a commitment.

---

## 3. Surface 1 — Notes (the second brain)

### Principles

- **Atomic.** One note, one idea. A 3,000-word company document is not a note; it is
  a folder pretending to be one.
- **Append-only.** Notes are never edited in place. A revision creates a new version;
  prior versions remain readable. This uses the same `seq bigserial` ordering pattern
  as the engine ledger — extend it, do not build a second store.
- **Date-stamped, always.** The date is not metadata. It is the thing that makes a note
  evidence of what you believed *then*.
- **Linked, not filed.** Notes reference companies, other notes, and theses. Folder
  hierarchy is secondary and may not exist at all.

### Note types

| Type | Purpose |
|---|---|
| `QUESTION` | Something you want to know. Open until answered. |
| `OBSERVATION` | A fact, with a source. |
| `INTERPRETATION` | What you think the fact means. Explicitly separate from the fact. |
| `THESIS_NOTE` | Attached to a thesis; forms part of the commitment record. |
| `LITERATURE` | Something you read, in your own words. Never a quote dump. |
| `DECISION` | Something you did, and why. |

The separation of `OBSERVATION` from `INTERPRETATION` is the highest-value constraint
in this list. It is also the hardest to keep. The UI should make it structural, not a
matter of discipline.

### Return mechanisms

A note that is never re-encountered is a note that was never written.

1. **On company open** — every note about this company, most recent first, with the
   open questions at the top
2. **On thesis review** — what you wrote when you formed the thesis, verbatim
3. **Spaced resurfacing** — a note from 6 / 12 / 24 months ago, presented without
   commentary. Just: *this is what you thought.*
4. **On contradiction** — when new evidence conflicts with a stored note, both are
   shown side by side. Neither is overwritten.

### Proposed investor-memory contract

Context engineering selects relevant authorized evidence; persistent memory retains versioned
investor records. Neither retrains the model. Shared harness improvements use permitted test
cases; private research does not automatically enter cross-customer evaluations or training.

- Extend existing notes, thesis revisions, decision records and scoped memory; no parallel
  memory store. Retrieval returns exact record/version IDs, authorship, dates and scope.
- Distinguish explicit investor statements, sourced observations and AI-inferred patterns.
  Inferences cite supporting/counter-evidence and stay proposed until reviewed; repetition
  in chat does not promote them to facts, preferences, commitments or instructions. No
  autonomous prompt/tool/policy changes or cross-investor learning.
- Link assumptions to a thesis version: statement, fact/hypothesis, evidence refs,
  deterministic check where applicable, review date/state. Qualitative assumptions do not
  automatically become executable exit conditions.
- Link journal entries to thesis/assumption versions, then-available evidence, action or
  inaction and reason; append outcomes/reviews without rewriting the original reasoning.
- Authenticate owner/investor scope before retrieval; future institutional access also
  requires membership. Exclude revoked/superseded content from active memory while retaining
  authorized historical review; erasure/holds follow `MASTER_PLAN.md` D4.

---

## 4. Surface 2 — The question ritual

This is the notebook habit, made structural. It is also the single most distinctive
feature in this document.

### The flow

```
You open a company for research
          ↓
BEFORE anything else:
  "What do you need to know?"
          ↓
  Free-form. Write every question. No answers yet.
  No AI, no data, no search. Just questions.
          ↓
  Questions are saved, date-stamped, marked OPEN
          ↓
  ── research happens ──
          ↓
  Return to the question list
          ↓
  Answer each one, in your own words
          ↓
  Review each answer with AI:
    "Is this answer supported by what I wrote?
     What did I not address? What did I assume?"
          ↓
  Questions close. Unanswered ones stay OPEN, visibly.
```

### Why the order matters

Questions written *before* research are your questions. Questions written *after* are
the ones the material suggested, which is a different and much weaker thing. Writing
them first also creates the only honest record of what you did not think to ask.

### Rules

- The AI may not answer a question until you have written your own answer first.
- Open questions never disappear. They surface on every subsequent visit to that company.
- A thesis cannot be created while a question tagged `blocking` is open.

---

## 5. Surface 3 — The thesis ledger

Immutable. This is the heart of the product and the part with no substitute elsewhere.

### Structure

```
THESIS                  what must be true for this to work
ANTI-THESIS             what would prove me wrong
MEASURABLE VARIABLES    the specific numbers the thesis depends on
EXIT CONDITIONS         explicit, deterministic, checkable
HOLDING PERIOD          intended
PRE-MORTEM              it is three years later and this failed. why?
CONVICTION              with the date of every change, and the reason
```

Every field is date-stamped. Every change creates a new version. **Nothing is ever
edited in place.**

### Falsifiability requirement

A thesis that cannot be proven wrong is not a thesis. On creation, the system requires:

- At least one measurable variable with a threshold
- At least one exit condition expressible as a deterministic check
- A pre-mortem

If the user cannot supply these, the thesis is saved as `DRAFT` and flagged — not
rejected, but not treated as a commitment either.

### Deterministic trigger checking

Exit conditions are evaluated **in code, not by the LLM**. The LLM may explain a
trigger; it may never determine one.

```
FACT               Operating margin fell from 21.2% to 17.9%
USER COMMITMENT    Thesis stated the business should sustain >20% operating margin
TRIGGER            Exit plan specifies two consecutive quarters below 18%
STATUS             TRIGGERED
INTERPRETATION     This weakens a central assumption
UNCERTAINTY        Management attributes it to temporary raw-material inflation
```

The output ends there. It does not say SELL. It says: **your thesis needs a review.**

### The override path

A triggered condition does not force an action. If you decide to continue holding, that
creates a decision event:

```
OVERRIDE_EXIT_TRIGGER
reason: <required, free text, date-stamped, permanent>
```

This is where the system strengthens the commitment ledger instead of bypassing it. The
override is itself a commitment, and it will be resurfaced later.

---

## 6. Surface 4 — Skills

A skill is a **reusable research method**, not a prompt.

### Phase 2 — build exactly two

**Forensic accounting.** Financial Shenanigans framework, Beneish M-Score, cash-flow
shenanigans. First because you have the domain expertise to detect when its output is
wrong — which is the only reliable way to evaluate a skill.

**Thesis validation.** Separates facts from assumptions, defines counterarguments and
invalidation conditions. Pressure-tests an idea before it becomes a position.

### Phase 2b — one at a time, each only after the previous is genuinely used

Financial statement analysis · Earnings analysis · Initiating coverage · Comparable
companies · Catalyst calendar · Due-diligence checklist

Eight shallow skills are worth less than two that work.

### Skill contract

Every skill declares: which tools it may call, what it must cite, what it outputs, and
what it is forbidden from concluding. A skill that can reach a buy/sell conclusion is
misconfigured.

---

## 7. Surface 5 — Chat

Grounded in your corpus first, external sources second.

- Answers from your own notes cite the note and its date
- Answers from external sources carry full provenance
- Answers from neither say so plainly
- The chat may not write to notes, theses, or decisions. It may **propose** a note,
  which you accept or discard.

---

## 8. Surface 6 — The tool layer (Phase 3)

MCP is plumbing. **The user never sees the word.** They see "Research this company."

### Order of construction

**First: Trackr+'s own context as tools.** Free, already yours, and the only part no
competitor can replicate.

```
get_active_thesis(position)
get_thesis_history(position)
get_exit_plan(position)
get_pre_mortem(position)
get_decision_history(position)
get_open_questions(position)
get_notes(position)
get_position_state(position)
get_trigger_status(position)
```

**Second: deterministic calculators.** Built in-house, never delegated to the LLM.

```
calculate_financial_metrics(company, period)
calculate_valuation(company, method, assumptions)
```

Returns value, period, the calculation performed, and sources. The model interprets
the result. The model does not produce the result.

**Third: external data.** Blocked by the licensing gate — see `MASTER_PLAN.md` §5.1.
Start with the smallest set that makes the forensic skill work: filings, structured
financials, announcements. Not fifteen tools.

### Provenance is mandatory

Every externally sourced fact carries `source`, `source_type`, `source_url`,
`publication_date`, `period`, `retrieved_at`, `company`, `document_reference`. A tool
returning a financial fact without provenance is a bug, not a degraded result. The only
exception is an internal deterministic calculation.

### Contradiction handling

```json
{
  "status": "CONFLICT",
  "claim": "...",
  "sources": ["...", "..."],
  "conflict": "..."
}
```

Surfaced, never resolved silently. Exchange filings, annual reports, news and management
commentary disagree constantly, and the disagreement is frequently the most informative
thing available.

### Read-only

The tool layer cannot place trades, modify holdings, modify a thesis, modify exit
conditions, delete decisions, or rewrite history. No exceptions, no configuration flag.

### Proposed document/search contract

- Reuse existing private document storage and extraction. Retain immutable source bytes,
  digest, provenance and extraction version; keep metadata/relationships in the existing
  database. Search indexes/embeddings are rebuildable derivatives, never the source of truth.
- Idempotent ingestion: fetch/upload → validate/quarantine → extract → index; persist stage,
  attempt, digest and failure reason. OCR or another parser is a separately versioned change.
- Chunk refs bind document digest/version to page/span and extraction/chunking version;
  embeddings additionally pin model/version. Do not overwrite an index version in use by a run.
- Search filters owner/investor permissions **before** ranking; enforce again at source read.
  Include authorization/version scope in cache keys and worker context, not text alone.
- Start with existing structured/keyword retrieval. Add vector/hybrid ranking only against
  a measured benchmark; define collection sizes, upload bounds, pagination and latency (D7).
- RAG returns permitted evidence plus exact citations and coverage gaps; retrieved text is
  untrusted data, never tool authority. Recheck digest, excerpt, company, period, units and
  accounting basis; copied filings are not independently originated corroboration.
- Revocation/deletion invalidates active chunks, embeddings, caches and derived access;
  retained history and backups follow the approved retention/hold policy (D4).

### Provider abstraction

Each data provider is replaceable. Adding a source must not require touching the
research engine. But do not build the abstraction before the second provider exists —
one implementation behind an interface is an interface written from a guess.

---

## 9. Surface 7 — Monitor (Phase 4)

### Proposed runtime harness (shared by chat, skills and monitors)

The harness is the controlled execution environment: context, tools, workflow, verification,
state and budgets. Start with one research runner over existing stages; additional agents or
frameworks require a demonstrated gap, not a replacement of working contracts.

- Reuse current sealed task/report/job contracts: pin investor scope, purpose, thesis/memory
  versions, evidence cutoff, method/output schema, model and budget before execution.
- Bound plan → retrieve → deterministic tools → draft → verify → render/review; authorize
  each tool call. Missing evidence leads to bounded retrieval or `UNKNOWN`, not endless loops.
- Record stage/tool inputs and outputs, source refs, checks, attempts, cost and terminal
  state; no secrets or unrestricted private prompt logs. Do not require hidden chain-of-thought.
- Verification rejects unsupported facts/calculations/citations; conflicting evidence stays
  visible. Only an explicit human acceptance may append a research record.
- Checkpoints, cancellation, idempotency and retry budgets reuse existing workers. A model
  timeout/refusal or partial run cannot be reported as complete; replay uses pinned inputs.
  Evaluation requirements live in `AGENT_PIPELINE.md` §7; execution approval remains D6.
- Offline harness optimisation is a separate proposal in `AGENT_PIPELINE.md` §7,
  “Proposed offline harness experiments”; it grants no runtime self-modification authority.

```
Chat     = research now
Skill    = how to research
Tools    = what research can reach
Monitor  = research this again later
```

Monitor is a **scheduled research run**, not an alert. The distinction:

> An alert says: ABC fell 10%.
>
> A Monitor says: ABC fell 10%. I reread your thesis. Your thesis depended on stable
> margins; the latest filing shows gross margin down 300bps for two consecutive
> quarters. Here is the evidence, and here is the exit condition you wrote in March.

### Execution

```
Schedule fires → create research run → load Trackr+ context →
load the thesis version in force → invoke skill → invoke tools →
gather fresh evidence → compare against the commitment →
run deterministic guardrails → generate report → store immutably
```

Every run is independently auditable and **never overwritten**. The history is the
product:

```
What did I believe?  →  What changed?  →  What did the evidence show?
  →  What did my own rules say?  →  What did I do?
```

### Output structure

Every run answers, in this order: what changed (material only) · why it matters to
*your* thesis · what your thesis actually said · supported or challenged · did any of
your own conditions trigger (deterministic) · what remains uncertain · what to
investigate next (questions, never recommendations).

### Scope

Thesis-linked monitors only. Generic watchlist digests are explicitly out of scope —
they are the feature that turns this back into a news reader.

Scheduled triggers first. Event triggers (post-results, post-concall) only once event
detection is trustworthy. **Fail closed:** a monitor that cannot verify an event did not
happen does not run, rather than running on a guess.

A Monitor never creates a decision. It can only ask you to review.

---

## 10. UX principles

Apple-clean means restraint, not minimalism as decoration.

- **One primary action per screen.** Everything else is secondary or hidden.
- **The plumbing is invisible.** No MCP, no tool registry, no provider, no "agent,"
  no function calls. The user sees *Research this company*, *Investigate my thesis*,
  *Monitor this thesis*.
- **Writing is the centre.** The editor is the largest thing on screen and has no
  chrome around it.
- **Dates are always visible.** They are the load-bearing element of the whole product.
- **Facts and interpretation are visually distinct.** Not by convention — by layout.
- **No dashboards of numbers that tell you nothing.** The allocation chart that showed
  a single 100% "Stocks" ring is the anti-pattern: technically correct, informationally
  empty.
- **No settings the user must understand to get value.** Defaults are opinions, and
  this product has opinions.

### Component discipline

React confirmed. "Fewest files" means few large components, not many small ones. The
existing tree has already produced three orphans from the opposite habit. A feature is
one file until it demonstrably needs two, and an unimported component is deleted in the
commit that orphans it.

---

## 11. What this is, in one sentence

> An investment research system that remembers what you believed and periodically
> checks reality against it.

```
Notes       = memory
Questions   = honesty
Thesis      = commitment
Tools       = eyes
Monitor     = time
Guardrails  = discipline
LLM         = reasoning and explanation
```

Not one of those is the product on its own. The product is that they are in the same
place, and that the first four of them are yours rather than the machine's.
