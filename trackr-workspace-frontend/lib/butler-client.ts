/**
 * Typed client for Butler (`/investors/{id}/butler`, BT 01-06; `contracts/openapi.yaml` tag
 * `butler`).
 *
 * WORKSPACE ONLY. Like `research-api.ts`, this file lives in the Workspace app and in no shared
 * package, so Plus cannot import a Butler call even by accident. The HTTP mechanics are the
 * shared `api` client's; only Butler's paths and shapes are here.
 *
 * NOTHING HERE TALKS TO A MODEL. Every card, question and lesson arrives already rendered by
 * the server from reviewed templates, and is displayed as plain text. There is no chat call, no
 * provider key and no streaming -- the server says `model_execution: "NOT_CONNECTED"` and the UI
 * repeats it rather than filling the space with simulated answers.
 *
 * WRITES CARRY AN IDEMPOTENCY KEY the caller owns (`useSubmit` in `research-hooks.ts`), so a
 * retried click replays the original result instead of recording a second follow or answer.
 */

import { api } from "@trackr/core";
import type { Identity, Page } from "./research-api";

export type { Page };

// --- shapes ---------------------------------------------------------------------------

export interface Preference {
  state: "NOT_SET" | "SET";
  version: number;
  timezone: string | null;
  quiet_start: string;
  quiet_end: string;
  digest_limit: number;
  recorded_at: string | null;
}

export interface Checkpoint {
  state: "NOT_SET" | "TIMEZONE_REQUIRED" | "SCHEDULED" | "PAUSED" | "ENDED";
  every_days: number | null;
  next_due_on: string | null;
  offered_days: number | null;
}

export interface Subscription {
  id: string;
  subject_kind: "COMPANY" | "TOPIC";
  isin: string | null;
  identity: Identity | null;
  topic: string | null;
  topic_aliases: string[];
  state: "ACTIVE" | "PAUSED" | "ENDED";
  version: number;
  checkpoint: Checkpoint;
  recorded_at: string;
  history: { version: number; action: string; checkpoint_days: number | null; recorded_at: string }[];
  coverage: { saved_workspace_records: string; external_sources: string; topic_matching: string | null };
}

export type MemoryRefKind = "NOTE" | "ANSWER" | "THESIS" | "CHAT_MESSAGE";

export interface Memory {
  id: string;
  isin: string;
  ref_kind: MemoryRefKind;
  ref_id: string;
  attribution: string;
  status: "ACTIVE" | "FORGOTTEN" | "SUPERSEDED";
  superseded_by: string | null;
  recorded_at: string;
  ended_at: string | null;
  record: {
    available: boolean;
    title: string | null;
    preview: string | null;
    recorded_at: string | null;
    is_latest_version: boolean | null;
  };
}

export interface CardCitation {
  id: string;
  kind: string;
  record_id: string;
  label: string;
  source_type?: string | null;
  published_on: string | null;
  retrieved_at: string | null;
  recorded_at: string | null;
  content_sha256: string | null;
  /** https only, resolved by the server from an authorised stored source. */
  href: string | null;
}

export interface CatalogueText {
  id: string;
  version: string;
  text: string;
}

export interface ItemStatus {
  version: number;
  seen: boolean;
  snoozed_until: string | null;
  dismissed: boolean;
  resolved: boolean;
}

export interface Card {
  id: string;
  kind: string;
  template_id: string;
  template_version: string;
  rule_version: string;
  priority: "INFORMATIONAL" | "REQUIRED";
  isin: string;
  identity: Identity;
  subscription_id: string | null;
  recorded_at: string;
  deliver_after: string;
  supersedes_item_id: string | null;
  superseded_by_item_id: string | null;
  status: ItemStatus;
  coverage: Record<string, string>;
  model_involved: boolean;
  state: "ACTIVE" | "WITHDRAWN";
  withdrawn_reason: string | null;
  title: string;
  statements: { text: string; basis: string }[];
  passages: {
    citation_id: string;
    text: string;
    truncated: boolean;
    author_kind: string;
    trust: string;
    label: string;
    recorded_at: string;
  }[];
  question: CatalogueText | null;
  lesson: CatalogueText | null;
  citations: CardCitation[];
}

export interface WorkerStatus {
  last_success_at: string | null;
  last_run_at: string | null;
  last_outcome: string;
  pending_events: number;
  oldest_pending_at: string | null;
  lag_seconds: number;
  delivery: string;
  model_execution: string;
}

export interface InboxPage {
  items: Card[];
  next_cursor: string | null;
  new_count: number;
  worker: WorkerStatus;
  preference: Preference;
}

export type FieldState =
  | "MISSING"
  | "ANSWER_RECORDED"
  | "EVIDENCE_ATTACHED"
  | "CHECKED_BY_CODE"
  | "USER_ATTESTED"
  | "UNKNOWN"
  | "NOT_APPLICABLE_WITH_REASON";

export interface ReviewField {
  question_id: string;
  question_text: string;
  question_version: string;
  /** BT 14: chosen from the notebook; the UI must offer "Why this question?". */
  personalised?: boolean;
  state: FieldState;
  resolved: boolean;
  response: {
    id: string;
    answer: string;
    attested: boolean;
    not_applicable_reason: string | null;
    milestone_on: string | null;
    recorded_at: string;
    actor_uid: string;
    previous_id: string | null;
    revision_ids: string[];
  } | null;
  evidence: {
    kind: string;
    id: string;
    available: boolean;
    reason: string | null;
    label: string | null;
    published_on: string | null;
  }[];
  code_check: { id: string; result: "PASSED" | "FAILED" | "NOT_RUN" } | null;
  follow_up: string | null;
}

export type DecisionKind = "RESEARCH_CHECKPOINT" | "THESIS_CHANGE" | "POSITION_DECISION";
export type ReviewChoice = "CONTINUE" | "PAUSE" | "REVISE" | "MORE_INFORMATION";

export interface Review {
  id: string;
  isin: string;
  identity: Identity | null;
  decision_kind: DecisionKind;
  status: "DRAFT" | "AWAITING_INPUT" | "DOCUMENTED" | "SUPERSEDED";
  checklist: Record<string, string>;
  pinned_thesis: {
    id: string;
    version: number;
    version_on: string;
    intended_holding_period: string;
    argument_excerpt: string;
  } | null;
  trigger_item_id: string | null;
  supersedes_review_id: string | null;
  superseded_by_review_id: string | null;
  fields: ReviewField[];
  next: { question_id: string; follow_up: string | null; follow_up_text: string | null } | null;
  unresolved: string[];
  differences: {
    code: string;
    question_id: string | null;
    record_id: string;
    from_version?: number | null;
    to_version?: number | null;
  }[];
  stale: boolean;
  completion: {
    choice: ReviewChoice;
    reason: string;
    unresolved: string[];
    recorded_at: string;
    actor_uid: string;
    statement: string;
  } | null;
  recorded_at: string;
  actor_uid: string;
}

export interface ReviewSummary {
  id: string;
  isin: string;
  identity: Identity | null;
  decision_kind: DecisionKind;
  status: Review["status"];
  unresolved: string[];
  recorded_at: string;
  stale: boolean;
}

// --- paths ------------------------------------------------------------------------------

const enc = encodeURIComponent;

export function butlerBase(investorId: string): string {
  return `/investors/${enc(investorId)}/butler`;
}

export const butlerPaths = {
  inbox: (inv: string) => `${butlerBase(inv)}/inbox`,
  preferences: (inv: string) => `${butlerBase(inv)}/preferences`,
  subscriptions: (inv: string) => `${butlerBase(inv)}/subscriptions`,
  memories: (inv: string) => `${butlerBase(inv)}/memories`,
  reviews: (inv: string) => `${butlerBase(inv)}/reviews`,
  review: (inv: string, id: string) => `${butlerBase(inv)}/reviews/${enc(id)}`,
};

// --- writes -----------------------------------------------------------------------------

export interface ButlerWriteCtx {
  investorId: string;
  token: string | null;
  idempotencyKey: string;
}

function post<T>(ctx: ButlerWriteCtx, path: string, json: unknown): Promise<T> {
  return api.post<T>(`${butlerBase(ctx.investorId)}${path}`, {
    token: ctx.token,
    json,
    headers: { "Idempotency-Key": ctx.idempotencyKey },
  });
}

export const butlerWrite = {
  setPreferences: (
    ctx: ButlerWriteCtx,
    body: { timezone: string; quiet_start: string; quiet_end: string; digest_limit: number; expected_version: number }
  ) => post<Preference>(ctx, "/preferences", body),
  followCompany: (ctx: ButlerWriteCtx, isin: string, checkpointDays: number | null) =>
    post<Subscription>(ctx, "/subscriptions", {
      subject_kind: "COMPANY",
      isin,
      checkpoint_days: checkpointDays,
    }),
  subscriptionEvent: (
    ctx: ButlerWriteCtx,
    id: string,
    body: { action: "PAUSE" | "RESUME" | "UNFOLLOW" | "SET_CHECKPOINT"; expected_version: number; checkpoint_days?: number | null }
  ) => post<Subscription>(ctx, `/subscriptions/${enc(id)}/events`, body),
  remember: (ctx: ButlerWriteCtx, refKind: MemoryRefKind, refId: string) =>
    post<Memory>(ctx, "/memories", { ref_kind: refKind, ref_id: refId }),
  forget: (ctx: ButlerWriteCtx, memoryId: string) =>
    post<Memory>(ctx, `/memories/${enc(memoryId)}/events`, { action: "FORGET", superseded_by: null }),
  inboxEvent: (
    ctx: ButlerWriteCtx,
    itemId: string,
    body: { action: "SEEN" | "SNOOZE" | "DISMISS" | "RESOLVE" | "RESTORE"; expected_version: number; snooze_until?: string | null }
  ) =>
    post<{ item_id: string; status: ItemStatus; replayed: boolean }>(ctx, `/inbox/${enc(itemId)}/events`, body),
  startReview: (
    ctx: ButlerWriteCtx,
    body: { isin: string; decision_kind: DecisionKind; trigger_item_id?: string | null; supersedes_review_id?: string | null }
  ) => post<Review>(ctx, "/reviews", body),
  respond: (
    ctx: ButlerWriteCtx,
    reviewId: string,
    body: {
      question_id: string;
      answer: string;
      attested: boolean;
      not_applicable_reason: string | null;
      milestone_on: string | null;
      evidence: { source_id?: string; note_id?: string }[];
      expected_latest_response_id: string | null;
    }
  ) => post<Review>(ctx, `/reviews/${enc(reviewId)}/responses`, body),
  complete: (
    ctx: ButlerWriteCtx,
    reviewId: string,
    body: { choice: ReviewChoice; reason: string; acknowledged_unresolved: string[] }
  ) => post<Review>(ctx, `/reviews/${enc(reviewId)}/complete`, body),
};

// --- labels -----------------------------------------------------------------------------

/** Plain-language field states. "Checked" is only ever said of an approved code check. */
export const FIELD_STATE_LABELS: Record<FieldState, string> = {
  MISSING: "Not answered",
  ANSWER_RECORDED: "Answer recorded",
  EVIDENCE_ATTACHED: "Evidence attached (not checked for sufficiency)",
  CHECKED_BY_CODE: "Checked by code",
  USER_ATTESTED: "Attested by you, not checked",
  UNKNOWN: "Unknown — attached evidence is no longer available",
  NOT_APPLICABLE_WITH_REASON: "Not applicable (your reason recorded)",
};

export const ATTRIBUTION_LABELS: Record<string, string> = {
  USER_BELIEF: "Your thesis",
  USER_HYPOTHESIS: "Your hypothesis",
  USER_STATEMENT: "Your note",
  USER_DECISION: "Your decision",
  USER_QUESTION: "Your question",
  USER_ANSWER: "Your answer",
  ACCEPTED_ASSISTANT_TEXT: "Assistant text you accepted",
  ASSISTANT_SUGGESTION: "Assistant suggestion",
  UNAVAILABLE: "Unavailable",
};

export const WITHDRAWN_LABELS: Record<string, string> = {
  SOURCE_RETRACTED: "Source retracted or corrected",
  SOURCE_RIGHTS_UNDECIDED: "Source use not approved",
  SOURCE_RIGHTS_WITHDRAWN: "Source use withdrawn",
  EVIDENCE_UNAVAILABLE: "Evidence unavailable",
  MEMORY_FORGOTTEN: "You asked Butler to forget this",
  RITUAL_REQUIRED: "Company locked",
  STALE_INPUT: "Record changed",
};
