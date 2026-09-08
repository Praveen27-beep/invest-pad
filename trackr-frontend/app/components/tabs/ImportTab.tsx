"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError } from "@/lib/api-client";
import { useFetch } from "@/lib/use-fetch";
import type { AccountOut, BatchSummaryOut, BrokerOut, ConsentStatusOut, StageResultOut } from "@/lib/api-types";
import { Banner, Button, Card, Input } from "../ds";
import { ConsentCapture } from "../ConsentCapture";
import { StagingBatch } from "../StagingBatch";
import { FileUploadStep } from "../onboarding/FileUploadStep";

function summaryFromBatchRow(row: BatchSummaryOut): StageResultOut {
  return {
    batch_id: row.batch_id,
    parsed: row.row_count,
    rejected: row.rejected_count,
    sha256: "",
    document_id: null,
    notes: [],
  };
}

/**
 * The upload flow, reused unchanged from the onboarding wizard's `FileUploadStep`.
 *
 * This used to be its own form here: a hardcoded two-way choice between "Zerodha
 * tradebook (CSV)" and "Contract note (XLSX)", with a disabled "Adapter" dropdown that
 * only ever showed one working option. Every broker other than Zerodha silently had
 * nowhere to go. `FileUploadStep` already solves this the right way — one drop zone,
 * `POST /ingest/files` classifies each file itself and routes it to whichever adapter
 * (or none, with a plain sentence) actually applies — and it already reads the broker
 * registry (`GET /brokers`) instead of naming brokers in this component, so a broker
 * added there needs no change here. Reusing it rather than re-solving the same problem
 * a second time is also what keeps the two screens from drifting apart.
 */
export function ImportTab() {
  const { investorId, token } = useAuth();
  const router = useRouter();
  const [batches, setBatches] = useState<StageResultOut[]>([]);
  const [searchBatchId, setSearchBatchId] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [hasLiveConsent, setHasLiveConsent] = useState<boolean | null>(null);

  // The staged-batch list lives on the SERVER, not in this component's state -- a
  // refresh used to orphan every staged batch behind a UUID nobody could see anywhere.
  const refreshBatches = useCallback(async () => {
    if (!token || !investorId) return;
    try {
      const rows = await api.get<BatchSummaryOut[]>("/ingest/batches", {
        query: { investor_id: investorId, status: "STAGED" },
        token,
      });
      setBatches(rows.map(summaryFromBatchRow));
    } catch (err) {
      if (err instanceof ApiError) setLoadError(err.message);
    }
  }, [investorId, token]);

  useEffect(() => {
    void refreshBatches();
  }, [refreshBatches]);

  const accounts = useFetch<AccountOut[]>(
    investorId ? `/investors/${investorId}/accounts` : null,
    undefined,
    token
  );
  const brokers = useFetch<BrokerOut[]>(investorId ? "/brokers" : null, undefined, token);

  useEffect(() => {
    if (!investorId) return;
    let cancelled = false;
    api
      .get<ConsentStatusOut>(`/investors/${investorId}/consent`, { token })
      .then((s) => {
        if (!cancelled) setHasLiveConsent(s.has_live_consent);
      })
      .catch(() => {
        if (!cancelled) setHasLiveConsent(null);
      });
    return () => {
      cancelled = true;
    };
  }, [investorId, token]);

  if (!investorId) {
    return (
      <Banner tone="info">
        No investor selected. Set one up in Settings to import trades.
      </Banner>
    );
  }

  function handleLoadBatch(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = searchBatchId.trim();
    if (!trimmed) return;
    setBatches((prev) => {
      if (prev.some((b) => b.batch_id === trimmed)) return prev;
      return [
        { batch_id: trimmed, parsed: 0, rejected: 0, sha256: "", document_id: null, notes: [] },
        ...prev,
      ];
    });
    setSearchBatchId("");
    setLoadError(null);
  }

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <Card title="Upload a statement" subtitle="From any broker — we work out what each file is.">
        <div style={{ display: "grid", gap: 16 }}>
          {hasLiveConsent === false && (
            <Banner tone="warning" title="One step first: record consent for this investor">
              Indian data-protection law (DPDP) requires an explicit OK before this app processes
              anyone&apos;s statements, including your own. It&apos;s a one-time click per investor.
              <div style={{ marginTop: 10 }}>
                <ConsentCapture
                  investorId={investorId}
                  token={token}
                  onStatusChange={(live) => setHasLiveConsent(live)}
                />
              </div>
            </Banner>
          )}

          {hasLiveConsent !== false && (
            <FileUploadStep
              accounts={accounts.data ?? []}
              brokers={brokers.data ?? []}
              onStaged={() => void refreshBatches()}
              onTypeInstead={() => router.push("/transactions")}
            />
          )}
        </div>
      </Card>

      <Card title="Review staged batches" subtitle="Nothing here reaches the ledger until you promote it.">
        {loadError && <Banner tone="negative">{loadError}</Banner>}
        {batches.length === 0 ? (
          <p style={{ margin: 0, font: "var(--type-body-sm)", color: "var(--text-tertiary)" }}>
            Nothing staged yet — upload a file above, or look one up by batch ID below.
          </p>
        ) : (
          <div style={{ display: "grid", gap: 12 }}>
            {batches.map((b) => (
              <StagingBatch key={b.batch_id} stageResult={b} />
            ))}
          </div>
        )}
      </Card>

      <Card title="Look up an existing batch" subtitle="Have a batch ID from somewhere else? Pull it in here.">
        <form onSubmit={handleLoadBatch} style={{ display: "flex", gap: 10 }}>
          <div style={{ flex: 1 }}>
            <Input
              value={searchBatchId}
              onChange={setSearchBatchId}
              placeholder="e.g. c195c00f-264c-4fae-ad45-d1135da22ed2"
              style={{ fontFamily: "var(--font-mono)" }}
            />
          </div>
          <Button type="submit" variant="secondary">
            Load batch
          </Button>
        </form>
      </Card>
    </div>
  );
}
