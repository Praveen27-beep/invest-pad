# Trackr+ — Agent Pipeline

How work moves from a product decision to `main`.

This is the **development/review pipeline**, not the product's runtime agent loop.
The proposed runtime contract is in `WORKSPACE_SPEC.md` §9; its adoption remains pending.

---

## 1. The pipeline

```
                      YOU
                       │
                Product decisions
                       │
                       ▼
                ┌─────────────┐
                │  ARCHITECT  │
                └──────┬──────┘
                       │
                ARCHITECTURE.md
                       │
                       ▼
                ┌─────────────┐
                │ IMPLEMENTER │
                │ Claude Code │
                └──────┬──────┘
                       │
            ┌──────────┼──────────┐
            ↓          ↓          ↓
         TEST QA   FINANCIAL   DATA QA
                    AUDITOR
            │          │          │
            └──────────┼──────────┘
                       ↓
                ┌─────────────┐
                │ INTEGRATION │
                │   / GATES   │
                └──────┬──────┘
                       ↓
                DOCS / CONTEXT
                       ↓
                    REVIEW
                       ↓
                     MAIN
```

Each stage is a **separate session with a separate context**. That separation is the
entire point — see §5.

---

## 2. Roles

### ARCHITECT

**Input:** a product decision from you, in a sentence or two.
**Output:** a written plan appended to the relevant spec. No code.

Remit:
- Read the existing architecture before proposing anything
- Identify which existing models, services and invariants the change touches
- Name the files that will change and why each is necessary
- **Justify every new file.** The default answer is "extend what exists"
- State what could break, and what will be tested to prove it didn't

Hard rules:
- Writes documentation only. Never source code.
- If the requirement conflicts with an established invariant: **stop and flag it.**
  Do not design around it silently.
- No new abstraction layer for a single implementation.
- Output must fit on one screen. A plan that needs more than that is a plan for
  work that should be split.

### IMPLEMENTER

**Input:** the ARCHITECT's plan.
**Output:** working code, plus tests for the happy path only.

Remit:
- Implement exactly the plan. Nothing adjacent, nothing "while I'm in here."
- If the plan turns out to be wrong mid-implementation: stop, report, return to
  ARCHITECT. Do not improvise a different design.
- Leave nothing orphaned. A component that is no longer imported is deleted in the
  same change that orphans it.

Hard rules:
- **Does not write its own adversarial tests.** See §5.
- Does not modify `ARCHITECTURE_INVARIANTS.md`.
- Does not commit.

### TEST QA

**Input:** the implemented change, and the plan it was meant to satisfy.
**Output:** adversarial tests and a verdict.

Remit — test the cases the IMPLEMENTER had no incentive to think of:
- Absent data, stale data, conflicting sources
- Boundary conditions on every threshold and floor
- Idempotency: what happens when this runs twice
- Failure of every external dependency
- Permission and isolation (once multi-user exists)
- **Whether the tests that already exist are pinning correct behaviour.** The
  documentation audit found a test asserting a factually wrong error message. Tests
  are not automatically evidence.

Verdict: PASS / FAIL / FAIL-WITH-FINDINGS. A finding is not a suggestion.

### FINANCIAL AUDITOR

**Input:** any change touching money, quantities, dates, or corporate actions.
**Output:** a correctness verdict against real data.

Remit:
- Cost basis (FIFO and weighted-average), XIRR, allocation, day change
- Corporate action transformations — split, bonus, demerger, merger, rights
- Reconciliation against known-good fixtures (the 324 real Zerodha trades)
- Anything asserting an absence: a waived price, an excluded ISIN, an unfetched value

Hard rules:
- **Never infers a corporate action from price/quantity arithmetic.**
- An unverified number is a FAIL, not a caveat.
- Reports in the format: FACT / SOURCE / EXPECTED / ACTUAL / VERDICT.

### DATA QA

**Input:** any change touching ingestion or external sources.
**Output:** a provenance and licensing verdict.

Remit:
- Every externally sourced fact carries full provenance
- Source terms of use have a recorded, dated verdict (`MASTER_PLAN.md` §5.1)
- Contradictory sources are **surfaced, never silently reconciled**
- Identity resolution goes through the existing ISIN alias machinery, not a new one

### INTEGRATION / GATES

Mechanical. No judgement.

```
pytest                      full suite, zero failures
ruff check .                clean
tsc --noEmit                clean
architecture gates          pass
no un-ignored client documents in the working tree
no orphaned components      nothing unimported in the tree
```

A gate failure stops the pipeline. Gates are never waived "just this once."

### DOCS / CONTEXT

**Input:** the merged-ready change.
**Output:** documentation that matches reality.

Remit:
- Every invariant names *where it is enforced*, so a rule and its enforcement cannot
  drift apart
- Correct any doc the change has falsified — including docstrings
- Maintain the four-way split: implemented-and-verified / implemented-but-unexercised /
  unresolved-and-visible / deliberately-excluded
- Never state a hypothesis as a fact. Third-party internal design is a hypothesis.

### REVIEW

You. The only stage that commits.

---

## 3. Handoff contract

Every stage hands over the same four things:

```
WHAT I DID
WHAT I DID NOT DO        ← including anything I was asked to do and declined
WHAT I AM UNSURE OF
WHAT NEEDS YOUR DECISION
```

"What I did not do" is the most valuable of the four. A report that omits it is
incomplete and goes back.

---

## 4. Commit discipline

- Working tree only until REVIEW. `main` is never touched by an agent.
- One logical change per commit. Four fixes is four commits.
- A commit that mixes a correction with a refactor cannot be reverted cleanly, and
  will eventually need to be.

---

## 5. The separation rule

**No agent grades its own work.**

This exists because of a specific failure: a price-waiver function was written in one
session with zero tests, and the tests for it were written later by the same author in
the same session. Both sides of the check had one author, one context, and one set of
assumptions. The tests passed. That proves the code matches the author's mental model;
it proves nothing about whether the mental model is correct.

Therefore:

| Written by | Must be checked by |
|---|---|
| IMPLEMENTER | TEST QA — different session, different context |
| Any financial logic | FINANCIAL AUDITOR — against real data, not fixtures the same agent wrote |
| Any ingestion | DATA QA |
| Any documentation | the agent whose code it describes, reading it cold |

The checking agent is given the **requirement**, not the implementation's reasoning. If
it needs the reasoning to understand the code, that is itself a finding.

---

## 6. The stop-and-flag rule

Applies to every agent at every stage:

> If a proposed implementation conflicts with an existing invariant, **stop and flag the
> conflict rather than improvising.**

Frontier models are extremely good at building systems that look architecturally
impressive. The larger risk here is not insufficient capability — it is unnecessary
complexity and the quiet violation of financial-data invariants that already exist and
already work.

An agent that flags a conflict and stops has done its job correctly, even if it produced
no code.

---

## 7. What "done" means

Not: the happy path demo works.

Done is:
- Gates green
- TEST QA verdict is PASS with no open findings
- FINANCIAL AUDITOR verdict against real data, where applicable
- Documentation matches the code, with no falsified claims left behind
- Nothing orphaned in the tree
- The handoff report's "what needs your decision" section is empty, or you have decided

### Proposed research evaluation gate

A runtime loop revises one research run; the engineering loop converts reviewed failures
into regression cases, changes the harness, then evaluates a candidate version before release.

- Reuse existing source/guardrail tests and report corpus; add held-out cases per method.
  Pin corpus, model, prompt/method, extractor, retriever and output-schema versions.
- Measure retrieval recall, citation/claim support, period/unit/basis accuracy, contradiction
  retention, memory-version attribution, abstention, cost and latency; approve thresholds
  before release. LLM grading alone cannot certify financial facts or tenant isolation.
- Adversarial cases: inaccessible/deleted sources, stale memory, forged citations, injected
  document instructions, cross-tenant search/cache/artifacts, duplicated/stalled jobs,
  cancellation, exhausted budgets and unknown provider billing. Preserve deterministic tests.
- Store failures and compare each model/prompt/retrieval change against the same baseline;
  synthetic fixtures do not prove real-source extraction or configured deployment readiness.
- Evaluating stored traces establishes a baseline, not proof of a fix: rerun the candidate
  agent on held-out cases and compare its new outputs. Use public, synthetic or explicitly
  authorized/redacted cases; never copy private investor traces into shared tests by default.
