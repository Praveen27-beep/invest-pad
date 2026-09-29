/**
 * Browser execution of a sealed research task against the person's OWN model endpoint (BE 23),
 * reused unchanged by chat (BE 24), inline/answer review (BE 25) and Butler selection (BT 08).
 *
 * THE TWO CREDENTIALS NEVER MEET.
 *   - The provider key lives ONLY in this module's in-memory Map, namespaced by login,
 *     investor, agent, configuration version and exact destination origin. It is never written
 *     to localStorage/sessionStorage/IndexedDB, a cookie, a URL, a log, an error object or any
 *     request to Trackr+. It is sent only in the provider's own auth header to that origin.
 *   - The Trackr+ session token is used only by `research-client.ts` for Trackr+ routes. The
 *     adapters below build their headers from scratch and never include it, and it is never
 *     placed in model context.
 * A page reload loses the key by design (memory only); logout clears it (`clearAllKeys`).
 *
 * PROTOCOLS -- verified 2026-09-28 against current sources, not memory:
 *   ANTHROPIC: platform.claude.com/docs/en/api/overview (headers `x-api-key`,
 *     `anthropic-version: 2023-06-01`, `content-type: application/json`) and
 *     /docs/en/build-with-claude/streaming (SSE `message_start`, `content_block_delta` with
 *     `delta.type = "text_delta"`, `ping`, `error`, `message_stop`). The browser opt-in header
 *     `anthropic-dangerous-direct-browser-access: true` is what the official TypeScript SDK
 *     sends when `dangerouslyAllowBrowser` is set (anthropic-sdk-typescript src/client.ts).
 *   OPENAI_COMPATIBLE: `Authorization: Bearer <key>`, POST `{base}/chat/completions`, streamed
 *     `choices[0].delta.content` chunks ending in `data: [DONE]` (openai-node src/client.ts; the
 *     platform.openai.com reference page refused automated fetch with 403 on that date).
 *   An OpenAI-compatible RESPONSE FORMAT IS NOT EVIDENCE OF BROWSER (CORS) SUPPORT. Whether a
 *   given endpoint accepts a browser request is found out by `testConnection`, locally.
 *
 * WHAT A RUN IS (BLUEPRINT_BACKEND.md 8.2), in this order and no other:
 *   1. the key is present locally, and the destination is allowed by this app's CSP;
 *   2. POST attempts -- the SERVER's ten-minute lease starts; a replayed start is NOT
 *      permission to call the provider (`replayed: true` stops here);
 *   3. one provider request, streamed into a local buffer marked unreviewed;
 *   4. POST the strict proposal (retried with the SAME key on a network failure), or a fixed
 *      failure code with no body, or a cancellation that does not claim the provider stopped.
 * There is no automatic model retry, no proxy, no relay, no deployment-key fallback and no
 * sample substitution for a missing key.
 */

import { ApiError } from "@trackr/core";
import {
  newKey,
  rwrite,
  type Agent,
  type ContextPacket,
  type FailureCode,
  type Provider,
  type Task,
} from "./research-client";

// =========================================================================================
// key store (memory only)
// =========================================================================================

export interface KeyScope {
  login: string;
  investorId: string;
  agentId: string;
  agentVersion: number;
  origin: string;
}

const KEYS = new Map<string, string>();

function scopeId(s: KeyScope): string {
  return [s.login, s.investorId, s.agentId, String(s.agentVersion), s.origin].join("\u0000");
}

export function originOf(baseUrl: string): string {
  return new URL(baseUrl).origin;
}

export function scopeFor(login: string, investorId: string, agent: Agent): KeyScope {
  return {
    login,
    investorId,
    agentId: agent.id,
    agentVersion: agent.version,
    origin: originOf(agent.base_url),
  };
}

export function setKey(scope: KeyScope, key: string): void {
  KEYS.set(scopeId(scope), key);
}

export function hasKey(scope: KeyScope): boolean {
  return KEYS.has(scopeId(scope));
}

export function clearKey(scope: KeyScope): void {
  KEYS.delete(scopeId(scope));
}

/** Logout, identity change or investor switch. */
export function clearAllKeys(): void {
  KEYS.clear();
}

function keyFor(scope: KeyScope): string | null {
  return KEYS.get(scopeId(scope)) ?? null;
}

// =========================================================================================
// destination policy (mirrors next.config.mjs connect-src)
// =========================================================================================

/** The provider origins this app's Content-Security-Policy lets the page reach. The same env
 * value feeds `connect-src`, so an endpoint outside it would be blocked by the browser anyway;
 * checking first gives a plain explanation instead of an opaque network error. */
export function allowedModelOrigins(): string[] {
  const raw = process.env.NEXT_PUBLIC_MODEL_ORIGINS ?? "https://api.anthropic.com https://api.openai.com";
  return raw.split(/[\s,]+/).filter((o) => o.startsWith("https://"));
}

export function destinationAllowed(baseUrl: string): boolean {
  try {
    return allowedModelOrigins().includes(originOf(baseUrl));
  } catch {
    return false;
  }
}

// =========================================================================================
// errors -- reduced locally to the fixed code set; no body, URL, header or trace is kept
// =========================================================================================

export class ProviderError extends Error {
  constructor(public readonly code: FailureCode, message: string) {
    super(message);
    this.name = "ProviderError";
  }
}

/** Raised before anything leaves the browser. No attempt is started. */
export class RunBlocked extends Error {
  constructor(
    public readonly reason: "NO_KEY" | "DESTINATION_BLOCKED" | "PRECONDITION" | "BUDGET" | "REPLAYED_START",
    message: string
  ) {
    super(message);
    this.name = "RunBlocked";
  }
}

function statusCode(status: number): FailureCode {
  if (status === 401 || status === 403) return "AUTH_FAILED";
  if (status === 429 || status === 529) return "RATE_LIMITED";
  return "PROVIDER_UNREACHABLE";
}

const MESSAGES: Record<FailureCode, string> = {
  PROVIDER_UNREACHABLE:
    "The model endpoint could not be reached from this browser (network, CORS, TLS or this app's content policy).",
  AUTH_FAILED: "The model endpoint refused the key held in this browser.",
  RATE_LIMITED: "The model endpoint is rate limiting or overloaded.",
  CLIENT_CLOSED: "The request was stopped in this browser before a complete answer arrived.",
  INVALID_OUTPUT: "The model's output was not a valid proposal; nothing was shown or recorded.",
};

// =========================================================================================
// adapters
// =========================================================================================

interface ProviderRequest {
  system: string;
  user: string;
  maxTokens: number;
  signal: AbortSignal;
  /** Untrusted text, for a local "receiving" indicator only. */
  onText?: (chunk: string) => void;
}

async function* sseEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<{ event: string; data: string }> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) yield { event, data: data.join("\n") };
    }
  }
}

async function send(url: string, headers: Record<string, string>, body: unknown, signal: AbortSignal): Promise<Response> {
  let res: Response;
  try {
    // credentials: "omit" -- no cookie of any origin rides along; referrerPolicy keeps the
    // Workspace URL (which names an investor) out of the provider's logs.
    res = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal,
      credentials: "omit",
      referrerPolicy: "no-referrer",
      mode: "cors",
      cache: "no-store",
    });
  } catch (err) {
    if (signal.aborted) throw err;
    throw new ProviderError("PROVIDER_UNREACHABLE", MESSAGES.PROVIDER_UNREACHABLE);
  }
  if (!res.ok || !res.body) {
    // The provider's body is NOT read: it may echo the request and has no business here.
    throw new ProviderError(statusCode(res.status), MESSAGES[statusCode(res.status)]);
  }
  return res;
}

async function callAnthropic(agent: Agent, key: string, req: ProviderRequest): Promise<string> {
  const res = await send(
    `${agent.base_url.replace(/\/$/, "")}/v1/messages`,
    {
      "content-type": "application/json",
      "x-api-key": key,
      "anthropic-version": "2023-06-01",
      "anthropic-dangerous-direct-browser-access": "true",
    },
    {
      model: agent.model,
      max_tokens: req.maxTokens,
      stream: true,
      system: req.system,
      messages: [{ role: "user", content: req.user }],
    },
    req.signal
  );
  let text = "";
  for await (const ev of sseEvents(res.body!)) {
    if (ev.event === "ping") continue;
    let data: { type?: string; delta?: { type?: string; text?: string }; error?: { type?: string } };
    try {
      data = JSON.parse(ev.data);
    } catch {
      throw new ProviderError("INVALID_OUTPUT", MESSAGES.INVALID_OUTPUT);
    }
    if (data.type === "error") {
      const t = data.error?.type ?? "";
      throw new ProviderError(
        t === "overloaded_error" || t === "rate_limit_error" ? "RATE_LIMITED" : "PROVIDER_UNREACHABLE",
        MESSAGES.PROVIDER_UNREACHABLE
      );
    }
    if (data.type === "content_block_delta" && data.delta?.type === "text_delta" && data.delta.text) {
      text += data.delta.text;
      req.onText?.(data.delta.text);
    }
  }
  return text;
}

async function callOpenAICompatible(agent: Agent, key: string, req: ProviderRequest): Promise<string> {
  const res = await send(
    `${agent.base_url.replace(/\/$/, "")}/chat/completions`,
    { "content-type": "application/json", authorization: `Bearer ${key}` },
    {
      model: agent.model,
      stream: true,
      max_tokens: req.maxTokens,
      messages: [
        { role: "system", content: req.system },
        { role: "user", content: req.user },
      ],
    },
    req.signal
  );
  let text = "";
  for await (const ev of sseEvents(res.body!)) {
    if (ev.data === "[DONE]") break;
    let data: { choices?: { delta?: { content?: string } }[]; error?: unknown };
    try {
      data = JSON.parse(ev.data);
    } catch {
      throw new ProviderError("INVALID_OUTPUT", MESSAGES.INVALID_OUTPUT);
    }
    if (data.error) throw new ProviderError("PROVIDER_UNREACHABLE", MESSAGES.PROVIDER_UNREACHABLE);
    const chunk = data.choices?.[0]?.delta?.content;
    if (chunk) {
      text += chunk;
      req.onText?.(chunk);
    }
  }
  return text;
}

const ADAPTERS: Record<Provider, (agent: Agent, key: string, req: ProviderRequest) => Promise<string>> = {
  ANTHROPIC: callAnthropic,
  OPENAI_COMPATIBLE: callOpenAICompatible,
};

// =========================================================================================
// test connection (local only)
// =========================================================================================

export interface ConnectionResult {
  ok: boolean;
  code: FailureCode | "DESTINATION_BLOCKED" | "NO_KEY" | null;
  message: string;
  checkedAt: string;
}

/** A minimal documented request, straight from this browser. The result is what THIS browser
 * observed and is never sent to Trackr+; no server field claims a key works. */
export async function testConnection(scope: KeyScope, agent: Agent): Promise<ConnectionResult> {
  const checkedAt = new Date().toISOString();
  if (!destinationAllowed(agent.base_url)) {
    return { ok: false, code: "DESTINATION_BLOCKED", message: "This app's content policy does not allow that endpoint.", checkedAt };
  }
  const key = keyFor(scope);
  if (!key) return { ok: false, code: "NO_KEY", message: "No key is held in this browser for this configuration.", checkedAt };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20_000);
  try {
    await ADAPTERS[agent.provider](agent, key, {
      system: "Reply with the single word ok.",
      user: "ok?",
      maxTokens: 5,
      signal: controller.signal,
    });
    return { ok: true, code: null, message: "This browser reached the endpoint and the key was accepted.", checkedAt };
  } catch (err) {
    if (err instanceof ProviderError) return { ok: false, code: err.code, message: err.message, checkedAt };
    return { ok: false, code: "CLIENT_CLOSED", message: MESSAGES.CLIENT_CLOSED, checkedAt };
  } finally {
    clearTimeout(timer);
  }
}

// =========================================================================================
// running a task
// =========================================================================================

/** Research methods: the packet as data, the closed output shape as data. Everything inside
 * ordered_context is quoted corpus, never instruction (also stated in system_instructions). */
function researchPrompt(packet: ContextPacket): { system: string; user: string } {
  return {
    system: packet.system_instructions,
    user: JSON.stringify({
      task: { purpose: packet.purpose, brief: packet.brief },
      output_contract: packet.skill.output_contract,
      ordered_context: packet.ordered_context,
      prior_chat_turns: packet.prior_chat_turns,
      calculation_results: packet.calculation_results,
      exclusions: packet.exclusions,
      value_reference_rule:
        "Use value_refs {context_id, field} and {{vN}} placeholders for every number, date, period and label.",
    }),
  };
}

function butlerPrompt(packet: ContextPacket): { system: string; user: string } {
  const b = packet.butler_packet!;
  return {
    system: b.system_prompt,
    user: JSON.stringify({ output_schema: b.proposal_shape, packet: b.packet }),
  };
}

/** Pull one JSON object out of the model's text. Anything else is INVALID_OUTPUT. */
export function parseProposal(text: string): unknown {
  let body = text.trim();
  const fenced = /^```(?:json)?\s*([\s\S]*?)\s*```$/.exec(body);
  if (fenced) body = fenced[1]!;
  try {
    const value = JSON.parse(body);
    if (value && typeof value === "object" && !Array.isArray(value)) return value;
  } catch {
    /* fall through */
  }
  throw new ProviderError("INVALID_OUTPUT", MESSAGES.INVALID_OUTPUT);
}

export interface RunContext {
  investorId: string;
  token: string | null;
  scope: KeyScope;
  agent: Agent;
  task: Task;
  packet: ContextPacket;
  signal: AbortSignal;
  /** Local, untrusted progress. Butler passes nothing: its raw stream is never shown. */
  onText?: (chunk: string) => void;
  onPhase?: (phase: "starting" | "requesting" | "submitting") => void;
}

export type RunOutcome =
  | { kind: "SUBMITTED"; task: Task }
  | { kind: "FAILED"; code: FailureCode; message: string; task: Task | null }
  | { kind: "CANCELLED"; task: Task | null }
  | { kind: "UNCERTAIN"; message: string; localDraft: string | null };

async function withRetry<T>(fn: () => Promise<T>): Promise<T> {
  // Submission uncertainty only: the SAME idempotency key is reused, so a request that
  // committed before the connection dropped replays its original result.
  let lastError: unknown;
  for (let i = 0; i < 3; i++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err;
      if (err instanceof ApiError) throw err; // the server answered; do not repeat
      await new Promise((r) => setTimeout(r, 400 * (i + 1)));
    }
  }
  throw lastError;
}

export async function runTask(rc: RunContext): Promise<RunOutcome> {
  const { investorId, token, agent, task, packet } = rc;
  const isButler = packet.butler_packet !== null;
  const key = keyFor(rc.scope);
  if (!key) throw new RunBlocked("NO_KEY", "Enter a key for this agent in this browser first. Nothing was started.");
  if (!destinationAllowed(agent.base_url)) {
    throw new RunBlocked("DESTINATION_BLOCKED", "This app's content policy does not allow that endpoint. Nothing was started.");
  }
  if (packet.precondition.state !== "READY") {
    throw new RunBlocked("PRECONDITION", "This method's precondition is not met: " +
      packet.precondition.missing.map((m) => m.code).join(", "));
  }
  const prompt = isButler ? butlerPrompt(packet) : researchPrompt(packet);
  const budget = isButler ? packet.butler_packet!.budgets : null;
  if (budget && Math.ceil((prompt.system.length + prompt.user.length) / 4) > budget.max_input_tokens) {
    throw new RunBlocked("BUDGET", "The sealed packet exceeds the input budget; narrow the review. Nothing was sent.");
  }

  rc.onPhase?.("starting");
  const ctxFor = (k: string) => ({ investorId, token, idempotencyKey: k });
  const start = await rwrite.startAttempt(ctxFor(newKey()), task.id, { mode: "BROWSER_MODEL" });
  if (start.replayed) {
    throw new RunBlocked("REPLAYED_START", "That attempt was already started elsewhere; no second request was sent.");
  }
  const attemptId = start.attempt.id;

  // One provider request, bounded by our own timeout (Butler: its 60-second budget).
  const local = new AbortController();
  const onAbort = () => local.abort();
  rc.signal.addEventListener("abort", onAbort);
  const timeoutMs = (budget?.client_timeout_seconds ?? 240) * 1000;
  const timer = setTimeout(() => local.abort(), timeoutMs);
  let text: string | null = null;
  rc.onPhase?.("requesting");
  try {
    text = await ADAPTERS[agent.provider](agent, key, {
      ...prompt,
      maxTokens: budget?.max_output_tokens ?? 4000,
      signal: local.signal,
      onText: rc.onText,
    });
  } catch (err) {
    clearTimeout(timer);
    rc.signal.removeEventListener("abort", onAbort);
    if (rc.signal.aborted) {
      const t = await withRetry(() => rwrite.submitCancellation(ctxFor(newKey()), task.id, attemptId)).catch(() => null);
      return { kind: "CANCELLED", task: t };
    }
    const code: FailureCode = err instanceof ProviderError ? err.code : "CLIENT_CLOSED";
    const t = await withRetry(() => rwrite.submitFailure(ctxFor(newKey()), task.id, attemptId, code)).catch(() => null);
    return { kind: "FAILED", code, message: MESSAGES[code], task: t };
  }
  clearTimeout(timer);
  rc.signal.removeEventListener("abort", onAbort);

  let proposal: unknown;
  try {
    proposal = parseProposal(text);
  } catch {
    const t = await withRetry(() => rwrite.submitFailure(ctxFor(newKey()), task.id, attemptId, "INVALID_OUTPUT")).catch(() => null);
    return { kind: "FAILED", code: "INVALID_OUTPUT", message: MESSAGES.INVALID_OUTPUT, task: t };
  }

  rc.onPhase?.("submitting");
  const submitKey = newKey();
  try {
    const saved = await withRetry(() =>
      rwrite.submitResult(ctxFor(submitKey), task.id, attemptId, packet.context_digest, proposal)
    );
    return { kind: "SUBMITTED", task: saved };
  } catch (err) {
    if (err instanceof ApiError && err.code === "LEASE_EXPIRED") {
      return {
        kind: "UNCERTAIN",
        message: "The attempt's lease expired before the proposal was recorded. It is kept below as a local draft only; it is not recorded research.",
        localDraft: isButler ? null : JSON.stringify(proposal, null, 2),
      };
    }
    if (err instanceof ApiError) {
      return { kind: "FAILED", code: "INVALID_OUTPUT", message: err.message, task: null };
    }
    return {
      kind: "UNCERTAIN",
      message: "The proposal may or may not have been recorded. Reload the task to see its real state; nothing will be resent automatically.",
      localDraft: null,
    };
  }
}
