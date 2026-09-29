"use client";

/**
 * Monitors (FE 18 over BE 36-37): saved schedules, their due moments and an immutable history.
 *
 * EVERYTHING ON THIS SCREEN IS A PERSISTED SERVER RECORD. No timer makes a schedule "fire", no
 * sample run is shown, and no row is synthesised to fill the layout. The server's tick records
 * due occurrences; this page reads them.
 *
 * BE-Q01 IS OPEN, AND THE SCREEN SAYS SO WHERE THE DECISION IS MADE. A saved schedule is shown as
 * "Saved · execution not available", never as active or running, and every recorded occurrence
 * says why nothing ran. Blocked (the gate), event-blocked (the evidence failed a check),
 * superseded (the thesis moved on) and -- once BE 38 exists -- queued, failed and completed are
 * rendered as different facts with different labels. "Nothing ran" is never shown as "nothing
 * changed".
 *
 * Controls are only the ones the API allows: create, and new versions (pause, resume, rebind to
 * the thesis in force). A manual run is not offered because the server refuses it (409
 * EXECUTION_POLICY_UNRESOLVED); pausing does not erase history.
 */

import Link from "next/link";
import { useState } from "react";
import { ApiError, useFetch } from "@trackr/core";
import { paths, type CompanyListItem, type Page, type Thesis } from "@/lib/research-api";
import { rpaths, type Agent } from "@/lib/research-client";
import {
  inIst,
  inputOf,
  istLocalToInstant,
  KIND_LABEL,
  mpaths,
  mwrite,
  RUN_STATE,
  SCHEDULE_STATE,
  WATCH_STATE,
  type MonitorKind,
  type MonitorRun,
  type MonitorSchedule,
  type ScheduleInput,
} from "@/lib/monitor-client";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";

function explain(error: ApiError | Error | null): string | null {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "TIMEZONE_UNSUPPORTED":
        return "Only Asia/Kolkata schedules are supported.";
      case "NO_COMMITMENT_IN_FORCE":
      case "STALE_PREDECESSOR":
      case "COMMITMENT_CONFLICT":
        return "An enabled monitor must watch the thesis version in force now. Choose that version, or save it paused.";
      case "VERSION_CONFLICT":
        return "This monitor was changed elsewhere first. Reload before changing it again.";
      case "MONITORS_UNAVAILABLE":
        return "Monitor storage is not installed on this server yet.";
      case "EXECUTION_POLICY_UNRESOLVED":
        return "Monitor runs are not available: how a scheduled model check runs is an open decision (BE-Q01).";
    }
  }
  return describeError(error);
}

function Chip({ tone, children }: { tone: string; children: React.ReactNode }) {
  return <span className={`ws-chip ws-chip--${tone}`}>{children}</span>;
}

function cadence(s: MonitorSchedule): string {
  if (s.kind !== "SCHEDULED") return KIND_LABEL[s.kind];
  const every = s.interval_days === 1 ? "every day" : `every ${s.interval_days} days`;
  return `${every} at ${inIst(s.starts_at).split(", ").pop()}`;
}

// --- create ------------------------------------------------------------------------------------

function NewMonitor({ onSaved }: { onSaved: () => void }) {
  const { investorId, token } = useResearchAuth();
  const companies = useFetch<Page<CompanyListItem>>(investorId ? paths.companies(investorId) : null, { limit: 100 }, token);
  const agents = useFetch<Page<Agent>>(investorId ? rpaths.agents(investorId) : null, { limit: 100 }, token);
  const [isin, setIsin] = useState("");
  const theses = useFetch<Page<Thesis>>(investorId && isin ? paths.companyTheses(investorId, isin) : null, { limit: 100 }, token);
  const [thesisId, setThesisId] = useState("");
  const [agentKey, setAgentKey] = useState("");
  const [kind, setKind] = useState<MonitorKind>("SCHEDULED");
  const [startsLocal, setStartsLocal] = useState("");
  const [interval, setIntervalDays] = useState(7);
  const [enabled, setEnabled] = useState(true);
  const { submit, pending, error } = useSubmit<MonitorSchedule>();

  const unlocked = (companies.data?.items ?? []).filter((c) => c.ritual_complete);
  const active = (theses.data?.items ?? []).filter((t) => t.status === "ACTIVE");
  const agentList = (agents.data?.items ?? []).filter((a) => a.enabled);
  const agent = agentList.find((a) => `${a.id}:${a.version}` === agentKey);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!agent || !thesisId || !startsLocal) return;
    const input: ScheduleInput = {
      thesis_id: thesisId,
      skill_id: agent.skill_id,
      skill_version: agent.skill_version,
      agent_id: agent.id,
      agent_version: agent.version,
      kind,
      timezone: "Asia/Kolkata",
      starts_at: istLocalToInstant(startsLocal),
      interval_days: kind === "SCHEDULED" ? interval : null,
      enabled,
    };
    const saved = await submit({ isin, input }, (key) =>
      mwrite.create({ investorId, token, idempotencyKey: key }, isin, input)
    );
    if (saved) onSaved();
  }

  return (
    <form className={`ws-form${pending ? " ws-pending" : ""}`} onSubmit={save}>
      <div className="ws-form-row">
        <label className="ws-field">
          <span className="ws-field-label">Company (one you have opened with your own questions)</span>
          <select className="ws-input" value={isin} onChange={(e) => { setIsin(e.target.value); setThesisId(""); }} required>
            <option value="">choose…</option>
            {unlocked.map((c) => (
              <option key={c.isin} value={c.isin}>
                {c.symbol ?? c.isin} · {c.name ?? ""}
              </option>
            ))}
          </select>
        </label>
        <label className="ws-field">
          <span className="ws-field-label">Thesis version to watch</span>
          <select className="ws-input" value={thesisId} onChange={(e) => setThesisId(e.target.value)} required disabled={!isin}>
            <option value="">choose…</option>
            {active.map((t) => (
              <option key={t.id} value={t.id}>
                v{t.version} · {t.version_on}
              </option>
            ))}
          </select>
          {isin && theses.data && active.length === 0 && (
            <span className="ws-field-hint">No active thesis for this company. A monitor watches a commitment you have made.</span>
          )}
        </label>
      </div>
      <div className="ws-form-row">
        <label className="ws-field">
          <span className="ws-field-label">Agent (and the exact method version it runs)</span>
          <select className="ws-input" value={agentKey} onChange={(e) => setAgentKey(e.target.value)} required>
            <option value="">choose…</option>
            {agentList.map((a) => (
              <option key={`${a.id}:${a.version}`} value={`${a.id}:${a.version}`}>
                {a.name} v{a.version}
              </option>
            ))}
          </select>
        </label>
        <label className="ws-field">
          <span className="ws-field-label">When</span>
          <select className="ws-input" value={kind} onChange={(e) => setKind(e.target.value as MonitorKind)}>
            <option value="SCHEDULED">{KIND_LABEL.SCHEDULED}</option>
            <option value="POST_RESULTS">{KIND_LABEL.POST_RESULTS}</option>
            <option value="POST_CONCALL">{KIND_LABEL.POST_CONCALL}</option>
          </select>
        </label>
      </div>
      <div className="ws-form-row">
        <label className="ws-field">
          <span className="ws-field-label">{kind === "SCHEDULED" ? "First check (Asia/Kolkata wall time)" : "Watch from (Asia/Kolkata)"}</span>
          <input className="ws-input ws-mono" type="datetime-local" value={startsLocal} onChange={(e) => setStartsLocal(e.target.value)} required />
          <span className="ws-field-hint">The wall time is kept across every interval; it does not drift.</span>
        </label>
        {kind === "SCHEDULED" ? (
          <label className="ws-field">
            <span className="ws-field-label">Every (days)</span>
            <input className="ws-input ws-mono" type="number" min={1} max={366} value={interval} onChange={(e) => setIntervalDays(Number(e.target.value))} required />
          </label>
        ) : (
          <p className="ws-muted" style={{ alignSelf: "end" }}>
            Fires only on an event you have verified: exact type, this company&apos;s verified identifiers, an exact period and
            an approved source. Claims, dates and price moves never count.
          </p>
        )}
      </div>
      <label className="ws-check">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Enabled (records due moments; it
        does not make anything run while BE-Q01 is open)
      </label>
      <button type="submit" className="ws-btn ws-btn--primary" disabled={pending || !agent}>
        Save monitor
      </button>
      {error && <p className="ws-notice ws-notice--error">{explain(error)}</p>}
    </form>
  );
}

// --- history -----------------------------------------------------------------------------------

function RunRow({ run }: { run: MonitorRun }) {
  const st = RUN_STATE[run.display_state];
  return (
    <div className="ws-row">
      <span className="ws-row-grow">
        <span className="ws-row-t">
          {run.event?.event_date ? `Event of ${run.event.event_date}` : `Due ${inIst(run.due_at)}`}
          <span className="ws-muted"> · version {run.schedule_version}</span>
          {run.recorded_late && <span className="ws-muted"> · recorded {Math.round(run.recorded_after_due_seconds / 60)} min late</span>}
        </span>
        {run.event && (
          <span className="ws-row-m ws-mono">
            {run.event.event_type} · period {run.event.period_start} → {run.event.period_end} ·{" "}
            <Link href={`/research/companies/${run.isin}?mode=evidence`}>source</Link>
          </span>
        )}
        {run.blocked_reason && <span className="ws-row-m">{run.blocked_reason}</span>}
        {run.task_id && (
          <span className="ws-row-m">
            <Link href={`/research/companies/${run.isin}?mode=tasks`}>Open task</Link>
            {run.task_state ? ` · ${run.task_state}` : ""}
          </span>
        )}
      </span>
      <Chip tone={st.tone}>{st.label}</Chip>
    </div>
  );
}

function History({ schedule }: { schedule: MonitorSchedule }) {
  const { investorId, token } = useResearchAuth();
  const [cursor, setCursor] = useState<string | null>(null);
  const runs = useFetch<Page<MonitorRun>>(investorId ? mpaths.runs(investorId, schedule.id) : null, { limit: 50, cursor: cursor ?? undefined }, token);
  const items = runs.data?.items ?? [];
  return (
    <div className="ws-panel" style={{ marginTop: 8 }}>
      {runs.errorDetail && <p className="ws-notice ws-notice--error">{explain(runs.errorDetail)}</p>}
      {items.length === 0 && !runs.loading && (
        <div className="ws-empty">No due moment has been recorded yet. Nothing has run.</div>
      )}
      {items.map((r) => (
        <RunRow key={r.id} run={r} />
      ))}
      {runs.data?.next_cursor && (
        <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => setCursor(runs.data!.next_cursor)}>
          Older
        </button>
      )}
    </div>
  );
}

// --- one schedule --------------------------------------------------------------------------------

function ScheduleCard({ s, onChanged }: { s: MonitorSchedule; onChanged: () => void }) {
  const { investorId, token } = useResearchAuth();
  const { submit, pending, error } = useSubmit<MonitorSchedule>();
  const [open, setOpen] = useState(false);
  const st = SCHEDULE_STATE[s.display_state];

  async function newVersion(change: Partial<ScheduleInput>) {
    const input = { ...inputOf(s), ...change };
    const saved = await submit({ id: s.id, v: s.version, input }, (key) =>
      mwrite.appendVersion({ investorId, token, idempotencyKey: key }, s.id, input, s.version)
    );
    if (saved) onChanged();
  }

  return (
    <div className={`ws-panel${pending ? " ws-pending" : ""}`}>
      <div className="ws-row">
        <span className="ws-row-grow">
          <span className="ws-row-t">
            <Link href={`/research/companies/${s.isin}?mode=thesis`} className="ws-mono">{s.isin}</Link>{" "}
            <span className="ws-muted">· {cadence(s)} · version {s.version}</span>
          </span>
          <span className="ws-row-m">
            {s.kind === "SCHEDULED"
              ? s.enabled
                ? `Next due moment ${inIst(s.next_due_at)} — it will be recorded, not run.`
                : "Paused: no due moments are recorded. History is kept."
              : s.event_watch
                ? `${WATCH_STATE[s.event_watch.state]} · watching from ${s.event_watch.watching_from}`
                : ""}
          </span>
          <span className="ws-row-m ws-muted">
            {s.occurrences.total} recorded · {s.occurrences.executed} executed · {s.occurrences.blocked_execution_policy} blocked
            by BE-Q01 · {s.occurrences.blocked_event} event-blocked · {s.occurrences.superseded_thesis} superseded
          </span>
        </span>
        <Chip tone={st.tone}>{st.label}</Chip>
      </div>

      {s.display_state === "NEEDS_REBIND" && (
        <p className="ws-notice">
          This monitor watches a thesis version that is no longer your commitment in force
          {s.commitment.state === "CONFLICT" ? " (verified identifiers hold more than one active commitment)" : ""}. It will not
          be switched for you.
        </p>
      )}

      {s.event_watch && s.event_watch.pending.length > 0 && (
        <div className="ws-panel">
          {s.event_watch.pending.map((p) => (
            <div key={p.event_id} className="ws-row">
              <span className="ws-row-grow">
                <span className="ws-row-t ws-mono">{p.identity ?? "period unknown"}</span>
                <span className="ws-row-m">{p.reason}</span>
              </span>
              <Link href={`/research/companies/${s.isin}?mode=evidence`} className="ws-btn ws-btn--ghost ws-btn--sm">
                Evidence
              </Link>
            </div>
          ))}
        </div>
      )}

      <div className="ws-form-row">
        <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={pending} onClick={() => newVersion({ enabled: !s.enabled })}>
          {s.enabled ? "Pause" : "Resume"}
        </button>
        {s.display_state === "NEEDS_REBIND" && s.commitment.state === "ACTIVE" && s.commitment.in_force_thesis_id && (
          <button
            type="button"
            className="ws-btn ws-btn--ghost ws-btn--sm"
            disabled={pending}
            onClick={() => newVersion({ thesis_id: s.commitment.in_force_thesis_id! })}
          >
            Rebind to the thesis in force
          </button>
        )}
        <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => setOpen(!open)}>
          {open ? "Hide history" : "History"}
        </button>
        <span className="ws-muted" title={s.execution_policy_reason}>
          Manual run: not available (BE-Q01)
        </span>
      </div>
      {error && <p className="ws-notice ws-notice--error">{explain(error)}</p>}
      {open && <History schedule={s} />}
    </div>
  );
}

// --- page ------------------------------------------------------------------------------------------

export default function Monitors() {
  const { investorId, token } = useResearchAuth();
  const [cursor, setCursor] = useState<string | null>(null);
  const list = useFetch<Page<MonitorSchedule>>(investorId ? mpaths.monitors(investorId) : null, { limit: 50, cursor: cursor ?? undefined }, token);
  const [creating, setCreating] = useState(false);
  const items = list.data?.items ?? [];
  const gate = items[0]?.execution_policy_reason;

  return (
    <div>
      <div className="ws-crumb">Research &middot; Monitors</div>
      <h1 className="ws-h1">Monitors</h1>
      <p className="ws-sub">Scheduled and event-driven checks against a thesis you committed to, with a history that is never rewritten.</p>

      <div className="ws-panel" style={{ maxWidth: 760 }}>
        <div className="ws-row">
          <span className="ws-row-grow">
            <span className="ws-row-t">Monitors are saved and their due moments recorded. Nothing runs yet.</span>
            <span className="ws-row-m">
              {gate ??
                "No supported way exists yet to run a scheduled model check while your provider key stays in your browser (open decision BE-Q01)."}{" "}
              Every recorded moment says why nothing ran; none is shown as a completed check.
            </span>
          </span>
          <Chip tone="warn">Execution unavailable</Chip>
        </div>
      </div>

      {list.errorDetail && <p className="ws-notice ws-notice--error">{explain(list.errorDetail)}</p>}
      <div className="ws-sechead">
        <h2>Schedules</h2>
        <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => setCreating(!creating)}>
          {creating ? "Close" : "New monitor"}
        </button>
      </div>
      {creating && (
        <NewMonitor
          onSaved={() => {
            setCreating(false);
            list.refetch();
          }}
        />
      )}
      {items.length === 0 && !list.loading && !creating && (
        <div className="ws-empty">No monitors. A monitor watches an active thesis; publish one on a company&apos;s Thesis tab first.</div>
      )}
      {items.map((s) => (
        <ScheduleCard key={s.id} s={s} onChanged={list.refetch} />
      ))}
      {list.data?.next_cursor && (
        <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => setCursor(list.data!.next_cursor)}>
          More
        </button>
      )}
    </div>
  );
}
