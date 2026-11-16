# HANDOFF

Last updated: 16 Nov 2026, end of session 1 (Phases 0, 1 and 2).

Branch: `invest-pad/planning` (from `codex/invest-pad-ui`), local commits, **not pushed**
— this session has no push access to the repo.

## Done

- Phase 0: `docs/00-inventory.md`.
- Phase 1: `docs/01-landscape.md`, `docs/06-data-sources.md`.
- Phase 2: `docs/02-product-spec.md`, `docs/03-architecture.md`, `docs/04-roadmap.md`,
  `docs/05-eval-plan.md`.

## Checkpoint 1 — one-page summary

**Landscape.** Analysis is crowded (Investi in the US; Screener AI, Multibagg AI,
Trendlyne in India). Memory of the investor's own reasoning is thinly served. Closest in
shape: TradeClips (extension + ticker page + thesis + cited chat), then Stockxy,
StockGeniuses, Folyo's unfinished Workbook. No Indian product found that keeps the user's
own versioned thesis.

**Wedge.** A dated, cited, versioned record of one investor's reasoning, handed back when
they reopen the company. No scores, no AI-written thesis.

**Honest risk.** "NotebookLM plus a folder" is good enough for reading reports. The
product only works if testers return weekly to write.

**Borrow.** Notion: blocks, slash menu, fixed views and counters. Obsidian: wikilinks,
block links, linked and unlinked backlinks, plain-file export. Skip: generic databases,
graph view, plugin system.

**Build vs adopt.** Adopt an editor library (Tiptap, MIT, or BlockNote core, MPL-2.0 —
avoid its GPL `xl-*` packages). Do not fork any second-brain app: Khoj, Obsidian Copilot,
AppFlowy, SiYuan, Logseq are AGPL; Outline is BSL. Open Notebook (MIT) is worth reading
for its multi-provider adapter.

**Data sources.** MVP is uploads, notes and pasted pages, private per user, no shared
corpus. Zip Filings plugs in first as "download ZIP, upload ZIP". Screener's terms rule it
out as a source. NSE/BSE terms unverified; NSE Data portals require written consent to
redistribute.

## Checkpoint 2 — summary

**Spec.** The success test is met by structure, not by AI: the decisive reason is a
required field written at decision time, shown first when a company is reopened. It must
pass with the AI switched off. Core objects are domain-neutral; investing is a pack.

**Architecture.** One FastAPI service, one worker, Postgres + pgvector, Next.js, MV3
extension. Raw SQL migrations. Isolation by Postgres row-level security. Job queue is a
Postgres table. One OpenAI-compatible model adapter. No Redis, Celery or agent framework.

**Hosts (read 16 Nov 2026).** V4.1 Flash is $0.30/$1.20 per 1M tokens on Together and
Fireworks, less on DeepInfra. Only Together states a region (US processing, +25%), and it
stores prompts unless zero-retention is switched on. DeepInfra and Fireworks do not store
open-model prompts by default but state no region on the pages read.

**Caps.** With assumed token sizes, a typical question costs about $0.005–0.006 on Flash;
$2 buys roughly 317. Pro is about four times dearer; proposed as own-key only.

**Roadmap.** MVP M1–M6 estimated at 29 build days (rough). **Eval.** 50 question
templates in eight groups; synthetic corpus for CI, real IEX corpus kept local.

## Decisions made by Parasu (16 Nov 2026)

- Build on a separate branch inside `invest-pad`; leave `codex/invest-pad-ui` untouched.
- Repo stays public until the MVP is built.
- `BEXPD1234F` in tests is not a real PAN.

## Assumed, please confirm

- Demo company: IEX. IEX notes are needed as test data; none supplied yet.
- Owner delete = hard delete with cascade; all other history append-only.
- Question-first ritual is an investing-template default, not a core rule; the AI may
  answer queued questions from the user's own corpus.
- MCP later; scheduled agents use uploads, notes, pasted pages and web/news only.
- Raw SQL + numbered migrations (Trackr+ style); pgvector added behind an eval.
- Floating notepad = Chrome side panel opened by shortcut, plus optional in-page button.
- Editor: BlockNote core unless Phase 2 finds a blocker; Tiptap as fallback.
- Build branch will be a clean tree (orphan branch `invest-pad/main`), not the Trackr+ files.
- Default model DeepSeek V4.1 Flash on platform credit; V4 Pro on the user's own key.
- Host chosen after written region confirmation; fallback Together US-pinned + zero retention.
- Local embedding model; hybrid search ships only if the eval shows it beats keyword-only.
- One thesis per company per user; decision types as listed in `02-product-spec.md` §9.

## Next

1. Phase 3 M1 (Foundation) on a new orphan branch `invest-pad/main`.
2. Then M2–M6 in order; `docs/MVP-REPORT.md` before M7.

## Not done / not verified

- Desktop "investing space" folder never inspected; unpushed local changes unknown.
- Backend test suite not re-run.
- AlphaNote not found; several pricing pages not opened; ChatGPT Projects behaviour not
  verified (see `01-landscape.md` §7).
- NSE and BSE website terms not retrieved.

## Things only Parasu can do

- Push access: either approve repo access for the session or push the branch from the
  Desktop checkout.
- Supply IEX notes and the DuPont skill; send the AlphaNote link.
- Provide a model API key and spending limit before the first paid eval run (stop condition).
- Ask DeepInfra and Fireworks, in writing, where inference runs.
- Read and query NSE/BSE terms (questions listed in `06-data-sources.md` §3).
- Lawyer review: SEBI position on an IA operating this tool; privacy policy and terms
  before analyst friends get accounts; storing captured web pages.

## Open questions

- Are Mei Capital references acceptable in a public Invest-pad repo?
- Keep the PVR INOX pilot as a second demo?
