# Landing page

The public pages live in the web app: `/welcome` (landing), `/features`, `/manifesto`,
`/docs`, `/pricing` and `/blog` (both "coming soon"). Signed-out visitors to `/` land on
`/welcome`; the login page links to it. Code: `web/components/public/`.

Ported from the earlier draft on `codex/invest-pad-ui`
(`trackr-workspace-frontend/app/components/Landing.tsx`, 16 Oct 2026). Design, header,
footer, FAQ, manifesto and brain visual are kept; the copy is corrected against
`docs/00-inventory.md` §4:

| Earlier line | Now |
|---|---|
| "Open any of thousands of companies… live price, fundamentals, earnings" | Removed: no price feed or filings download; FAQ says so |
| "An AI analyst… answer in seconds", "Research that runs on a schedule… filing watch" | Answers from your own notes, documents and decisions, every statement quoting its source |
| "No philosophy baked in. Organize coverage like a codebase…" (Investi's line) | "A thesis you can trace"; "Your rules, your portfolio" |
| "Sign in with your existing Trackr+ account", Trackr+ ledger | Invest-pad's own invite-only login; holdings by CSV import |
| "Raise an army", "institutional-grade research" | "Keep your mind for thinking"; memory first, analysis second |
| Workspace demo (needed Trackr+ code) | A still overview card, labelled as a fictional company |
| Added | One-liner, "Your research. Your thinking. Your AI.", side panel, own model, export and delete |

Not deployed. Terms and Privacy show "coming soon" until the drafts in `docs/legal/` are
reviewed by a lawyer. Nothing on meicapital.in.
