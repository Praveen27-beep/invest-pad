"use client";

/**
 * One sealed research task: its pinned context, a Run control that calls the person's own
 * model FROM THIS BROWSER (BE 23), the recorded result as the server rendered it, and the
 * explicit human review (BE 22). Used by the Tasks and Ask modes of a company document.
 *
 * WHAT IS SHOWN, AND WITH WHAT STANDING.
 *   - While a request streams, the text appears in a plain, escaped <pre> labelled UNREVIEWED.
 *     It is never parsed as HTML, no link in it is clickable, and nothing in it can call a
 *     tool or change state. It disappears once the server answers.
 *   - The recorded result is the SERVER's rendering: values filled from pinned rows by code,
 *     quotes checked against pinned text, citations listed, guardrail status and reasons shown.
 *     "Client reported" is said plainly: the server did not see the model call.
 *   - A blocked proposal stays visible and can only be rejected.
 *   - Acceptance files exactly one note, in the person's own wording, attributed to the
 *     proposal. It never creates a thesis, a decision, a conviction or a trade.
 */

import { useEffect, useRef, useState } from "react";
import { useAuth, useFetch } from "@trackr/core";
import { istToday } from "@/lib/research-api";
import {
  type DeterministicBlock,
  type ResearchEvent,
  getContext,
  rpaths,
  rwrite,
  type Agent,
  type Page,
  type Rendered,
  type Task,
} from "@/lib/research-client";
import {
  RunBlocked,
  destinationAllowed,
  hasKey,
  runTask,
  scopeFor,
  type RunOutcome,
} from "@/lib/research-agent";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";

const STATE_LABEL: Record<Task["state"], string> = {
  assigned: "Assigned",
  running: "Running",
  review: "Awaiting your review",
  done: "Accepted",
  rejected: "Rejected",
};

export function useAgents() {
  const { investorId, token } = useResearchAuth();
  return useFetch<Page<Agent>>(investorId ? rpaths.agents(investorId) : null, { limit: 100 }, token);
}

/** Tables computed by the SERVER from pinned rows (BE 30-35). The model wrote none of this. */
export function DeterministicBlockView({ block }: { block: DeterministicBlock }) {
  if (block.block === "PEER_TABLE") {
    return (
      <section className="ws-rendered-section">
        <h4 className="ws-field-label">Peer comparison — computed from your pinned peers, cell by cell</h4>
        <div className="ws-scroll-x">
        <table className="ws-rules">
          <thead>
            <tr>
              <th>Company</th>
              {block.compared_series.map((s) => <th key={s} className="ws-mono">{s}</th>)}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((r) => (
              <tr key={r.company}>
                <td className="ws-mono">{r.company === "SUBJECT" ? "This company" : r.isins.join(" / ")}</td>
                {block.compared_series.map((s) => {
                  const cell = r.cells[s];
                  return (
                    <td key={s} className="ws-mono">
                      {!cell ? "—" : cell.state === "OK" ? `${String(cell.value)} ${String(cell.unit)} (${String(cell.period_end)})` : `${cell.state}${cell.reason ? `: ${String(cell.reason)}` : ""}`}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        {block.excluded_peers.length > 0 && (
          <p className="ws-notice">
            Not compared: {block.excluded_peers.map((p) => `${p.isins.join("/")} (${p.reasons.join(", ")})`).join("; ")}
          </p>
        )}
      </section>
    );
  }
  if (block.block === "STATEMENT_COVERAGE") {
    return (
      <section className="ws-rendered-section">
        <h4 className="ws-field-label">Statement coverage by period (required: {block.required.join(", ").toLowerCase()})</h4>
        <ul>
          {Object.entries(block.periods).map(([period, sts]) => (
            <li key={period} className="ws-mono">
              {period}: {block.required.map((r) => `${r.toLowerCase()} ${sts[r] ? "held" : "MISSING"}`).join(" · ")}
            </li>
          ))}
        </ul>
      </section>
    );
  }
  if (block.block === "REQUIREMENTS") {
    return (
      <section className="ws-rendered-section">
        <h4 className="ws-field-label">Your requirements — each supported, contradicted or open (no score)</h4>
        <ul>
          {block.requirements.map((r) => (
            <li key={r.requirement_context_id}>
              <span className="ws-chip">{r.state.toLowerCase()}</span> {r.title ?? r.requirement_context_id.slice(0, 8)}
              {r.reason ? <span className="ws-muted ws-mono"> · {r.reason}</span> : null}
            </li>
          ))}
        </ul>
      </section>
    );
  }
  const row = (e: ResearchEvent) => (
    <li key={e.id} className="ws-mono">
      {e.event_type} · {e.event_date ?? `date ${e.date_precision.toLowerCase()}`} · {e.verification.toLowerCase()} · published {e.publication_date}
    </li>
  );
  return (
    <section className="ws-rendered-section">
      <h4 className="ws-field-label">Events from your pinned sources</h4>
      <div className="ws-field-label">Scheduled</div>
      <ul>{block.scheduled.map(row)}</ul>
      <div className="ws-field-label">Observed</div>
      <ul>{block.observed.map(row)}</ul>
      {block.claimed.length > 0 && (
        <>
          <div className="ws-field-label">Claimed by others (no date — not events)</div>
          <ul>{block.claimed.map(row)}</ul>
        </>
      )}
      {block.cancelled.length > 0 && (
        <>
          <div className="ws-field-label">Cancelled</div>
          <ul>{block.cancelled.map(row)}</ul>
        </>
      )}
    </section>
  );
}

export function RenderedResult({ rendered }: { rendered: Rendered }) {
  return (
    <div className="ws-rendered">
      {rendered.summary && <p className="ws-row-t">{rendered.summary}</p>}
      {rendered.sections.map((s, i) => (
        <section key={`${s.heading}-${i}`} className="ws-rendered-section">
          <h4 className="ws-field-label">
            {s.heading.replace(/_/g, " ").toLowerCase()}
            {s.deterministic ? " — verbatim from your pinned thesis" : ""}
          </h4>
          {s.paragraphs.map((p, j) => (
            <div key={j} className="ws-rendered-p">
              {p.label && <span className="ws-chip">{p.label}</span>} <span>{p.text}</span>
              {p.classification && <span className="ws-muted"> · {p.classification.toLowerCase()}</span>}
              {p.citations.length > 0 && (
                <span className="ws-muted ws-mono"> · cites {p.citations.map((c) => c.slice(0, 8)).join(", ")}</span>
              )}
              {(p.quotes ?? []).map((q, k) => (
                <blockquote key={k} className="ws-quote">
                  “{q.text}”
                </blockquote>
              ))}
            </div>
          ))}
        </section>
      ))}
      {rendered.answer_review && (
        <section className="ws-rendered-section">
          <h4 className="ws-field-label">What your answer covers</h4>
          {rendered.answer_review.ok.map((p, i) => (
            <p key={`ok${i}`}>{p.text}</p>
          ))}
          <h4 className="ws-field-label">Gaps the proposal states (not instructions)</h4>
          {rendered.answer_review.gap.map((p, i) => (
            <p key={`gap${i}`}>{p.text}</p>
          ))}
        </section>
      )}
      {(rendered.deterministic_blocks ?? []).map((b, i) => (
        <DeterministicBlockView key={`${b.block}-${i}`} block={b} />
      ))}
      {rendered.note_proposal && (
        <section className="ws-rendered-section">
          <h4 className="ws-field-label">Proposed {rendered.note_proposal.kind.toLowerCase()} note</h4>
          <p className="ws-row-t">{rendered.note_proposal.title}</p>
          <p style={{ whiteSpace: "pre-wrap" }}>{rendered.note_proposal.body}</p>
        </section>
      )}
    </div>
  );
}

function RunControls({
  task,
  agent,
  onChanged,
}: {
  task: Task;
  agent: Agent | null;
  onChanged: (t: Task | null) => void;
}) {
  const { investorId, token } = useResearchAuth();
  const { user } = useAuth();
  const [phase, setPhase] = useState<string | null>(null);
  const [stream, setStream] = useState("");
  const [outcome, setOutcome] = useState<RunOutcome | null>(null);
  const [blocked, setBlocked] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const running = phase !== null;

  // Leaving the page aborts locally. The provider may still finish and bill; nothing is resent.
  useEffect(() => () => abort.current?.abort(), []);

  if (!agent) {
    return <p className="ws-muted">The agent configuration this task pinned is not available.</p>;
  }
  const scope = user ? scopeFor(String(user.id), investorId, agent) : null;
  const keyReady = scope !== null && hasKey(scope);
  const canRun = task.state === "assigned" && !running;

  async function run() {
    if (!scope) return;
    setBlocked(null);
    setOutcome(null);
    setStream("");
    abort.current = new AbortController();
    try {
      const packet = await getContext(investorId, token, task.id);
      const result = await runTask({
        investorId,
        token,
        scope,
        agent: agent!,
        task,
        packet,
        signal: abort.current.signal,
        onText: (chunk) => setStream((s) => (s + chunk).slice(-20000)),
        onPhase: setPhase,
      });
      setOutcome(result);
      onChanged("task" in result ? result.task : null);
    } catch (err) {
      setBlocked(err instanceof RunBlocked ? err.message : describeError(err as Error) ?? String(err));
      onChanged(null);
    } finally {
      setPhase(null);
      setStream("");
    }
  }

  return (
    <div className="ws-run">
      {!keyReady && (
        <p className="ws-notice">
          No key for this agent is held in this browser. Add one on the Agents page; it stays in this
          tab&apos;s memory only.
        </p>
      )}
      {!destinationAllowed(agent.base_url) && (
        <p className="ws-notice ws-notice--error">
          This app&apos;s content policy does not allow {agent.base_url}. The endpoint cannot be used from
          this browser.
        </p>
      )}
      <div className="ws-form-row">
        <button
          type="button"
          className="ws-btn ws-btn--primary"
          disabled={!canRun || !keyReady}
          onClick={run}
          title="Starts one attempt, then sends one request from this browser to your endpoint"
        >
          {task.attempts > 0 && task.state === "assigned" ? "Retry (new attempt)" : "Run with my model"}
        </button>
        {running && (
          <button type="button" className="ws-btn ws-btn--ghost" onClick={() => abort.current?.abort()}>
            Stop
          </button>
        )}
        {phase && <span className="ws-muted">{phase}…</span>}
      </div>
      {running && stream && (
        <div>
          <div className="ws-field-label">Unreviewed model output (not recorded, not checked)</div>
          <pre className="ws-stream">{stream}</pre>
        </div>
      )}
      {blocked && <p className="ws-notice ws-notice--error">{blocked}</p>}
      {outcome?.kind === "FAILED" && (
        <p className="ws-notice ws-notice--error">
          {outcome.message} Recorded as {outcome.code}. You can retry explicitly.
        </p>
      )}
      {outcome?.kind === "CANCELLED" && (
        <p className="ws-notice">
          Stopped in this browser and recorded as cancelled. The provider may still have generated and
          billed the request.
        </p>
      )}
      {outcome?.kind === "UNCERTAIN" && (
        <div className="ws-notice">
          {outcome.message}
          {outcome.localDraft && <pre className="ws-stream">{outcome.localDraft}</pre>}
        </div>
      )}
    </div>
  );
}

function ReviewForms({ task, onChanged }: { task: Task; onChanged: () => void }) {
  const { investorId, token } = useResearchAuth();
  const result = task.result!;
  const proposed = result.rendered?.note_proposal;
  const [kind, setKind] = useState<"OBSERVATION" | "INTERPRETATION">(
    proposed?.kind === "OBSERVATION" ? "OBSERVATION" : "INTERPRETATION"
  );
  const [title, setTitle] = useState(proposed?.title ?? task.title);
  const [body, setBody] = useState(
    proposed?.body ??
      [result.rendered?.summary, ...(result.rendered?.sections ?? []).flatMap((s) => s.paragraphs.map((p) => p.text))]
        .filter(Boolean)
        .join("\n\n")
  );
  const [sourceId, setSourceId] = useState("");
  const [reason, setReason] = useState("");
  const accept = useSubmit<unknown>();
  const reject = useSubmit<unknown>();
  const blocked = result.guardrail_status !== "PASS";

  async function doAccept(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      result_id: result.id,
      reason,
      note: { kind, title, body, written_on: istToday(), primary_source_id: sourceId || null, links: [] as never[] },
    };
    const ok = await accept.submit(payload, (key) =>
      rwrite.accept({ investorId, token, idempotencyKey: key }, task.id, payload)
    );
    if (ok) onChanged();
  }

  async function doReject() {
    const payload = { result_id: result.id, reason };
    const ok = await reject.submit(payload, (key) =>
      rwrite.reject({ investorId, token, idempotencyKey: key }, task.id, payload)
    );
    if (ok) onChanged();
  }

  return (
    <form className="ws-form" onSubmit={doAccept}>
      <label className="ws-field">
        <span className="ws-field-label">Your reason (required either way)</span>
        <input className="ws-input" value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      {!blocked && (
        <>
          <div className="ws-form-row">
            <label className="ws-field">
              <span className="ws-field-label">File as</span>
              <select className="ws-input" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
                <option value="INTERPRETATION">interpretation</option>
                <option value="OBSERVATION">observation (needs a pinned source)</option>
              </select>
            </label>
            {kind === "OBSERVATION" && (
              <label className="ws-field">
                <span className="ws-field-label">Source id (pinned in this task)</span>
                <input className="ws-input ws-mono" value={sourceId} onChange={(e) => setSourceId(e.target.value)} />
              </label>
            )}
          </div>
          <label className="ws-field">
            <span className="ws-field-label">Title</span>
            <input className="ws-input" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label className="ws-field">
            <span className="ws-field-label">Note text — edit it into your own words; the machine origin stays recorded</span>
            <textarea className="ws-input" rows={6} value={body} onChange={(e) => setBody(e.target.value)} />
          </label>
        </>
      )}
      <div className="ws-form-row">
        {!blocked && (
          <button type="submit" className="ws-btn ws-btn--primary" disabled={accept.pending || !reason.trim()}>
            Accept into one note
          </button>
        )}
        <button
          type="button"
          className="ws-btn ws-btn--ghost"
          disabled={reject.pending || !reason.trim()}
          onClick={doReject}
        >
          Reject (output is kept)
        </button>
      </div>
      {(accept.error || reject.error) && (
        <p className="ws-notice ws-notice--error">{describeError(accept.error ?? reject.error)}</p>
      )}
    </form>
  );
}

export function TaskView({ taskId, agents, onChanged }: { taskId: string; agents: Agent[]; onChanged?: () => void }) {
  const { investorId, token } = useResearchAuth();
  const task = useFetch<Task>(investorId ? rpaths.task(investorId, taskId) : null, undefined, token);
  const t = task.data;
  if (!t) return <div className="ws-empty">{task.error ?? "Loading…"}</div>;
  const agent = agents.find((a) => a.id === t.agent_id && a.version === t.agent_version) ?? null;
  const r = t.result;
  const refresh = () => {
    task.refetch();
    onChanged?.();
  };

  return (
    <div className="ws-panel">
      <div className="ws-row">
        <span className="ws-row-grow">
          <span className="ws-row-t">{t.title}</span>
          <span className="ws-row-m">
            {t.purpose.toLowerCase().replace("_", " ")} · {t.method_key ?? "method"} v{t.skill_version} · agent v
            {t.agent_version} · evidence as of {new Date(t.context_cutoff).toLocaleString()}
          </span>
        </span>
        <span className="ws-chip">{STATE_LABEL[t.state]}</span>
      </div>
      <p style={{ whiteSpace: "pre-wrap" }}>{t.brief}</p>
      {t.error_code && t.state === "assigned" && (
        <p className="ws-muted">Last attempt ended: {t.error_code}.</p>
      )}
      {(t.state === "assigned" || t.state === "running") && (
        <RunControls
          task={t}
          agent={agent}
          onChanged={() => {
            refresh();
          }}
        />
      )}
      {t.state === "running" && t.latest_attempt?.lease_expired && (
        <p className="ws-muted">
          The attempt&apos;s ten-minute lease has passed; it will be recorded as expired before any retry.
        </p>
      )}
      {r && r.outcome === "PROPOSED" && (
        <div>
          <p className="ws-muted">
            {r.sample
              ? "STORED SAMPLE — written in advance, not a model run for this task."
              : "Client reported: this browser says it called the model; the server did not see that call."}{" "}
            Guardrails: <strong>{r.guardrail_status}</strong>
            {r.guardrail_status === "PASS" && " (structural checks only — not a verification of the content)"}
          </p>
          {r.guardrail_reasons.length > 0 && (
            <ul className="ws-reasons">
              {r.guardrail_reasons.map((x) => (
                <li key={x} className="ws-mono">
                  {x}
                </li>
              ))}
            </ul>
          )}
          {r.rendered && <RenderedResult rendered={r.rendered} />}
          {t.state === "review" && <ReviewForms task={t} onChanged={refresh} />}
          {t.review && (
            <p className="ws-muted">
              {t.review.decision === "ACCEPT" ? "Accepted" : "Rejected"} on{" "}
              {new Date(t.review.reviewed_at).toLocaleString()}: {t.review.reason}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

