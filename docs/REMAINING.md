# Remaining work (updated 17 Nov 2026, after session 2)

Read `docs/HANDOFF.md` and `docs/MVP-REPORT.md` first. Working rules are unchanged (see
the top of the previous version of this file in git history and `HANDOFF.md`): branch
from `invest-pad/main`, owner-scoped tables with RLS and composite foreign keys, no
advice wording, no spend or keys without Parasu.

Done since the last version: export, delete audit, calculations, contradiction scan,
editable/forensic checklists, workspace graph, journal, review badge, Markdown export,
MCP server, rate limits, injection and cross-tenant tests, backup/restore, onboarding,
eval runner, account deletion, decisions as cited Q&A sources, deploy/demo/legal drafts, MVP report.

## Needs Parasu

1. **Model key** for a DeepSeek model on a third-party host (never DeepSeek's own API).
   Then: `python -m eval.run` (dry run), check the host's live price and data terms,
   `--send`, fill the human column, put results in `MVP-REPORT.md`.
2. **Trackr+ link**: whether the Trackr+ side may be built. Proposed contract: a
   read-only token created in Trackr+, pasted into Invest-pad Settings;
   `GET <trackr>/api/v1/holdings` → `[{symbol, isin, quantity, avg_cost, current_value,
   as_of}]`, stored through `portfolio.store_snapshot`; token Fernet-encrypted.
3. **Run on his Mac**: `docker compose up --build`, the e2e scripts, the backup scripts,
   and the extension's toolbar/shortcut/context menu/permission prompt.
4. **Lawyer review** of `docs/legal/*-DRAFT.md`; hosting, domain, DNS; Web Store.

## Can be built without him, in order

1. **"How I invest" suggestions** — small/medium. After 3+ decisions share a stated
   reason, propose a rule the user accepts (new profile version) or dismisses. Model
   call, explicit button, same verification style as the scan.
2. **Landing page** — on its own branch (`invest-pad/landing`), static, only features in
   `MVP-REPORT.md`, no SEBI/advice claims, no testimonials or numbers, not deployed,
   nothing on meicapital.in.
3. **Vector search** — pgvector is in the image; embeddings need a model call per
   passage (cost), so only after the eval shows keyword retrieval misses.
4. **OCR** for scanned PDFs (e.g. Tesseract) — check licence and image size first.
5. **Rate limits across processes** — move `ratelimit.py` to a Postgres table if more
   than one API process is ever run.
