# 00 — Inventory (Phase 0)

Date: 16 Nov 2026. Read-only pass. Nothing in the repo was changed except adding this
file and `docs/HANDOFF.md` on branch `invest-pad/phase-0-inventory` (local, not pushed).

## 0. What I could and could not inspect

| Item | Status |
|---|---|
| GitHub repo `Praveen27-beep/invest-pad` | Cloned (public as of today). Default and only branch: `codex/invest-pad-ui`, head `b600a34` (19 Oct 2026). 93 commits, 773 tracked files. |
| Local folder "investing space" on Desktop | **Not inspected.** Folder access was declined, then refused. `git remote -v`, `git pull` and "local changes never pushed" are therefore **unchecked**. `docs/INVEST_PAD_UI_HANDOFF.md` says the original Desktop checkout had uncommitted changes that were "preserved" — those are still unknown to me. |
| `files_1.zip` | 3 files: `MASTER_PLAN.md`, `WORKSPACE_SPEC.md`, `AGENT_PIPELINE.md` (older draft of the master plan). |
| `Main.zip` | 10 files: the same three (newer master plan), `INVESTI_TEARDOWN.md`, and six Claude Code role prompts (`architect`, `implementer`, `test-qa`, `financial-auditor`, `data-qa`, `docs-context`). |
| "The attached notes file" | I treated the two zips as the notes. No IEX or GSM Foils research notes were supplied. |

## 1. The headline finding

**`invest-pad` is not a standalone Invest-pad repo. It is the full Trackr+ monorepo with
an Invest-pad UI branch on top.**

- Commits 1–83 are Trackr+ history (engine, ingestion, tax, dividends, migrations 001–059).
- Commits 84–93 (7–19 Oct 2026) are the Invest-pad work: landing pages, an illustrative
  workspace preview, a PVR INOX research pilot, and four proposal docs.
- The README still opens "Trackr+ — Portfolio Intelligence Platform". `MASTER_PLAN.md` and
  `WORKSPACE_SPEC.md` are titled Trackr+ and describe the workspace as a layer on the
  Trackr+ engine: "One database, one auth model".
- `trackr-workspace-frontend/.env.example`: "There is no Workspace backend" — it talks to
  the same FastAPI backend and accounts as Trackr+.

Consequences:

1. **Making the repo public today published Trackr+'s source and history.** I scanned all
   history: no API keys, private keys or credentialed DB URLs; the real 324-trade golden
   portfolio was never committed (gitignored); fixtures are labelled synthetic; no
   statement PDFs/zips. PAN-shaped strings in tests look like placeholders (`ABCDE1234F`,
   `AAAPZ1234C`, `BEXPD1234F` — confirm the last is not real). Docs name Mei Capital, the
   IA registration number and the `ingest.mei.capital` mail domain.
2. **It conflicts with three decisions in the brief:** "standalone product, separate repo,
   its own login"; "do not touch Trackr+"; "No Mei Capital … anywhere in Invest-pad".
   Building in this tree means editing a copy of Trackr+ code.

## 2. What already exists

### 2.1 Invest-pad-specific (last 10 commits)

| Thing | Where | State |
|---|---|---|
| Marketing pages: landing, Features, Pricing (coming soon), Blog (coming soon), Manifesto, Docs | `trackr-workspace-frontend/app/components/Landing.tsx` (376 lines), `app/[info]/page.tsx`, `public.css` | Built. Not deployed. See §4. |
| Illustrative workspace preview (company / writing / skills) | `WorkspaceDemo.tsx` | Demo only; notes are lost on reload. |
| Research UI: explorer, note editor, note kinds, thesis panel, evidence panel, tasks, reports, chat, skills, monitors, agents routes | `app/components/research/*`, `app/skills`, `app/monitors`, `app/agents`, `app/explorer` | UI over the Trackr+ research API. End-to-end save/revision/proposal was **not** exercised (privacy-policy gate refused writes). |
| PVR INOX curated research pilot (10-chapter report, 4 concall observations, scenario model) | `lib/pvr-research.ts`, `lib/pvr-company-report.ts`, `docs/PVR_RESEARCH_RECONSTRUCTION.md`, `docs/COMPANY_RESEARCH_METHOD.md` | Hand-curated content in frontend code. 15 focused tests. |
| Proposal docs (18–19 Oct 2026), all marked PROPOSED | `docs/MASTER_PLAN.md`, `WORKSPACE_SPEC.md`, `AGENT_PIPELINE.md`, `INVESTI_TEARDOWN.md` | Positioning ("Your research. Your thinking. Your AI.", "AI Investment Studio"), investor-memory contract, document/search contract, runtime harness, eval gate, open decisions D1–D7. |

### 2.2 Inherited from Trackr+ (in this repo)

- **Backend** `trackr-backend/` — FastAPI, raw SQL via `psycopg`, 59 numbered `.sql`
  migrations, no ORM. 110 test files.
- **Research backend already present** (migrations 040–058; `app/research/` 33 modules):
  workspace evidence, commitments (thesis), execution, monitors, chat, guards, access
  (ownership/RLS, migration 045), source extraction, fact attribution, evaluation replay
  manifest, "Butler" notebook memory, hosted jobs with budgets/leases, report documents,
  retention categories. Also `calculator.py`, `guardrails.py`, `skills.py`, `tools.py`,
  `documents.py`, `sources.py`.
- **Auth** `app/auth/` (service, repository, dependencies, capabilities via
  `GET /auth/capabilities`).
- **Storage** `app/storage/` (local + S3 adapters, key handling). **Jobs** `app/jobs/` (queue,
  drain, hosted, monitors).
- **Model clients**: `app/ai/groq.py`, `app/ai/jev.py` (plain `urllib`, no SDK); optional
  `anthropic` SDK for hosted report jobs.
- **Frontends**: `trackr-frontend/` (portfolio app + Trackr+ landing),
  `trackr-workspace-frontend/` (Next 14, React 18), shared `packages/trackr-{core,ui,portfolio}`.
- **Contracts**: `contracts/openapi.yaml`, `schema/*.schema.json`, `fixtures/*`.

### 2.3 Known test state (reported by the repo, **not re-run by me**)

`docs/INVEST_PAD_UI_HANDOFF.md`: frontend typechecks and build pass; full backend run was
**1,424 passed, 17 failed, 36 skipped, 501 errors**, mostly test-harness DB-role
provisioning. "This suite is not green and production release remains blocked."

### 2.4 Not present anywhere

- No Chrome extension / floating notepad (no MV3 manifest in the repo).
- No pgvector, embeddings or hybrid retrieval (search contract says "start with existing
  structured/keyword retrieval").
- No DeepSeek or OpenAI-compatible adapter; no bring-your-own-key; no per-question model
  choice; no per-user cost caps as described in the brief.
- No docker compose. No Invest-pad-only login.
- No DuPont skill in the repo (no file mentions it). The forensic-accounting method is
  described in docs and configured server-side; your `forensic-analyzer` skill lives
  outside the repo.
- No IEX or GSM Foils material. The only demo company is PVR INOX.
- No Zip Filings code (handoff: "the supplied standalone Zip Filings archive is not a newly
  deployed connector").

## 3. What is reusable

| Asset | Reuse verdict | Note |
|---|---|---|
| Product thinking in `WORKSPACE_SPEC.md` (note types, observation vs interpretation, thesis ledger, falsifiability, deterministic triggers, override path, monitor ≠ alert, "AI proposes a diff") | **Reuse as-is.** | Matches the non-negotiables closely. Best material in the repo. |
| Investor-memory, document/search and harness contracts (proposed) | **Reuse as design input** for `docs/03-architecture.md`. | Already domain-neutral in shape (statements / observations / inferences, versions, citations). |
| Eval gate in `AGENT_PIPELINE.md` §7 | **Reuse** for `docs/05-eval-plan.md`. | Metrics and adversarial cases are already listed. |
| Trackr+ auth, tenancy/RLS, storage, job queue, audit, consent patterns | **Copy the patterns, not the tables.** | Tied to `investor`, ISIN identity and portfolio capabilities. A domain-neutral core should not depend on them. |
| `app/research/calculator.py`, `guardrails.py`, citation/claim checks | **Port selectively.** | Deterministic-calculation and unsupported-claim checks are exactly what M6 needs. |
| Landing/manifesto copy and visual design | **Partly.** | Rewrite claims per §4. |
| PVR INOX pilot | **Reference only.** | Hard-coded in frontend; not your notes; not the chosen demo company. |
| Six role prompts (architect, implementer, test-qa, financial-auditor, data-qa, docs-context) | **Adapt.** | Written for Trackr+; the review-separation idea carries over. |
| Zip Filings | **Later**, via `docs/06-data-sources.md`. | Not in this repo. |
| Your forensic-accounting skill | **Yes**, as the first checklist skill (M8). | DuPont skill: not found; needs to be supplied or written. |

## 4. Landing page report

Location: `trackr-workspace-frontend/app/components/Landing.tsx` plus `/features`,
`/pricing`, `/blog`, `/manifesto`, `/docs` via `app/[info]/page.tsx`. Not deployed.
Nothing found on, and nothing touched at, meicapital.in.

**What it says:** "The AI Investment Studio for Indian equities." "Your entire investment
routine, in one place." "Built for Indian listed equities." "Research and information, not
investment advice." Manifesto: "Raise an army." / "Institutions had the analysts. Now you
have the harness." FAQ states no buy/sell/hold, price targets or conviction scores.

**Good:** no "SEBI compliant" claim; no testimonials or user numbers; pricing honestly
"coming soon"; the non-advice line is present.

**Outdated or wrong against the brief:**

| Line on the page | Problem |
|---|---|
| "Open any of thousands of companies and get live price, fundamentals, earnings, and initial research one click apart." | **False for this build.** The page's own Docs section says a company quote feed and automated filings retrieval "are not connected". Brief: only features that exist. |
| "An AI analyst that shows its work … answer in seconds", "Research that runs on a schedule … earnings recap, the filing watch, the weekly portfolio check" | Not built for Invest-pad; filings watch contradicts "skip live filing integrations". |
| "No philosophy baked in. Organize coverage like a codebase, in watchlists, themes, and folders…" | Investi's positioning, and it **contradicts your own** teardown ("the opposite, and this is the whole differentiation"; folders are what to avoid). Wording tracks Investi's site closely — rewrite in your own words. |
| "Sign in with your existing Trackr+ account", "Portfolio views use Trackr+ and its existing transaction ledger" | Conflicts with "its own login" and "standalone". Portfolio linking is deferred in the brief. |
| "Every investor deserves institutional-grade research capabilities", "Raise an army" of agents | Capability-first. Brief says memory and thinking first, analysis second. |

**Missing:** the one-liner ("remembers why you bought, passed, or walked away"); the
message "Your research. Your thinking. Your AI." (it is in `MASTER_PLAN.md`, not on the
page); the floating notepad / capture; question queue; bring-your-own-model; data
ownership, export and delete; "for every kind of investor".

## 5. Stale items and conflicts with the decisions in the brief

| # | In the repo / notes | Decision in the brief | Severity |
|---|---|---|---|
| C1 | Workspace is a layer on the Trackr+ engine; shared DB, auth, accounts | Standalone repo, own login; don't touch Trackr+ | **Blocking for Phase 3** |
| C2 | Mei Capital, INA000022279 and `ingest.mei.capital` appear across docs | Kept separate from the advisory practice | High (now public) |
| C3 | "Notes are never edited in place… append-only"; D4 unresolved | Deleting a document deletes text, embeddings, summaries, derived memory | High — needs a rule: versions are append-only **until the owner deletes**, then hard-delete cascades |
| C4 | Question ritual: "The AI may not answer a question until you have written your own answer first"; questions must be saved before research opens (D1 unresolved) | Question queue: AI answers from my notes and documents first, read live or later | High — product behaviour |
| C5 | "Deliberately not built: a user-visible MCP or tool marketplace"; "the user never sees the word" | M8: MCP connector support, user-editable skills | Medium |
| C6 | Monitors do filing/earnings watch; landing promises it | Skip live filings; agents work on uploads, notes, pasted pages, news | Medium |
| C7 | Models: Groq + optional Anthropic SDK; D6 "browser-owned vs hosted" open | Default DeepSeek V4 via non-PRC third-party host; BYO key; per-question choice | Medium |
| C8 | "Start with keyword retrieval; add vector only against a benchmark" (D7) | Postgres + pgvector, hybrid retrieval | Low — compatible if evals gate the vector half |
| C9 | Raw SQL + numbered migrations, no ORM | "Reuse Trackr+'s stack" | Low — keep raw SQL for consistency |
| C10 | "Opinionated by design… not settings" | "For every kind of investor"; domain-neutral core with investing as a template pack | Medium — make the discipline a template default, not core |
| C11 | Proposed retail + institutional deployments, SSO, residency (MASTER_PLAN) | No institutional deployments, no SOC 2 | Low — drop |
| C12 | "Mobile apps: no"; folders secondary | Not addressed | None |
| C13 | Master plan Phase 0 = "finish the engine first; nothing in the workspace starts until this closes" | Invest-pad proceeds now, independently | Stale |
| C14 | `STACK_DECISION.md` originally Django (reversed in-file) | FastAPI | Stale, already flagged in the file |
| C15 | Alpha gate: separate legal entity, lawyer/CA review, privacy policy **before user #2** | Beta with analyst friends | High — your friends are "user #2". Legal text is on your stop-list; flagging the timing. |

Two things in the notes I would keep even though the brief doesn't mention them: the data
licensing gate (`MASTER_PLAN` §5.1) and "UNKNOWN is the correct output".

## 6. Claims check

Checked 16 Nov 2026. "Verified (secondary)" means reputable reporting or a regulator
summary, not the primary instrument itself.

| # | Claim (where) | Verdict | Source |
|---|---|---|---|
| 1 | Investi is a product of Ombra, Inc. (teardown, master plan) | **Verified** | https://tryinvesti.com |
| 2 | Investi links "40+ US brokerages" via an aggregator (teardown) | **Unverified number.** Site names SnapTrade and four brokers "and others"; no count. | https://tryinvesti.com/features |
| 3 | Investi broker link is read-only; disconnecting removes synced data (teardown) | **Verified** | https://tryinvesti.com |
| 4 | Investi AI edits arrive as a diff you approve (teardown) | **Verified** | https://tryinvesti.com/features |
| 5 | Investi starts unopinionated; philosophy added as skills (teardown) | **Verified** in substance | https://tryinvesti.com |
| 6 | Investi says "organize coverage like a codebase — watchlists, themes, folders" (teardown; reused on Invest-pad landing) | **Not on the site today** — stale or never verbatim | https://tryinvesti.com |
| 7 | Investi "monitor" reruns questions on schedule (teardown) | **Verified, renamed**: now "Routines"; at most daily or on filing/price events; emailed | https://tryinvesti.com/features |
| 8 | Investi covers SEC filings, SKILL.md skills, remote MCP, per-question model choice, CSV/xlsx export, voice (brief) | **Verified** | https://tryinvesti.com/features |
| 9 | Investi has a free tier (teardown) | **Unverified** — pricing page not checked | — |
| 10 | "No equivalent [broker aggregation] exists in India" (teardown) | **Unverified / doubtful as stated** — the RBI Account Aggregator rail exists; your own `ACCOUNT_AGGREGATOR.md` explores it | repo doc |
| 11 | AMFI closed MF Central third-party access, Sept 2025 (backlog, ingestion) | **Verified (secondary).** Business Standard, 19 Sep 2025, sourced to "people in the know"; no AMFI circular found | https://www.magzter.com/stories/newspaper/Business-Standard/STOP-SHARING-DATA-WITH-3RDPARTY-APPS-AMFI-TO-MF-CENTRAL |
| 12 | Account Aggregator path costs ₹5–25 lakh and 5–10 months (earlier notes) | **Unverified.** Only source found is a vendor's marketing page selling the alternative | https://casparser.in/blog/mfcentral-shutdown-what-to-do/ |
| 13 | Kite Connect tokens expire daily; manual login required (master plan) | **Verified** (Zerodha staff on the official forum) | https://kite.trade/forum/discussion/16226/how-to-keep-the-api-running |
| 14 | Gmail restricted scopes need a Google CASA assessment, annually (ingestion) | **Verified** | https://support.google.com/cloud/answer/13465431 |
| 15 | DPDP Rules 2025 notified Nov 2025, phased over 18 months (compliance) | **Verified.** Date appears as 13 Nov (Gazette) and 14 Nov (PIB) | https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf |
| 16 | DPDP penalties up to ₹250 crore (compliance) | **Verified** (for security-safeguard failures) | same PIB document |
| 17 | DPDP minimum one-year log retention (compliance) | **Verified (secondary)** | https://www.mondaq.com/india/data-protection/1775140/from-draft-to-reality-key-changes-in-indias-dpdp-rules-2025 |
| 18 | "No grace period is expected after stage 3" (compliance) | **Unverified** — a prediction, not a rule. Main obligations are reported to start 13 May 2027 | https://taxguru.in/corporate-law/dpdp-act-2023-simple-guide-businesses-india.html |
| 19 | SEBI IA Regulation 19: records kept five years (compliance) | **Verified** — Reg 19(2) | https://taxmanagementindia.com/visitor/detail_act.asp?ID=34275 |
| 20 | IA annual audit within 6 months of FY end, report within 1 month (compliance) | **Partly verified** (annual compliance audit under Reg 19(3); timings not re-checked at sebi.gov.in) | https://taxguru.in/sebi/sebi-guidelines-investment-advisers.html |
| 21 | "Building or using [the tool] does not itself require SEBI registration" (compliance) | **Unverified — legal opinion.** Needs your lawyer | — |
| 22 | A separate entity resolves the IA-operates-software question (teardown, master plan) | **Unverified — legal opinion.** The notes themselves say verify at source | — |
| 23 | Harness² exists: `google-research/harness2`, arXiv 2610.14224 (pipeline) | **Verified (secondary)**; Apache-2.0, released Oct 2026 | https://ntorres.dev/blog/harness2-google-recursive-agent-harness |
| 24 | DeepSeek's own API stores data in China (brief) | **Verified** — DeepSeek's privacy policy | https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy-2025-02-14.html |
| 25 | DeepSeek V4 is an open-weight family (brief) | **Verified (secondary)**: V4-Flash and V4-Pro, MIT licence, weights on Hugging Face; model cards not opened directly | https://www.yottalabs.ai/post/deepseek-v4-release-date-specs-how-to-access-2026 |
| 26 | Third-party hosts offer DeepSeek V4 with non-PRC region and no prompt retention (brief) | **Unverified** — to be evaluated host by host in Phase 1/2 | — |
| 27 | Cost caps $0.25/task, $2/user/month are workable (brief) | **Unverified** — depends on live pricing | — |
| 28 | Infra "~$22–60/month" (stack decision) | **Unverified**, no source in the doc | — |
| 29 | Landing: "thousands of companies… live price, fundamentals, earnings" | **Wrong** for this product today | repo |
| 30 | Zerodha Console tradebook capped at 365 days; R2 has no egress fees; TDS threshold ₹5,000→₹10,000; SEBI contract-note format change; PVR filing dates | **Not checked** — Trackr+ or PVR scope, not needed for Invest-pad decisions | — |

## 7. Assumptions I am recording (please confirm)

1. **Build base:** start Invest-pad on a clean tree (own schema, own login), porting
   patterns and selected modules from the Trackr+ code — not building on the shared
   Trackr+ database. *Needs your decision before Phase 3; see HANDOFF.*
2. **Demo company:** IEX. I have no notes for it yet; they need to be supplied.
3. **C3:** owner-initiated delete hard-deletes and cascades; everything else is append-only.
4. **C4:** the write-your-questions-first ritual becomes an investing-template default the
   user can relax; the AI may answer queued questions from the user's own corpus.
5. **C5/C6:** MCP stays a later milestone; scheduled agents use uploads, notes, pasted
   pages and web/news only.
