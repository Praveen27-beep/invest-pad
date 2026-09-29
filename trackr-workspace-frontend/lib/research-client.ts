/**
 * Typed client for methods, agents, tasks, attempts, review and grounded chat (BE 16-25;
 * `contracts/openapi.yaml` tags `research` and `tasks`) plus Butler's model selection,
 * teaching and status routes (BT 08-10).
 *
 * WORKSPACE ONLY, like `research-api.ts`. Plus must never import a research call.
 *
 * NO PROVIDER KEY EVER PASSES THROUGH THIS FILE. Every function here talks to Trackr+ only,
 * with the Trackr+ session token. The provider call lives in `research-agent.ts`, which holds
 * the key in memory and sends it only to the configured provider origin. Request bodies are
 * built FIELD BY FIELD (see `agentBody`) so a local object carrying a key can never be spread
 * into an API payload by a future refactor.
 */

import { api } from "@trackr/core";
import { wsBase, type Page } from "./research-api";

const enc = encodeURIComponent;

export interface WriteCtx {
  investorId: string;
  token: string | null;
  idempotencyKey: string;
}

function post<T>(ctx: WriteCtx, path: string, json: unknown): Promise<T> {
  return api.post<T>(path, {
    token: ctx.token,
    json,
    headers: { "Idempotency-Key": ctx.idempotencyKey },
  });
}

// --- methods --------------------------------------------------------------------------------

export interface MissingItem {
  id: string;
  kind: string;
  code: string;
  gate: string | null;
}

export interface Availability {
  state: "READY" | "UNKNOWN";
  missing: MissingItem[];
}

export interface Skill {
  id: string;
  version: number;
  name: string;
  summary: string;
  method: string;
  reads: string[];
  citation_rules: string[];
  permitted_tools: string[];
  forbidden_conclusions: string[];
  output_contract: Record<string, unknown>;
  house_rules_version: string;
  enabled: boolean;
  recorded_at: string;
  method_key: string | null;
  task_route: "TASKS" | "BUTLER_ONLY" | null;
  availability: Availability;
}

export interface SkillCreate {
  expected_version: number;
  name: string;
  summary: string;
  method: string;
  reads: string[];
  citation_rules: string[];
  permitted_tools: string[];
  forbidden_conclusions: string[];
  output_contract: Record<string, unknown>;
  enabled: boolean;
}

export interface CatalogueMethod {
  skill_id: string;
  key: string;
  task_route: "TASKS" | "BUTLER_ONLY";
  purposes: string[];
  precondition: string | null;
  reads: { id: string; obligation: string; required: boolean; capability: string }[];
  dependencies: { id: string; kind: string; status: string; gate: string | null; description: string }[];
  availability: Availability;
  default: Omit<SkillCreate, "expected_version">;
}

/** An approved calculator definition (BE 27-28). The list is EMPTY while BE-Q03 is open. */
export interface ApprovedFormula {
  formula_id: string;
  version: string;
  kind: "METRIC" | "SCENARIO";
  title: string;
  digest: string;
  output_contract_approved: boolean;
  output_unit: string;
  inputs: { name: string; metric: string; basis: string; unit: string; cadence: string; period_role: string }[];
  assumptions: { name: string; unit: string; minimum: string | null; maximum: string | null; description: string }[];
}

export interface Catalogue {
  catalogue_version: string;
  house_rules_version: string;
  house_rules: { id: string; text: string }[];
  methods: CatalogueMethod[];
  undeclared_methods: string[];
  /** BE 35 cross-method audit: findings per method (empty findings = no drift found). */
  audit?: { method_key: string; findings: string[]; house_rules_version: string }[];
  formulas?: { registry_version: string; synthetic: boolean; approved: ApprovedFormula[] };
  source_adapters?: { adapter_id: string; synthetic: boolean; source_types: string[] }[];
  tools: { available: string[]; unavailable: { name: string; code: string; gate: string }[] };
}

// --- calculators and evidence tools (BE 27-29) ----------------------------------------------

export interface ToolResponse {
  status: "OK" | "UNKNOWN" | "CONFLICT";
  data: unknown;
  references: { kind: string; id: string }[];
  conflicts: { claim: string; source_ids: string[]; description: string }[];
  notices: { code: string; message: string }[];
  calculation: CalculationTrace | null;
}

/** The calculator's own trace. `value` is a decimal STRING computed on the server; the UI shows
 * it verbatim and never re-derives, rounds or reformats it into another unit. */
export interface CalculationTrace {
  engine_version: string;
  status: "OK" | "UNKNOWN" | "CONFLICT";
  kind: "METRIC" | "SCENARIO";
  formula_id: string;
  formula_version: string;
  registry_version: string | null;
  definition_digest: string | null;
  value: string | null;
  unit: string | null;
  period: { period_start: string; period_end: string; cadence: string } | null;
  expression: string | null;
  inputs: Record<string, unknown>[];
  assumptions: { operand: string; label: "ASSUMPTION"; value: string; unit: string; reason: string; stated_by: string }[];
  reasons: ({ code: string } & Record<string, unknown>)[];
  conflicts: Record<string, unknown>[];
}

export interface AssumptionInput {
  name: string;
  value: string;
  unit: string;
  reason: string;
}

export interface ResearchEvent {
  id: string;
  isin: string;
  source_id: string;
  event_type: string;
  status: "SCHEDULED" | "OBSERVED" | "CLAIMED" | "CANCELLED";
  event_date: string | null;
  date_precision: "EXACT" | "IMPRECISE" | "UNKNOWN";
  period_start: string | null;
  period_end: string | null;
  description: string;
  locator: string;
  verification: "UNVERIFIED" | "VERIFIED";
  verification_reference: string | null;
  supersedes_id: string | null;
  superseded_by: string | null;
  reschedules_id: string | null;
  rescheduled_by: string[];
  source_type: string;
  publication_date: string;
  retrieved_at: string;
  recorded_at: string;
  classification_verified: boolean;
}

export interface RefreshSummary {
  adapter_id: string;
  synthetic: boolean;
  isin: string;
  sources: { origin_item_id: string; source_id: string; retained: boolean }[];
  facts: { fact_id: string; metric: string; supersedes_id: string | null }[];
  events: { event_id: string; event_type: string; status: string }[];
  unknowns: ({ code: string } & Record<string, unknown>)[];
  duplicates: { origin_item_id: string; source_id: string }[];
  revisions: { source_id: string; revises_source_id: string }[];
  conflicts: { fact_id: string; conflicts_with: string[]; metric: string }[];
  replayed: boolean;
}

/** One tool call on the READ route. Trackr+ only, with the session token -- no provider key. */
export function callTool(
  investorId: string,
  token: string | null,
  tool: string,
  isin: string,
  args: Record<string, unknown>
): Promise<ToolResponse> {
  return api.post<ToolResponse>(`${wsBase(investorId)}/tools/${enc(tool)}`, {
    token,
    json: { isin, args },
  });
}

// --- agents ---------------------------------------------------------------------------------

export type Provider = "ANTHROPIC" | "OPENAI_COMPATIBLE";

/** Server configuration. There is NO key, status or readiness field -- the server cannot
 * know whether this browser holds a key, and does not pretend to. */
export interface Agent {
  id: string;
  version: number;
  name: string;
  provider: Provider;
  model: string;
  base_url: string;
  role_description: string;
  skill_id: string;
  skill_version: number;
  enabled: boolean;
  actor_uid: string;
  recorded_at: string;
}

export interface AgentInput {
  name: string;
  provider: Provider;
  model: string;
  base_url: string;
  role_description: string;
  skill_id: string;
  skill_version: number;
  enabled: boolean;
}

/** Field-by-field copy. Never `{...input}`: an object that happens to carry a key must not be
 * able to ride along into a Trackr+ request. */
export function agentBody(input: AgentInput): AgentInput {
  return {
    name: input.name,
    provider: input.provider,
    model: input.model,
    base_url: input.base_url,
    role_description: input.role_description,
    skill_id: input.skill_id,
    skill_version: input.skill_version,
    enabled: input.enabled,
  };
}

// --- tasks ----------------------------------------------------------------------------------

export type TaskState = "assigned" | "running" | "review" | "done" | "rejected";
export type Purpose = "RESEARCH" | "ANSWER_REVIEW" | "CHAT" | "INLINE" | "MONITOR";

export interface Attempt {
  id: string;
  task_id: string;
  attempt_no: number;
  mode: "BROWSER_MODEL" | "STORED_SAMPLE";
  sample_ref: string | null;
  started_at: string;
  lease_until: string;
  lease_expired: boolean;
}

export interface RenderedValue {
  status: "RESOLVED" | "UNAVAILABLE" | "LIVE_REFERENCE" | "UNKNOWN" | "CALCULATED";
  text: string;
  context_id?: string;
  field?: string;
  code?: string;
}

/** Code-computed tables beside a method's proposal (BE 30-35). Never model-written. */
export type DeterministicBlock =
  | { block: "PEER_TABLE"; rows: { company: string; isins: string[]; cells: Record<string, Record<string, unknown> & { state: string }> }[]; excluded_peers: { company: string; isins: string[]; reasons: string[] }[]; compared_series: string[] }
  | { block: "STATEMENT_COVERAGE"; periods: Record<string, Record<string, string[]>>; required: string[] }
  | { block: "REQUIREMENTS"; requirements: { requirement_context_id: string; title: string | null; written_on: string; state: "SUPPORTED" | "CONTRADICTED" | "OPEN"; reason?: string }[] }
  | { block: "EVENT_TIMELINE"; scheduled: ResearchEvent[]; observed: ResearchEvent[]; claimed: ResearchEvent[]; cancelled: ResearchEvent[]; unknown_dates: string[] };

export interface RenderedParagraph {
  text: string;
  classification?: string;
  citations: string[];
  quotes?: { context_id: string; text: string }[];
  values?: RenderedValue[];
  label?: string;
  verbatim?: boolean;
}

export interface Rendered {
  summary: string;
  sections: { heading: string; deterministic?: boolean; paragraphs: RenderedParagraph[] }[];
  note_proposal: { kind: string; title: string; body: string; source_context_ids: string[] } | null;
  answer_review: { ok: RenderedParagraph[]; gap: RenderedParagraph[] } | null;
  deterministic_blocks?: DeterministicBlock[];
}

export interface Result {
  id: string;
  task_id: string;
  attempt_id: string;
  outcome: "PROPOSED" | "FAILED" | "CANCELLED" | "EXPIRED";
  guardrail_status: "PASS" | "BLOCKED" | "NOT_APPLICABLE";
  guardrail_reasons: string[];
  error_code: string | null;
  finished_at: string;
  duration_ms: number;
  citations: { context_id: string; claim_ref: string }[];
  sample: boolean;
  invocation_evidence: "CLIENT_REPORTED" | "STORED_SAMPLE";
  proposal: Record<string, unknown> | null;
  rendered: Rendered | null;
}

export interface Review {
  id: string;
  task_id: string;
  result_id: string;
  decision: "ACCEPT" | "REJECT";
  reason: string;
  accepted_note_id: string | null;
  reviewer_uid: string;
  reviewed_at: string;
}

export interface Task {
  id: string;
  isin: string;
  purpose: Purpose;
  title: string;
  brief: string;
  skill_id: string;
  skill_version: number;
  agent_id: string;
  agent_version: number;
  thesis_id: string | null;
  answer_id: string | null;
  chat_thread_id: string | null;
  parent_task_id: string | null;
  created_by: string | null;
  created_at: string;
  context_cutoff: string;
  context_digest: string;
  house_rules_version: string;
  method_key: string | null;
  state: TaskState;
  latest_attempt: Attempt | null;
  result: Result | null;
  review: Review | null;
  sample: boolean;
  error_code: string | null;
  attempts: number;
}

export interface ContextSelection {
  note_ids: string[];
  source_ids: string[];
  fact_ids: string[];
  evaluation_ids: string[];
  calculation_specs: never[];
  include_position_query: { as_of: string; advised_only: boolean } | null;
  expected_thesis_id: string | null;
}

export interface TaskCreate {
  isin: string;
  purpose: "RESEARCH" | "INLINE" | "ANSWER_REVIEW";
  title: string;
  brief: string;
  agent_id: string;
  agent_version: number;
  skill_id: string;
  skill_version: number;
  thesis_id: string | null;
  answer_id: string | null;
  parent_task_id: string | null;
  context_selection: ContextSelection;
}

export interface ContextPacket {
  task_id: string;
  context_digest: string;
  house_rules_version: string;
  skill: Record<string, unknown> & { output_contract: Record<string, unknown> };
  agent: { id: string; version: number; provider: Provider; model: string; base_url: string };
  purpose: Purpose;
  brief: string;
  system_instructions: string;
  ordered_context: { context_id: string; ordinal: number; kind: string; ref_id: string; content: Record<string, unknown> }[];
  prior_chat_turns: { message_id: string; role: string; content: string }[];
  calculation_results: Record<string, unknown>[];
  position_query: Record<string, unknown> | null;
  allowed_tools: string[];
  exclusions: { context_id: string; code: string; message: string }[];
  disclosure: { destination_origin: string; source_verdict_refs: string[] };
  precondition: Availability;
  butler_packet: ButlerPacket | null;
}

export interface ButlerPacket {
  packet: Record<string, unknown> & { packet_id: string };
  system_prompt: string;
  prompt_version: string;
  prompt_sha256: string;
  proposal_shape: Record<string, unknown>;
  expires_at: string;
  budgets: {
    max_input_tokens: number;
    max_output_tokens: number;
    client_timeout_seconds: number;
    automatic_retry: false;
    one_in_flight_per_investor: true;
  };
}

export interface AttemptOut {
  attempt: Attempt;
  context_digest: string;
  /** True when this replays an earlier start. NEVER permission to call the provider again. */
  replayed: boolean;
}

export type FailureCode =
  | "PROVIDER_UNREACHABLE"
  | "AUTH_FAILED"
  | "RATE_LIMITED"
  | "CLIENT_CLOSED"
  | "INVALID_OUTPUT";

export interface ReviewOut {
  review: Review;
  note: Record<string, unknown> | null;
  task: Task;
}

// --- chat -----------------------------------------------------------------------------------

export interface Thread {
  id: string;
  isin: string;
  title: string;
  actor_uid: string;
  created_at: string;
  messages: number;
}

export interface ChatMessage {
  id: string;
  thread_id: string;
  role: "HUMAN" | "ASSISTANT" | "REFUSAL";
  body: string;
  actor_uid: string | null;
  result_id: string | null;
  task_id: string | null;
  recorded_at: string;
  rendered: Rendered | null;
  guardrail_status: string | null;
  review_decision: string | null;
  sample: boolean;
}

export interface TurnOut {
  message: ChatMessage;
  task: Task | null;
  refusal: { code: string; message: string } | null;
}

// --- Butler (BT 08-10) ----------------------------------------------------------------------

export interface Selection {
  task_id: string;
  isin: string;
  intent: string | null;
  created_at: string;
  context_cutoff: string;
  task_state: TaskState;
  state:
    | "NO_RESULT"
    | "ASSIGNED"
    | "RUNNING"
    | "VALIDATED"
    | "ABSTAINED"
    | "STALE"
    | "WITHDRAWN"
    | "REJECTED_BY_VALIDATION"
    | "VALIDATION_UNAVAILABLE";
  cards: Record<string, unknown>[];
  reason_codes: string[];
  coverage: Record<string, unknown> | null;
  abstain_code: string | null;
  error_code: string | null;
  sample: boolean;
  execution: "NONE" | "CLIENT_REPORTED_MODEL" | "STORED_SAMPLE";
  attempts: number;
  latest_attempt: Attempt | null;
  versions: Record<string, string>;
  agent: { id: string; version: number };
}

export interface Teaching {
  state: "NOT_SET" | "SET";
  version: number;
  detail: "CONCISE" | "DETAILED";
  lesson_cadence: "EVERY_REVIEW" | "WEEKLY" | "OFF";
  follow_ups: "ASK" | "SKIP";
  recorded_at: string | null;
}

export interface Feedback {
  id: string;
  subject_kind: "QUESTION" | "LESSON" | "CARD";
  subject_id: string;
  subject_version: string;
  inbox_item_id: string | null;
  rating: "USEFUL" | "NOT_USEFUL";
  recorded_at: string;
}

export interface ButlerStatus {
  worker: Record<string, unknown> & { model_execution: string; last_outcome: string; lag_seconds: number };
  switches: Record<string, boolean>;
  selections: { window_days: number; attempts?: { outcome: string; guardrail: string; error_code: string; mode: string; count: number }[] };
  coverage: Record<string, unknown>;
  limits: Record<string, unknown>;
}

// --- paths ----------------------------------------------------------------------------------

const butlerBase = (inv: string) => `/investors/${enc(inv)}/butler`;

export const rpaths = {
  catalogue: (inv: string) => `${wsBase(inv)}/skill-catalogue`,
  skills: (inv: string) => `${wsBase(inv)}/skills`,
  skillVersion: (inv: string, id: string, v: number) => `${wsBase(inv)}/skills/${enc(id)}/versions/${v}`,
  agents: (inv: string) => `${wsBase(inv)}/agents`,
  agentVersion: (inv: string, id: string, v: number) => `${wsBase(inv)}/agents/${enc(id)}/versions/${v}`,
  tasks: (inv: string) => `${wsBase(inv)}/tasks`,
  task: (inv: string, id: string) => `${wsBase(inv)}/tasks/${enc(id)}`,
  taskContext: (inv: string, id: string) => `${wsBase(inv)}/tasks/${enc(id)}/context`,
  chats: (inv: string) => `${wsBase(inv)}/chats`,
  messages: (inv: string, thread: string) => `${wsBase(inv)}/chats/${enc(thread)}/messages`,
  selections: (inv: string) => `${butlerBase(inv)}/selections`,
  selection: (inv: string, id: string) => `${butlerBase(inv)}/selections/${enc(id)}`,
  teaching: (inv: string) => `${butlerBase(inv)}/teaching`,
  feedback: (inv: string) => `${butlerBase(inv)}/feedback`,
  status: (inv: string) => `${butlerBase(inv)}/status`,
  events: (inv: string, isin: string) => `${wsBase(inv)}/companies/${enc(isin)}/events`,
};

// --- writes ---------------------------------------------------------------------------------

export const rwrite = {
  publishSkill: (ctx: WriteCtx, skillId: string, body: SkillCreate) =>
    post<Skill>(ctx, `${wsBase(ctx.investorId)}/skills/${enc(skillId)}/versions`, body),
  createAgent: (ctx: WriteCtx, input: AgentInput) =>
    post<Agent>(ctx, rpaths.agents(ctx.investorId), agentBody(input)),
  appendAgentVersion: (ctx: WriteCtx, agentId: string, input: AgentInput, expectedVersion: number) =>
    post<Agent>(ctx, `${rpaths.agents(ctx.investorId)}/${enc(agentId)}/versions`, {
      ...agentBody(input),
      expected_version: expectedVersion,
    }),
  createTask: (ctx: WriteCtx, body: TaskCreate) => post<Task>(ctx, rpaths.tasks(ctx.investorId), body),
  startAttempt: (ctx: WriteCtx, taskId: string, body: { mode: "BROWSER_MODEL" | "STORED_SAMPLE"; sample_ref?: string }) =>
    post<AttemptOut>(ctx, `${rpaths.task(ctx.investorId, taskId)}/attempts`, body),
  submitResult: (ctx: WriteCtx, taskId: string, attemptId: string, contextDigest: string, proposal: unknown) =>
    post<Task>(ctx, `${rpaths.task(ctx.investorId, taskId)}/attempts/${enc(attemptId)}/results`, {
      context_digest: contextDigest,
      proposal,
    }),
  submitFailure: (ctx: WriteCtx, taskId: string, attemptId: string, code: FailureCode) =>
    post<Task>(ctx, `${rpaths.task(ctx.investorId, taskId)}/attempts/${enc(attemptId)}/failures`, { code }),
  submitCancellation: (ctx: WriteCtx, taskId: string, attemptId: string) =>
    post<Task>(ctx, `${rpaths.task(ctx.investorId, taskId)}/attempts/${enc(attemptId)}/cancellations`, {}),
  accept: (
    ctx: WriteCtx,
    taskId: string,
    body: {
      result_id: string;
      reason: string;
      note: {
        kind: "OBSERVATION" | "INTERPRETATION";
        title: string;
        body: string;
        written_on: string;
        primary_source_id: string | null;
        links: never[];
      };
    }
  ) => post<ReviewOut>(ctx, `${rpaths.task(ctx.investorId, taskId)}/acceptances`, body),
  reject: (ctx: WriteCtx, taskId: string, body: { result_id: string; reason: string }) =>
    post<ReviewOut>(ctx, `${rpaths.task(ctx.investorId, taskId)}/rejections`, body),
  createThread: (ctx: WriteCtx, isin: string, title: string) =>
    post<Thread>(ctx, `${wsBase(ctx.investorId)}/companies/${enc(isin)}/chats`, { title }),
  turn: (
    ctx: WriteCtx,
    threadId: string,
    body: {
      text: string;
      agent_id: string;
      agent_version: number;
      skill_id: string;
      skill_version: number;
      context_selection: ContextSelection;
    }
  ) => post<TurnOut>(ctx, `${wsBase(ctx.investorId)}/chats/${enc(threadId)}/turns`, body),
  createSelection: (
    ctx: WriteCtx,
    body: { isin: string; intent: string; agent_id: string; agent_version: number; parent_task_id: string | null }
  ) => post<Selection>(ctx, rpaths.selections(ctx.investorId), body),
  setTeaching: (
    ctx: WriteCtx,
    body: { detail: string; lesson_cadence: string; follow_ups: string; expected_version: number }
  ) => post<Teaching>(ctx, rpaths.teaching(ctx.investorId), body),
  feedback: (
    ctx: WriteCtx,
    body: { subject_kind: string; subject_id: string; subject_version: string; inbox_item_id: string | null; rating: string }
  ) => post<Feedback>(ctx, rpaths.feedback(ctx.investorId), body),
  refreshSources: (ctx: WriteCtx, isin: string, body: { adapter_id: string; periods: string[] }) =>
    post<RefreshSummary>(ctx, `${wsBase(ctx.investorId)}/companies/${enc(isin)}/source-refreshes`, body),
  verifyEvent: (ctx: WriteCtx, eventId: string, body: { verification_reference: string; expected_event_id: string }) =>
    post<ResearchEvent>(ctx, `${wsBase(ctx.investorId)}/events/${enc(eventId)}/verifications`, body),
};

export function getContext(investorId: string, token: string | null, taskId: string): Promise<ContextPacket> {
  return api.get<ContextPacket>(rpaths.taskContext(investorId, taskId), { token });
}

export function getTask(investorId: string, token: string | null, taskId: string): Promise<Task> {
  return api.get<Task>(rpaths.task(investorId, taskId), { token });
}

export function getSelection(investorId: string, token: string | null, taskId: string): Promise<Selection> {
  return api.get<Selection>(rpaths.selection(investorId, taskId), { token });
}

export function emptySelection(expectedThesisId: string | null = null): ContextSelection {
  return {
    note_ids: [],
    source_ids: [],
    fact_ids: [],
    evaluation_ids: [],
    calculation_specs: [],
    include_position_query: null,
    expected_thesis_id: expectedThesisId,
  };
}

export type { Page };

/** A fresh idempotency key for a single write the caller does not retry through useSubmit. */
export function newKey(): string {
  return crypto.randomUUID();
}
