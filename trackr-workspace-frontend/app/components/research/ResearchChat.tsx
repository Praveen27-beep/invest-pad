"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useAuth, useFetch } from "@trackr/core";
import { emptySelection, getContext, rpaths, rwrite, type ChatMessage, type ContextSelection, type Page, type Thread, type TurnOut } from "@/lib/research-client";
import { destinationAllowed, hasKey, runTask, scopeFor } from "@/lib/research-agent";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";
import { EvidencePicker, useTaskAgents } from "./TasksPanel";
import { RenderedResult, TaskView, useAgents } from "./TaskView";

/** The existing grounded conversation transport, with one explicit send-and-run action. */
export function ResearchChat({ isin, label, thesisId }: { isin: string; label: string; thesisId: string | null }) {
  const { investorId, token } = useResearchAuth();
  const { user } = useAuth();
  const available = useTaskAgents();
  const allAgents = useAgents();
  const threads = useFetch<Page<Thread>>(investorId ? rpaths.chats(investorId) : null, { isin, limit: 50 }, token);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [agentKey, setAgentKey] = useState("");
  const [selection, setSelection] = useState<ContextSelection>(emptySelection(thesisId));
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [review, setReview] = useState(false);
  const newThread = useSubmit<Thread>();
  const turn = useSubmit<TurnOut>();
  const messages = useFetch<Page<ChatMessage>>(threadId ? rpaths.messages(investorId, threadId) : null, { limit: 100 }, token);
  const agent = available.agents.find(a => `${a.id}:${a.version}` === agentKey) ?? available.agents[0];
  const scope = agent && user ? scopeFor(String(user.id), investorId, agent) : null;
  const keyReady = scope !== null && hasKey(scope);
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const sending = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; controller.current?.abort(); }; }, []);
  useEffect(() => { bottom.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [messages.data, status]);

  async function send(event: React.FormEvent) {
    event.preventDefault();
    if (!text.trim() || !agent || !scope || !keyReady || sending.current) return;
    sending.current = true;
    setBusy(true); setError(null); setStatus("Saving your question…");
    controller.current = new AbortController();
    try {
      let id = threadId;
      if (!id) {
        const saved = await newThread.submit({ isin, title: text.trim().slice(0, 80) }, key => rwrite.createThread({ investorId, token, idempotencyKey: key }, isin, text.trim().slice(0, 80)));
        if (!saved || !mounted.current) return;
        id = saved.id; setThreadId(id); threads.refetch();
      }
      if (!mounted.current || controller.current.signal.aborted) return;
      const body = { text: text.trim(), agent_id: agent.id, agent_version: agent.version, skill_id: agent.skill_id, skill_version: agent.skill_version, context_selection: { ...selection, expected_thesis_id: thesisId } };
      const out = await turn.submit({ thread: id, ...body }, key => rwrite.turn({ investorId, token, idempotencyKey: key }, id!, body));
      if (!out || !mounted.current) return;
      setText(""); messages.refetch(); threads.refetch();
      if (out.refusal) { setError(out.refusal.message); return; }
      if (!out.task) return;
      setTaskId(out.task.id);
      if (controller.current.signal.aborted) { setError("Question saved. Open its review to run it when you are ready."); return; }
      setStatus("Reading your selected evidence…");
      const packet = await getContext(investorId, token, out.task.id);
      if (!mounted.current || controller.current.signal.aborted) return;
      const result = await runTask({ investorId, token, agent, scope, task: out.task, packet, signal: controller.current.signal, onPhase: phase => { if(mounted.current) setStatus(phase === "submitting" ? "Checking the answer and citations…" : "Thinking…"); } });
      if (!mounted.current) return;
      if (result.kind === "FAILED" || result.kind === "UNCERTAIN") setError(result.message);
      if (result.kind === "CANCELLED") setError("Stopped. Your question is saved; you can resume from its review.");
      messages.refetch(); threads.refetch();
    } catch (err) { if(mounted.current) setError(describeError(err as Error) ?? "Could not complete this answer."); }
    finally { sending.current = false; if(mounted.current) { setBusy(false); setStatus(""); } }
  }
  return <div className="ip-chat">
    <div className="ip-chat-threadbar"><select aria-label="Conversation history" disabled={busy} value={threadId ?? ""} onChange={e => { setThreadId(e.target.value || null); setTaskId(null); setReview(false); setError(null); }}><option value="">New conversation</option>{threads.data?.items.map(t => <option key={t.id} value={t.id}>{t.title}</option>)}</select><button aria-label="New conversation" title="New conversation" disabled={busy} onClick={() => { setThreadId(null); setTaskId(null); setReview(false); setError(null); setText(""); }}>+</button></div>
    <div className="ip-chat-messages" aria-busy={busy}>
      {threads.error && <p className="ws-notice">Conversation history unavailable. <button onClick={threads.refetch}>Retry</button></p>}
      {!threadId && <div className="ip-chat-welcome"><span>✧</span><h2>Let’s explore {label}</h2><p>What would you like to understand?</p>{["Help me understand the business", "Challenge my investment thesis", "What evidence am I missing?"].map(q => <button key={q} className="ip-chat-suggestion" onClick={() => setText(q)}>{q}<span>↗</span></button>)}</div>}
      {messages.loading && <p role="status">Loading conversation…</p>}
      {messages.error && <p className="ws-notice">Could not load messages. <button onClick={messages.refetch}>Retry</button></p>}
      {messages.data?.items.map(m => <article key={m.id} className={`ip-message ip-message--${m.role.toLowerCase()}`}><div className="ip-message-meta">{m.role === "HUMAN" ? "You" : m.role === "REFUSAL" ? "Research assistant" : "✧ Research assistant"}<time dateTime={m.recorded_at}>{new Date(m.recorded_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></div>{m.role === "ASSISTANT" && m.rendered ? <RenderedResult rendered={m.rendered} /> : <p>{m.body}</p>}{m.task_id && <button className="ip-chat-review" onClick={() => { setTaskId(m.task_id); setReview(true); }}>Sources & review</button>}</article>)}
      {messages.data?.next_cursor && <p className="ws-hint">Showing the first 100 messages in this conversation.</p>}
      {busy && <p role="status" className="ip-chat-thinking">✧ {status}</p>}
      {(error || newThread.error || turn.error) && <p role="alert" className="ws-notice ws-notice--error">{error ?? describeError(newThread.error ?? turn.error)}</p>}
      {taskId && !busy && <details open={review} onToggle={e => setReview(e.currentTarget.open)}><summary className="ip-chat-review">Review answer or resume question</summary>{review && <TaskView taskId={taskId} agents={allAgents.data?.items ?? []} onChanged={messages.refetch} />}</details>}
      <div ref={bottom} />
    </div>
    <form className="ip-chat-compose" onSubmit={send}>
      <details><summary>＋ Sources <span>{selection.note_ids.length + selection.source_ids.length + selection.fact_ids.length || ""}</span></summary><div className="ip-chat-evidence"><EvidencePicker isin={isin} selection={selection} onChange={setSelection} /></div></details>
      {!available.loading && !agent && <p className="ip-chat-setup">Connect a research model to start. <Link href="/agents">Set up model →</Link></p>}
      {agent && !keyReady && <p className="ip-chat-setup">Add your model key for this session. <Link href="/agents">Connect model →</Link></p>}
      <textarea aria-label="Message research assistant" placeholder={`Ask about ${label}…`} rows={3} value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if(e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if(!busy) e.currentTarget.form?.requestSubmit(); } }} disabled={busy} />
      <div className="ip-chat-compose-foot"><select aria-label="Research model" value={agent ? `${agent.id}:${agent.version}` : ""} onChange={e => setAgentKey(e.target.value)} disabled={busy}><option value="" disabled>Choose model</option>{available.agents.map(a => <option key={`${a.id}:${a.version}`} value={`${a.id}:${a.version}`}>{a.name} · {a.model}</option>)}</select>{busy ? <button type="button" className="ip-send" aria-label="Stop response" onClick={() => controller.current?.abort()}>■</button> : <button className="ip-send" type="submit" aria-label="Send message" disabled={!text.trim() || !keyReady || !agent || !destinationAllowed(agent.base_url)}>↑</button>}</div>
      <small>Uses selected sources. Answers can be wrong; check citations.</small>
    </form>
  </div>;
}
