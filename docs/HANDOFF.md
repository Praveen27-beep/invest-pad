# HANDOFF

Last updated: 16 Nov 2026, end of session 1 (Phases 0 and 1).

Branch: `invest-pad/planning` (from `codex/invest-pad-ui`), local commits, **not pushed**
— this session has no push access to the repo.

## Done

- Phase 0: `docs/00-inventory.md`.
- Phase 1: `docs/01-landscape.md`, `docs/06-data-sources.md`.

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

## Next

1. Phase 2: `02-product-spec.md`, `03-architecture.md` (includes evaluating 2–3 DeepSeek V4
   hosts for region and retention, and live pricing against the cost caps),
   `04-roadmap.md`, `05-eval-plan.md`.
2. Phase 3 M1 on `invest-pad/main`.

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
- Read and query NSE/BSE terms (questions listed in `06-data-sources.md` §3).
- Lawyer review: SEBI position on an IA operating this tool; privacy policy and terms
  before analyst friends get accounts; storing captured web pages.

## Open questions

- Are Mei Capital references acceptable in a public Invest-pad repo?
- Keep the PVR INOX pilot as a second demo?
