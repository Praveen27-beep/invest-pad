"use client";

/**
 * A company research document: `/research/companies/{ISIN}` (FE 15, FE 16).
 *
 * THE RITUAL COMES FIRST. `GET /companies/{isin}` answers RITUAL_REQUIRED with identity only,
 * and this screen then shows nothing but the ritual form: no note, question, thesis, trigger
 * or position exists on the page until the person has written down their own questions.
 * Completion means the questions were SAVED, not answered -- open questions stay visibly open.
 *
 * MODES (`?mode=`): overview, questions, notes, thesis, evidence, tasks, ask (FE 17). The mode is part of the URL
 * so it survives reload and Back, but not of the tab identity -- one company, one tab.
 *
 * Holding and company with the same ISIN never collide: this is a research document; the
 * holding page stays a portfolio page with its own route.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { descriptorId, noteHref } from "@trackr/portfolio";
import { Figure, useFetch } from "@trackr/core";
import { useWorkspaceNav } from "@/lib/workspace-context";
import {
  istToday,
  paths,
  write,
  type CompanyView,
  type CompanyViewReady,
  type Note,
  type Page,
  type Question,
  type Fact,
  type Source,
} from "@/lib/research-api";
import {
  describeError,
  useResearchAuth,
  useSubmit,
} from "@/lib/research-hooks";
import { NoteForm } from "./NoteForm";
import { ThesisPanel } from "./ThesisPanel";
import { EvidencePanel } from "./EvidencePanel";
import { AdvancedEvidence } from "./AdvancedEvidence";
import { AskPanel, TasksPanel } from "./TasksPanel";
import { ReportsPanel } from "./ReportsPanel";
import { companySections } from "@/lib/company-sections";
import { CompanySnapshot } from "./CompanySnapshot";
import { FollowControl } from "../butler/ButlerControls";

const MODES = [
  { key: "overview", label: "Overview" },
  { key: "financials", label: "Financials" },
  { key: "thesis", label: "Investment Thesis" },
  { key: "research", label: "Research Report" },
  { key: "valuation-summary", label: "Valuation Summary" },
  { key: "valuation", label: "Valuation Model" },
  { key: "capex", label: "Capex Tracker" },
  { key: "calls", label: "Read Between the Lines" },
  { key: "forensics", label: "Forensics" },
  { key: "consistency", label: "Management Consistency" },
] as const;
const WORK_MODES = [
  { key: "notes", label: "Research notes" },
  { key: "questions", label: "Questions" },
  { key: "evidence", label: "Get filings" },
  { key: "tasks", label: "Run a skill" },
  { key: "ask", label: "Review my thinking" },
] as const;
const ALL_MODES = [...MODES, ...WORK_MODES];
type Mode = (typeof ALL_MODES)[number]["key"];

export function CompanyDocument({ isin }: { isin: string }) {
  const { investorId, token } = useResearchAuth();
  const { labelDocument } = useWorkspaceNav();
  const view = useFetch<CompanyView>(
    investorId ? paths.company(investorId, isin) : null,
    undefined,
    token,
  );
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const requested = searchParams.get("mode") ?? searchParams.get("view");
  const requestedSection = MODES.find(section => section.key === requested);
  const mode: Mode = ALL_MODES.some((m) => m.key === requested) && (!requestedSection || companySections(view.data?.identity || {}).includes(requestedSection.label))
    ? (requested as Mode)
    : "overview";

  const identity = view.data?.identity;
  const label = identity
    ? (identity.symbol ?? identity.name ?? identity.isin)
    : null;
  useEffect(() => {
    // The tab label comes from the AUTHORISED record only, after it loaded.
    if (label) labelDocument(descriptorId("company", isin), label);
  }, [label, isin, labelDocument]);

  function setMode(next: Mode) {
    const query = new URLSearchParams(searchParams.toString());
    query.delete("view");
    if (next === "overview") query.delete("mode");
    else query.set("mode", next);
    const qs = query.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  }

  if (view.loading) return <div className="ws-empty">Loading&hellip;</div>;
  if (view.error || !view.data) {
    return (
      <div>
        <div className="ws-crumb">Research &middot; Company</div>
        <h1 className="ws-h1 ws-mono">{isin}</h1>
        <div className="ws-notice ws-notice--error">
          {view.errorDetail?.status === 404
            ? "This company is not in your research. Add it from Explorer."
            : (describeError(view.errorDetail) ?? view.error)}
        </div>
        <p>
          <Link href="/explorer" className="ws-btn ws-btn--ghost">
            Go to Explorer
          </Link>
        </p>
      </div>
    );
  }

  const data = view.data;
  const availableSections = companySections(data.identity);
  return (
    <div>
      <div className="ws-crumb">Research &middot; Company</div>
      <h1 className="ws-h1">{label}</h1>
      <p className="ws-sub ws-mono">
        {data.identity.isin}
        {data.identity.canonical_isin !== data.identity.isin
          ? ` → now ${data.identity.canonical_isin}`
          : ""}
        {data.identity.name && data.identity.symbol
          ? ` · ${data.identity.name}`
          : ""}
      </p>
      {data.state === "RITUAL_REQUIRED" ? (
        <RitualForm isin={isin} onSaved={view.refetch} />
      ) : (
        <>
          {mode !== "notes" && <nav className="ws-modes ip-company-tabs" aria-label="Company views">
            {MODES.filter(m => availableSections.includes(m.label)).map(m => <Link key={m.key} className="ws-mode" aria-current={mode === m.key ? "page" : undefined} href={`${pathname}?mode=${m.key}`}>{m.label}</Link>)}
          </nav>}
          {mode === "notes" ? <p><Link href={pathname}>← Company overview</Link></p> : <nav className="ws-modes" aria-label="Research workspace tools">
            {WORK_MODES.map(m => <Link key={m.key} className="ws-mode" aria-current={mode === m.key ? "page" : undefined} href={`${pathname}?mode=${m.key}`}>{m.label}</Link>)}
            <FollowControl isin={data.identity.isin} />
          </nav>}
          {mode === "research" && <ReportsPanel isin={isin} ritualComplete />}
          {mode === "valuation" && (
            <>
              <h2 className="ws-h1">Valuation Model</h2>
              <p className="ws-sub">
                Scenarios from your assumptions and verified inputs. No price
                targets.
              </p>
              <AdvancedEvidence isin={isin} section="calculations" />
            </>
          )}
          {[
            "financials",
            "valuation-summary",
            "capex",
            "calls",
            "forensics",
            "consistency",
          ].includes(mode) && (
            <ResearchSection
              key={`${isin}:${mode}`}
              isin={isin}
              mode={mode}
              onWrite={() => setMode("notes")}
              onEvidence={() => setMode("evidence")}
            />
          )}
          {mode === "overview" && (
            <Overview data={data} onChanged={view.refetch} />
          )}
          {mode === "questions" && (
            <QuestionsPanel isin={isin} onChanged={view.refetch} />
          )}
          {mode === "notes" && <NotesPanel isin={isin} />}
          {mode === "thesis" && (
            <ThesisPanel isin={isin} onChanged={view.refetch} />
          )}
          {mode === "evidence" && <EvidencePanel isin={isin} />}
          {mode === "tasks" && (
            <TasksPanel
              isin={isin}
              thesisId={
                data.state === "READY" ? (data.thesis?.id ?? null) : null
              }
            />
          )}
          {mode === "ask" && (
            <AskPanel
              isin={isin}
              thesisId={
                data.state === "READY" ? (data.thesis?.id ?? null) : null
              }
            />
          )}
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------
// Ritual
// ------------------------------------------------------------------------------------

function RitualForm({ isin, onSaved }: { isin: string; onSaved: () => void }) {
  const { investorId, token } = useResearchAuth();
  const [questions, setQuestions] = useState<
    { text: string; blocking: boolean }[]
  >([{ text: "", blocking: true }]);
  const [writtenOn, setWrittenOn] = useState(istToday());
  const { submit, pending, error } = useSubmit<unknown>();
  const filled = questions.filter((q) => q.text.trim());

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const body = { questions: filled, written_on: writtenOn };
    const saved = await submit(body, (key) =>
      write.createRitual(
        { investorId, token, idempotencyKey: key },
        isin,
        body,
      ),
    );
    if (saved) onSaved();
  }

  return (
    <div className="ws-panel" style={{ maxWidth: 720 }}>
      <div className="ws-panel-head">
        <h2>Your questions come first</h2>
        <span className="ws-hint">
          nothing here opens until at least one is saved
        </span>
      </div>
      <form
        className={`ws-form${pending ? " ws-pending" : ""}`}
        onSubmit={save}
      >
        <p className="ws-row-m">
          Write down what you need to find out about this company before you
          form a view. Mark a question as blocking if no thesis should be
          published while it is unanswered. Saving them does not answer them.
        </p>
        {questions.map((question, index) => (
          <div
            key={index}
            className="ws-form-row"
            style={{ gridTemplateColumns: "1fr auto auto" }}
          >
            <label className="ws-field">
              <span className="ws-field-label">Question {index + 1}</span>
              <input
                className="ws-input"
                value={question.text}
                maxLength={2000}
                onChange={(e) =>
                  setQuestions((all) =>
                    all.map((q, i) =>
                      i === index ? { ...q, text: e.target.value } : q,
                    ),
                  )
                }
              />
            </label>
            <label className="ws-check" style={{ alignSelf: "end" }}>
              <input
                type="checkbox"
                checked={question.blocking}
                onChange={(e) =>
                  setQuestions((all) =>
                    all.map((q, i) =>
                      i === index ? { ...q, blocking: e.target.checked } : q,
                    ),
                  )
                }
              />{" "}
              Blocks a thesis
            </label>
            <button
              type="button"
              className="ws-btn ws-btn--ghost ws-btn--sm"
              style={{ alignSelf: "end" }}
              disabled={questions.length === 1}
              onClick={() =>
                setQuestions((all) => all.filter((_, i) => i !== index))
              }
            >
              Remove
            </button>
          </div>
        ))}
        <div className="ws-form-actions">
          <button
            type="button"
            className="ws-btn ws-btn--ghost ws-btn--sm"
            disabled={questions.length >= 20}
            onClick={() =>
              setQuestions((all) => [...all, { text: "", blocking: false }])
            }
          >
            Add another question
          </button>
          <label className="ws-field" style={{ marginLeft: "auto" }}>
            <span className="ws-field-label">Written on</span>
            <input
              className="ws-input"
              type="date"
              value={writtenOn}
              onChange={(e) => setWrittenOn(e.target.value)}
            />
          </label>
        </div>
        {error && (
          <div className="ws-notice ws-notice--error">
            {describeError(error)}
          </div>
        )}
        <div className="ws-form-actions">
          <button
            type="submit"
            className="ws-btn ws-btn--primary"
            disabled={pending || filled.length === 0}
          >
            {pending
              ? "Saving…"
              : `Save ${filled.length || ""} question${filled.length === 1 ? "" : "s"}`}
          </button>
        </div>
      </form>
    </div>
  );
}

// ------------------------------------------------------------------------------------
// Overview
// ------------------------------------------------------------------------------------

function Overview({
  data,
  onChanged,
}: {
  data: CompanyViewReady;
  onChanged: () => void;
}) {
  return (
    <div className="ws-stack">
      <MarketSummary data={data} />
      {data.notices.map((notice) => (
        <div key={notice.code} className="ws-notice ws-notice--warn">
          {notice.message}
        </div>
      ))}

      <div>
        <div className="ws-sechead">
          <h2>Open questions</h2>
          <div className="ws-hint">{data.open_questions.length} unanswered</div>
        </div>
        <div className="ws-panel">
          {data.open_questions.length === 0 ? (
            <div className="ws-empty">
              Every question you recorded has an answer.
            </div>
          ) : (
            data.open_questions.map((question) => (
              <QuestionItem
                key={question.id}
                question={question}
                onChanged={onChanged}
              />
            ))
          )}
        </div>
      </div>

      <div>
        <div className="ws-sechead">
          <h2>Commitment in force</h2>
        </div>
        <div className="ws-panel">
          {data.thesis ? (
            <div className="ws-row">
              <span className="ws-row-grow">
                <span className="ws-row-t">
                  Version {data.thesis.version} &middot; formed{" "}
                  {data.thesis.formed_on}
                </span>
                <span className="ws-row-m">
                  {data.trigger
                    ? `Latest stored evaluation: ${data.trigger.state} (evidence to ${data.trigger.evidence_cutoff.slice(0, 10)})`
                    : "No evaluation has been recorded for this version."}
                </span>
              </span>
              <span className="ws-chip ws-chip--ink">
                {data.thesis.display_status}
              </span>
            </div>
          ) : (
            <div className="ws-empty">No active thesis is in force.</div>
          )}
        </div>
      </div>

      <div>
        <div className="ws-sechead">
          <h2>Latest notes</h2>
        </div>
        <div className="ws-panel">
          {data.notes.items.length === 0 ? (
            <div className="ws-empty">No notes yet.</div>
          ) : (
            data.notes.items.map((note) => (
              <NoteRow key={note.id} note={note} />
            ))
          )}
        </div>
      </div>

      <div>
        <div className="ws-sechead">
          <h2>Position</h2>
          <div className="ws-hint">
            read from your ledger now; never stored with research
          </div>
        </div>
        <div className="ws-panel">
          {data.position ? (
            <>
              {data.position.holdings.map((holding, index) => (
                <div key={index} className="ws-row">
                  <span className="ws-row-grow">
                    <span className="ws-row-t ws-mono">
                      {String(holding.isin)}
                    </span>
                    <span className="ws-row-m">
                      Quantity {String(holding.quantity)} &middot; invested{" "}
                      {String(holding.invested)} &middot; value{" "}
                      {String(holding.market_value)}
                    </span>
                  </span>
                </div>
              ))}
              {data.position.unpriced.map((holding) => (
                <div key={holding.isin} className="ws-row">
                  <span className="ws-row-grow">
                    <span className="ws-row-t ws-mono">{holding.isin}</span>
                    <span className="ws-row-m">
                      Invested {holding.invested} &middot; not valued: no price
                      available
                    </span>
                  </span>
                  <span className="ws-chip ws-chip--warn">Unpriced</span>
                </div>
              ))}
            </>
          ) : (
            <div className="ws-empty">You do not hold this company.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function NoteRow({ note }: { note: Note }) {
  const contradicts = note.links.filter((l) => l.relation === "CONTRADICTS");
  return (
    <Link
      className="ws-row"
      data-kind={note.kind}
      href={noteHref(note.id) ?? "#"}
    >
      <span className="ws-row-grow">
        <span className="ws-row-t">{note.title}</span>
        <span className="ws-row-m">
          {note.kind.toLowerCase().replace("_", " ")} &middot; written{" "}
          {note.written_on}
          {note.revision_ids.length > 1
            ? ` · ${note.revision_ids.length} revisions`
            : ""}
          {note.source ? ` · cites ${note.source.source}` : ""}
          {note.authorship === "ACCEPTED_AGENT"
            ? " · accepted from an agent proposal"
            : ""}
        </span>
      </span>
      {contradicts.length > 0 && (
        <span className="ws-chip ws-chip--neg">Contradiction</span>
      )}
    </Link>
  );
}

// ------------------------------------------------------------------------------------
// Questions and answers
// ------------------------------------------------------------------------------------

function QuestionsPanel({
  isin,
  onChanged,
}: {
  isin: string;
  onChanged: () => void;
}) {
  const { investorId, token } = useResearchAuth();
  const list = useFetch<Page<Question>>(
    investorId ? paths.questions(investorId) : null,
    { isin, limit: 100 },
    token,
  );
  const { submit, pending, error } = useSubmit<Question>();
  const [text, setText] = useState("");
  const [blocking, setBlocking] = useState(false);
  const [writtenOn, setWrittenOn] = useState(istToday());

  async function add(event: React.FormEvent) {
    event.preventDefault();
    const body = { text, blocking, written_on: writtenOn };
    const saved = await submit(body, (key) =>
      write.createQuestion(
        { investorId, token, idempotencyKey: key },
        isin,
        body,
      ),
    );
    if (saved) {
      setText("");
      setBlocking(false);
      list.refetch();
      onChanged();
    }
  }

  return (
    <div className="ws-stack">
      <div className="ws-panel">
        {list.loading && <div className="ws-empty">Loading&hellip;</div>}
        {list.error && (
          <div className="ws-notice ws-notice--error">{list.error}</div>
        )}
        {list.data?.items.map((question) => (
          <QuestionItem
            key={question.id}
            question={question}
            onChanged={() => {
              list.refetch();
              onChanged();
            }}
          />
        ))}
        {list.data?.next_cursor && (
          <div className="ws-empty">
            More questions exist beyond the first 100.
          </div>
        )}
      </div>
      <div className="ws-panel">
        <div className="ws-panel-head">
          <h3>Ask another question</h3>
          <span className="ws-hint">
            earlier questions and rituals are never edited
          </span>
        </div>
        <form
          className={`ws-form${pending ? " ws-pending" : ""}`}
          onSubmit={add}
        >
          <label className="ws-field">
            <span className="ws-field-label">Question</span>
            <input
              className="ws-input"
              required
              value={text}
              maxLength={2000}
              onChange={(e) => setText(e.target.value)}
            />
          </label>
          <div className="ws-form-actions">
            <label className="ws-check">
              <input
                type="checkbox"
                checked={blocking}
                onChange={(e) => setBlocking(e.target.checked)}
              />{" "}
              Blocks a thesis
            </label>
            <input
              className="ws-input"
              type="date"
              value={writtenOn}
              onChange={(e) => setWrittenOn(e.target.value)}
              style={{ maxWidth: 170 }}
            />
            <button
              type="submit"
              className="ws-btn ws-btn--primary"
              disabled={pending || !text.trim()}
            >
              {pending ? "Saving…" : "Save question"}
            </button>
          </div>
          {error && (
            <div className="ws-notice ws-notice--error">
              {describeError(error)}
            </div>
          )}
        </form>
      </div>
    </div>
  );
}

function QuestionItem({
  question,
  onChanged,
}: {
  question: Question;
  onChanged: () => void;
}) {
  const { investorId, token } = useResearchAuth();
  const [answering, setAnswering] = useState(false);
  const [answer, setAnswer] = useState("");
  const [answeredOn, setAnsweredOn] = useState(istToday());
  const { submit, pending, error } = useSubmit<unknown>();
  const latest = question.latest_answer;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const body = {
      answer,
      answered_on: answeredOn,
      expected_latest_answer_id: latest?.id ?? null,
    };
    const saved = await submit(body, (key) =>
      write.answerQuestion(
        { investorId, token, idempotencyKey: key },
        question.id,
        body,
      ),
    );
    if (saved) {
      setAnswer("");
      setAnswering(false);
      onChanged();
    }
  }

  return (
    <div
      className="ws-row"
      style={{ flexDirection: "column", alignItems: "stretch" }}
    >
      <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
        <span className="ws-row-grow">
          <span className="ws-row-t">{question.text}</span>
          <span className="ws-row-m">
            asked {question.written_on}
            {question.answer_ids.length > 1
              ? ` · ${question.answer_ids.length} answers kept`
              : ""}
          </span>
        </span>
        {question.blocking && (
          <span className="ws-chip ws-chip--warn">Blocking</span>
        )}
        <span
          className={`ws-chip ${question.status === "OPEN" ? "ws-chip--open" : "ws-chip--pos"}`}
        >
          {question.status === "OPEN" ? "Open" : "Answered"}
        </span>
      </div>
      {latest && (
        <div style={{ marginTop: 8 }}>
          <p className="ws-verbatim">{latest.answer}</p>
          <span className="ws-row-m">your answer of {latest.answered_on}</span>
        </div>
      )}
      {question.review && (
        <div className="ws-notice ws-notice--open" style={{ marginTop: 8 }}>
          <strong>
            Review of this exact answer
            {question.review.sample ? " (stored sample)" : ""}
          </strong>
          {question.review.ok.length > 0 && (
            <ul>
              {question.review.ok.map((s, i) => (
                <li key={`ok${i}`}>{s}</li>
              ))}
            </ul>
          )}
          {question.review.gap.length > 0 && (
            <ul>
              {question.review.gap.map((s, i) => (
                <li key={`gap${i}`}>Gap: {s}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {answering ? (
        <form
          className={`ws-form${pending ? " ws-pending" : ""}`}
          style={{ padding: "10px 0 0" }}
          onSubmit={save}
        >
          <textarea
            className="ws-textarea"
            required
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder='In your own words. "I cannot establish this" is a valid answer.'
          />
          <div className="ws-form-actions">
            <input
              className="ws-input"
              type="date"
              value={answeredOn}
              onChange={(e) => setAnsweredOn(e.target.value)}
              style={{ maxWidth: 170 }}
            />
            <button
              type="submit"
              className="ws-btn ws-btn--primary ws-btn--sm"
              disabled={pending || !answer.trim()}
            >
              {pending
                ? "Saving…"
                : latest
                  ? "Save revised answer"
                  : "Save answer"}
            </button>
            <button
              type="button"
              className="ws-btn ws-btn--ghost ws-btn--sm"
              onClick={() => setAnswering(false)}
            >
              Discard
            </button>
          </div>
          {error && (
            <div className="ws-notice ws-notice--error">
              {describeError(error)}
            </div>
          )}
        </form>
      ) : (
        <div className="ws-form-actions" style={{ marginTop: 8 }}>
          <button
            type="button"
            className="ws-btn ws-btn--sm"
            onClick={() => setAnswering(true)}
          >
            {latest ? "Revise answer" : "Answer"}
          </button>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------
// Notes
// ------------------------------------------------------------------------------------

function NotesPanel({ isin }: { isin: string }) {
  const { investorId, token } = useResearchAuth();
  const [history, setHistory] = useState(false);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [writing, setWriting] = useState(false);
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const notes = useFetch<Page<Note>>(
    investorId
      ? query.trim()
        ? paths.noteSearch(investorId)
        : paths.companyNotes(investorId, isin)
      : null,
    {
      q: query.trim() || undefined,
      isin,
      kind: kind || undefined,
      history,
      cursor,
      limit: 50,
    },
    token,
  );
  const router = useRouter();

  return (
    <div className="ip-notes-layout">
      <aside className="ip-note-groups" aria-label="Note groups">
        {[
          ["", "All notes"],
          ["QUESTION", "Questions"],
          ["OBSERVATION", "Observations"],
          ["INTERPRETATION", "Interpretations"],
          ["THESIS_NOTE", "Thesis notes"],
          ["LITERATURE", "Reading notes"],
          ["DECISION", "Decisions"],
        ].map(([value, label]) => (
          <button
            key={value}
            aria-pressed={kind === value}
            onClick={() => {
              setKind(value ?? "");
              setCursor(undefined);
            }}
          >
            {label}
          </button>
        ))}
      </aside>
      <div className="ws-stack">
        <label className="ws-field">
          <span className="ws-field-label">
            Find in this company’s research
          </span>
          <input
            className="ws-input"
            placeholder="Search your earlier thinking"
            maxLength={200}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setCursor(undefined);
            }}
          />
        </label>
        <div className="ws-form-actions">
          <button
            type="button"
            className="ws-btn ws-btn--primary ws-btn--sm"
            onClick={() => setWriting(true)}
            disabled={writing}
          >
            New note
          </button>
          <label className="ws-check">
            <input
              type="checkbox"
              disabled={Boolean(query.trim())}
              checked={history}
              onChange={(e) => {
                setCursor(undefined);
                setHistory(e.target.checked);
              }}
            />{" "}
            Show every revision
          </label>
        </div>
        {writing && (
          <div>
            <NoteForm
              isin={isin}
              onCancel={() => setWriting(false)}
              onSaved={(note) => {
                setWriting(false);
                notes.refetch();
                const href = noteHref(note.id);
                if (href) router.push(href);
              }}
            />
          </div>
        )}
        <div className="ws-panel">
          {notes.loading && <div className="ws-empty">Loading&hellip;</div>}
          {notes.error && (
            <div className="ws-notice ws-notice--error">{notes.error}</div>
          )}
          {notes.data && notes.data.items.length === 0 && (
            <div className="ws-empty">
              No notes match this group or search. Start with one idea.
            </div>
          )}
          {notes.data?.items.map((note) => (
            <NoteRow key={note.id} note={note} />
          ))}
        </div>
        {notes.data?.next_cursor && (
          <button
            type="button"
            className="ws-btn ws-btn--ghost ws-btn--sm"
            onClick={() => setCursor(notes.data?.next_cursor ?? undefined)}
          >
            Older notes
          </button>
        )}
      </div>
    </div>
  );
}

/** Existing ledger price seam: no second quote fetch, no numeric conversion or guessed exchange. */
function MarketSummary({ data }: { data: CompanyViewReady }) {
  const holding = data.position?.holdings.find(
    (h) =>
      h.isin === data.identity.canonical_isin || h.isin === data.identity.isin,
  );
  const price =
    typeof holding?.last_price === "string" ? holding.last_price : null;
  return (
    <CompanySnapshot name={data.identity.name || data.identity.symbol || data.identity.isin} symbol={data.identity.symbol} price={price} asOf={data.position?.as_of} statistics={[
      { label: "ISIN", value: data.identity.canonical_isin },
      { label: "Research as of", value: data.as_of.slice(0, 10) },
    ]}/>

  );
}

const SECTION_GUIDES: Record<
  string,
  { title: string; question: string; metrics: RegExp; prompts: string[] }
> = {
  financials: {
    title: "Financials",
    question: "What do the statements establish?",
    metrics: /./,
    prompts: [
      "Read profit and loss alongside cash flow.",
      "Keep consolidated and standalone figures separate.",
      "Compare like periods and keep restatements visible.",
    ],
  },
  "valuation-summary": {
    title: "Valuation Summary",
    question: "Which assumptions carry the valuation?",
    metrics: /valuation|multiple|enterprise|market_cap|cash_flow|earnings/i,
    prompts: [
      "Separate recorded inputs from assumptions.",
      "Test the range of outcomes in Valuation Model.",
      "An unavailable input stays unknown.",
    ],
  },
  capex: {
    title: "Capex Tracker",
    question: "Is capital turning into productive capacity?",
    metrics: /capex|capital_expenditure|capacity|fixed_asset|cwip/i,
    prompts: [
      "Compare announced spending with reported deployment.",
      "Record the expected commissioning date.",
      "Revisit utilisation and returns when new evidence arrives.",
    ],
  },
  calls: {
    title: "Read Between the Lines",
    question: "What was said, and what was left unanswered?",
    metrics: /guidance|commentary|outlook/i,
    prompts: [
      "Read the prepared remarks against the questions asked.",
      "Keep management’s statement verbatim in the source.",
      "Write your interpretation separately, with the call date.",
    ],
  },
  forensics: {
    title: "Forensics",
    question: "Do the earnings stand up to scrutiny?",
    metrics: /receivable|cash|related|pledge|auditor|debt|inventory/i,
    prompts: [
      "Reconcile earnings with operating cash flow.",
      "Inspect related-party transactions and promoter pledges.",
      "Record auditor qualifications without inferring misconduct.",
    ],
  },
  consistency: {
    title: "Management Consistency",
    question: "What did management commit to, and what followed?",
    metrics: /guidance|commitment|target|actual|execution/i,
    prompts: [
      "Date each original commitment.",
      "Compare it with subsequently reported evidence.",
      "Keep both records when they conflict. Do not rewrite the promise.",
    ],
  },
};

/** A reading surface over the existing sourced-fact store, not a second financial model. */
function ResearchSection({
  isin,
  mode,
  onWrite,
  onEvidence,
}: {
  isin: string;
  mode: string;
  onWrite: () => void;
  onEvidence: () => void;
}) {
  const { investorId, token } = useResearchAuth();
  const [cursor, setCursor] = useState<string | undefined>();
  const facts = useFetch<Page<Fact>>(
    investorId ? paths.companyFacts(investorId, isin) : null,
    { limit: 100, cursor },
    token,
  );
  const sources = useFetch<Page<Source>>(
    investorId ? paths.companySources(investorId, isin) : null,
    { limit: 100 },
    token,
  );
  const guide = SECTION_GUIDES[mode];
  if (!guide) return null;
  const rows =
    facts.data?.items.filter((f) => guide.metrics.test(f.metric)) ?? [];
  return (
    <article className="ip-research-section">
      <span className="ws-eyebrow">
        {guide.title} / {isin}
      </span>
      <h2>{guide.question}</h2>
      <p className="ws-sub">
        Recorded evidence, with its period and verification status. Research
        prompts below are a method, not findings about this company.
      </p>
      <div className="ws-sechead">
        <h3>Source evidence</h3>
        <button className="ws-btn ws-btn--sm" onClick={onEvidence}>
          Get filings
        </button>
      </div>
      {facts.loading ? (
        <p role="status">Loading evidence…</p>
      ) : facts.error ? (
        <div className="ws-notice ws-notice--error">
          {facts.error}
          <button className="ws-btn ws-btn--sm" onClick={facts.refetch}>
            Try again
          </button>
        </div>
      ) : rows.length ? (
        <div className="ip-table-scroll">
          <table className="ip-research-table">
            <thead>
              <tr>
                <th>Reported measure</th>
                <th>Value / basis</th>
                <th>Period</th>
                <th>Source / status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((f) => {
                const source = sources.data?.items.find(
                  (s) => s.id === f.source_id,
                );
                return (
                  <tr key={f.id}>
                    <td>{f.metric.replace(/_/g, " ")}</td>
                    <td>
                      {f.numeric_value ??
                        f.text_value ??
                        (f.boolean_value === null
                          ? "Unknown"
                          : String(f.boolean_value))}{" "}
                      {f.unit}
                      <small>{f.basis}</small>
                    </td>
                    <td>
                      {f.period_start}
                      <br />
                      {f.period_end}
                    </td>
                    <td>
                      {source?.source ?? `Source ${f.source_id}`}
                      <small>
                        {source
                          ? `Published ${source.publication_date} · ${source.document_reference}`
                          : "Source details are not loaded. Open Get filings to inspect the citation."}
                      </small>
                      <small>
                        {f.verification === "VERIFIED"
                          ? "Verified"
                          : "Unverified"}
                        {f.superseded_by ? " · Superseded" : ""}
                        {f.conflicts_with.length
                          ? " · Conflicting evidence"
                          : ""}
                      </small>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="ws-empty">
          No matching evidence on this page. Add a dated source and recorded
          facts to begin.
        </div>
      )}
      {sources.error && (
        <p className="ws-notice">Source details unavailable: {sources.error}</p>
      )}
      {facts.data?.next_cursor && (
        <button
          className="ws-btn ws-btn--sm"
          onClick={() => setCursor(facts.data?.next_cursor ?? undefined)}
        >
          More evidence
        </button>
      )}
      <section>
        <h2>Research questions</h2>
        {guide.prompts.map((p, i) => (
          <div className="ws-row" key={p}>
            <span className="ws-mono ws-muted">0{i + 1}</span>
            <span>{p}</span>
          </div>
        ))}
      </section>
      <p>
        <button className="ws-btn ws-btn--primary" onClick={onWrite}>
          Write your interpretation
        </button>
      </p>
    </article>
  );
}
