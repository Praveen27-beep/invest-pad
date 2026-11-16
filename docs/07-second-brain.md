# 07 — A research-specific second brain

Date: 16 Nov 2026. Written after Parasu's feedback that the build so far "is too simple,
only Google-Doc-like", and after reading seven references he supplied. Sources at the end,
all accessed 16 Nov 2026.

## 1. What the references do, and what to take

| Reference | What it is | Take | Leave |
|---|---|---|---|
| **GBrain** (open source, MIT) [1][2] | A memory layer for AI agents: Markdown pages synced into Postgres (PGLite or pgvector), keyword + vector search, a `think` command that writes cited answers and notes gaps, scheduled enrichment that finds contradictions, an onboarding interview that writes identity files. | **Cited answers that say what is missing. A scheduled pass that looks for contradictions. An interview to learn who you are instead of guessing.** Keyword search that works with no model. | General-purpose people/company/meeting pages; Gmail and Calendar connectors. |
| **Meta's "organizational second brain"** [4] | A compliance expert-assistant. Knowledge ("position files") is kept apart from procedures ("recipes"). Each expert correction is traced to a root cause, compiled into a small reviewable diff, replay-tested, and added to a regression suite. Dense material lives in a curated wiki; sparse material is searched. | **Keep what you believe apart from how you check it. Every correction becomes a small diff plus a permanent test. A human approves every change.** This is the strongest model for us. | 200-file routing indexes; multi-agent review. |
| **second-brain-starter** [6] | A Claude Code starter: files for agent identity, user profile, memory, daily logs; a 30-minute "heartbeat" that checks mail and tasks; proactivity levels from Observer to Partner. | **A user profile file the assistant always reads. Proactivity as a setting the user chooses.** | Mail/Slack/Asana integrations; an agent that acts on your behalf. |
| **minimi** [3] | Mac app that reads the screen and pings you about open loops. | **An "open loops" list; pinging at the right moment.** | Reading everything on screen. |
| **TwinMind** [5] | Transcribes your day into a memory; capture starts and stops when you say. | **Capture only when the user turns it on.** | Audio capture. |
| **ai-second-brain** [7] | A skill that builds an Obsidian wiki: `raw/` inputs, `wiki/` compiled by the AI. | **Raw material and compiled summaries are different things, stored apart.** | Obsidian. |

None of these is research-specific. All of them store what you *saw* or *said*. None stores
what you *concluded, on what evidence, and whether it still holds* — which is the part
already built here (thesis, assumptions, evidence, decisions).

## 2. The design: five layers and four loops

**Layers** (each stored separately, each with its own rule about who may write):

| Layer | Contents | Who writes | Changes by |
|---|---|---|---|
| 1. Raw | Documents, captured pages, questions asked | You | Never edited; deleted only by you |
| 2. Record | Thesis, assumptions, evidence, decisions, checklists | You | New versions only |
| 3. **How I invest** | Your rules and style in your words: what you buy, what you avoid, position-size limits, what makes you sell | You; the assistant may *propose* additions | New versions only; you approve each |
| 4. Procedures | Checklists and skills (red flags, DuPont, forensic) | You | Edited as files |
| 5. Compiled | AI-written answers and briefs, every claim cited to layers 1–2 | The assistant | Regenerated; always labelled AI |

Layer 3 is new and is what makes it *yours*: every answer and every check reads it.

**Loops** (what makes it feel alive rather than a document store):

1. **Ask → cited answer.** In the app or in the browser notepad. The assistant answers from
   your notes and documents first, quotes its sources, and says what is missing.
2. **Decide → guardrail.** Before a decision is recorded, the assistant compares it with
   "How I invest" and asks about any conflict, quoting your own rule back to you. You can
   proceed; the conflict is recorded with the decision.
3. **Review → hard questions.** Monthly (M7): position sizes against your own limits,
   holdings without a thesis, watchlist names you keep researching but never buy,
   assumptions marked broken that you still hold.
4. **Correct → remember.** When you mark an answer wrong, the case is saved and replayed
   after every change (the eval plan), so the same mistake does not come back.

## 3. Your requests, mapped

| You asked for | Where | Note |
|---|---|---|
| AI chatbot | **M6** — Ask tab per company, and across companies | Answers cite passages; unsupported claims are removed before you see them |
| Second brain in the floating pad that answers questions | **M6** — "Ask now" in the extension | The token must be given permission to ask; an answer shows your own notes, so this is opt-in per browser |
| Remembers your investing style | **M6** — "How I invest" | You write it; later the assistant proposes additions from your decisions, as diffs you approve |
| Guardrail against a deviating strategy | **M6** — check at decision time | Quotes your rule, asks a question, records it. Never blocks, never says buy or sell |
| Is my portfolio too risky, and how to offset it | **M7** | See the boundary below |
| Trackr+ connection | **M7**, in two steps | Step 1: upload a holdings CSV (works with any export, no change to Trackr+). Step 2: a read-only link, which needs a small change in Trackr+ — your call, since Trackr+ is off-limits to me |
| Monthly hard questions on sizing | **M7** — a monthly routine | In-app first; email optional |
| Portfolio against watchlist, to test conviction | **M7** | Needs a watchlist (simple list per user) |
| "Investment studio", not a document editor | M6 onwards | The company page becomes: Overview · Ask · Thesis · Documents · Notes · Red flags |

**One boundary I am holding, because it is your own rule** ("no buy/sell recommendations"):
the portfolio check will show where your portfolio departs from limits **you** wrote
("you set a 10% ceiling; this position is 17%") and ask you about it. It will not say what
to sell or what to buy to "offset" risk. If you want it to go further, that is a change to
your non-negotiables and worth a conversation with your lawyer first, given you are a
registered adviser.

**One thing I need you to clarify:** "No obsidian like backlink connection." Links and
backlinks exist today (type `[[Note title]]`; the side panel lists what links here). I read
your message as "I couldn't find them", not "remove them". Tell me if you meant remove.

## 4. Proactivity is a setting

| Level | The assistant… |
|---|---|
| Quiet | answers when asked; nothing else |
| **Ask** (default) | also runs the guardrail check when you record a decision |
| Review | also raises the monthly questions and flags contradictions it finds (M7) |

It never edits your record, never acts outside Invest-pad, and never contacts anyone.

## 5. Revised milestones

- **M6a (now):** model connection with your own key; "How I invest"; Ask with cited,
  verified answers in the app and in the notepad; guardrail check on decisions; usage and
  cost caps.
- **M6b:** calculation tools with visible formulas; accept an AI claim as evidence from a
  document page; export everything; the 50-question eval; worker process.
- **M7:** holdings and watchlist; monthly review; contradiction scan; routines on new
  documents; assistant-proposed additions to "How I invest".

## Sources

1. https://github.com/garrytan/gbrain
2. https://gbrain.io/
3. https://www.projectminimi.com/
4. https://engineering.fb.com/2026/09/02/ml-applications/organizational-second-brain-ai-learns-from-experts/
5. https://twinmind.com/
6. https://github.com/coleam00/second-brain-starter
7. https://github.com/charlie947/ai-second-brain
