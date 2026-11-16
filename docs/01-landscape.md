# 01 — Landscape (Phase 1)

All sources accessed **16 Nov 2026**. Each row cites its source by number (list at the
end). "Not stated" means the page I read did not say; it is not a claim of absence.
Licence and last-commit facts come from reading each repository's `LICENSE` file and
`git log` directly on 16 Nov 2026.

## 1. Short version

- The **analysis** side is crowded and well funded: Investi in the US, Screener AI,
  Multibagg AI, Trendlyne and others in India. Competing there means competing on data
  coverage, which the brief has deferred.
- The **memory** side — a dated, versioned record of what I believed and why, that comes
  back at the right moment — is thinly served. The closest products are small:
  TradeClips, Stockxy, StockGeniuses, and Folyo's unfinished Workbook. None of the ones I
  could read describes versioned assumptions with diffs, or a strict split between fact,
  my opinion and AI conclusion.
- No India-focused product I found combines the investor's own notes with AI answers
  over them. The Indian tools read filings **for** you; none of the pages I read mention
  remembering what **you** concluded.
- The honest threat is not a competitor. It is "NotebookLM plus a folder", which is
  already good at cited Q&A. Invest-pad only wins on the parts a notebook cannot hold: the
  thesis as a structured object, time, and capture while reading.

## 2. Notion and Obsidian — what to borrow, what to skip

### Notion (official help)

| Mechanic | What it is | Verdict |
|---|---|---|
| Blocks | A page is a stack of blocks; any block can be turned into another type and dragged to reorder. `/` opens the type menu. [1] | **Borrow**: block editor, slash menu, drag handle, "turn into". This is the "Notion-like comfort". |
| Database views | Table, Board, Timeline, Calendar, List, Gallery, Chart; filters, sorts and groups are per view over the same data. [2] | **Borrow narrowly**: one fixed set of views over our own objects (questions by status, assumptions by state, companies by decision). **Skip** user-defined databases. |
| Relations | Link items across databases; one-way by default, optional two-way. [3] | **Borrow as fixed links**: note ↔ company, evidence ↔ assumption, question ↔ answer. Not user-configurable. |
| Rollups | Aggregate a property across related pages (count, sum, earliest/latest date…); cannot roll up a rollup. [3] | **Borrow as computed counters only**: "3 open questions", "2 assumptions challenged", "last reviewed". Computed in code. |
| Generic database builder, formulas, templates marketplace | — | **Skip.** It is the largest part of Notion and none of it serves the success test. |

### Obsidian (official help)

| Mechanic | What it is | Verdict |
|---|---|---|
| `[[wikilinks]]` | `[[Note]]`, `[[Note#Heading]]`, `[[Note#^block-id]]`, `[[Note\|display text]]`; links update automatically on rename; a link to a missing note creates it. [4] | **Borrow all of it**, including block links — they are how a citation points at one passage. |
| Backlinks | Linked mentions and **unlinked mentions** (plain-text occurrences of the note's name); can be shown at the bottom of the note. [5] | **Borrow both.** Unlinked mentions are cheap and feel like memory. |
| Plain-file storage | Each note is a Markdown file in a folder ("vault"); readable by any editor. [6] | **Borrow the promise, not the mechanism**: store in Postgres, but full Markdown export with links intact (already a non-negotiable). |
| Graph view | Visual node graph | **Skip for MVP.** Decorative for this use; backlinks do the work. |
| Community plugins | Third-party code inside the app | **Skip.** Replace with user-editable checklist skills (M8). Plugin systems are a security and support cost. |

### Chrome side panel (official API reference)

Extensions can host their own UI beside the page; needs Chrome 114+, Manifest V3 and the
`sidePanel` permission; panels can be global or per tab; `sidePanel.open()` (Chrome 116+)
must be called from a user gesture such as the toolbar icon, a keyboard shortcut or a
context-menu item. [7] **Implication:** the "floating notepad" can be a side panel opened
by shortcut, plus an optional in-page floating button via content script. Decide in
Phase 2.

## 3. Second-brain and research tools

### Open source

| Tool | What it is | Licence | Last commit | Verdict |
|---|---|---|---|---|
| **Khoj** | Self-hostable "AI second brain": chat over your docs and the web, custom agents, scheduled automations and email newsletters, any LLM. [8] | **AGPL-3.0** ⚠ | 1 Aug 2026 — quiet for 3+ months; README now promotes a newer product, Pipali [8] | **Borrow ideas** (scheduled research delivered to inbox). Do not use code: AGPL would oblige publishing our service's source. |
| **Open Notebook** | Open-source NotebookLM alternative; 20+ model providers including any OpenAI-compatible server. [9] | MIT | 14 Nov 2026 | **Borrow ideas; read the code** for the multi-provider adapter and source ingestion before writing ours. Not a fork: notebook-shaped, no thesis objects. Its stack was not reviewed. |
| **SurfSense** | "Air-gapped, open-source NotebookLM alternative"; an agent that researches and edits documents locally. [10] | Apache-2.0 (root `LICENSE`; sub-directory licences not checked) | 3 Nov 2026 | **Borrow ideas** (document formats handled). Not a fork. |
| **Fabric** (danielmiessler) | CLI framework that organises reusable prompts ("patterns") by task. [11] | MIT | 15 Nov 2026 | **Borrow the idea**: a pattern ≈ a checklist skill in a Markdown file. No code needed. |
| **Copilot for Obsidian** | Agents inside an Obsidian vault; projects with their own instructions and context; skills shared across agents; bring your own provider key or local model. [12] | **AGPL-3.0** ⚠ | 13 Nov 2026 | **Borrow ideas** (per-project context, BYO key UX). No code. |
| **Smart Connections** (Obsidian) | Related-notes plugin | Custom "Smart Plugins License": bars use in competing general-purpose note products ⚠ [13] | 10 Oct 2026 | **Ignore.** |

### Editor libraries (input to build-vs-adopt in Phase 2)

| Library | Licence | Last commit | Note |
|---|---|---|---|
| **Tiptap** | MIT [14] | 13 Nov 2026 | Safe to adopt. More assembly needed for Notion-style blocks. |
| **BlockNote** | Core **MPL-2.0** (usable in closed-source apps; changes to its own files must be published); `xl-*` packages **GPL-3.0** or commercial ⚠ [15] | 15 Nov 2026 | Notion-style out of the box. Adoptable if we avoid the `xl-*` packages. |
| AFFiNE | MIT, except `packages/backend` under its own licence [16] | 12 Nov 2026 | Whole app; do not fork. |
| AppFlowy, SiYuan, Logseq | **AGPL-3.0** ⚠ [17] | Oct–Nov 2026 | Do not fork. |
| Outline | Business Source License 1.1 ⚠ [18] | 15 Nov 2026 | Do not fork. |

**Do not write an editor from scratch.** Adopt Tiptap or BlockNote core; choose in Phase 2.

### Closed source

| Tool | What it does | Price shown | Borrow |
|---|---|---|---|
| **Recall** | Summarises videos, podcasts, PDFs, articles; browser extension; auto-tagging into a knowledge graph; chat over your knowledge; spaced-repetition quizzes. [19] | Not on the page | Spaced resurfacing — matches "this is what you thought 12 months ago". |
| **Readwise Reader** | Read-later for articles, PDFs, newsletters, YouTube; highlights anywhere via extension; export to Obsidian and Notion; AI reading assistant. [20] | $9.99/month billed annually [20] | Highlight-then-note capture. Later: import highlights. |
| **Heptabase** | Cards on whiteboards; break PDFs and web pages into cards; journal; bi-directional links; web clipper. [21] | Not on the page | "One source → several atomic cards". Skip whiteboards. |
| Fabric.so (the app, unrelated to the CLI above) | — | — | **Not reviewed.** |

## 4. Investor tools

Legend: ✔ stated on the source page · ✖ page says no / positions against it · — not stated.

| Tool | Market | Own notes / editor | Browser capture | Thesis object | Q&A over **my** material, cited | Scheduled re-checks | Model choice / BYO key | Stance |
|---|---|---|---|---|---|---|---|---|
| **Investi** [22][23] | US (SEC filings from 1993) | ✔ notes; AI edits arrive as a diff | — | — | Uploads of PDFs/sheets ✔; core is Q&A over **filings** with every number linked | ✔ "Routines": at most daily, or on a filing/price event; emailed | ✔ model and effort per question; BYO key — | "No opinions baked in"; not advice |
| **TradeClips** [24] | Not stated | ✔ notes | ✔ Chrome extension: articles, YouTube, Reddit; detects tickers | ✔ per ticker, with a **conviction score**; AI writes bull/bear | ✔ chat over your library with cited sources | Weekly AI digest of your activity | — | — |
| **Stockxy** [25][26] | US, HK, China A-shares | ✔ block editor with slash commands | — | ✔ rationale and sentiment per stock, pinned to the price chart | — (no AI mentioned) | — | — | "Tracks why you own it" |
| **StockGeniuses** [27] | Not stated | ✔ decision journal | — | ✔ thesis, risks, reflections | AI explains model outputs (not my documents) | ✔ "monitor meaningful changes" | — | Not a stock picker |
| **Folyo** [28][29] | India (per its own roadmap board) | "Workbook" per stock — **in progress** (Dec 2025) | "Sidekick" mentioned, not described | Planned inside Workbook | Planned ("smart search, embeddings") | — | — | Trading journal with execution |
| **Bipsync** [30] | Institutions (hedge funds, asset owners, consultants) | ✔ research notes, documents | — | ✔ thesis tracking tied to positions | ✔ "Toro" AI assistant with sources | — | — | SOC 2 / ISO 27001; demo-only pricing |
| **AlphaNote** | — | — | — | — | — | — | — | **Could not find the product.** Please send a link. |

### India-specific

| Tool | What I could confirm | Notes / thesis / memory of my own thinking |
|---|---|---|
| **Screener** [31][32][33] | Screens over 10 years of financials; "Screener AI" extracts insights from company documents; announcement search and alerts. Premium ₹4,999/year incl. GST with AI credits; concall features "currently working on". Terms: "personal, non-commercial" viewing only, no copying or mirroring. | None mentioned |
| **Multibagg AI** [34] | "Ask Iris" AI assistant for listed Indian companies; themes; live market data; portfolio dashboard; WhatsApp alerts; free tier. | None mentioned |
| **Trendlyne** [35] | Screeners, fundamental and technical analysis, portfolio reports; a "MarketMind AI" / Ask AI entry in the menu. | None mentioned |
| **Tijori Finance** [36] | Company and sector research, screener, raw-material tracking, alerts, concall listings. | None mentioned |
| **Tickertape** [37] | Home page shows indices, prices, funds, smallcase portfolios. | None mentioned |
| QARO, Stock Alpha, StockInsights AI, Perplexity Finance (India coverage), broker assistants | **Seen in search results only; not reviewed.** [38] | Unknown |

Read across: the Indian tools I could open are data-and-analysis products. I found no
Indian product whose page describes the user's own versioned thesis. Folyo is the nearest,
and it is trading-led and unfinished. This is an absence in what I read, not proof none exists.

## 5. "Why wouldn't an investor just use ChatGPT or NotebookLM with a folder of reports?"

**Honest answer: for the question "what does this annual report say?", many should, and
will.** Google's notebook product answers from uploaded sources with inline citations,
accepts sources up to 500,000 words or 200 MB each, and says uploads are not used for
training unless you submit feedback. [39][40] Invest-pad will not
beat that on reading a PDF, and should not try.

What a notebook does not give you (my analysis, not a sourced claim):

1. **It stores sources and chats, not positions.** There is no object called "thesis"
   with assumptions, evidence for and against, and a dated history. The decisive reason
   lives in chat turn 47 of a notebook you last opened in March.
2. **It has no sense of time.** "What did I believe in August, and what changed?" needs
   versions and diffs. A notebook gives you today's answer over today's sources.
3. **It blends voices.** Fact from the filing, my opinion, and the model's conclusion come
   out as one fluent paragraph. Keeping them apart is a storage decision.
4. **It starts when you sit down to research.** Questions that occur while reading a web
   page are lost unless you stop and switch tools. Capture is the extension's job.
5. **It does not come back to you.** Nothing re-checks an assumption when a new document
   arrives, or shows the note you wrote a year ago when you reopen the company.
6. **Your data model is theirs.** Export of notes with their links, versions and citations
   as plain files is not what these products are for.

Where this argument is **weak**, and should be watched:

- General assistants are adding memory, projects and scheduled tasks. I could not open
  OpenAI's Projects help page today, so I am not asserting what ChatGPT does or does not do.
- A free "thesis tracker" skill for a general assistant already exists in public skill
  catalogues (seen in search results, not reviewed). [38] Structure alone is copyable.
- So the defensible part is narrow: **the accumulated, structured, exportable record of
  one investor's reasoning, plus the habit loop that makes them keep writing it.** If
  testers do not come back weekly to write, there is no product.

## 6. Gaps and the wedge

| Gap | Who leaves it open | Invest-pad answer |
|---|---|---|
| The reason behind a decision is not a first-class, versioned object | Everyone except TradeClips / Stockxy / StockGeniuses / Bipsync, and none of those describe versions with diffs | Thesis → assumptions → evidence, append-only versions, diff view, "decisive reason" card |
| Fact / my opinion / AI conclusion are mixed | All reviewed | Separate storage and separate visual treatment |
| Capture happens outside the research tool | All except TradeClips and the read-later apps | MV3 side panel + question queue |
| AI answers from the market's documents, not mine | Investi, Screener AI, Multibagg, Trendlyne | Answer from my notes and uploads first, cited to the passage |
| Scores and AI-written theses | TradeClips (conviction scores, AI bull/bear) | No scores; the AI proposes, the investor writes |
| India, for individuals | Bipsync is institutional; Investi is US; Indian tools have no notebook | India-first templates (forensic red flags, promoter/governance checks) |
| Model lock-in | Most do not state BYO key | BYO key and local endpoint from day one |

**Wedge, in one line:** the only place an Indian investor's own reasoning is kept as a
dated, cited, versioned record — and handed back when they reopen the company.

**Closest thing to watch:** TradeClips (same shape: extension + ticker page + thesis +
cited chat). **Largest risk:** a general assistant with good memory makes the structure
feel unnecessary.

## 7. What I could not verify

- AlphaNote: not found.
- Stockxy's own site blocks automated reading; facts come from its Product Hunt listing.
- TradeClips: marketing site is on a `pages.dev` preview domain; markets and pricing not stated.
- Folyo: only its public roadmap board was read.
- Pricing pages for Investi, Recall, Heptabase, Trendlyne, Tijori: not opened.
- ChatGPT Projects/memory behaviour: help page not retrievable today.
- Star counts and contributor activity: GitHub API was not reachable; "last commit" is the
  only activity measure used.
- Tickertape, Trendlyne, Tijori: only the landing/feature pages were read; a notes feature
  could exist deeper in the product.

## Sources

1. https://www.notion.com/help/what-is-a-block
2. https://www.notion.com/help/views-filters-and-sorts
3. https://www.notion.com/help/relations-and-rollups
4. https://obsidian.md/help/links
5. https://obsidian.md/help/plugins/backlinks
6. https://obsidian.md/help/data-storage
7. https://developer.chrome.com/docs/extensions/reference/api/sidePanel
8. https://github.com/khoj-ai/khoj (LICENSE, README, git log)
9. https://github.com/lfnovo/open-notebook (LICENSE, README, git log)
10. https://github.com/MODSetter/SurfSense (LICENSE, README, git log)
11. https://github.com/danielmiessler/fabric (LICENSE, README, git log)
12. https://github.com/logancyang/obsidian-copilot (LICENSE, README, git log)
13. https://github.com/brianpetro/obsidian-smart-connections (LICENSE)
14. https://github.com/ueberdosis/tiptap (LICENSE.md)
15. https://github.com/TypeCellOS/BlockNote (LICENSE.txt)
16. https://github.com/toeverything/AFFiNE (LICENSE)
17. https://github.com/AppFlowy-IO/AppFlowy , https://github.com/siyuan-note/siyuan , https://github.com/logseq/logseq (LICENSE files)
18. https://github.com/outline/outline (LICENSE)
19. https://www.recall.it/
20. https://readwise.io/read
21. https://heptabase.com/
22. https://tryinvesti.com/features
23. https://tryinvesti.com/
24. https://tradeclips-marketing.pages.dev/features
25. https://www.producthunt.com/products/stockxy
26. https://www.saasworthy.com/product/stockxy
27. https://peerlist.io/rroncena/project/stockgeniuses
28. https://folyo.userjot.com/board/p/folyo-workbook
29. https://folyo.userjot.com/board/p/major-folyo-journal---the-integrated-trading-journal
30. https://www.bipsync.com/
31. https://www.screener.in/
32. https://www.screener.in/premium/
33. https://www.screener.in/guides/terms/
34. https://www.multibagg.ai/llms.txt
35. https://trendlyne.com/features/
36. https://www.tijorifinance.com/
37. https://www.tickertape.in/
38. Search results only, not opened: https://yourstory.com/companies/qaro , https://www.theaireport.ai/tooldatabase/stock-alpha , https://whichaitools.pages.dev/tools/stockinsights-ai , https://claudemarket.ai/skills/claude/anthropics/financial-services-plugins/thesis-tracker
39. https://support.google.com/notebooklm/answer/16164461
40. https://support.google.com/notebooklm/answer/16269187
