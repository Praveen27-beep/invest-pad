/**
 * Typed client for Butler's private notebook (`/investors/{id}/butler/notebook`, BT 12-15).
 *
 * WORKSPACE ONLY, and deliberately not in a shared package: `make lint` fails if the Plus app or
 * `packages/` reference the notebook. Nothing here talks to a model -- "Refresh understanding"
 * asks the server to QUEUE one bounded reflection job and returns immediately.
 *
 * Everything shown comes from the server: reviewed catalogue text, exact episode references,
 * code-computed counts and status. The UI never words an observation about the person itself.
 */

import { api } from "@trackr/core";

export type ConsentState = "NOT_SET" | "ACTIVE" | "PAUSED" | "REVOKED";
export type SourceCategory =
  | "RESEARCH_NOTES"
  | "REVIEW_RESPONSES"
  | "BUTLER_CONVERSATION"
  | "DECISION_RECEIPTS"
  | "PORTFOLIO_LINKED_DECISIONS";

export interface Consent {
  state: ConsentState;
  version: number;
  sources: SourceCategory[];
  include_from: string | null;
  effective_include_from: string | null;
  reflection_enabled: boolean;
  disclosure_version: string | null;
  opted_in_at: string | null;
  recorded_at: string | null;
  history: { version: number; action: string; sources: string[]; include_from: string | null; reflection_enabled: boolean; recorded_at: string }[];
}

export interface Episode {
  id: string;
  catalogue_id: string;
  polarity: "SUPPORTS" | "COUNTERS" | "UNDETERMINED";
  observation_code: string;
  source_category: string;
  comparability_key: string;
  isin: string;
  occurred_on: string;
  knowable_at: string;
  anchor_kind: string;
  anchor_id: string;
  review_id: string | null;
  thesis_id: string | null;
  prior_thesis_id: string | null;
  response_id: string | null;
  evaluation_id: string | null;
  limitations: string[];
  builder_version: string;
  consent_version: number;
  recorded_at: string;
  corrected: boolean;
  correction_code: string | null;
  origin: "CODE";
}

export interface Pattern {
  pattern_id: string;
  catalogue_id: string;
  catalogue_version: string | null;
  text: string;
  eligible: string;
  comparison: string;
  positive: boolean;
  scope: string;
  revision: number;
  revision_id: string;
  origin: "CODE" | "MODEL";
  stored_status: string;
  status: string;
  status_reason: string;
  supporting: Episode[];
  counterexamples: Episode[];
  counts: { eligible: number; supporting: number; counter: number; undetermined: number; distinct_dates: number; denominator_known: boolean };
  window: { start: string; end: string };
  alternatives: { id: string; text: string }[];
  questions: { id: string; text: string }[];
  limitations: { id: string; text: string }[];
  user_state: { disputed: boolean; disabled: boolean };
  user_notes: { action: string; note: string | null; recorded_at: string }[];
  consent_version: number;
  reflection_job_id: string | null;
  rule_version: string;
  last_evaluated_at: string;
  influence: { question_id: string; review_id: string; revision_id: string; recorded_at: string }[];
  used_for_coaching: boolean;
}

export interface SelfDescription {
  id: string;
  isin: string | null;
  statement: string;
  previous_id: string | null;
  recorded_at: string;
  origin: "USER";
  superseded?: boolean;
}

export interface ReflectionJob {
  id: string;
  state: string;
  state_reason: string;
  stage: string | null;
  completed_stages: string[];
  currency: string;
  budget_limit: string;
  spent_worst_case: string;
  deadline_at: string;
  recorded_at: string;
}

export interface Notebook {
  consent: Consent;
  profiling_active: boolean;
  self_descriptions: SelfDescription[];
  patterns: Pattern[];
  episodes: Episode[];
  episode_counts: { total: number; supports: number; counters: number; undetermined: number };
  retention: { category: string; policy: string; statement: string };
  generated_at: string;
  reflection: ReflectionJob | null;
}

export interface NotebookCatalogue {
  disclosure_version: string;
  disclosure_text: string;
  revocation_limit_text: string;
  source_categories: { id: SourceCategory; label: string }[];
  heuristics: { min_repeated_episodes: number; min_repeated_dates: number; stale_after_days: number; follow_through_grace_days: number; note: string };
  limitations: { id: string; text: string }[];
}

export interface WhyQuestion {
  review_id: string;
  question_id: string;
  personalised: boolean;
  pattern: Pattern | null;
  statement: string;
}

export type ControlAction =
  | "DISPUTE"
  | "WITHDRAW_DISPUTE"
  | "DISABLE"
  | "ENABLE"
  | "DELETE"
  | "CORRECT_EPISODE"
  | "EXCLUDE_EPISODE"
  | "RETRACT_SELF_DESCRIPTION";

export const CORRECTION_CODES: { id: string; label: string }[] = [
  { id: "WRONG_RECORD", label: "This is the wrong record" },
  { id: "NOT_COMPARABLE", label: "Not comparable with the others" },
  { id: "CIRCUMSTANCES_CHANGED", label: "Circumstances changed" },
  { id: "OUTSIDE_WORK_NOT_RECORDED", label: "I did the work outside the app" },
  { id: "LONG_HORIZON_INTENDED", label: "A long wait was intended" },
  { id: "OTHER", label: "Other" },
];

const enc = encodeURIComponent;

export function notebookBase(investorId: string): string {
  return `/investors/${enc(investorId)}/butler/notebook`;
}

export const notebookPaths = {
  view: (inv: string) => notebookBase(inv),
  catalogue: (inv: string) => `${notebookBase(inv)}/catalogue`,
  why: (inv: string) => `${notebookBase(inv)}/why`,
};

export interface NotebookWriteCtx {
  investorId: string;
  token: string | null;
  idempotencyKey: string;
}

function post<T>(ctx: NotebookWriteCtx, path: string, json: unknown): Promise<T> {
  return api.post<T>(`${notebookBase(ctx.investorId)}${path}`, {
    token: ctx.token,
    json,
    headers: { "Idempotency-Key": ctx.idempotencyKey },
  });
}

export const notebookWrite = {
  consent: (
    ctx: NotebookWriteCtx,
    body: {
      action: "OPT_IN" | "UPDATE_SCOPE" | "PAUSE" | "RESUME" | "REVOKE";
      expected_version: number;
      disclosure_version?: string | null;
      sources?: SourceCategory[];
      include_from?: string | null;
      reflection_enabled?: boolean;
    }
  ) => post<Consent>(ctx, "/consent", body),
  selfDescription: (ctx: NotebookWriteCtx, body: { statement: string; isin?: string | null; previous_id?: string | null }) =>
    post<SelfDescription>(ctx, "/self-descriptions", body),
  control: (
    ctx: NotebookWriteCtx,
    body: { action: ControlAction; target_id: string; correction_code?: string | null; note?: string | null }
  ) => post<{ event_id: string; action: string }>(ctx, "/controls", body),
  deleteAll: (ctx: NotebookWriteCtx) =>
    post<{ fence_id: string; purge: { status: string }; kept: string[]; note: string }>(ctx, "/delete", {
      confirm: "DELETE_MY_NOTEBOOK",
    }),
  refresh: (ctx: NotebookWriteCtx) => post<ReflectionJob>(ctx, "/refresh", {}),
};

export function exportNotebook(investorId: string, token: string | null): Promise<unknown> {
  return api.get<unknown>(`${notebookBase(investorId)}/export`, { token });
}

export function whyQuestion(investorId: string, token: string | null, reviewId: string, questionId: string): Promise<WhyQuestion> {
  return api.get<WhyQuestion>(notebookPaths.why(investorId), {
    token,
    query: { review_id: reviewId, question_id: questionId },
  });
}

/** Plain-language provenance states. These describe records, never a person. */
export const STATUS_LABELS: Record<string, string> = {
  TENTATIVE: "Tentative -- not enough comparable records",
  REPEATED_IN_RECORDS: "Seen repeatedly in your saved records",
  DISPUTED_BY_USER: "You disagreed -- not used for questions",
  SUSPENDED_PENDING_RECHECK: "Paused -- a cited record was corrected",
  STALE: "Stale -- no recent comparable record",
  RETIRED: "Retired",
};

export const POLARITY_LABELS: Record<Episode["polarity"], string> = {
  SUPPORTS: "fits the observation",
  COUNTERS: "counterexample",
  UNDETERMINED: "could not be decided",
};
