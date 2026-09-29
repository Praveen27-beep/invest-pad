"use client";

/**
 * Butler's optional model selection (BT 08) and its teaching and status controls (BT 09-10).
 *
 * NOTHING HERE RUNS ON ITS OWN. No model is called on load, on tab switch, on reconnect or when
 * an inbox card arrives. One click on "Review with my model" seals a packet (a Trackr+ task),
 * starts ONE attempt and sends ONE request from this browser to the person's own endpoint --
 * never twice, never retried automatically, cut off after 60 seconds.
 *
 * THE RAW STREAM IS NEVER SHOWN. The model may only return identifiers; its text is buffered in
 * memory, parsed, and submitted. What appears here is what the SERVER validated and rendered from
 * reviewed templates and exact saved passages -- re-validated on every read, so a retracted
 * source or forgotten memory withdraws a card instead of leaving stale text. A failure shows the
 * honest state and leaves Butler's deterministic cards exactly as they were.
 */

import { useState } from "react";
import { useAuth, useFetch } from "@trackr/core";
import { paths, type CompanyListItem, type Page } from "@/lib/research-api";
import {
  getContext,
  getSelection,
  getTask,
  rpaths,
  rwrite,
  type Agent,
  type ButlerStatus,
  type Feedback,
  type Selection,
  type Skill,
  type Teaching,
} from "@/lib/research-client";
import { RunBlocked, hasKey, runTask, scopeFor } from "@/lib/research-agent";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";
import { UnderstandingYou } from "./UnderstandingYou";

const STATE_TEXT: Record<Selection["state"], string> = {
  NO_RESULT: "No result yet.",
  ASSIGNED: "Sealed; no attempt has finished.",
  RUNNING: "An attempt is in progress.",
  VALIDATED: "Checked by Butler's validator.",
  ABSTAINED: "The model declined to select anything, with a stated reason.",
  STALE: "The saved evidence changed since this review was sealed; nothing is shown. Start a new review.",
  WITHDRAWN: "Access to this evidence is gone; nothing is shown.",
  REJECTED_BY_VALIDATION: "The model's selection failed validation; nothing it returned is shown.",
  VALIDATION_UNAVAILABLE: "Validation is unavailable right now, so nothing is shown. Butler's checked cards are unaffected.",
};

function FeedbackButtons({ kind, id, version }: { kind: "QUESTION" | "LESSON"; id: string; version: string }) {
  const { investorId, token } = useResearchAuth();
  const { submit, pending } = useSubmit<Feedback>();
  const [done, setDone] = useState<string | null>(null);
  const rate = async (rating: "USEFUL" | "NOT_USEFUL") => {
    const body = { subject_kind: kind, subject_id: id, subject_version: version, inbox_item_id: null, rating };
    const saved = await submit(body, (key) => rwrite.feedback({ investorId, token, idempotencyKey: key }, body));
    if (saved) setDone(rating);
  };
  return (
    <span className="ws-form-row">
      <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={pending} onClick={() => rate("USEFUL")} aria-pressed={done === "USEFUL"}>
        Useful
      </button>
      <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={pending} onClick={() => rate("NOT_USEFUL")} aria-pressed={done === "NOT_USEFUL"}>
        Not useful
      </button>
    </span>
  );
}

type SelCard = {
  kind: string;
  statements: { text: string; basis: string }[];
  passages: { ref: string; text: string; trust: string; recorded_at: string }[];
  question: { id: string; version: string; text: string } | null;
  lesson: { id: string; version: string; text: string } | null;
};

function SelectionCards({ selection, detail }: { selection: Selection; detail: boolean }) {
  return (
    <div>
      <p className="ws-muted">
        {STATE_TEXT[selection.state]}
        {selection.sample ? " Stored sample, not a model run." : ""}
        {selection.execution === "CLIENT_REPORTED_MODEL" ? " Model call reported by this browser." : ""}
      </p>
      {selection.reason_codes.length > 0 && <p className="ws-mono ws-muted">{selection.reason_codes.join(", ")}</p>}
      {selection.abstain_code && <p className="ws-notice">Abstained: {selection.abstain_code}</p>}
      {(selection.cards as SelCard[]).map((c, i) => (
        <div key={i} className="ws-card">
          {c.statements.map((s, j) => (
            <p key={j}>
              {s.text} <span className="ws-muted">({s.basis.toLowerCase()})</span>
            </p>
          ))}
          {c.passages.map((p) => (
            <blockquote key={p.ref} className="ws-quote">
              “{p.text}” <span className="ws-muted">— {p.trust.toLowerCase()}, {new Date(p.recorded_at).toLocaleDateString()}</span>
            </blockquote>
          ))}
          {c.question && (
            <div>
              <p className="ws-row-t">{c.question.text}</p>
              <FeedbackButtons kind="QUESTION" id={c.question.id} version={c.question.version} />
            </div>
          )}
          {c.lesson && (
            <div>
              <p>{detail ? c.lesson.text : c.lesson.text.split(". ")[0] + "."}</p>
              <FeedbackButtons kind="LESSON" id={c.lesson.id} version={c.lesson.version} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export function ModelReview() {
  const { investorId, token } = useResearchAuth();
  const { user } = useAuth();
  const companies = useFetch<Page<CompanyListItem>>(investorId ? paths.companies(investorId) : null, { limit: 100 }, token);
  const agents = useFetch<Page<Agent>>(investorId ? rpaths.agents(investorId) : null, { limit: 100 }, token);
  const skills = useFetch<Page<Skill>>(investorId ? rpaths.skills(investorId) : null, { history: true, limit: 100 }, token);
  const teaching = useFetch<Teaching>(investorId ? rpaths.teaching(investorId) : null, undefined, token);
  const [isin, setIsin] = useState("");
  const [intent, setIntent] = useState("review_evidence");
  const [agentKey, setAgentKey] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const history = useFetch<Selection[]>(investorId ? rpaths.selections(investorId) : null, isin ? { isin } : undefined, token);

  const butlerSkills = new Set((skills.data?.items ?? []).filter((s) => s.task_route === "BUTLER_ONLY").map((s) => s.id));
  const butlerAgents = (agents.data?.items ?? []).filter((a) => a.enabled && butlerSkills.has(a.skill_id));
  const agent = butlerAgents.find((a) => `${a.id}:${a.version}` === agentKey) ?? null;
  const scope = agent && user ? scopeFor(String(user.id), investorId, agent) : null;

  async function review() {
    if (!agent || !scope || !isin || busy) return;
    setMessage(null);
    setSelection(null);
    setBusy("sealing");
    const controller = new AbortController();
    try {
      const sealed = await rwrite.createSelection(
        { investorId, token, idempotencyKey: crypto.randomUUID() },
        { isin, intent, agent_id: agent.id, agent_version: agent.version, parent_task_id: null }
      );
      const packet = await getContext(investorId, token, sealed.task_id);
      const task = await getTask(investorId, token, sealed.task_id);
      setBusy("asking your model");
      const outcome = await runTask({
        investorId,
        token,
        scope,
        agent,
        task,
        packet,
        signal: controller.signal,
        // no onText: Butler never shows raw model text
        onPhase: (p) => setBusy(p === "submitting" ? "checking" : "asking your model"),
      });
      if (outcome.kind === "FAILED") setMessage(`${outcome.message} Butler's checked cards are unchanged.`);
      if (outcome.kind === "UNCERTAIN") setMessage(outcome.message);
      if (outcome.kind === "CANCELLED") setMessage("Stopped. The provider may still bill the request.");
      setSelection(await getSelection(investorId, token, sealed.task_id));
      history.refetch();
    } catch (err) {
      setMessage(err instanceof RunBlocked ? err.message : describeError(err as Error));
    } finally {
      setBusy(null);
    }
  }

  const detail = teaching.data?.detail === "DETAILED";
  return (
    <div>
      <p className="ws-muted">
        Optional. Your model may only choose from checked observations, saved passages and reviewed questions;
        it cannot write facts, approve a decision or change anything. One request per click, from this browser,
        with your own key.
      </p>
      <div className="ws-form">
        <select className="ws-input" value={isin} onChange={(e) => setIsin(e.target.value)}>
          <option value="">company…</option>
          {(companies.data?.items ?? [])
            .filter((c) => c.ritual_complete)
            .map((c) => (
              <option key={c.isin} value={c.isin}>
                {c.symbol ?? c.name ?? c.isin}
              </option>
            ))}
        </select>
        <select className="ws-input" value={intent} onChange={(e) => setIntent(e.target.value)}>
          <option value="review_evidence">review my evidence</option>
          <option value="new_material">new material</option>
          <option value="checkpoint">checkpoint</option>
          <option value="decision_review">decision review</option>
        </select>
        <select className="ws-input" value={agentKey} onChange={(e) => setAgentKey(e.target.value)}>
          <option value="">agent (Butler selector method)…</option>
          {butlerAgents.map((a) => (
            <option key={`${a.id}:${a.version}`} value={`${a.id}:${a.version}`}>
              {a.name} · {a.model}
            </option>
          ))}
        </select>
        {butlerAgents.length === 0 && (
          <p className="ws-muted">
            Publish the Butler selector on the Skills page and configure an agent for it to enable this.
          </p>
        )}
        {agent && scope && !hasKey(scope) && (
          <p className="ws-notice">No key is held in this browser for that agent. Add one on the Agents page.</p>
        )}
        <button
          type="button"
          className="ws-btn ws-btn--primary"
          disabled={!agent || !isin || busy !== null || !scope || !hasKey(scope)}
          onClick={review}
        >
          {busy ? `${busy}…` : "Review with my model"}
        </button>
      </div>
      {message && <p className="ws-notice ws-notice--error">{message}</p>}
      {selection && <SelectionCards selection={selection} detail={detail} />}
      {isin && (history.data ?? []).length > 0 && (
        <details>
          <summary className="ws-field-label">Earlier reviews (re-checked now)</summary>
          {(history.data ?? []).map((s) => (
            <div key={s.task_id}>
              <div className="ws-muted">{new Date(s.created_at).toLocaleString()} · {s.intent}</div>
              <SelectionCards selection={s} detail={detail} />
            </div>
          ))}
        </details>
      )}
    </div>
  );
}

export function ButlerSettings() {
  const { investorId, token } = useResearchAuth();
  const teaching = useFetch<Teaching>(investorId ? rpaths.teaching(investorId) : null, undefined, token);
  const status = useFetch<ButlerStatus>(investorId ? rpaths.status(investorId) : null, undefined, token);
  const { submit, pending, error } = useSubmit<Teaching>();
  const t = teaching.data;

  async function save(patch: Partial<Pick<Teaching, "detail" | "lesson_cadence" | "follow_ups">>) {
    if (!t) return;
    const body = {
      detail: patch.detail ?? t.detail,
      lesson_cadence: patch.lesson_cadence ?? t.lesson_cadence,
      follow_ups: patch.follow_ups ?? t.follow_ups,
      expected_version: t.version,
    };
    const saved = await submit(body, (key) => rwrite.setTeaching({ investorId, token, idempotencyKey: key }, body));
    if (saved) teaching.refetch();
  }

  const s = status.data;
  return (
    <div>
      <div className="ws-field-label">Teaching (your explicit choices; they never relax a check)</div>
      {t && (
        <div className="ws-form">
          <label className="ws-field">
            <span className="ws-field-label">Lesson text</span>
            <select className="ws-input" value={t.detail} disabled={pending} onChange={(e) => save({ detail: e.target.value as Teaching["detail"] })}>
              <option value="CONCISE">concise</option>
              <option value="DETAILED">detailed</option>
            </select>
          </label>
          <label className="ws-field">
            <span className="ws-field-label">Offer lessons</span>
            <select className="ws-input" value={t.lesson_cadence} disabled={pending} onChange={(e) => save({ lesson_cadence: e.target.value as Teaching["lesson_cadence"] })}>
              <option value="EVERY_REVIEW">in every review where one applies</option>
              <option value="WEEKLY">at most weekly</option>
              <option value="OFF">never</option>
            </select>
          </label>
          <label className="ws-field">
            <span className="ws-field-label">Follow-up questions after an answer</span>
            <select className="ws-input" value={t.follow_ups} disabled={pending} onChange={(e) => save({ follow_ups: e.target.value as Teaching["follow_ups"] })}>
              <option value="ASK">ask</option>
              <option value="SKIP">skip</option>
            </select>
          </label>
          {error && <p className="ws-notice ws-notice--error">{describeError(error)}</p>}
        </div>
      )}
      <div className="ws-field-label">Status</div>
      {s ? (
        <ul className="ws-muted">
          <li>Worker: last outcome {s.worker.last_outcome}, lag {s.worker.lag_seconds}s.</li>
          <li>Model selection: {s.worker.model_execution.toLowerCase().replace(/_/g, " ")}.</li>
          <li>
            Switches:{" "}
            {Object.entries(s.switches)
              .map(([k, v]) => `${k.replace(/_/g, " ")} ${v ? "on" : "off"}`)
              .join(", ")}
            .
          </li>
          <li>External sources: {String(s.coverage.external_sources).toLowerCase().replace(/_/g, " ")}. No “all clear” is ever inferred.</li>
          {(s.selections.attempts ?? []).map((a, i) => (
            <li key={i} className="ws-mono">
              {a.count} × {a.outcome}/{a.guardrail}/{a.error_code} ({a.mode.toLowerCase()})
            </li>
          ))}
        </ul>
      ) : (
        <p className="ws-muted">{status.error ?? "Loading…"}</p>
      )}
      <UnderstandingYou />
    </div>
  );
}
