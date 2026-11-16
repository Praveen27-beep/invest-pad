# 04 — Roadmap

Date: 16 Nov 2026. Effort is in **build days** (one focused day of agent-assisted work
plus your review). These are rough estimates with no track record behind them yet; I will
replace them with actuals after M1 and M2.

Rule for every milestone: feature branch off `invest-pad/main`, small commits, tests
included, CI green, `docs/HANDOFF.md` updated, one status line posted.

## MVP — M1 to M6, in order

| # | Milestone | Delivers | Done when | Est. |
|---|---|---|---|---|
| **M1** | Foundation | Repo skeleton, docker compose, migrations runner, config, signup/login with invite codes, sessions, RLS on every owned table, secret-free logging, CI (lint, tests) | `docker compose up` works from a clean clone; cross-tenant test suite passes; a table without an RLS policy fails CI | 3 |
| **M2** | Workspace | Company pages, block editor, note versions, `[[links]]`, block links, linked + unlinked backlinks, keyword search | I can write linked notes for the demo company; rename keeps links; old versions readable | 5 |
| **M3** | Capture | MV3 extension with side panel, extension tokens, inbox, assign-to-company, offline queue | A note and a question captured on a web page appear in the inbox with URL and selection; token cannot read data | 4 |
| **M4** | Documents and retrieval | Upload PDF/Excel/Word, extraction, chunking, period/type tags, full-text + vector index, hybrid search, passage viewer, delete cascade | A search returns the right passage with page number; deleting a document leaves no text, embedding or citation behind (test) | 5 |
| **M5** | Thesis engine | Thesis versions with diff, assumptions with states, evidence for/against with statement kinds, decision journal, red-flag checklist, decisive-reason card, "since you were last here" | **The success test passes with AI switched off** on the demo company | 5 |
| **M6** | Question queue and analyst | Job queue + worker, answer pipeline with claim verification, `UNKNOWN`, calculation tools with formulas, model adapter, bring-your-own-key, per-question model, cost caps, usage ledger, full export ZIP | 50-question eval runs end to end; every shown claim has a verified citation; caps refuse over-budget tasks; export round-trips | 7 |

**MVP gate:** all milestone tests pass, the success test passes on the demo company, and
`docs/MVP-REPORT.md` is written (what works, what doesn't, how to try it). M7 does not
start before this.

MVP total: about **29 build days**.

### Landing page (after the MVP gate)

On a branch, for review only. Replace the existing page's unsupported claims
(`00-inventory.md` §4) with the one-liner, category, message, and only shipped features.
No deployment. Est. **1**.

## After MVP

| # | Milestone | Delivers | Est. |
|---|---|---|---|
| **M7** | Routines and agents | Saved questions on a schedule or on new-document events; runs tied to assumptions; in-app digest; optional email; web/news summaries with source links under a separate cap | 5 |
| **M8** | Skills, MCP, exports, journal | User-editable checklist skills as Markdown (forensic red flags, DuPont); MCP connector support; CSV/xlsx table export; "how I've evolved" journal; article-idea suggestions grounded in my notes | 7 |
| **M9** | Hardening and beta | Eval regressions fixed; cross-tenant and prompt-injection tests on agents and extension; basic load test; draft privacy policy and terms (for lawyer review); deployment preparation; onboarding for analyst friends; demo script | 6 + your steps |

## Dependencies on you

| Needed for | What |
|---|---|
| M2 onward | Push access for the session, or you apply patches locally |
| M5 success test | Your IEX notes and documents (or confirm another company) |
| M6 eval with a hosted model | A real API key and a spending limit — a stop condition; until then the pipeline is tested with a fake model and, if you have one, a local endpoint |
| M8 | The DuPont skill text |
| M9 | Lawyer review; hosting accounts; Chrome Web Store; NSE/BSE terms |

## Deferred, deliberately

Institutional tiers · SOC 2 · customer-hosted deployment · brokerage / portfolio linking ·
payments · live NSE/BSE integrations · mobile apps · real-time collaboration · OCR for
scanned PDFs · student/researcher pack (the core stays neutral so this is a pack, not a rewrite).

## Risks

| Risk | Sign | Response |
|---|---|---|
| Testers read answers but don't write theses | Few decisions recorded after two weeks | Make decision capture a 30-second flow; cut features, don't add |
| Citation verification rejects too many good claims | High "claims removed" rate in eval | Tune quote matching (whitespace, numerals) before touching prompts |
| PDF extraction is poor on Indian annual reports (scans, tables) | Wrong or empty passages in M4 | Report it honestly per document; OCR and table extraction become their own milestone |
| Host terms don't meet the region requirement | No written confirmation | Together US-pinned + ZDR, or BYO-key only for beta |
| Scope creep from the Trackr+ research code | Porting whole modules | Port functions with tests, one at a time |
