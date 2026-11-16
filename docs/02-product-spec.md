# 02 — Product specification

Date: 16 Nov 2026. Status: proposed; build proceeds on these unless Parasu objects.
Items marked **(assumed)** are defaults I chose and should be confirmed.

## 1. What it is

> Invest-pad remembers why you bought, passed, or walked away from a stock, so you don't
> research it all over again.

Category: AI Investment Studio. Message: "Your research. Your thinking. Your AI."
A research and information tool. It gives no buy, sell or hold recommendation, no price
target and no score.

## 2. The success test, made concrete

*Can an investor reopen an old company and recover the decisive reason they bought,
passed, or stopped researching, without rereading their documents?*

Acceptance test (run on the demo company, then with each beta tester):

1. Open a company last touched 30+ days ago.
2. Within **10 seconds and one screen**, without opening any document, the user can read:
   the decision (bought / passed / stopped / still researching), its date, the **decisive
   reason in their own words**, and the assumptions it rested on.
3. One click from each assumption shows the evidence for and against, with the cited passage.
4. One click shows what has changed since the decision (new notes, new documents, changed
   assumptions), as a diff.

**Design consequence:** steps 1–4 must work with the AI switched off. The decisive reason
is a field the user writes at decision time, not something a model reconstructs later.
The AI helps find evidence and drafts proposals; the record is the product.

## 3. Core objects (domain-neutral)

The core knows nothing about stocks. Investing is a **template pack**: a set of labels,
checklists and prompts loaded at signup.

| Core object | Meaning | Investing pack calls it |
|---|---|---|
| Subject | The thing being studied | Company |
| Document | An uploaded or captured source | Annual report, concall, web page |
| Note | Block-based writing, linked with `[[...]]` | Research note |
| Capture | A quick note or question from the extension | Inbox item |
| Question | Something to be answered; has a status | Research question |
| Answer | A set of claims, each with citations | — |
| Position | A stated view on a subject, versioned | Thesis |
| Assumption | A statement the position depends on, versioned | Thesis assumption |
| Evidence | A cited passage linked to an assumption as *for* or *against* | — |
| Decision | A dated journal entry with a decisive reason | Bought / Passed / Stopped |
| Checklist | A reusable list of checks (a "skill") | Forensic red-flag checklist |
| Routine | A saved question re-run on a schedule | Assumption watch |

A student or researcher pack would relabel Subject → Topic/Paper, Position → Argument,
Decision → Conclusion, with different checklists. No schema change.

### Four kinds of statement, always stored apart

| Kind | Who authored | Rule |
|---|---|---|
| **Fact** | From a source | Must cite at least one passage. No citation → cannot be saved as a fact. |
| **Opinion** | The user | Free text. Never auto-generated. |
| **AI conclusion** | A model | Always labelled; every claim cited; never promoted to fact or opinion without the user accepting it, and then recorded as "accepted from AI on <date>". |
| **Outdated** | A state, not a kind | Any of the above can be marked superseded; it stays readable with its original date and is excluded from "current" views. |

Each kind has its own visual treatment. They are never merged into one paragraph.

## 4. Scope: MVP (M1–M6)

| Area | In the MVP |
|---|---|
| Accounts | Email + password, invite code, multi-user, each user's data isolated in the database |
| Workspace | Block editor; `[[links]]`, block links, linked and unlinked backlinks; a page per company; search |
| Capture | Chrome extension side panel: note or question on any page, with URL, selected text and time; inbox in the app |
| Documents | Upload PDF / Excel / Word; extract, chunk, index; company and period tags; cited passages; delete with full cascade |
| Thesis | One thesis per company; assumptions; evidence for/against; versions with diffs; decision journal; red-flag checklist before deeper research; "decisive reason" card |
| Questions | Queue answered from my notes and documents first, with citations; read live or later; `UNKNOWN` when evidence is missing |
| Calculations | Deterministic tools (CAGR, growth, TTM, margins, DuPont) with the formula and inputs shown |
| Models | Default hosted open-weight model; bring your own key or local endpoint; choose per question; cost caps enforced |
| Export | Everything as Markdown + CSV + original files in one ZIP |

After MVP: landing page update, then M7 routines, M8 skills/MCP/exports/journal, M9
hardening and beta.

## 5. User flows

**F1 — Start a company.** New company → red-flag checklist (from the pack) → write
questions → upload documents. *Investing-pack default:* the app asks for at least one
question before research; the user can skip **(assumed: a default, not a lock)**.

**F2 — Capture while reading.** On any page: shortcut opens the side panel → type a note
or a question, optionally with selected text → pick or auto-suggest the company → saved to
inbox. Nothing is sent to a model at capture time.

**F3 — Ask and read later.** A question enters the queue → the system searches my notes
and documents for that company → answers with numbered citations, or says what is missing
→ I read it now or later → I can accept a claim into a note (recorded as accepted-from-AI),
attach a passage as evidence to an assumption, or discard.

**F4 — Form a thesis.** Write the thesis → add assumptions (each marked fact-based or
judgement) → attach evidence → save as version 1. Later edits create version 2; the diff
is shown; version 1 is never changed.

**F5 — Decide.** Record a decision: type, date, **decisive reason (required, one or two
sentences)**, which assumptions it rested on, optional "what would change my mind". This
is the journal. It freezes a pointer to the thesis version in force.

**F6 — Reopen.** Company page opens on the decisive-reason card (section 2), then open
questions, then "since you were last here".

**F7 — Leave.** Export everything, or delete a document / a company / the account; derived
data goes with it.

## 6. AI behaviour rules

- Answers come from the user's corpus first. If web or model knowledge is used at all
  (later milestone), it is labelled and separated.
- Every claim carries a citation to a stored passage. A claim whose citation fails
  verification is dropped and the answer says so.
- Numbers are either copied from a cited passage or produced by a calculation tool that
  shows its formula. The model does not do arithmetic.
- Insufficient evidence → `UNKNOWN`, plus what document would settle it.
- The AI never edits a note, thesis, assumption or decision. It proposes; the user accepts.
- Text inside documents and captured pages is data, never instructions.
- No recommendation language. Output ends at "this assumption is challenged; review it".

## 7. Explicitly out of scope

Buy/sell/hold calls, price targets, conviction or quality scores · live NSE/BSE or any
data-site fetching · live prices, charts, screeners · brokerage or portfolio linking ·
payments and billing · institutional tiers, SSO, SOC 2, customer-hosted deployment ·
mobile apps · real-time collaboration and shared workspaces · a generic database builder,
graph view, third-party plugin system · social features · AI-written theses · model
fine-tuning or training on user data · any Mei Capital client data · any link to or from
meicapital.in.

## 8. Product copy rules

Use only features that exist in the build. No "SEBI compliant", no advice claims, no
testimonials or usage numbers not supplied by Parasu. Always show: "Research and
information, not investment advice."

## 9. Assumed, please confirm

1. Question-first is a pack default the user can skip, not a hard rule.
2. The AI may answer a queued question before the user writes their own answer.
3. One thesis per company per user (no competing theses).
4. Decision types in the investing pack: Bought, Added, Trimmed, Sold, Passed, Stopped
   researching, Still researching.
5. Demo company: IEX.
