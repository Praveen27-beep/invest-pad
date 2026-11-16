# HANDOFF

Last updated: 16 Nov 2026, end of session 1.

## Done

- Phase 0 inventory: `docs/00-inventory.md` (what exists, reusable, conflicts C1–C15,
  landing-page report, 30-row claims check).
- Security scan of the now-public repo history: no secrets or real client data found.

Branch: `invest-pad/phase-0-inventory`, one local commit, **not pushed** (no push access
from this session).

## Not done

- Local "investing space" folder was never inspected (access declined/refused). Remote
  match, pull, and unpushed local changes are unchecked.
- Phase 1 (landscape research, `01-landscape.md`, `06-data-sources.md`) not started.
- Backend test suite not re-run.

## Next

1. Phase 1 research → `docs/01-landscape.md`, `docs/06-data-sources.md`.
2. Phase 2 design docs `02`–`05`.
3. Phase 3 only after decision D-A below.

## Decisions needed from Parasu (stop conditions)

- **D-A. Build base.** The repo is the Trackr+ monorepo plus an Invest-pad UI branch.
  Options: (1) clean Invest-pad tree in this repo on a new orphan branch, existing branch
  left untouched; (2) a brand-new repo; (3) keep building on the Trackr+ fork. The brief
  ("standalone", "own login", "don't touch Trackr+") points to 1 or 2. Assumed: 1.
- **D-B. Repo visibility.** Trackr+ source and history are public as of today. Keep public
  or revert to private?

## Assumed, please confirm

- Demo company: IEX (your IEX notes are needed as test data; none supplied yet).
- Owner delete = hard delete with cascade; all other history append-only.
- Question-first ritual is a template default, not a core rule; AI may answer queued
  questions from the user's corpus.
- MCP later; scheduled agents use uploads, notes, pasted pages and web/news, no live filings.
- Keep raw SQL + numbered migrations (Trackr+ style), add pgvector behind an eval.

## Things only Parasu can do

- Connect the Desktop folder (desktop app → Add folder) or confirm it has nothing unpushed.
- Supply IEX / GSM Foils notes and the DuPont skill (not in the repo).
- Lawyer review: SEBI position on an IA operating this tool; privacy policy and terms
  before analyst friends get accounts (the repo's own "Alpha gate").
- Confirm `BEXPD1234F` in tests is a placeholder, not a real PAN.

## Open questions

- Are Mei Capital references acceptable in Invest-pad docs, given the repo is public?
- Should the PVR INOX pilot be kept as a second demo?
