"use client";

/**
 * Hooks shared by the research screens.
 *
 * `useSubmit` is the one place a research WRITE is made from the browser, and it owns the
 * Idempotency-Key contract (BLUEPRINT_BACKEND.md 7.1):
 *
 *   - An identical retry (same payload after a failure) REUSES the key, so a request that
 *     actually committed before the connection dropped replays its original result instead of
 *     writing a second note, answer or thesis version.
 *   - A changed payload gets a NEW key -- reusing one for different content is a 409.
 *   - A confirmed success clears the key; the next submission starts fresh.
 *
 * It also keeps the three states a person must be able to tell apart: unsaved input (the
 * form's own state), a PENDING save (`pending`), and a CONFIRMED save (the server response the
 * caller receives). Only a confirmed response is ever rendered as saved.
 */

import { useCallback, useRef, useState } from "react";
import { ApiError, useAuth } from "@trackr/core";

export interface WriteContext {
  investorId: string;
  token: string | null;
}

export function useResearchAuth(): WriteContext {
  const { investorId, token } = useAuth();
  return { investorId, token };
}

function newKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // RFC 4122 v4 from getRandomValues, for browsers without randomUUID.
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6]! & 0x0f) | 0x40;
  b[8] = (b[8]! & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export interface SubmitState<R> {
  submit: (fingerprint: unknown, run: (key: string) => Promise<R>) => Promise<R | null>;
  pending: boolean;
  error: ApiError | Error | null;
  clearError: () => void;
}

export function useSubmit<R>(): SubmitState<R> {
  const key = useRef<string | null>(null);
  const last = useRef<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | Error | null>(null);

  const submit = useCallback(
    async (fingerprint: unknown, run: (key: string) => Promise<R>): Promise<R | null> => {
      const print = JSON.stringify(fingerprint);
      if (key.current === null || last.current !== print) {
        key.current = newKey();
        last.current = print;
      }
      setPending(true);
      setError(null);
      try {
        const result = await run(key.current);
        key.current = null;
        last.current = null;
        return result;
      } catch (err) {
        setError(err instanceof Error ? err : new Error(String(err)));
        return null;
      } finally {
        setPending(false);
      }
    },
    []
  );

  return { submit, pending, error, clearError: () => setError(null) };
}

/** A human sentence for a research API failure, keyed on the stable `code`. */
export function describeError(error: ApiError | Error | null | undefined): string | null {
  if (!error) return null;
  if (error instanceof ApiError) {
    switch (error.code) {
      case "RITUAL_REQUIRED":
        return "Record your own questions for this company first.";
      case "STALE_PREDECESSOR":
        return "Something newer was saved first. Reload to see it before trying again.";
      case "IDEMPOTENCY_CONFLICT":
        return "This submission conflicts with an earlier one. Reload and try again.";
      case "WORKSPACE_WRITES_NOT_READY":
        return "Saving research is switched off on this server until its privacy decisions are recorded.";
      case "WORKSPACE_DISABLED":
      case "WORKSPACE_UNAVAILABLE":
        return "Research is not available on this server right now.";
      case "SOURCE_USE_DENIED":
        return "This use of this kind of source has not been approved yet.";
      case "METRIC_NOT_APPROVED":
        return "This metric is not an approved registry entry yet, so it cannot be recorded.";
      default:
        return error.message || `Request failed (${error.status})`;
    }
  }
  return error.message;
}
