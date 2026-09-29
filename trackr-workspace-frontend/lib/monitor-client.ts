/**
 * Typed client for monitor schedules and their due history (BE 36-37; `contracts/openapi.yaml`
 * tag `monitors`). Types mirror `trackr-backend/app/schemas/monitors.py`.
 *
 * WORKSPACE ONLY. Plus must never import this file.
 *
 * WHAT THE SERVER PROMISES, AND WHAT IT DOES NOT. While BE-Q01 is open, a schedule is saved and
 * its due moments are recorded, but nothing is executed: every occurrence is
 * BLOCKED_EXECUTION_POLICY, SUPERSEDED_THESIS or BLOCKED_EVENT with a stated reason. There is no
 * "run now" call here that could succeed -- `requestRun` exists so the refusal can be shown
 * truthfully, and it always answers 409 EXECUTION_POLICY_UNRESOLVED today.
 *
 * NO TIMERS, NO KEEPALIVE. The due clock is the server's tick; this file never polls to make a
 * schedule "fire", never asks a model anything, and never touches a provider key.
 */

import { api } from "@trackr/core";
import { wsBase, type Page } from "./research-api";

const enc = encodeURIComponent;

export type MonitorKind = "SCHEDULED" | "POST_RESULTS" | "POST_CONCALL";
export type Disposition = "QUEUED" | "BLOCKED_EXECUTION_POLICY" | "BLOCKED_EVENT" | "SUPERSEDED_THESIS";
export type RunDisplayState =
  | "BLOCKED_EXECUTION_POLICY"
  | "EVENT_MATCHED_EXECUTION_BLOCKED"
  | "EVENT_BLOCKED"
  | "SUPERSEDED_THESIS"
  | "QUEUED"
  | "EVENT_MATCHED_QUEUED"
  | "RUNNING"
  | "AWAITING_REVIEW"
  | "REVIEWED"
  | "FAILED"
  | "COMPLETED";
export type ScheduleDisplayState = "PAUSED" | "NEEDS_REBIND" | "SAVED_EXECUTION_BLOCKED";
export type EventWatchState = "NO_QUALIFYING_EVENT" | "EVENT_AWAITING_VERIFICATION" | "EVENT_UNVERIFIABLE";

export interface RunEvent {
  event_id: string;
  identity: string;
  event_type: string | null;
  event_date: string | null;
  period_start: string | null;
  period_end: string | null;
  source_id: string | null;
  verification: string | null;
  status: string | null;
}

export interface MonitorRun {
  id: string;
  isin: string;
  schedule_id: string;
  schedule_version: number;
  thesis_id: string;
  due_at: string;
  recorded_at: string;
  disposition: Disposition;
  blocked_reason: string | null;
  task_id: string | null;
  task_state: string | null;
  report_id: string | null;
  display_state: RunDisplayState;
  recorded_late: boolean;
  recorded_after_due_seconds: number;
  /** False unless a task exists. Always false while BE-Q01 is open. */
  executed: boolean;
  event: RunEvent | null;
}

export interface PendingEvent {
  event_id: string;
  identity: string | null;
  code: string;
  reason: string;
}

export interface MonitorSchedule {
  id: string;
  version: number;
  isin: string;
  thesis_id: string;
  skill_id: string;
  skill_version: number;
  agent_id: string;
  agent_version: number;
  kind: MonitorKind;
  timezone: string;
  starts_at: string;
  interval_days: number | null;
  enabled: boolean;
  actor_uid: string;
  recorded_at: string;
  created_at: string;
  versions: number;
  execution_policy_status: "EXECUTION_POLICY_UNRESOLVED";
  execution_policy_reason: string;
  commitment: { state: "ACTIVE" | "NONE" | "CONFLICT"; in_force_thesis_id: string | null; pinned_is_in_force: boolean };
  display_state: ScheduleDisplayState;
  next_due_at: string | null;
  occurrences: {
    total: number;
    executed: number;
    blocked_execution_policy: number;
    blocked_event: number;
    superseded_thesis: number;
  };
  latest_run: MonitorRun | null;
  event_watch: {
    event_type: string;
    state: EventWatchState;
    pending: PendingEvent[];
    awaiting_tick: number;
    watching_from: string;
  } | null;
}

export interface RunDetail {
  run: MonitorRun;
  task: Record<string, unknown> | null;
  report: { id: string; title: string; lede: string; recorded_at: string } | null;
}

/** ScheduleCreateIn. Built field by field so nothing else can ride along in the payload. */
export interface ScheduleInput {
  thesis_id: string;
  skill_id: string;
  skill_version: number;
  agent_id: string;
  agent_version: number;
  kind: MonitorKind;
  timezone: "Asia/Kolkata";
  starts_at: string;
  interval_days: number | null;
  enabled: boolean;
}

export function scheduleBody(i: ScheduleInput): ScheduleInput {
  return {
    thesis_id: i.thesis_id,
    skill_id: i.skill_id,
    skill_version: i.skill_version,
    agent_id: i.agent_id,
    agent_version: i.agent_version,
    kind: i.kind,
    timezone: i.timezone,
    starts_at: i.starts_at,
    interval_days: i.kind === "SCHEDULED" ? i.interval_days : null,
    enabled: i.enabled,
  };
}

/** A schedule's current configuration as a new-version input, for pause/resume/rebind. */
export function inputOf(s: MonitorSchedule): ScheduleInput {
  return {
    thesis_id: s.thesis_id,
    skill_id: s.skill_id,
    skill_version: s.skill_version,
    agent_id: s.agent_id,
    agent_version: s.agent_version,
    kind: s.kind,
    timezone: "Asia/Kolkata",
    starts_at: s.starts_at,
    interval_days: s.interval_days,
    enabled: s.enabled,
  };
}

export const mpaths = {
  monitors: (inv: string) => `${wsBase(inv)}/monitors`,
  runs: (inv: string, scheduleId: string) => `${wsBase(inv)}/monitors/${enc(scheduleId)}/runs`,
  run: (inv: string, runId: string) => `${wsBase(inv)}/monitor-runs/${enc(runId)}`,
};

interface WriteCtx {
  investorId: string;
  token: string | null;
  idempotencyKey: string;
}

function post<T>(ctx: WriteCtx, path: string, json: unknown): Promise<T> {
  return api.post<T>(path, { token: ctx.token, json, headers: { "Idempotency-Key": ctx.idempotencyKey } });
}

export const mwrite = {
  create: (ctx: WriteCtx, isin: string, input: ScheduleInput) =>
    post<MonitorSchedule>(ctx, `${wsBase(ctx.investorId)}/companies/${enc(isin)}/monitors`, scheduleBody(input)),
  appendVersion: (ctx: WriteCtx, scheduleId: string, input: ScheduleInput, expectedVersion: number) =>
    post<MonitorSchedule>(ctx, `${wsBase(ctx.investorId)}/monitors/${enc(scheduleId)}/versions`, {
      ...scheduleBody(input),
      expected_version: expectedVersion,
    }),
  /** Always 409 EXECUTION_POLICY_UNRESOLVED while BE-Q01 is open. */
  requestRun: (ctx: WriteCtx, scheduleId: string, scheduleVersion: number) =>
    post<MonitorRun>(ctx, mpaths.runs(ctx.investorId, scheduleId), { schedule_version: scheduleVersion }),
};

// --- presentation ------------------------------------------------------------------------------

/** An instant shown in the schedule's own zone, labelled, so 09:00 reads as 09:00 IST. */
export function inIst(instant: string | null): string {
  if (!instant) return "—";
  return (
    new Intl.DateTimeFormat("en-IN", {
      timeZone: "Asia/Kolkata",
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(instant)) + " IST"
  );
}

/** `datetime-local` value (IST wall time) -> ISO instant with the +05:30 offset. */
export function istLocalToInstant(local: string): string {
  return `${local.length === 16 ? `${local}:00` : local}+05:30`;
}

export const RUN_STATE: Record<RunDisplayState, { label: string; tone: string }> = {
  BLOCKED_EXECUTION_POLICY: { label: "Due · not run (BE-Q01)", tone: "warn" },
  EVENT_MATCHED_EXECUTION_BLOCKED: { label: "Event matched · not run (BE-Q01)", tone: "warn" },
  EVENT_BLOCKED: { label: "Event blocked", tone: "neg" },
  SUPERSEDED_THESIS: { label: "Thesis superseded · not run", tone: "mute" },
  QUEUED: { label: "Queued", tone: "open" },
  EVENT_MATCHED_QUEUED: { label: "Event matched · queued", tone: "open" },
  RUNNING: { label: "Running", tone: "open" },
  AWAITING_REVIEW: { label: "Awaiting your review", tone: "ink" },
  REVIEWED: { label: "Reviewed", tone: "ink" },
  FAILED: { label: "Failed", tone: "neg" },
  COMPLETED: { label: "Report published", tone: "pos" },
};

export const SCHEDULE_STATE: Record<ScheduleDisplayState, { label: string; tone: string }> = {
  PAUSED: { label: "Paused", tone: "mute" },
  NEEDS_REBIND: { label: "Needs rebinding", tone: "neg" },
  SAVED_EXECUTION_BLOCKED: { label: "Saved · execution not available", tone: "warn" },
};

export const WATCH_STATE: Record<EventWatchState, string> = {
  NO_QUALIFYING_EVENT: "No qualifying event yet",
  EVENT_AWAITING_VERIFICATION: "An event is waiting for your verification",
  EVENT_UNVERIFIABLE: "Only unverifiable claims held",
};

export const KIND_LABEL: Record<MonitorKind, string> = {
  SCHEDULED: "On a calendar",
  POST_RESULTS: "After verified results",
  POST_CONCALL: "After a verified earnings call",
};

export type { Page };
