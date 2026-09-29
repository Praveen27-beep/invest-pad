"use client";

/**
 * Tasks and Ask (grounded chat) for one company (FE 17 core over BE 20-25).
 *
 * A TASK IS SEALED WHEN IT IS CREATED. What you tick below is exactly what the model will be
 * given -- no more is added later, and new evidence means a new task. Creating it calls no
 * model; Run does, from this browser, with your own key.
 *
 * ASK IS NOT A CHATBOT. Each turn you send becomes a sealed CHAT task over the evidence you
 * selected plus the earlier turns; the answer appears only after the server has checked it,
 * rendered from its own template and citations. If a turn looks like a request to answer one
 * of your own open questions, it is refused before any task exists: write your answer first,
 * then ask for an ANSWER_REVIEW of that exact answer.
 */

import { useState } from "react";
import { useFetch } from "@trackr/core";
import {
  paths,
  type Fact,
  type Note,
  type Page,
  type Question,
  type Source,
} from "@/lib/research-api";
import {
  emptySelection,
  rpaths,
  rwrite,
  type Agent,
  type ChatMessage,
  type ContextSelection,
  type Skill,
  type Task,
  type Thread,
} from "@/lib/research-client";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";
import { RenderedResult, TaskView, useAgents } from "./TaskView";

function useTaskAgents(): { agents: Agent[]; skills: Skill[]; loading: boolean } {
  const { investorId, token } = useResearchAuth();
  const agents = useAgents();
  const skills = useFetch<Page<Skill>>(investorId ? rpaths.skills(investorId) : null, { history: true, limit: 100 }, token);
  const all = agents.data?.items ?? [];
  const skillList = skills.data?.items ?? [];
  const taskRoute = new Set(skillList.filter((s) => s.task_route === "TASKS").map((s) => s.id));
  return {
    agents: all.filter((a) => a.enabled && taskRoute.has(a.skill_id)),
    skills: skillList,
    loading: agents.loading || skills.loading,
  };
}

function EvidencePicker({
  isin,
  selection,
  onChange,
}: {
  isin: string;
  selection: ContextSelection;
  onChange: (s: ContextSelection) => void;
}) {
  const { investorId, token } = useResearchAuth();
  const notes = useFetch<Page<Note>>(investorId ? paths.companyNotes(investorId, isin) : null, { limit: 100 }, token);
  const sources = useFetch<Page<Source>>(investorId ? paths.companySources(investorId, isin) : null, { limit: 100 }, token);
  const facts = useFetch<Page<Fact>>(investorId ? paths.companyFacts(investorId, isin) : null, { limit: 100 }, token);

  function toggle(field: "note_ids" | "source_ids" | "fact_ids", id: string) {
    const current = selection[field];
    onChange({ ...selection, [field]: current.includes(id) ? current.filter((x) => x !== id) : [...current, id] });
  }

  const group = (label: string, field: "note_ids" | "source_ids" | "fact_ids", rows: { id: string; label: string }[]) => (
    <fieldset className="ws-fieldset">
      <legend className="ws-field-label">{label}</legend>
      {rows.length === 0 && <span className="ws-muted">none saved</span>}
      {rows.map((r) => (
        <label key={r.id} className="ws-check">
          <input type="checkbox" checked={selection[field].includes(r.id)} onChange={() => toggle(field, r.id)} />{" "}
          {r.label}
        </label>
      ))}
    </fieldset>
  );

  return (
    <div>
      {group("Notes", "note_ids", (notes.data?.items ?? []).map((n) => ({ id: n.id, label: `${n.title} (${n.written_on})` })))}
      {group(
        "Sources",
        "source_ids",
        (sources.data?.items ?? []).map((s) => ({ id: s.id, label: `${s.source} · ${s.source_type.toLowerCase()} (${s.content.state.toLowerCase()})` }))
      )}
      {group(
        "Facts",
        "fact_ids",
        (facts.data?.items ?? []).map((f) => ({ id: f.id, label: `${f.metric} ${f.period_end} · ${f.verification.toLowerCase()}` }))
      )}
      <p className="ws-muted">
        Source text is sent to a model only where disclosure is approved for that source type; otherwise
        the packet carries the citation metadata and says the text was withheld.
      </p>
    </div>
  );
}

function CreateTaskForm({
  isin,
  thesisId,
  agents,
  onCreated,
}: {
  isin: string;
  thesisId: string | null;
  agents: Agent[];
  onCreated: (t: Task) => void;
}) {
  const { investorId, token } = useResearchAuth();
  const [purpose, setPurpose] = useState<"RESEARCH" | "INLINE" | "ANSWER_REVIEW">("RESEARCH");
  const [title, setTitle] = useState("");
  const [brief, setBrief] = useState("");
  const [agentKey, setAgentKey] = useState("");
  const [answerId, setAnswerId] = useState("");
  const [pinThesis, setPinThesis] = useState(Boolean(thesisId));
  const [selection, setSelection] = useState<ContextSelection>(emptySelection(thesisId));
  const questions = useFetch<Page<Question>>(
    investorId && purpose === "ANSWER_REVIEW" ? paths.questions(investorId) : null,
    { isin, status: "ANSWERED", limit: 100 },
    token
  );
  const { submit, pending, error } = useSubmit<Task>();
  const agent = agents.find((a) => `${a.id}:${a.version}` === agentKey) ?? null;

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!agent) return;
    const body = {
      isin,
      purpose,
      title,
      brief,
      agent_id: agent.id,
      agent_version: agent.version,
      skill_id: agent.skill_id,
      skill_version: agent.skill_version,
      thesis_id: pinThesis ? thesisId : null,
      answer_id: purpose === "ANSWER_REVIEW" ? answerId || null : null,
      parent_task_id: null,
      context_selection: { ...selection, expected_thesis_id: thesisId },
    };
    const saved = await submit(body, (key) => rwrite.createTask({ investorId, token, idempotencyKey: key }, body));
    if (saved) onCreated(saved);
  }

  if (agents.length === 0) {
    return (
      <p className="ws-notice">
        No enabled agent is configured for a research method yet. Publish a method on the Skills page, then
        configure an agent on the Agents page.
      </p>
    );
  }

  return (
    <form className={`ws-form${pending ? " ws-pending" : ""}`} onSubmit={create}>
      <div className="ws-form-row">
        <label className="ws-field">
          <span className="ws-field-label">Purpose</span>
          <select className="ws-input" value={purpose} onChange={(e) => setPurpose(e.target.value as typeof purpose)}>
            <option value="RESEARCH">research</option>
            <option value="INLINE">note proposal</option>
            <option value="ANSWER_REVIEW">review my own answer</option>
          </select>
        </label>
        <label className="ws-field">
          <span className="ws-field-label">Agent</span>
          <select className="ws-input" value={agentKey} onChange={(e) => setAgentKey(e.target.value)} required>
            <option value="">choose…</option>
            {agents.map((a) => (
              <option key={`${a.id}:${a.version}`} value={`${a.id}:${a.version}`}>
                {a.name} · {a.model} (v{a.version})
              </option>
            ))}
          </select>
        </label>
      </div>
      {purpose === "ANSWER_REVIEW" && (
        <label className="ws-field">
          <span className="ws-field-label">Which of your answers</span>
          <select className="ws-input" value={answerId} onChange={(e) => setAnswerId(e.target.value)} required>
            <option value="">choose…</option>
            {(questions.data?.items ?? [])
              .filter((q) => q.latest_answer)
              .map((q) => (
                <option key={q.latest_answer!.id} value={q.latest_answer!.id}>
                  {q.text.slice(0, 80)}
                </option>
              ))}
          </select>
          <span className="ws-field-hint">Only an answer you already wrote can be reviewed. The review never edits or closes it.</span>
        </label>
      )}
      <label className="ws-field">
        <span className="ws-field-label">Title</span>
        <input className="ws-input" value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>
      <label className="ws-field">
        <span className="ws-field-label">Brief</span>
        <textarea className="ws-input" rows={3} value={brief} onChange={(e) => setBrief(e.target.value)} required />
      </label>
      {thesisId && (
        <label className="ws-check">
          <input type="checkbox" checked={pinThesis} onChange={(e) => setPinThesis(e.target.checked)} /> Pin the
          commitment in force (required for thesis validation)
        </label>
      )}
      <EvidencePicker isin={isin} selection={selection} onChange={setSelection} />
      <button type="submit" className="ws-btn ws-btn--primary" disabled={pending || !agent}>
        Seal task (no model is called)
      </button>
      {error && <p className="ws-notice ws-notice--error">{describeError(error)}</p>}
    </form>
  );
}

export function TasksPanel({ isin, thesisId }: { isin: string; thesisId: string | null }) {
  const { investorId, token } = useResearchAuth();
  const { agents } = useTaskAgents();
  const allAgents = useAgents().data?.items ?? [];
  const tasks = useFetch<Page<Task>>(investorId ? rpaths.tasks(investorId) : null, { isin, limit: 50 }, token);
  const [open, setOpen] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const list = (tasks.data?.items ?? []).filter((t) => t.purpose !== "CHAT");

  return (
    <div>
      <div className="ws-sechead">
        <h2>Tasks</h2>
        <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => setCreating(!creating)}>
          {creating ? "Close" : "New task"}
        </button>
      </div>
      {creating && (
        <CreateTaskForm
          isin={isin}
          thesisId={thesisId}
          agents={agents}
          onCreated={(t) => {
            setCreating(false);
            setOpen(t.id);
            tasks.refetch();
          }}
        />
      )}
      {list.length === 0 && !creating && <div className="ws-empty">No tasks for this company yet.</div>}
      {list.map((t) => (
        <div key={t.id}>
          <button type="button" className="ws-row ws-row--button" onClick={() => setOpen(open === t.id ? null : t.id)}>
            <span className="ws-row-grow">
              <span className="ws-row-t">{t.title}</span>
              <span className="ws-row-m">
                {t.purpose.toLowerCase().replace("_", " ")} · {new Date(t.created_at).toLocaleString()}
                {t.sample ? " · stored sample" : ""}
              </span>
            </span>
            <span className="ws-chip">{t.state}</span>
          </button>
          {open === t.id && <TaskView taskId={t.id} agents={allAgents} onChanged={tasks.refetch} />}
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------------------------
// Ask -- grounded chat
// ------------------------------------------------------------------------------------

function Messages({ threadId, agents }: { threadId: string; agents: Agent[] }) {
  const { investorId, token } = useResearchAuth();
  const msgs = useFetch<Page<ChatMessage>>(investorId ? rpaths.messages(investorId, threadId) : null, { limit: 100 }, token);
  const [openTask, setOpenTask] = useState<string | null>(null);
  return (
    <div>
      {(msgs.data?.items ?? []).map((m) => (
        <div key={m.id} className={`ws-chat-msg ws-chat-msg--${m.role.toLowerCase()}`}>
          <div className="ws-field-label">
            {m.role === "HUMAN" ? "You" : m.role === "REFUSAL" ? "Refused before any model call" : "Checked proposal"}
            {m.sample ? " · stored sample" : ""}
            {m.guardrail_status ? ` · guardrails ${m.guardrail_status}` : ""}
            {m.review_decision ? ` · ${m.review_decision.toLowerCase()}ed` : ""}
          </div>
          {m.role === "ASSISTANT" ? (
            m.rendered ? <RenderedResult rendered={m.rendered} /> : <p className="ws-muted">Not renderable.</p>
          ) : (
            <p style={{ whiteSpace: "pre-wrap" }}>{m.body}</p>
          )}
          {m.task_id && (
            <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => setOpenTask(openTask === m.task_id ? null : m.task_id)}>
              {m.role === "HUMAN" ? "Run / review this turn" : "Review"}
            </button>
          )}
          {openTask === m.task_id && m.task_id && (
            <TaskView taskId={m.task_id} agents={agents} onChanged={msgs.refetch} />
          )}
        </div>
      ))}
    </div>
  );
}

export function AskPanel({ isin, thesisId }: { isin: string; thesisId: string | null }) {
  const { investorId, token } = useResearchAuth();
  const { agents } = useTaskAgents();
  const allAgents = useAgents().data?.items ?? [];
  const threads = useFetch<Page<Thread>>(investorId ? rpaths.chats(investorId) : null, { isin, limit: 50 }, token);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [agentKey, setAgentKey] = useState("");
  const [selection, setSelection] = useState<ContextSelection>(emptySelection(thesisId));
  const [refusal, setRefusal] = useState<string | null>(null);
  const newThread = useSubmit<Thread>();
  const turn = useSubmit<unknown>();
  const agent = agents.find((a) => `${a.id}:${a.version}` === agentKey) ?? null;
  const [msgKey, setMsgKey] = useState(0);

  async function createThread(e: React.FormEvent) {
    e.preventDefault();
    const saved = await newThread.submit({ title }, (key) =>
      rwrite.createThread({ investorId, token, idempotencyKey: key }, isin, title)
    );
    if (saved) {
      setThreadId(saved.id);
      setTitle("");
      threads.refetch();
    }
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!agent || !threadId) return;
    setRefusal(null);
    const body = {
      text,
      agent_id: agent.id,
      agent_version: agent.version,
      skill_id: agent.skill_id,
      skill_version: agent.skill_version,
      context_selection: { ...selection, expected_thesis_id: thesisId },
    };
    const out = (await turn.submit(body, (key) =>
      rwrite.turn({ investorId, token, idempotencyKey: key }, threadId, body)
    )) as { refusal: { message: string } | null } | null;
    if (out) {
      setText("");
      if (out.refusal) setRefusal(out.refusal.message);
      setMsgKey((k) => k + 1);
    }
  }

  return (
    <div>
      <div className="ws-sechead">
        <h2>Ask</h2>
        <div className="ws-hint">each turn is a sealed task; answers appear only after checking</div>
      </div>
      <div className="ws-form-row">
        <select className="ws-input" value={threadId ?? ""} onChange={(e) => setThreadId(e.target.value || null)}>
          <option value="">choose a conversation…</option>
          {(threads.data?.items ?? []).map((t) => (
            <option key={t.id} value={t.id}>
              {t.title} ({t.messages})
            </option>
          ))}
        </select>
        <form className="ws-form-row" onSubmit={createThread}>
          <input className="ws-input" placeholder="New conversation title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <button type="submit" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={!title.trim() || newThread.pending}>
            Start
          </button>
        </form>
      </div>
      {threadId && (
        <>
          <Messages key={`${threadId}-${msgKey}`} threadId={threadId} agents={allAgents} />
          <form className="ws-form" onSubmit={send}>
            <select className="ws-input" value={agentKey} onChange={(e) => setAgentKey(e.target.value)} required>
              <option value="">agent…</option>
              {agents.map((a) => (
                <option key={`${a.id}:${a.version}`} value={`${a.id}:${a.version}`}>
                  {a.name} · {a.model}
                </option>
              ))}
            </select>
            <details>
              <summary className="ws-field-label">Evidence for this turn</summary>
              <EvidencePicker isin={isin} selection={selection} onChange={setSelection} />
            </details>
            <textarea className="ws-input" rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about the selected evidence" />
            <button type="submit" className="ws-btn ws-btn--primary" disabled={!text.trim() || !agent || turn.pending}>
              Send (seals a task; run it from the turn)
            </button>
            {refusal && <p className="ws-notice">{refusal}</p>}
            {turn.error && <p className="ws-notice ws-notice--error">{describeError(turn.error)}</p>}
          </form>
        </>
      )}
    </div>
  );
}
