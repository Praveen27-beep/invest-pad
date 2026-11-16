# 03 — Architecture

Date: 16 Nov 2026. Prices and host terms were read on this date; sources at the end.
First rule: code simplicity. Every component below exists because a milestone needs it.

## 1. Shape

```
Chrome extension (MV3) ─┐
Next.js web app ────────┼─► FastAPI (one service) ─► Postgres 16 + pgvector
                        │         │
                        │         └─► worker (same code, second process)
                        │                 └─► model host (OpenAI-compatible HTTP)
                        └─ files on local disk volume (S3-compatible later)
```

- **One backend service, one database, one worker process.** No Redis, no Celery, no
  LangGraph, no message broker, no vector database other than pgvector.
- **Raw SQL with numbered `.sql` migrations and `psycopg`**, the same style as Trackr+, so
  the two codebases read alike. No ORM.
- Local run: `docker compose up` starts `db`, `api`, `worker`, `web`.

### Repository layout (new orphan branch `invest-pad/main`)

```
backend/    app/ (api, db, retrieval, answer, calc, models, jobs)  migrations/  tests/
web/        Next.js app
extension/  MV3 side panel + content script
packs/      investing/  (labels, checklists, prompts as Markdown/JSON)
docs/       docker-compose.yml  README.md
```

Nothing is imported from the Trackr+ tree. Patterns are re-implemented; selected pure
functions (calculation, claim checks) are ported file by file with their tests.

## 2. Data model

Every user-owned table has `owner_id uuid not null`. Timestamps on everything. Versioned
objects are append-only: a change inserts a new version row.

| Table | Key columns | Notes |
|---|---|---|
| `app_user` | id, email, password_hash, created_at | argon2 hash |
| `session` | id, user_id, expires_at | Server-side sessions, httpOnly cookie |
| `invite` | code, used_by | Beta gating |
| `subject` | id, owner_id, name, identifiers jsonb, pack | "Company"; ISIN/ticker live in `identifiers` |
| `document` | id, owner_id, subject_id, kind, title, source_url, doc_date, period, sha256, storage_key, status | Original bytes kept; `kind` = upload / capture |
| `chunk` | id, owner_id, document_id, ordinal, page, char_start, char_end, text, tsv tsvector, embedding vector | Derived; rebuildable |
| `note` | id, owner_id, subject_id, title | Identity only |
| `note_version` | id, note_id, owner_id, seq, blocks jsonb, text, tsv, created_at | Append-only |
| `note_chunk` | id, owner_id, note_version_id, block_id, text, tsv, embedding | Notes are retrievable like documents |
| `link` | owner_id, from_note_id, to_kind, to_id, block_id | Backlinks are a query on this table |
| `capture` | id, owner_id, subject_id?, kind (note/question), text, selection, url, captured_at, status | Inbox |
| `question` | id, owner_id, subject_id, text, status, model, created_at | queued / answering / ready / failed |
| `answer` | id, owner_id, question_id, model, cost_usd, created_at, status | One row per attempt; never overwritten |
| `claim` | id, owner_id, answer_id, ordinal, text, kind, verified | kind = fact / ai / unknown |
| `citation` | owner_id, claim_id, chunk_id or note_chunk_id, quote, doc_sha256 | Quote must appear in the cited text |
| `position` | id, owner_id, subject_id | "Thesis" identity |
| `position_version` | id, position_id, owner_id, seq, body, created_at | Append-only |
| `assumption` | id, owner_id, position_id | Identity |
| `assumption_version` | id, assumption_id, owner_id, seq, text, basis (fact/judgement), state (holds/challenged/broken/outdated), reason, created_at | Append-only |
| `evidence` | id, owner_id, assumption_id, direction (for/against), statement_kind (fact/opinion/ai), text, chunk_id?, note_chunk_id?, accepted_from_answer_id?, created_at | Fact rows require a cited chunk (CHECK constraint) |
| `decision` | id, owner_id, subject_id, type, decided_on, decisive_reason, position_version_id, assumption_ids, would_change_mind, created_at | Append-only journal |
| `checklist_run` | id, owner_id, subject_id, checklist_key, items jsonb, created_at | Red-flag checklist results |
| `model_config` | id, owner_id, label, base_url, model, key_ciphertext, key_last4 | Bring-your-own-key |
| `usage` | id, owner_id, task_id, model, tokens_in, tokens_out, cost_usd, payer (platform/own), created_at | Cost caps read this |
| `job` | id, owner_id, kind, payload, status, attempts, run_after, locked_at | The queue |
| `routine`, `routine_run` | owner_id, question text, schedule, assumption_ids; immutable runs | M7 |
| `audit_log` | owner_id, actor, action, object, at | No content, no secrets |

**Fact / opinion / AI / outdated** are columns with CHECK constraints, not conventions:
`evidence.statement_kind='fact'` requires a citation; AI-authored rows keep
`accepted_from_answer_id`; `outdated` is a state on a version, never a delete.

### Deletion

Append-only governs **edits**. The owner can still delete:

- Delete a document → its row, file bytes, `chunk` rows (text + embeddings), every
  `citation` to them, and any `claim` left with no valid citation, in one transaction via
  `ON DELETE CASCADE`. Evidence rows that cited it remain as the user's text but are marked
  "source deleted" and lose fact status.
- Delete a company or the account → everything under it.
- A test asserts that after deletion no row and no file contains the document's text or digest.
- Backups: local dev has none; the hosting proposal must state backup expiry before beta.

## 3. Tenant isolation — in the database, not in prompts

1. The API connects as a role **without** `BYPASSRLS`. Migrations run as a separate owner role.
2. Every user-owned table has Row Level Security: `USING (owner_id = current_setting('app.user_id')::uuid)`,
   with `FORCE ROW LEVEL SECURITY`.
3. Each request runs in a transaction that does `SET LOCAL app.user_id = <session user>`.
   With no setting, queries return nothing.
4. The worker sets the same variable from `job.owner_id` before touching data.
5. Retrieval filters by owner inside the SQL **before** ranking. The model only ever sees
   rows the database already returned for that owner.
6. Tests: user A creates data; as user B, every read endpoint, search, citation lookup,
   file download and export must return nothing or 404. A migration test fails if any
   table with `owner_id` lacks a policy.

## 4. Documents and retrieval

**Ingest:** upload → size/type check → store bytes + SHA-256 → extract text (PDF by page;
Excel by sheet as rows; Word by paragraph) → chunk (~800 tokens, overlap, never across
pages) → `tsvector` + embedding → status `ready`. Each stage is idempotent and recorded;
a failed stage shows its reason. Scanned PDFs without text are reported as "no text
found"; OCR is not in the MVP.

**Metadata:** company (required), document type, document date, period (e.g. FY25, Q2 FY26).
Suggested from file name and first page by rules; the user confirms.

**Search (hybrid):**
1. Filter: owner, subject, optional period and type.
2. Keyword: Postgres full-text rank on `tsv`.
3. Semantic: pgvector cosine on `embedding`.
4. Merge with reciprocal rank fusion; return top passages from documents **and** notes.

**Embeddings (assumed, to be settled by the eval):** run a small open embedding model
inside the worker so document text never leaves the machine for indexing and indexing
costs nothing. Fallback: a hosted embedding model (DeepInfra lists bge-m3 at $0.01 per 1M
tokens [3]). The column type is fixed per model, so the model name and version are stored
with each chunk and a re-index job exists from day one.

**Per the earlier notes (D7):** the vector half ships behind the eval. If hybrid does not
beat keyword-only on retrieval recall for the 50 questions, we ship keyword-only.

## 5. Question-queue pipeline

```
question (queued)
  → retrieve passages (section 4)
  → not enough evidence?  → answer = UNKNOWN + what is missing        → ready
  → build prompt: question + numbered passages (as data) + rules
  → model returns JSON: claims[], each with passage numbers and an exact quote
  → verify (deterministic code):
        cited passage exists and belongs to this owner
        quote is present in the passage text
        every number in the claim appears in the quote, or came from a calc tool call
        no recommendation wording
  → drop failed claims, mark the answer "n of m claims removed"
  → store answer + claims + citations + usage                          → ready
```

- One model call per question in the MVP; a second only for a calculation tool round trip.
- Before the call, estimate cost from token counts. Over the per-task cap → refuse with a
  clear message. Over the monthly platform credit → ask for the user's own key.
- Answers are never overwritten; re-asking creates a new answer.
- "Live" reading is polling the question status; no websockets in the MVP.

**Calculation tools** (`backend/app/calc/`, pure functions on `Decimal`, each with tests):
growth, CAGR, TTM, margins, DuPont (3-step), simple ratios. Each returns value, formula
string, inputs and the citations of the inputs. The UI shows the formula.

## 6. Jobs, routines and agents

- **Queue:** the `job` table, claimed with `SELECT … FOR UPDATE SKIP LOCKED`. One worker
  process. Retries with a cap; a failed job is visible, never silently dropped.
- **Routine (M7):** a saved question + schedule + the assumptions it watches. The worker
  creates a run when due. Each run is immutable and stores: what changed since last run,
  which assumptions it touches, supported / challenged with citations, what is uncertain.
- **Filter rule:** an item is reported only if it links to an assumption. Otherwise it is
  counted ("7 items ignored") and not shown.
- **Sources for routines:** new uploads, new notes, new captures; web/news search is a
  later, separately-capped tool with source links. No live exchange filings.
- **Fail closed:** a run that cannot verify its inputs records "could not run" instead of guessing.
- A routine never changes a thesis, an assumption state or a decision. It proposes a review.

## 7. Chrome extension

- Manifest V3. **Side panel** as the notepad (Chrome 114+; `sidePanel.open()` needs a user
  gesture, so it opens from the toolbar icon, a keyboard shortcut, or a context-menu item)
  [7]. A small in-page floating button via content script is optional and off by default.
- Permissions: `sidePanel`, `activeTab`, `storage`, `contextMenus`. No blanket host access;
  the page is read only when the user acts.
- Captures: text, kind (note/question), selection, page title, URL, time, company guess.
- Auth: the user creates an **extension token** in app settings and pastes it once. The
  token can only create captures and list companies; it cannot read notes or documents.
- Offline: captures queue in `chrome.storage.local` and send when the API is reachable.
- Voice dictation: only if the browser's built-in speech recognition works in the side
  panel without extra services — to be tested in M3, otherwise dropped.
- Publishing to the Chrome Web Store is Parasu's step; local "load unpacked" for testers first.

## 8. Model adapter and bring-your-own-key

One interface:

```
complete(config, messages, json_schema=None, max_tokens=…) -> (text, tokens_in, tokens_out)
```

One implementation in the MVP: **OpenAI-compatible chat completions over `httpx`**. It
covers the hosted default, a user's OpenAI key, and local endpoints (Ollama, LM Studio,
vLLM). A second small implementation for Anthropic's native API is added when a tester
asks for it. Whether each host's endpoint is fully OpenAI-compatible for JSON output is
checked in M6, per host.

- A `model_config` row = label + base URL + model name + encrypted key.
- Keys: encrypted with AES-GCM under a master key from the environment; shown as last four
  characters only; never returned by the API; never written to logs (a log filter and a
  test enforce this).
- Per question the user picks a config; the default comes from server config.
- `usage` records every call and who paid.

### Default model and host

Model **(assumed, the eval decides)**: DeepSeek V4.1 Flash as default, V4 Pro as a
per-question upgrade. Both are in the V4 family the brief names.

| Host | V4.1 Flash, per 1M tokens in / out | Stores prompts? | Trains on them? | Region stated? |
|---|---|---|---|---|
| **DeepInfra** | $0.14 / $0.42 promotional; list $0.20 / $0.60. V4 Pro $1.30 / $2.60 [3] | Not stored to disk; in memory during inference; request content not logged [4] | No for open models [4] | **Not stated** on the page [4] |
| **Fireworks** | $0.30 / $1.20; spot tier $0.21 / $0.84 [2] | No logging or storage for open models unless opted in; exceptions: Batch API, and Responses API with `store=True` (its default) [5] | Not stated on the page [5] | **Not stated** on the page [5] |
| **Together** | $0.30 / $1.20; US-pinned $0.375 / $1.50. V4 Pro $1.32 / $3.96, US-pinned $1.65 / $4.95 [1] | **Yes by default**; an org admin must switch on zero data retention [6] | Opt-in only, off by default [6] | US-only **processing** via a separate endpoint; this covers processing, not storage, logging or routing [6] |

Reading: only Together puts a region in writing, and only for processing, at a 25%
premium, and it stores prompts unless ZDR is switched on. DeepInfra and Fireworks have the
stronger no-storage defaults but say nothing about location on the pages I read.

**Recommendation (assumed, please confirm):** develop against any of the three behind the
adapter; before beta, get the region in writing from DeepInfra and Fireworks. If neither
confirms, use Together's US-pinned endpoint with ZDR enabled. Use chat completions only
(not Fireworks' Responses API, whose default stores conversations).

## 9. Cost per user

Token sizes below are **my assumptions**, to be replaced by measured numbers in M6.

| Task | Assumed tokens in / out | V4.1 Flash at $0.30 / $1.20 | US-pinned $0.375 / $1.50 | V4 Pro US-pinned $1.65 / $4.95 |
|---|---|---|---|---|
| Typical question | 12,000 / 1,200 | $0.0050 | $0.0063 | $0.0257 |
| Heavy question | 40,000 / 3,000 | $0.0156 | $0.0195 | $0.0809 |
| Routine run (5 calls) | 100,000 / 10,000 | $0.0420 | $0.0525 | $0.2145 |

- **$0.25 per task** is comfortable for Flash (a heavy question is under 8% of the cap)
  and tight for Pro on multi-call runs ($0.21).
- **$2 per user per month** buys roughly 317 typical questions on US-pinned Flash, or 78
  on US-pinned Pro. Recommendation: platform credit applies to Flash only; Pro requires
  the user's own key.
- Indexing: with a local embedding model, zero. Hosted bge-m3 would be about $0.0015 for a
  150,000-token annual report [3].
- Both caps are config values. Enforcement is in the pipeline (section 5), checked before
  the call and reconciled after.

Hosting cost is not estimated here: nothing is deployed, and prices must be checked at the
time. See section 12.

## 10. Build versus adopt

| Need | Decision | Why |
|---|---|---|
| Block editor | **Adopt** BlockNote core (MPL-2.0); never its GPL `xl-*` packages. Fallback Tiptap (MIT). | Writing an editor is months; licence checked in `01-landscape.md` |
| Links / backlinks | **Build** (one table, one parser) | Small, and central to the product |
| Vector search | **Adopt** pgvector | Already in the stack decision |
| Keyword search | **Adopt** Postgres full-text | No extra service |
| PDF / Excel / Word extraction | **Adopt** one small library each (`pypdf`, `openpyxl`, `python-docx`) | Standard; licences to be re-checked at install in M4 |
| Job queue | **Build** on a Postgres table | ~100 lines; avoids Redis/Celery |
| Model calls | **Build** a thin `httpx` adapter | SDKs add weight and hide what is sent |
| Agent framework | **None** | A routine is a loop over a saved question |
| Auth | **Build** email + password + sessions (`argon2-cffi`) | Small; own login is a requirement; no third-party identity service |
| Second-brain apps (Khoj, Open Notebook, SurfSense…) | **Do not fork**; read Open Notebook (MIT) for ideas | See `01-landscape.md` |
| Trackr+ code | **Port selectively**, never import | Standalone product |

## 11. Security baseline

- Tenant isolation by RLS (section 3) with cross-tenant tests on every endpoint.
- Passwords: argon2. Sessions: server-side, httpOnly, SameSite=Lax, CSRF token on writes.
- Secrets only from environment; `.env` is gitignored; `.env.example` has no real values.
- Logs carry request id, user id, route, status, duration — never bodies, prompts,
  document text or keys. A test greps logs after a full run for a planted secret.
- Uploads: size cap, type allow-list by content sniffing, stored outside the web root,
  served only through an authenticated endpoint.
- Prompt injection: document and page text is passed as quoted data; the verifier drops
  claims that are not supported by quotes; the model has no tool that writes user data.
  Injection cases are in the eval set.
- Extension token is capture-only and revocable.
- Rate limits on login and on question submission.
- The repo is public: no real data, keys, or client references in fixtures or docs.

## 12. Running and hosting

**Local (now):** `docker compose up`. README covers first run, creating the first user
with an invite code, loading the extension unpacked, and adding a model key.

**Hosting (proposal only — nothing will be bought or created without your say-so):** one
small VM or container service running `api`, `worker`, `web`; managed Postgres with
pgvector; object storage for files; daily backups with a stated expiry. Choose a region
you are comfortable with for Indian users' research notes. Prices to be checked when we
get there (M9).

## 13. Assumed, please confirm

- Raw SQL + numbered migrations; no ORM.
- BlockNote core as the editor.
- Local embedding model, hybrid search gated by the eval.
- Polling instead of websockets.
- Flash on platform credit; Pro on the user's own key.
- Host: decide after written region confirmation; Together US-pinned + ZDR as the fallback.

## Sources (accessed 16 Nov 2026)

1. https://www.together.ai/pricing
2. https://fireworks.ai/pricing
3. https://deepinfra.com/pricing
4. https://docs.deepinfra.com/account/data-privacy
5. https://docs.fireworks.ai/guides/security_compliance/data_handling
6. https://docs.together.ai/docs/privacy-and-security
7. https://developer.chrome.com/docs/extensions/reference/api/sidePanel
