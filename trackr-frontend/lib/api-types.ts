/**
 * Hand-written, not generated. `contracts/openapi.yaml`'s `$ref`s point at
 * `https://mei.capital/schema/*.json` -- a placeholder domain, not the real local
 * `schema/*.schema.json` files -- so `openapi-typescript` tries to fetch them over the
 * network and fails. Worth fixing in the contract itself (rewrite those refs to
 * relative local paths); until then these types are derived directly from the
 * Pydantic response models in trackr-backend/app/schemas/*.py and app/auth/schemas.py,
 * which are the actual runtime source of truth.
 *
 * Money/quantity fields are Decimal on the backend and cross the wire as strings
 * (CLAUDE.md: "Money is Decimal. Never float."). Never reduce them to `number` except
 * for display formatting in components/format.ts -- and never feed that back into a
 * calculation. All arithmetic (totals, weights, P&L, XIRR) is computed once, in the
 * engine, and shipped ready to render.
 */

// ---------------------------------------------------------------------------
// Holdings / summary -- app/schemas/holdings.py
// ---------------------------------------------------------------------------

export interface HoldingOut {
  isin: string;
  symbol: string | null;
  name: string | null;
  quantity: string;
  avg_cost: string;
  invested: string;
  last_price: string | null;
  market_value: string | null;
  unrealised: string | null;
  unrealised_pct: number | null;
  weight_pct: number | null;
  cagr: number | null;
  cost_estimated: boolean;
  // True when `last_price` came from the intraday cache (yfinance), not bhavcopy --
  // only ever set for as_of == today, before tonight's bhavcopy settles.
  live: boolean;
}

export interface TotalsOut {
  invested: string | null;
  market_value: string | null;
  unrealised: string | null;
  unrealised_pct: number | null;
  cost_estimated: boolean;
}

export interface UnpricedHoldingOut {
  isin: string;
  symbol: string | null;
  name: string | null;
  invested: string;
}

export interface UnpricedOut {
  count: number;
  invested: string | null;
  holdings: UnpricedHoldingOut[];
}

// compute_holdings_partitioned (app/engine/holdings.py) -- an ISIN whose own ledger
// segment didn't reconcile (negative holding, or a demerger cost-adjustment with
// nothing to adjust), excluded from `holdings`/`totals` rather than the whole response
// failing. `deficit`/`as_of` are only ever populated for the negative-holding case.
export interface SkippedHoldingOut {
  isin: string;
  symbol: string | null;
  name: string | null;
  message: string;
  deficit: string | null;
  as_of: string | null;
}

export interface AllocationGroupOut {
  asset_class: string;
  label: string;
  market_value: string | null;
  weight_pct: number | null;
  children: HoldingOut[];
}

// security.sector is null for any ISIN the NSE classification loader
// (app/db/load_sectors.py) hasn't covered -- `sector: null` is that honest gap, not an
// error. `label` is always set ("Unclassified" in that case) so a renderer never has to
// special-case the null itself.
export interface SectorAllocationGroupOut {
  sector: string | null;
  label: string;
  market_value: string | null;
  weight_pct: number | null;
  children: HoldingOut[];
}

// security.market_cap_bucket is null for any ISIN AMFI's large/mid/small-cap
// classification (app/db/load_market_cap.py) hasn't covered -- same honest-gap shape as
// SectorAllocationGroupOut above.
export interface MarketCapAllocationGroupOut {
  market_cap_bucket: string | null;
  label: string;
  market_value: string | null;
  weight_pct: number | null;
  children: HoldingOut[];
}

export interface HoldingsResponse {
  as_of: string;
  holdings: HoldingOut[];
  totals: TotalsOut;
  unpriced: UnpricedOut;
  skipped: SkippedHoldingOut[];
  // ISO 8601 timestamp of the freshest intraday quote behind any `live` holding in
  // this response, or null when nothing here is live (a past as_of, or today but
  // every price already came from bhavcopy).
  live_as_of: string | null;
}

export interface SummaryResponse {
  as_of: string;
  invested: string | null;
  market_value: string | null;
  unrealised: string | null;
  unrealised_pct: number | null;
  cost_estimated: boolean;
  unpriced: UnpricedOut;
  skipped: SkippedHoldingOut[];
  allocation: AllocationGroupOut[];
  allocation_by_sector: SectorAllocationGroupOut[];
  allocation_by_market_cap: MarketCapAllocationGroupOut[];
  live_as_of: string | null;
}

// ---------------------------------------------------------------------------
// Performance -- app/schemas/analytical.py
// ---------------------------------------------------------------------------

export interface BenchmarkOut {
  name: string;
  xirr: number | null;
  terminal_value: string | null;
}

export interface PerformanceResponse {
  as_of: string;
  xirr_all: number | null;
  xirr_holdings: number | null;
  fy_xirr: number | null;
  xirr_1y: number | null;
  xirr_3y: number | null;
  xirr_5y: number | null;
  // TWRR (docs/ENGINE_SPEC.md section 5) -- the adviser-skill companion to the four
  // windows above, never shown alone. Chains the persisted daily snapshot series
  // instead of solving a single money-weighted rate; same resolution, same
  // independent nullability.
  fy_twrr: number | null;
  twrr_1y: number | null;
  twrr_3y: number | null;
  twrr_5y: number | null;
  period_xirr: number | null;
  period_start: string | null;
  absolute_return: number | null;
  cagr: number | null;
  invested: string | null;
  market_value: string | null;
  unrealised: string | null;
  realised_to_date: string | null;
  benchmark: BenchmarkOut | null;
  warning: string | null;
}

// GET /investors/{id}/contribution -- app/schemas/analytical.py's ContributionOut/
// ContributionResponse. The first Intelligence-layer feature (docs/PRODUCT_VISION.md,
// docs/ENGINE_SPEC.md section 10): per-ISIN rupee attribution of the portfolio's gain
// over (period_start, as_of]. A fully-exited holding still appears, with end_value "0"
// -- never dropped, per section 10's "which investments destroyed value?" decision.
export interface ContributionOut {
  isin: string;
  symbol: string | null;
  start_value: string;
  end_value: string;
  net_flow: string;
  gain: string;
  // gain / total_gain. Shown uncapped -- can exceed 100% or go negative when holdings
  // offset (section 10's "show as-is, never normalise" decision). Null only when
  // total_gain is exactly zero.
  pct_of_total: number | null;
}

export interface ContributionResponse {
  as_of: string;
  period_start: string;
  total_gain: string;
  // Sorted by gain, descending -- best contributor first, worst last.
  contributions: ContributionOut[];
}

export interface PriceRefreshResponse {
  prices_stored: number;
  missing_isins: string[];
}

// GET /investors/{id}/snapshots -- a bare array of these, ascending by as_of. A date
// with no persisted row is simply absent; never filled or interpolated client-side.
export interface SnapshotOut {
  as_of: string;
  invested: string;
  market_value: string;
  unrealised: string | null;
  realised_to_date: string | null;
}

/** One point on the benchmark line -- app/schemas/analytical.py::BenchmarkPointOut.
 *  Dated to a persisted snapshot's `as_of`, so it shares an x-position with that
 *  snapshot's market value. A snapshot date whose index level was missing has no point
 *  here at all, rather than a null -- the chart draws that as a gap. */
export interface BenchmarkPointOut {
  as_of: string;
  value: string;
}

export interface BenchmarkSeriesResponse {
  name: string;
  points: BenchmarkPointOut[];
}

// ---------------------------------------------------------------------------
// Transactions / lots / realised -- app/schemas/transactions.py
// ---------------------------------------------------------------------------

export type TxnType =
  | "BUY"
  | "SELL"
  | "BONUS"
  | "SPLIT_ADJ"
  | "DEMERGER_IN"
  | "TRANSFER_IN"
  | "TRANSFER_OUT"
  | "IPO_ALLOT"
  | "BUYBACK"
  | "DIVIDEND";

export const TXN_TYPES: TxnType[] = [
  "BUY",
  "SELL",
  "BONUS",
  "SPLIT_ADJ",
  "DEMERGER_IN",
  "TRANSFER_IN",
  "TRANSFER_OUT",
  "IPO_ALLOT",
  "BUYBACK",
  "DIVIDEND",
];

export interface TransactionIn {
  account_id: string;
  isin: string;
  txn_date: string;
  txn_type: TxnType;
  quantity: string;
  price: string;
  charges?: string;
  dividend_amount?: string;
  source?: string | null;
  source_ref?: string | null;
  raw_payload?: Record<string, unknown> | null;
}

export interface TransactionOut {
  id: string | null;
  account_id: string | null;
  isin: string;
  txn_date: string;
  txn_type: string;
  quantity: string;
  price: string;
  charges: string;
  dividend_amount: string;
  source: string | null;
  source_ref: string | null;
  created_at: string | null;
}

export interface ImportSummaryOut {
  inserted: number;
  skipped_duplicates: number;
  rejected: Array<{ row: number; reason: string }>;
}

export interface LotOut {
  isin: string;
  open_date: string;
  quantity_open: string;
  cost_per_unit: string;
}

export interface RealisedOut {
  isin: string | null;
  sell_date: string | null;
  quantity: string;
  proceeds: string;
  cost: string;
  gain: string;
  term: string;
  holding_days: number | null;
}

// GET /investors/{id}/dividends -- app/schemas/transactions.py's DividendSummaryOut.
// DIVIDEND is already a positive XIRR cash flow (ENGINE_SPEC section 4); this is the
// display aggregation over those same rows. Only ISINs with at least one DIVIDEND row
// appear -- an ISIN absent here has a true, known zero, not a missing value.
export interface DividendYearOut {
  fy: string;
  amount: string;
}

export interface DividendSummaryOut {
  isin: string;
  total: string;
  by_year: DividendYearOut[];
}

// ---------------------------------------------------------------------------
// Ingest / staging -- app/schemas/ingest.py (not in openapi.yaml -- confirmed by grep)
// ---------------------------------------------------------------------------

export interface StageResultOut {
  /**
   * Null when the file was refused before any batch existed -- today only an identity
   * mismatch, where the document named a PAN or client code that is not this account's
   * and nothing was staged or stored. `notes` carries the reason, already redacted.
   * Same shape and same reasoning as `FileOutcomeOut.batch_id` below.
   */
  batch_id: string | null;
  parsed: number;
  rejected: number;
  sha256: string;
  document_id: string | null;
  notes: string[];
  // Rows written to holding_snapshot -- 0 for every current adapter (app.db.imports
  // .stage_batch's optional parse_declared_holdings hook has no active caller yet).
  declared_holdings?: number;
}

/**
 * One file's fate in a mixed multi-file upload -- POST /ingest/files
 * (app/schemas/ingest.py::FileOutcomeOut).
 *
 * Not a `StageResultOut`: a file can fail before any batch exists (wrong extension,
 * contents that don't match the name, a locked PDF), so `batch_id` is nullable and the
 * two fields that matter for a rejection are `reason` (what is wrong) and `hint` (what
 * to do instead). Both are written for the person who picked the file.
 */
export interface FileOutcomeOut {
  filename: string;
  ok: boolean;
  /** What the bytes actually are, from magic numbers -- `pdf`, `xlsx`, `text`, ... */
  container: string;
  /** What the document is -- `tradebook_csv`, `contract_note_pdf`, `cas_pdf`, ... */
  document: string;
  adapter: string | null;
  batch_id: string | null;
  parsed: number;
  rejected: number;
  reason: string | null;
  hint: string | null;
  /** A PDF we could not unlock. The fix is a PAN in Settings, not another file. */
  encrypted: boolean;
  notes: string[];
}

export interface FilesUploadOut {
  files: FileOutcomeOut[];
  accepted: number;
  rejected: number;
  /** Batches with rows waiting. Promoted with POST /ingest/stage/{id}/promote -- the
   * route itself never writes to the ledger. */
  staged_batch_ids: string[];
}

export interface RejectionOut {
  row_number: number;
  reason: string;
}

export interface NeedsReviewOut {
  row_number: number;
  confidence: string;
}

export interface ReviewBatchOut {
  status: string;
  adapter: string;
  filename: string | null;
  row_count: number;
  rejected_count: number;
  notes: string[] | null;
  uploaded_at: string;
  staged: number;
  will_insert: number;
  will_skip_as_duplicate: number;
  rejections: RejectionOut[];
  needs_review: NeedsReviewOut[];
}

export interface PromoteResultOut {
  inserted: number;
  skipped_duplicates: number;
  rejected: Array<{ row: number; reason: string }>;
}

// ---------------------------------------------------------------------------
// Reconcile -- app/schemas/reconcile.py
// ---------------------------------------------------------------------------

export interface DeclaredHoldingIn {
  isin: string;
  quantity: string;
}

export interface ReconcileRequest {
  as_of?: string | null;
  source?: string | null;
  holdings: DeclaredHoldingIn[];
}

export interface DiscrepancyOut {
  isin: string;
  computed_qty: string;
  declared_qty: string;
  difference: string;
  ratio: number | null;
  likely_cause: string | null;
}

// ---------------------------------------------------------------------------
// Onboarding -- app/schemas/investors.py
// ---------------------------------------------------------------------------

export interface InvestorIn {
  code: string;
  display_name: string;
  family_group_id?: string | null;
  // Write-only: routed through app.db.crypto and never echoed back on InvestorOut.
  pan?: string | null;
  onboarding_date?: string | null;
}

export interface InvestorOut {
  id: string;
  code: string;
  display_name: string;
  family_group_id: string | null;
  onboarding_date: string | null;
  created_at: string;
}

export interface AccountIn {
  broker: string;
  dp_id?: string | null;
  client_id?: string | null;
  is_advised?: boolean;
  label?: string | null;
}

export interface AccountOut {
  id: string;
  investor_id: string;
  broker: string;
  dp_id: string | null;
  client_id: string | null;
  is_advised: boolean;
  label: string | null;
  // One address per (broker, doctype) pair with a working adapter -- see
  // app.ingest.addresses.forwarding_addresses. Empty when the broker has no adapter
  // yet; never fabricate one client-side.
  forwarding_addresses: string[];
}

/**
 * One entry of GET /brokers -- app/brokers.py, served through app/routers/brokers.py.
 *
 * THE CLIENT MAY NOT SECOND-GUESS ANY OF THIS. Every capability below is derived on the
 * server from a registry a real, tested parser is already in; the UI's job is to render
 * what it is told, including the empty cases. A broker with `documents: []` still works
 * end to end — the account exists, files are accepted and classified, and unrecognised
 * ones are refused with a sentence. Hardcoding a broker list, or inferring a capability
 * the response did not state, reintroduces exactly the bug this endpoint removed
 * (docs/ONBOARDING_AS_IS_VS_TO_BE.md, loophole L7).
 */
export interface BrokerOut {
  /** Written verbatim into `account.broker`. */
  code: string;
  name: string;
  /** Document kinds a deterministic adapter handles. Empty is a valid, honest answer. */
  documents: string[];
  parses_contract_notes: boolean;
  parses_tradebooks: boolean;
  /** The same phrases a rejected upload uses, so promise and failure message agree. */
  document_labels: string[];
  /** True only with an email adapter AND a mail-receiving domain on this deployment.
   *  False means no address exists — say so, never render one anyway. */
  forwarding: boolean;
  /** How this broker locks contract-note PDFs. "" when we have no documented rule. */
  pdf_password: string;
  console_steps: string[];
}

/**
 * GET /investors/{id}/onboarding — how far along this account is, derived on read.
 *
 * REPLACES A localStorage KEY, which is the bug it exists to fix: "they finished setup"
 * used to live in one browser, so the same account on a phone was offered the wizard
 * again — and offered to create a second broker account with it. Every field here is
 * computed from the database per request, so the answer is identical on a laptop, a
 * phone, and a browser whose storage was cleared (docs/ONBOARDING_AS_IS_VS_TO_BE.md §4).
 *
 * The one thing deliberately NOT here is "I'll do this later" — that is a per-browser
 * preference about being interrupted, not a fact about the account, and it stays in
 * lib/onboarding.ts's own storage.
 */
export interface OnboardingStateOut {
  terms_accepted: boolean;
  consent: boolean;
  accounts: number;
  transactions: number;
  /** Whether this deployment can receive mail at all. When false, omit the forwarding
   *  step entirely rather than showing an address that cannot receive anything. */
  forwarding_available: boolean;
  /** consent && accounts > 0 && transactions > 0. Forwarding is never part of it. */
  complete: boolean;
  next_step: "permission" | "brokers" | "history" | null;
}

// ---------------------------------------------------------------------------
// Consent -- app/schemas/consent.py / contracts/openapi.yaml's `consent` tag
// ---------------------------------------------------------------------------

export interface ConsentGrantIn {
  notice_version: string;
  evidence_ref: string;
  purpose?: string;
  lawful_basis?: string;
}

export interface ConsentGrantOut {
  id: string;
  investor_id: string;
  notice_version: string;
  purpose: string;
  lawful_basis: string;
}

export interface ConsentWithdrawOut {
  withdrawn_count: number;
}

export interface ConsentStatusOut {
  has_live_consent: boolean;
}

// ---------------------------------------------------------------------------
// Privacy / DPDP rights -- app/db/privacy.py (not in openapi.yaml -- confirmed by
// grep; these return raw dicts, not Pydantic models, built directly from `SELECT *`
// against the tables named, which is why every row type below mirrors a migration
// rather than a schemas/*.py file).
// ---------------------------------------------------------------------------

export interface PrivacyInvestorOut {
  id: string;
  code: string;
  display_name: string | null;
  family_group_id: string | null;
  onboarding_date: string | null;
  created_at: string;
}

export interface PrivacyAccountOut {
  id: string;
  investor_id: string;
  broker: string;
  dp_id: string | null;
  client_id: string | null;
  is_advised: boolean;
  label: string | null;
}

export interface PrivacyConsentOut {
  id: string;
  investor_id: string;
  notice_version: string;
  purpose: string;
  lawful_basis: string;
  consent_given_at: string;
  withdrawn_at: string | null;
  evidence_ref: string;
}

export interface PrivacyLegalHoldOut {
  id: string;
  investor_id: string;
  reason: string;
  placed_at: string;
  released_at: string | null;
}

export interface PrivacyTransactionOut {
  id: string;
  account_id: string;
  isin: string;
  txn_date: string;
  txn_type: TxnType;
  quantity: string;
  price: string;
  charges: string;
  dividend_amount: string;
  source: string;
  source_ref: string | null;
  dedupe_key: string;
  raw_payload: Record<string, unknown> | null;
  created_at: string;
  seq: number;
}

export interface PrivacyDocumentOut {
  id: string;
  doctype: string;
  storage_key: string;
  sha256: string;
  byte_size: number;
  filename: string | null;
  received_at: string | null;
  stored_at: string;
  parse_status: string;
}

export interface PrivacyIdentifiersOut {
  pan: string | null;
  demat: string | null;
}

export interface PrivacyExportOut {
  investor: PrivacyInvestorOut;
  accounts: PrivacyAccountOut[];
  consents: PrivacyConsentOut[];
  legal_holds: PrivacyLegalHoldOut[];
  transactions: PrivacyTransactionOut[];
  // Present only when the export was requested with include_identifiers=true --
  // a separately audited access event (app/db/privacy.py export_investor).
  identifiers?: PrivacyIdentifiersOut;
  documents: PrivacyDocumentOut[];
}

export interface EraseResultOut {
  investors: number;
  transactions: number;
  documents: number;
}

// ---------------------------------------------------------------------------
// Auth -- app/auth/schemas.py (not in openapi.yaml -- confirmed by grep)
// ---------------------------------------------------------------------------

export interface RegisterRequest {
  email: string;
  password: string;
  display_name?: string | null;
  /**
   * Which Terms + Privacy version was ticked. REQUIRED, and the server rejects any
   * value that is not the one this build serves (app/auth/schemas.py) -- an acceptance
   * of a version nobody was shown is a false record, which is worse than no record.
   * Send `CURRENT_TOS_VERSION` from lib/terms.ts and nothing else.
   */
  tos_version: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface UserResponse {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string;
}

export interface TokenResponse {
  token: string;
  token_type: string;
  expires_in: number;
  user: UserResponse;
  /** The login's oldest owned investor (app/routers/auth.py). Always present on
   * register; null on login when the user owns no investor. Clients take the id from
   * here -- never from localStorage or a build-time default. */
  investor_id: string | null;
}

export interface BatchSummaryOut {
  batch_id: string;
  filename: string | null;
  adapter: string;
  status: string;
  row_count: number;
  rejected_count: number;
  uploaded_at: string;
}

export interface ChatMessageIn {
  role: "user" | "assistant";
  content: string;
}

export interface AskAIRequest {
  messages: ChatMessageIn[];
  context?: string;
}

export interface AskAIResponse {
  reply: string;
}
