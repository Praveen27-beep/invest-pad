/**
 * Typed client for the Workspace research API (BE 08-15, `contracts/openapi.yaml` tags
 * `workspace` and `research`).
 *
 * WORKSPACE ONLY. Research browser code lives in this app, never in a shared package: Plus
 * must not be able to import a research call even by accident. The HTTP mechanics are the
 * shared `api` client's; only the research paths and shapes are here.
 *
 * TYPES MIRROR THE SERVER DTOs (`trackr-backend/app/schemas/workspace.py`, `research.py`).
 * Every numeric research value is a DECIMAL STRING and stays one here -- nothing in this file
 * parses a threshold or a fact into a JS number.
 *
 * WRITES CARRY AN IDEMPOTENCY KEY that the CALLER owns (see `useSubmit` in
 * `research-hooks.ts`): the same key is reused when an identical request is retried after a
 * network failure, so a retry replays the original result instead of writing twice, and a new
 * key is minted when the payload changes.
 */

import { api } from "@trackr/core";

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface Notice {
  code: string;
  message: string;
}

export interface Identity {
  /** Optional company research coverage; specialised views never depend on a sector guess. */
  research_sections?: readonly import("./company-sections").ResearchSection[];
  isin: string;
  canonical_isin: string;
  symbol: string | null;
  name: string | null;
}

export interface CompanyListItem extends Identity {
  ritual_complete: boolean;
}

export interface Answer {
  id: string;
  question_id: string;
  answer: string;
  answered_on: string;
  recorded_at: string;
  previous_id: string | null;
  actor_uid: string;
}

export interface AnswerReview {
  answer_id: string;
  task_id: string;
  result_id: string;
  ok: string[];
  gap: string[];
  decision: "ACCEPT" | "REJECT" | null;
  sample: boolean;
}

export interface Question {
  id: string;
  isin: string;
  note_id: string;
  ritual_id: string | null;
  blocking: boolean;
  recorded_at: string;
  text: string;
  written_on: string;
  status: "OPEN" | "ANSWERED";
  answer_ids: string[];
  latest_answer: Answer | null;
  review: AnswerReview | null;
}

export interface SourceContentState {
  state: "METADATA_ONLY" | "EXTRACTED" | "UNAVAILABLE";
  unavailable_reason: string | null;
  extractor_id: string | null;
  extractor_version: string | null;
  normalization: string | null;
  text_sha256: string | null;
  page_count: number | null;
}

export const SOURCE_TYPES = [
  "EXCHANGE_FILING",
  "ANNUAL_REPORT",
  "RESULTS",
  "PRESENTATION",
  "TRANSCRIPT",
  "SHAREHOLDING",
  "NEWS",
  "MANAGEMENT_COMMENTARY",
  "USER_DOCUMENT",
  "BOOK",
] as const;
export type SourceType = (typeof SOURCE_TYPES)[number];

export interface Source {
  id: string;
  isin: string;
  source: string;
  source_type: SourceType;
  source_url: string;
  publication_date: string;
  period: string;
  retrieved_at: string;
  document_reference: string;
  document_id: string | null;
  content_sha256: string | null;
  recorded_at: string;
  content: SourceContentState;
}

export type Relation = "READS" | "SUPPORTS" | "CONTRADICTS" | "CITES";

export interface NoteLink {
  id: string;
  from_note_id: string;
  to_note_id: string | null;
  source_id: string | null;
  thesis_id: string | null;
  relation: Relation;
  recorded_at: string;
  actor_uid: string;
  direction: "OUT" | "IN";
}

export const WRITABLE_NOTE_KINDS = [
  "OBSERVATION",
  "INTERPRETATION",
  "THESIS_NOTE",
  "LITERATURE",
  "DECISION",
] as const;
export type WritableNoteKind = (typeof WRITABLE_NOTE_KINDS)[number];

export interface Note {
  id: string;
  isin: string;
  kind: WritableNoteKind | "QUESTION";
  title: string;
  body: string;
  written_on: string;
  recorded_at: string;
  actor_uid: string;
  authorship: "HUMAN" | "ACCEPTED_AGENT";
  primary_source_id: string | null;
  previous_id: string | null;
  source: Source | null;
  links: NoteLink[];
  revision_ids: string[];
  latest_id: string;
  is_latest: boolean;
  accepted_from: { task_id: string; result_id: string; sample: boolean } | null;
}

export interface NoteLinkInput {
  relation: Relation;
  to_note_id?: string | null;
  source_id?: string | null;
  thesis_id?: string | null;
}

export interface NoteInput {
  kind: WritableNoteKind;
  title: string;
  body: string;
  written_on: string;
  primary_source_id: string | null;
  links: NoteLinkInput[];
}

/** One exit or variable rule. Every value a string -- including the threshold. */
export interface Rule {
  id: string;
  label: string;
  metric: string;
  basis: string;
  unit: string;
  op: "LT" | "LE" | "EQ" | "GE" | "GT" | "IS_TRUE" | "IS_FALSE";
  threshold: string;
  cadence: "QUARTER" | "YEAR" | "POINT";
  periods: string;
}

export interface FieldReason {
  field: string;
  code: string;
}

export interface ThesisEvent {
  id: string;
  thesis_id: string;
  kind: "CONVICTION" | "OVERRIDE_EXIT_TRIGGER" | "REVIEWED";
  conviction: string | null;
  reason: string;
  evaluation_id: string | null;
  actor_uid: string;
  occurred_on: string;
  recorded_at: string;
}

export interface EvaluationSummary {
  id: string;
  thesis_id: string;
  state: string;
  evaluated_at: string;
  evidence_cutoff: string;
}

export interface Thesis {
  id: string;
  isin: string;
  version: number;
  status: "DRAFT" | "ACTIVE" | "RETIRED";
  display_status: "DRAFT" | "ACTIVE" | "RETIRED" | "NEEDS_REVIEW";
  formed_on: string;
  version_on: string;
  recorded_at: string;
  actor_uid: string;
  argument: string;
  anti_thesis: string;
  pre_mortem: string;
  intended_holding_period: string;
  variables: Rule[];
  exits: Rule[];
  draft_reasons: FieldReason[];
  events: ThesisEvent[];
  links: { id: string; from_note_id: string; thesis_id: string; relation: Relation; recorded_at: string }[];
  latest_evaluation: EvaluationSummary | null;
  is_latest: boolean;
}

export interface ThesisInput {
  intent: "SAVE" | "RETIRE";
  expected_version: number;
  formed_on: string;
  version_on: string;
  argument: string;
  anti_thesis: string;
  pre_mortem: string;
  intended_holding_period: string;
  variables: Rule[];
  exits: Rule[];
}

export interface WindowResult {
  period_start: string;
  period_end: string;
  state: string;
  value: string | boolean | null;
  fact_ids: string[];
  source_ids: string[];
  publication_date: string | null;
  reason: string | null;
  comparison: boolean | null;
}

export interface RuleResult {
  rule_id: string;
  kind: "VARIABLE" | "EXIT";
  state: "MET" | "NOT_MET" | "UNKNOWN" | "CONFLICT";
  ok: boolean | null;
  required_windows: { period_start: string; period_end: string }[];
  windows: WindowResult[];
  fact_ids: string[];
  source_ids: string[];
  comparator: string;
  threshold: string;
  latest: string | boolean | null;
  latest_publication_date: string | null;
  met_on: string | null;
  reason_codes: string[];
}

export interface Evaluation {
  id: string | null;
  thesis_id: string;
  state: "TRIGGERED" | "NOT_TRIGGERED" | "UNKNOWN" | "CONFLICT";
  variables: RuleResult[];
  exits: RuleResult[];
  evidence_cutoff: string;
  evaluated_at: string | null;
  engine_version: string;
  input_digest: string;
  replay_manifest: Record<string, unknown> | null;
  fact_ids: string[];
  replay?: { status: "VERIFIED" | "DRIFT" | "UNAVAILABLE"; reasons: string[] } | null;
}

export interface Fact {
  id: string;
  isin: string;
  source_id: string;
  metric: string;
  basis: string;
  unit: string;
  period_start: string;
  period_end: string;
  cadence: string;
  numeric_value: string | null;
  boolean_value: boolean | null;
  text_value: string | null;
  verification: "UNVERIFIED" | "VERIFIED";
  verified_by: string | null;
  verification_reference: string | null;
  supersedes_id: string | null;
  registry_version: string | null;
  recorded_at: string;
  superseded_by: string | null;
  conflicts_with: string[];
}

export interface FactInput {
  source_id: string;
  metric: string;
  basis: string;
  unit: string;
  period_start: string;
  period_end: string;
  cadence: "QUARTER" | "YEAR" | "POINT";
  numeric_value: string | null;
  boolean_value: boolean | null;
  text_value: string | null;
}

export interface SourceInput {
  source: string;
  source_type: SourceType;
  source_url: string;
  publication_date: string;
  period: string;
  retrieved_at: string;
  document_reference: string;
  document_id?: string | null;
}

export interface SourceContent {
  source_id: string;
  content_sha256: string;
  text_sha256: string;
  extractor_id: string;
  extractor_version: string;
  normalization: string;
  page: number | null;
  page_count: number;
  text: string;
  document_reference: string;
}

export interface CompanyViewLocked {
  state: "RITUAL_REQUIRED";
  identity: Identity;
}

export interface CompanyViewReady {
  state: "READY";
  identity: Identity;
  open_questions: Question[];
  thesis: Thesis | null;
  trigger: EvaluationSummary | null;
  notes: Page<Note>;
  position: {
    as_of: string;
    advised_only: boolean;
    holdings: Record<string, unknown>[];
    unpriced: { isin: string; invested: string }[];
  } | null;
  notices: Notice[];
  as_of: string;
}

export type CompanyView = CompanyViewLocked | CompanyViewReady;

export interface ReturnItem {
  kind: "NOTE" | "THESIS" | "OVERRIDE" | "CONTRADICTION";
  reason: "MONTH_6" | "MONTH_12" | "MONTH_24" | "CONTRADICTION";
  isin: string;
  original_date: string;
  content_ref: string;
  note_id?: string | null;
  thesis_id?: string | null;
  event_id?: string | null;
  link_id?: string | null;
  other_note_id?: string | null;
  other_date?: string | null;
}

export interface Home {
  as_of: string;
  open_questions: Page<Question>;
  returns: ReturnItem[];
  reviews: unknown[];
  notices: Notice[];
}

// --- paths ---------------------------------------------------------------------------

/** `/investors/{id}/workspace`. Every research path is built from this, never by hand. */
export function wsBase(investorId: string): string {
  return `/investors/${encodeURIComponent(investorId)}/workspace`;
}

const enc = encodeURIComponent;

export const paths = {
  companies: (inv: string) => `${wsBase(inv)}/companies`,
  company: (inv: string, isin: string) => `${wsBase(inv)}/companies/${enc(isin)}`,
  securities: (inv: string) => `${wsBase(inv)}/securities`,
  companyNotes: (inv: string, isin: string) => `${wsBase(inv)}/companies/${enc(isin)}/notes`,
  companyTheses: (inv: string, isin: string) => `${wsBase(inv)}/companies/${enc(isin)}/theses`,
  companySources: (inv: string, isin: string) => `${wsBase(inv)}/companies/${enc(isin)}/sources`,
  companyFacts: (inv: string, isin: string) => `${wsBase(inv)}/companies/${enc(isin)}/facts`,
  note: (inv: string, id: string) => `${wsBase(inv)}/notes/${enc(id)}`,
  noteSearch: (inv: string) => `${wsBase(inv)}/notes/search`,
  questions: (inv: string) => `${wsBase(inv)}/questions`,
  question: (inv: string, id: string) => `${wsBase(inv)}/questions/${enc(id)}`,
  home: (inv: string) => `${wsBase(inv)}/home`,
  thesis: (inv: string, id: string) => `${wsBase(inv)}/theses/${enc(id)}`,
  thesisEvaluations: (inv: string, id: string) => `${wsBase(inv)}/theses/${enc(id)}/evaluations`,
  evaluation: (inv: string, id: string) => `${wsBase(inv)}/evaluations/${enc(id)}`,
  source: (inv: string, id: string) => `${wsBase(inv)}/sources/${enc(id)}`,
  sourceContent: (inv: string, id: string) => `${wsBase(inv)}/sources/${enc(id)}/content`,
};

// --- writes --------------------------------------------------------------------------

interface WriteCtx {
  investorId: string;
  token: string | null;
  /** Owned by the caller's submission, reused on an identical retry. */
  idempotencyKey: string;
}

function post<T>(ctx: WriteCtx, path: string, json: unknown): Promise<T> {
  return api.post<T>(path, {
    token: ctx.token,
    json,
    headers: { "Idempotency-Key": ctx.idempotencyKey },
  });
}

const W = (ctx: WriteCtx) => wsBase(ctx.investorId);

export const write = {
  linkCompany: (ctx: WriteCtx, isin: string) =>
    post<Identity>(ctx, `${W(ctx)}/companies`, { isin }),
  createRitual: (
    ctx: WriteCtx,
    isin: string,
    body: { questions: { text: string; blocking: boolean }[]; written_on: string }
  ) =>
    post<{ ritual_id: string; questions: Question[]; state: "READY" }>(
      ctx,
      `${W(ctx)}/companies/${enc(isin)}/rituals`,
      body
    ),
  createQuestion: (
    ctx: WriteCtx,
    isin: string,
    body: { text: string; blocking: boolean; written_on: string }
  ) => post<Question>(ctx, `${W(ctx)}/companies/${enc(isin)}/questions`, body),
  answerQuestion: (
    ctx: WriteCtx,
    questionId: string,
    body: { answer: string; answered_on: string; expected_latest_answer_id: string | null }
  ) => post<Answer>(ctx, `${W(ctx)}/questions/${enc(questionId)}/answers`, body),
  createNote: (ctx: WriteCtx, isin: string, body: NoteInput) =>
    post<Note>(ctx, `${W(ctx)}/companies/${enc(isin)}/notes`, body),
  reviseNote: (ctx: WriteCtx, noteId: string, body: NoteInput & { expected_latest_id: string }) =>
    post<Note>(ctx, `${W(ctx)}/notes/${enc(noteId)}/revisions`, body),
  linkNote: (ctx: WriteCtx, noteId: string, body: NoteLinkInput) =>
    post<NoteLink>(ctx, `${W(ctx)}/notes/${enc(noteId)}/links`, body),
  createThesis: (ctx: WriteCtx, isin: string, body: ThesisInput) =>
    post<{ thesis: Thesis; validation: { draft_reasons: FieldReason[] } }>(
      ctx,
      `${W(ctx)}/companies/${enc(isin)}/theses`,
      body
    ),
  createThesisVersion: (ctx: WriteCtx, thesisId: string, body: ThesisInput) =>
    post<{ thesis: Thesis; validation: { draft_reasons: FieldReason[] } }>(
      ctx,
      `${W(ctx)}/theses/${enc(thesisId)}/versions`,
      body
    ),
  thesisEvent: (
    ctx: WriteCtx,
    thesisId: string,
    body: { kind: "CONVICTION" | "REVIEWED"; conviction: string | null; reason: string; occurred_on: string }
  ) => post<ThesisEvent>(ctx, `${W(ctx)}/theses/${enc(thesisId)}/events`, body),
  overrideTrigger: (
    ctx: WriteCtx,
    thesisId: string,
    body: { evaluation_id: string; reason: string; occurred_on: string }
  ) => post<ThesisEvent>(ctx, `${W(ctx)}/theses/${enc(thesisId)}/overrides`, body),
  recordEvaluation: (ctx: WriteCtx, thesisId: string, evidenceCutoff: string) =>
    post<Evaluation>(ctx, `${W(ctx)}/theses/${enc(thesisId)}/evaluations`, {
      evidence_cutoff: evidenceCutoff,
    }),
  createSource: (ctx: WriteCtx, isin: string, body: SourceInput) =>
    post<Source>(ctx, `${W(ctx)}/companies/${enc(isin)}/sources`, body),
  uploadSourceDocument: (ctx: WriteCtx, isin: string, file: File, provenance: SourceInput) => {
    const form = new FormData();
    form.append("file", file);
    form.append("provenance", JSON.stringify(provenance));
    return api.post<Source>(`${W(ctx)}/companies/${enc(isin)}/source-documents`, {
      token: ctx.token,
      formData: form,
      headers: { "Idempotency-Key": ctx.idempotencyKey },
    });
  },
  createFact: (ctx: WriteCtx, isin: string, body: FactInput) =>
    post<Fact>(ctx, `${W(ctx)}/companies/${enc(isin)}/facts`, body),
  verifyFact: (ctx: WriteCtx, factId: string, body: { verification_reference: string; expected_fact_id: string }) =>
    post<Fact>(ctx, `${W(ctx)}/facts/${enc(factId)}/verifications`, body),
  reviseFact: (ctx: WriteCtx, factId: string, body: FactInput & { expected_fact_id: string }) =>
    post<Fact>(ctx, `${W(ctx)}/facts/${enc(factId)}/revisions`, body),
};

/** READ, even though it is a POST: it computes and stores nothing. */
export function evaluateNow(
  investorId: string,
  token: string | null,
  thesisId: string,
  evidenceCutoff: string
): Promise<Evaluation> {
  return api.post<Evaluation>(`${wsBase(investorId)}/theses/${enc(thesisId)}/evaluate`, {
    token,
    json: { evidence_cutoff: evidenceCutoff },
  });
}

/** Today in Asia/Kolkata, as YYYY-MM-DD -- the date a person means when they say "today". */
export function istToday(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}
