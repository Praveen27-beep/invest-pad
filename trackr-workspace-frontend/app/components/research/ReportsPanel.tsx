"use client";

/**
 * Research this company (RP 07 over RP 00-06): request, durable progress, the checked
 * document and its private PDF/HTML.
 *
 * NO PERSONAL THESIS NEEDED. An issuer-only report can be requested before the research ritual
 * -- it reads permitted issuer evidence only, never your notes, thesis, answers or the Butler
 * notebook. Adding your private research is a separate, explicit scope that needs the ritual.
 *
 * NOTHING IS SENT UNTIL YOU CONFIRM. The form shows what will be read, the cost bound and the
 * deadline first; the job is created only on the explicit confirm click. Closing the browser
 * does not stop it; cancelling is explicit and immediate on our side (a provider call already
 * in flight may still be billed, and this says so).
 *
 * PROGRESS IS STAGES, NOT PERCENTAGES. The screen shows completed stages and the event history
 * (reconnectable by cursor), never a fictitious percentage. A report that could not be supported
 * shows why, with no body. A published report shows its status label, every limitation, the
 * withheld claims and the source register; a PDF inherits exactly that status and evidence.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  TERMINAL,
  downloadArtifact,
  reports,
  type JobEvent,
  type ReportDocumentOut,
  type ReportJob,
  type ReportRequest,
  type Statement,
} from "@/lib/report-client";
import { describeError, useResearchAuth } from "@/lib/research-hooks";

const STATEMENTS: { key: Statement; label: string }[] = [
  { key: "INCOME_STATEMENT", label: "Profit and loss" },
  { key: "BALANCE_SHEET", label: "Balance sheet" },
  { key: "CASH_FLOW", label: "Cash flow" },
  { key: "SEGMENTS", label: "Segments" },
  { key: "SHAREHOLDING", label: "Shareholding" },
  { key: "AUDITOR_REPORT", label: "Auditor's report" },
];

const STATE_TEXT: Record<string, string> = {
  QUEUED: "Queued",
  RUNNING: "Working",
  WAITING_FOR_SOURCE: "Waiting for a source",
  BUDGET_PAUSED: "Stopped at its budget",
  NEEDS_REVIEW: "Needs review",
  READY_WITH_LIMITATIONS: "Ready — with stated limitations",
  READY_CHECKED_SCOPE: "Ready — declared checks passed for the stated scope",
  FAILED: "Stopped without a report",
  CANCEL_REQUESTED: "Cancelling",
  CANCELLED: "Cancelled",
  EXPIRED: "Deadline reached",
};

const STAGES = ["PLAN", "SOURCE_DISCOVERY", "NORMALIZE", "DRAFT", "CHECK", "RENDER"];
const STAGE_TEXT: Record<string, string> = {
  PLAN: "coverage plan",
  SOURCE_DISCOVERY: "permitted sources",
  NORMALIZE: "comparable history",
  DRAFT: "claims",
  CHECK: "checks",
  RENDER: "HTML and PDF",
};

const CLASS_TEXT: Record<string, string> = {
  SOURCE_STATEMENT: "What the source reports",
  CALCULATED_VALUE: "Calculated by an approved formula",
  INTERPRETATION: "AI interpretation — not a verified fact",
  HYPOTHETICAL_RISK: "Conditional risk — not an event",
  UNKNOWN: "Not established",
};

function newKey(): string {
  return crypto.randomUUID();
}

export function ReportsPanel({ isin, ritualComplete }: { isin: string; ritualComplete: boolean }) {
  const { investorId, token } = useResearchAuth();
  const [jobs, setJobs] = useState<ReportJob[] | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);

  const load = useCallback(async () => {
    if (!investorId) return;
    try {
      const all = await reports.list(investorId, token);
      setJobs(all.filter((j) => j.isin === isin || (j.request as { requested_isin?: string }).requested_isin === isin));
      setError(null);
    } catch (e) {
      setError(e as Error);
    }
  }, [investorId, token, isin]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="ws-panel">
      <div className="ws-row">
        <span className="ws-row-grow">
          <span className="ws-row-t">Research this company</span>
          <span className="ws-row-m">
            A checked research document from permitted issuer evidence, with every gap shown. You decide what it means.
          </span>
        </span>
        {!asking && (
          <button type="button" className="ws-btn ws-btn--primary ws-btn--sm" onClick={() => setAsking(true)}>
            Request a report
          </button>
        )}
      </div>
      {error && <p className="ws-notice ws-notice--error">{describeError(error)}</p>}
      {asking && (
        <RequestForm
          isin={isin}
          ritualComplete={ritualComplete}
          onDone={(job) => {
            setAsking(false);
            if (job) {
              setOpen(job.id);
              load();
            }
          }}
        />
      )}
      {jobs && jobs.length === 0 && !asking && <p className="ws-muted">No report requested for this company yet.</p>}
      {jobs?.map((j) => (
        <JobRow key={j.id} job={j} open={open === j.id} onToggle={() => setOpen(open === j.id ? null : j.id)} onChanged={load} />
      ))}
    </div>
  );
}

// --- request ------------------------------------------------------------------------------------

function RequestForm({ isin, ritualComplete, onDone }: { isin: string; ritualComplete: boolean; onDone: (job: ReportJob | null) => void }) {
  const { investorId, token } = useResearchAuth();
  const [question, setQuestion] = useState("Help me understand this business");
  const [mode, setMode] = useState<ReportRequest["mode"]>("CURRENT_WITH_HISTORY");
  const [cutoff, setCutoff] = useState("");
  const [years, setYears] = useState(10);
  const [statements, setStatements] = useState<Statement[]>(["INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"]);
  const [basis, setBasis] = useState<ReportRequest["basis"]>("CONSOLIDATED");
  const [scope, setScope] = useState<ReportRequest["scope"]>("ISSUER_ONLY");
  const [budget, setBudget] = useState("");
  const [deadline, setDeadline] = useState(240);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const key = useRef<string>(newKey());

  const body: ReportRequest = {
    isin,
    question: question.trim(),
    mode,
    cutoff: mode === "POINT_IN_TIME" ? cutoff || null : null,
    window_years: years,
    statements,
    basis,
    scope,
    budget: budget.trim(),
    deadline_minutes: deadline,
  };
  const valid =
    body.question.length >= 3 &&
    statements.length > 0 &&
    /^(0|[1-9][0-9]{0,17})(\.[0-9]{1,6})?$/.test(body.budget) &&
    body.budget !== "0" &&
    (mode !== "POINT_IN_TIME" || !!cutoff);

  async function submit() {
    if (!investorId) return;
    setBusy(true);
    setError(null);
    try {
      // One key per confirmed request: a retry of the same click cannot create a second job.
      const job = await reports.create({ investorId, token, idempotencyKey: key.current }, body);
      onDone(job);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  if (confirming) {
    return (
      <div className="ws-rendered">
        <p className="ws-row-t">Before anything starts</p>
        <ul>
          <li>Company <span className="ws-mono">{isin}</span> — your question: “{body.question}”.</li>
          <li>
            {mode === "POINT_IN_TIME"
              ? `As it could have been known on ${cutoff}: anything published later is excluded.`
              : "Current knowledge, with earlier figures kept where a filing was restated."}
          </li>
          <li>Up to {years} fiscal year(s) — a maximum, not a promise. Missing years are shown as missing, never filled.</li>
          <li>
            Reads: issuer evidence already held under approved source rights.{" "}
            {scope === "ISSUER_ONLY"
              ? "None of your notes, thesis, answers or Butler notebook is read."
              : "Plus your private research for this company (you completed its questions)."}{" "}
            No web crawl; nothing is sent to anyone.
          </li>
          <li>
            A platform model may draft clearly labelled interpretations inside this budget. Your own model key is not used.
            Spending stops at <span className="ws-mono">{body.budget}</span> (in the operator's declared currency) and the job
            stops after {deadline} minutes.
          </li>
          <li>The result is research information. It will not tell you to buy, sell or hold.</li>
        </ul>
        {error && <p className="ws-notice ws-notice--error">{describeError(error)}</p>}
        <div className="ws-form-row">
          <button type="button" className="ws-btn ws-btn--primary ws-btn--sm" disabled={busy} onClick={submit}>
            Confirm and start
          </button>
          <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={busy} onClick={() => setConfirming(false)}>
            Back
          </button>
          <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={busy} onClick={() => onDone(null)}>
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="ws-rendered">
      <label className="ws-field">
        <span className="ws-field-label">Your question, in your own words</span>
        <input className="ws-input" value={question} maxLength={500} onChange={(e) => setQuestion(e.target.value)} />
      </label>
      <fieldset className="ws-field">
        <legend className="ws-field-label">As of</legend>
        <label>
          <input type="radio" checked={mode === "CURRENT_WITH_HISTORY"} onChange={() => setMode("CURRENT_WITH_HISTORY")} /> Now, with history
        </label>{" "}
        <label>
          <input type="radio" checked={mode === "POINT_IN_TIME"} onChange={() => setMode("POINT_IN_TIME")} /> A past date
        </label>
        {mode === "POINT_IN_TIME" && (
          <input className="ws-input" type="date" value={cutoff} onChange={(e) => setCutoff(e.target.value)} aria-label="Cutoff date" />
        )}
      </fieldset>
      <label className="ws-field">
        <span className="ws-field-label">Years of history (at most)</span>
        <input className="ws-input" type="number" min={1} max={10} value={years} onChange={(e) => setYears(Math.min(10, Math.max(1, Number(e.target.value) || 1)))} />
      </label>
      <fieldset className="ws-field">
        <legend className="ws-field-label">Statements</legend>
        {STATEMENTS.map((s) => (
          <label key={s.key} style={{ marginRight: 12 }}>
            <input
              type="checkbox"
              checked={statements.includes(s.key)}
              onChange={(e) => setStatements(e.target.checked ? [...statements, s.key] : statements.filter((x) => x !== s.key))}
            />{" "}
            {s.label}
          </label>
        ))}
      </fieldset>
      <label className="ws-field">
        <span className="ws-field-label">Reporting basis (never mixed in one series)</span>
        <select className="ws-input" value={basis} onChange={(e) => setBasis(e.target.value as ReportRequest["basis"])}>
          <option value="CONSOLIDATED">Consolidated</option>
          <option value="STANDALONE">Standalone</option>
        </select>
      </label>
      <fieldset className="ws-field">
        <legend className="ws-field-label">What it may read</legend>
        <label>
          <input type="radio" checked={scope === "ISSUER_ONLY"} onChange={() => setScope("ISSUER_ONLY")} /> Company evidence only
        </label>{" "}
        <label title={ritualComplete ? "" : "Record your own questions for this company first"}>
          <input
            type="radio"
            disabled={!ritualComplete}
            checked={scope === "ISSUER_PLUS_PRIVATE_RESEARCH"}
            onChange={() => setScope("ISSUER_PLUS_PRIVATE_RESEARCH")}
          />{" "}
          Also my private research {ritualComplete ? "" : "(record your questions first)"}
        </label>
      </fieldset>
      <div className="ws-form-row">
        <label className="ws-field">
          <span className="ws-field-label">Spending limit (required; no default)</span>
          <input className="ws-input" inputMode="decimal" placeholder="e.g. 2.50" value={budget} onChange={(e) => setBudget(e.target.value)} />
        </label>
        <label className="ws-field">
          <span className="ws-field-label">Stop after (minutes, at most 240)</span>
          <input className="ws-input" type="number" min={5} max={240} value={deadline} onChange={(e) => setDeadline(Math.min(240, Math.max(5, Number(e.target.value) || 5)))} />
        </label>
      </div>
      <div className="ws-form-row">
        <button type="button" className="ws-btn ws-btn--primary ws-btn--sm" disabled={!valid} onClick={() => setConfirming(true)}>
          Review before starting
        </button>
        <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => onDone(null)}>
          Cancel
        </button>
      </div>
    </div>
  );
}

// --- one job -------------------------------------------------------------------------------------

function JobRow({ job, open, onToggle, onChanged }: { job: ReportJob; open: boolean; onToggle: () => void; onChanged: () => void }) {
  const { investorId, token } = useResearchAuth();
  const [current, setCurrent] = useState<ReportJob>(job);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const cursor = useRef(0);
  const [error, setError] = useState<Error | null>(null);
  const terminal = TERMINAL.includes(current.state);

  const poll = useCallback(async () => {
    if (!investorId) return;
    try {
      const page = await reports.events(investorId, token, job.id, cursor.current);
      if (page.items.length) {
        cursor.current = page.next_cursor;
        setEvents((prev) => [...prev, ...page.items]);
      }
      setCurrent(await reports.get(investorId, token, job.id));
    } catch (e) {
      setError(e as Error);
    }
  }, [investorId, token, job.id]);

  useEffect(() => {
    if (!open) return;
    poll();
    if (terminal) return;
    // Reconnectable progress: resume from the last event version, every few seconds.
    const t = setInterval(poll, 5000);
    return () => clearInterval(t);
  }, [open, poll, terminal]);

  async function cancel() {
    if (!investorId) return;
    try {
      setCurrent(await reports.cancel({ investorId, token, idempotencyKey: newKey() }, job.id));
      onChanged();
    } catch (e) {
      setError(e as Error);
    }
  }

  const done = new Set(current.completed_stages);
  return (
    <div className="ws-row" style={{ flexDirection: "column", alignItems: "stretch" }}>
      <button type="button" className="ws-row ws-btn--ghost" onClick={onToggle} aria-expanded={open} style={{ textAlign: "left" }}>
        <span className="ws-row-grow">
          <span className="ws-row-t">“{String((current.request as { question?: string }).question ?? "")}”</span>
          <span className="ws-row-m">
            {STATE_TEXT[current.state] ?? current.state}
            {current.state_reason ? ` · ${current.state_reason.replace(/_/g, " ").toLowerCase()}` : ""} · requested{" "}
            {current.recorded_at.slice(0, 16).replace("T", " ")}
            {current.revision_of ? " · revision" : ""}
          </span>
        </span>
      </button>
      {open && (
        <div className="ws-rendered">
          <p className="ws-muted">
            Stages:{" "}
            {STAGES.map((s) => (
              <span key={s} className="ws-chip" style={{ opacity: done.has(s) ? 1 : 0.45 }}>
                {done.has(s) ? "✓ " : ""}
                {STAGE_TEXT[s]}
              </span>
            ))}
          </p>
          <p className="ws-muted ws-mono">
            spent (worst case) {current.spent_worst_case} of {current.budget_limit} {current.currency} · stops at{" "}
            {current.deadline_at.slice(0, 16).replace("T", " ")} · {current.provider}/{current.model}
          </p>
          {!terminal && current.state !== "CANCEL_REQUESTED" && (
            <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={cancel}>
              Cancel this report
            </button>
          )}
          {!terminal && (
            <p className="ws-muted">
              You can close this page; the report keeps going. Cancelling stops further work; a model call already in flight may
              still be billed.
            </p>
          )}
          {error && <p className="ws-notice ws-notice--error">{describeError(error)}</p>}
          {current.state === "FAILED" && (
            <p className="ws-notice">
              No report was published: {current.state_reason.replace(/_/g, " ").toLowerCase()}. Nothing unsupported is shown in
              its place.
            </p>
          )}
          {(current.state === "READY_WITH_LIMITATIONS" || current.state === "READY_CHECKED_SCOPE") && (
            <DocumentView reportId={job.id} onChanged={onChanged} />
          )}
          {terminal && <Revise reportId={job.id} onDone={onChanged} />}
          <details>
            <summary className="ws-field-label">History ({events.length})</summary>
            <ul>
              {events.map((e) => (
                <li key={e.version} className="ws-mono">
                  v{e.version} {e.recorded_at.slice(0, 19).replace("T", " ")} {e.state}
                  {e.stage ? ` ${e.stage}` : ""} {e.reason_code}
                </li>
              ))}
            </ul>
          </details>
        </div>
      )}
    </div>
  );
}

function Revise({ reportId, onDone }: { reportId: string; onDone: () => void }) {
  const { investorId, token } = useResearchAuth();
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [budget, setBudget] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const key = useRef(newKey());
  if (!open) {
    return (
      <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => setOpen(true)}>
        Request a new version
      </button>
    );
  }
  async function go() {
    if (!investorId) return;
    try {
      await reports.revise({ investorId, token, idempotencyKey: key.current }, reportId, {
        ...(question.trim() ? { question: question.trim() } : {}),
        budget: budget.trim(),
        deadline_minutes: 240,
      });
      setOpen(false);
      onDone();
    } catch (e) {
      setError(e as Error);
    }
  }
  return (
    <div className="ws-form-row">
      <input className="ws-input" placeholder="new question (optional)" value={question} onChange={(e) => setQuestion(e.target.value)} />
      <input className="ws-input" placeholder="spending limit" inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)} />
      <button type="button" className="ws-btn ws-btn--sm" disabled={!/^(0|[1-9][0-9]{0,17})(\.[0-9]{1,6})?$/.test(budget.trim())} onClick={go}>
        Start new version
      </button>
      <span className="ws-muted">The earlier report stays as it was.</span>
      {error && <p className="ws-notice ws-notice--error">{describeError(error)}</p>}
    </div>
  );
}

// --- the published document ---------------------------------------------------------------------

function DocumentView({ reportId, onChanged }: { reportId: string; onChanged: () => void }) {
  const { investorId, token } = useResearchAuth();
  const [doc, setDoc] = useState<ReportDocumentOut | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!investorId) return;
    try {
      setDoc(await reports.document(investorId, token, reportId));
    } catch (e) {
      setError(e as Error);
    }
  }, [investorId, token, reportId]);
  useEffect(() => {
    load();
  }, [load]);

  const byId = useMemo(() => new Map((doc?.document.claims ?? []).map((c) => [c.claim_id, c])), [doc]);
  if (error) return <p className="ws-notice ws-notice--error">{describeError(error)}</p>;
  if (!doc) return <p className="ws-muted">Loading the checked document…</p>;
  const d = doc.document;
  const missingYears = [...new Set(d.coverage.cells.filter((c) => c.status !== "SUPPORTED" && c.status !== "RESTATED").map((c) => c.period.label))];
  const blocked = doc.retracted || doc.rights_changed.length > 0;

  async function download(id: string, fmt: string) {
    if (!investorId) return;
    setDownloadError(null);
    try {
      await downloadArtifact(investorId, token, reportId, id, `report-${d.isin}-v${d.report_version}.${fmt.toLowerCase()}`);
    } catch (e) {
      setDownloadError((e as Error).message);
    }
  }
  async function retract() {
    if (!investorId) return;
    if (!window.confirm("Withdraw this report? Downloads stop now. Copies already downloaded cannot be recalled.")) return;
    try {
      await reports.retract({ investorId, token, idempotencyKey: newKey() }, reportId, null);
      await load();
      onChanged();
    } catch (e) {
      setError(e as Error);
    }
  }

  return (
    <div>
      <p className="ws-notice">{d.decision_notice}</p>
      <p>
        <span className="ws-chip">{doc.status === "READY_CHECKED_SCOPE" ? "checked for the stated scope" : "published with limitations"}</span>{" "}
        report v{d.report_version} · {d.mode === "POINT_IN_TIME" ? `as of ${d.cutoff}` : "current with history"} · basis{" "}
        {d.coverage.basis.toLowerCase()}
      </p>
      {missingYears.length > 0 && <p className="ws-muted">Not established for: {missingYears.join(", ")}.</p>}
      {d.limitations.length > 0 && (
        <p className="ws-muted ws-mono">Limitations: {[...new Set(d.limitations.map((l) => l.code))].join(", ")}</p>
      )}
      {Object.keys(doc.withheld).length > 0 && (
        <details>
          <summary className="ws-field-label">{Object.keys(doc.withheld).length} claim(s) withheld at publication</summary>
          <ul>
            {Object.entries(doc.withheld).map(([id, reasons]) => (
              <li key={id} className="ws-mono">
                {id}: {reasons.join(", ")}
              </li>
            ))}
          </ul>
        </details>
      )}
      {d.sections.map((s) => (
        <section key={s.section_id} className="ws-rendered-section">
          <h4 className="ws-field-label">
            {s.section_id.replace(/_/g, " ").toLowerCase()} · {s.status.toLowerCase()}
          </h4>
          {s.claim_ids.map((id) => {
            const c = byId.get(id);
            if (!c) return null;
            return (
              <div key={id} className="ws-rendered-p">
                <span className="ws-chip">{CLASS_TEXT[c.claim_class]}</span> <span>{c.text}</span>
                {c.excerpt && <blockquote className="ws-quote">“{c.excerpt}”</blockquote>}
                {(c.premise_claim_ids?.length || c.input_claim_ids?.length) ? (
                  <span className="ws-muted ws-mono"> · rests on {(c.premise_claim_ids ?? c.input_claim_ids ?? []).join(", ")}</span>
                ) : null}
              </div>
            );
          })}
        </section>
      ))}
      <details>
        <summary className="ws-field-label">Source register ({d.sources.length})</summary>
        <ul>
          {d.sources.map((s) => (
            <li key={s.source_id}>
              <span className="ws-mono">{s.source_id.slice(0, 8)}</span> {s.title} — {s.attribution.toLowerCase()}, published{" "}
              {s.published_on ?? "unknown"}, retrieved {s.retrieved_at.slice(0, 10)} · export {s.rights.EXPORT?.toLowerCase()}
            </li>
          ))}
        </ul>
      </details>
      <div className="ws-form-row">
        {doc.artifacts.map((a) => (
          <button key={a.id} type="button" className="ws-btn ws-btn--sm" disabled={blocked} onClick={() => download(a.id, a.format)}>
            Download {a.format}
            {a.page_count ? ` (${a.page_count} pages)` : ""}
          </button>
        ))}
        {!doc.retracted && (
          <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={retract}>
            Withdraw report
          </button>
        )}
      </div>
      {doc.retracted && <p className="ws-notice">Withdrawn. Downloads are stopped; copies already downloaded cannot be recalled.</p>}
      {doc.rights_changed.length > 0 && (
        <p className="ws-notice">A source's export permission changed since this was rendered. Request a new version to download.</p>
      )}
      {downloadError && <p className="ws-notice ws-notice--error">{downloadError}</p>}
      <p className="ws-muted">
        Values the source does not permit exporting are withheld from the download and named there. The PDF carries the same
        status and evidence as this page.
      </p>
    </div>
  );
}
