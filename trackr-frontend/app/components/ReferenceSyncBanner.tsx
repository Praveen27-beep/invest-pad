"use client";

import { useEffect, useRef } from "react";
import { useAuth } from "@/lib/auth-context";
import { useFetch } from "@/lib/use-fetch";
import { broadcastPortfolioRefresh } from "@/lib/onboarding";

interface ReferenceStatus {
  enabled: boolean;
  state: "idle" | "processing" | "retrying" | "needs_evidence";
  pending: number;
  retrying: number;
  last_success_at: string | null;
  unresolved: { isin: string; reason: string }[];
}

export function ReferenceSyncBanner() {
  const { investorId, token } = useAuth();
  const result = useFetch<ReferenceStatus>(
    investorId ? `/investors/${investorId}/reference-status` : null,
    undefined, token, { refreshMs: 15_000 },
  );
  const previous = useRef<string | null>(null);
  const stamp = result.data?.last_success_at ?? null;
  useEffect(() => {
    const key = `${investorId}:${stamp}`;
    if (previous.current !== null && previous.current !== key) broadcastPortfolioRefresh();
    previous.current = key;
  }, [investorId, stamp]);
  if (result.error) return (
    <p role="status" className="rounded-lg border p-3 text-sm">
      Automatic reconciliation status is unavailable. Portfolio figures may be incomplete.
    </p>
  );
  const data = result.data;
  if (!data || (data.enabled && data.state === "idle")) return null;
  const message = !data.enabled
    ? "Automatic reference updates are disabled."
    : data.state === "retrying"
      ? "Some reference checks are waiting for source data. We’ll retry automatically. Figures may be incomplete."
      : data.state === "processing"
        ? "Checking security changes and corporate actions. Available figures are shown while this completes."
        : "Some corporate actions need further evidence. Their effects may be missing from these figures.";
  return (
    <div
      role="status"
      className="rounded-lg border p-3 text-sm space-y-2"
      style={{ marginBottom: "var(--space-6)" }}
    >
      <p>{message}</p>
      {data.unresolved.length > 0 && (
        <details>
          <summary>{data.unresolved.length} unresolved security changes</summary>
          <ul className="mt-2 space-y-1">
            {data.unresolved.map((item, index) => (
              <li key={`${item.isin}:${index}`}>{item.isin}: {item.reason}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
