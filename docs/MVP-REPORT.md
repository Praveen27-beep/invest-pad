# MVP report

17 Nov 2026. Branch `invest-pad/main`. Everything below is from the code and test runs;
nothing is estimated unless it says so.

## The success test

*Can an investor reopen an old company and recover the decisive reason they bought,
passed, or stopped researching, without rereading their documents?*

**Yes, on a synthetic company, without a model.** The company page opens on an Overview
that shows the last decision, its decisive reason in the user's own words, what would
change their mind, the thesis version in force that day, the assumptions it rested on
then and how each stands now, and what was added since. `e2e/thesis.py` checks this in
real Chrome. No AI is involved, so the answer cannot be invented. With a model connected,
"why did I buy this?" in Ask or the Chrome side panel is answered from the decision
entry, cited to it; a statement whose quotation is not in the decision is dropped.

**Not yet proven with real material**: no real investor has used it on a real company
for months, and no real model has answered a question (see below).

## What exists

| Area | What |
|---|---|
| Accounts | Invite-only sign-up, sessions, login and sign-up rate limits, export everything, delete account |
| Isolation | Forced row-level security on every owned table, owner-scoped foreign keys; guard tests fail the build if a new table misses either |
| Notes | Versions, `[[links]]`, backlinks, mentions, rename, search |
| Capture | Chrome side panel: save selections, offline queue, ask questions (token permission) |
| Documents | PDF / Excel / Word upload, passage extraction and search; delete removes text and everything derived |
| Thesis | Versions with diffs, assumptions (sourced fact vs judgement) with versions, evidence for/against, decision journal with snapshot, Overview |
| Assistant | Bring-your-own model (OpenAI-compatible), cited answers from documents, notes and your recorded decisions, with quotation checking, advice refusal, per-task and monthly caps, "How I invest" guardrail, contradiction scan suggestions |
| Analysis | Editable checklists (red flags, forensic), Numbers tab: 11 calculations with formulas, including DuPont, Beneish M-score, Sloan accruals |
| Portfolio | Holdings CSV import, user-set limits with alerts, watchlist, monthly review questions |
| Views | Connections graph (per company and workspace), decision journal, company Markdown export |
| Integrations | Read-only MCP server (list, search, get company) |
| Operations | Docker compose, backup/restore scripts, CI (backend, web, extension) |

## Evidence

- Backend: **203 tests** pass (pytest, Postgres 16), ruff clean. Includes isolation,
  delete-leaves-nothing (a marker word searched across every text column after delete),
  export completeness (row counts per owned table), prompt-tag forging, cross-tenant
  access on every endpoint added after M6, calculations against hand-worked values.
- Extension: 9 unit tests.
- Browser (real Chrome, by hand, all passing on 17 Nov): `workspace.py`, `capture.py`,
  `thesis.py` (success test), `assistant.py`, `portfolio.py` (holdings, limits, alerts,
  checklists, numbers, graph, review, export download, account deletion).
- CI green on every push of `invest-pad/m8-export`.

## Model quality — not measured

No paid model has been called; no money was spent. `python -m eval.run` is ready: it
builds a fictional corpus, prints the worst-case cost (about $0.05 for 15 questions at
$0.30 / $1.20 per million tokens — prices you set), and runs only with `--send`.
Run with the built-in test model, it exercises the whole path (4 of 15 checks pass,
which reflects the crude test extractor, not a real model).

**Needed from Parasu:** a key for a DeepSeek model **on a third-party host** (not
DeepSeek's own API). Check that host's current price and data terms, then run the eval
and fill the human-check column.

## Known gaps

- Keyword search only; vector search is not built.
- No OCR; large scanned annual reports untested.
- `docker compose up`, the backup scripts under Docker, and the extension's toolbar,
  shortcut, context menu and permission prompt were never run on a real machine here.
- Trackr+ live link not built (needs the Trackr+ side; CSV import works today).
- Rate limits are per process.
- Privacy policy and terms are drafts for a lawyer.

## Costs

Development spend on models: $0. Running cost depends on hosting (not chosen) and on
included credit, which is off unless `PLATFORM_MODEL_*` is set.
