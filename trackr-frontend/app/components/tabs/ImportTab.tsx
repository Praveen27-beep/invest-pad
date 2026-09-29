"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError } from "@/lib/api-client";
import { useFetch } from "@/lib/use-fetch";
import type { AccountOut, BatchSummaryOut, BrokerOut, ConsentStatusOut, StageResultOut } from "@/lib/api-types";
import { Banner, Card, Skeleton } from "../ds";
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
 *
 * THERE IS NO "LOOK UP A BATCH BY ID" FORM. It asked for a UUID, which is a debugging
 * affordance wearing a product's clothes: nobody has a batch id to hand, and the one place
 * they used to come from -- a staged batch the page had forgotten -- is exactly what
 * `GET /ingest/batches` fixed. The list below shows every STAGED batch this investor has,
 * from the server, so there is nothing left for a person to paste in.
 */
export function ImportTab() {
  const { investorId, token } = useAuth();
  const [batches, setBatches] = useState<StageResultOut[]>([]);
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

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <Card title="Upload a statement" subtitle="From any broker. We work out what each file is.">
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

          {/* Until the accounts land, `accounts.data` is undefined and FileUploadStep's
              honest answer to "no accounts" is a warning banner -- which flashed up on
              every visit and vanished a moment later. A placeholder of the right shape is
              the truthful thing to show while we do not know yet. */}
          {hasLiveConsent !== false &&
            (accounts.loading || brokers.loading ? (
              <div style={{ display: "grid", gap: 10 }}>
                <Skeleton height={112} />
                <Skeleton height={12} width="52%" />
              </div>
            ) : (
              <FileUploadStep
                accounts={accounts.data ?? []}
                brokers={brokers.data ?? []}
                onStaged={() => void refreshBatches()}
              />
            ))}
        </div>
      </Card>

      <Card title="Review staged batches" subtitle="Nothing here reaches the ledger until you promote it.">
        {loadError && <Banner tone="negative">{loadError}</Banner>}
        {batches.length === 0 ? (
          <p style={{ margin: 0, font: "var(--type-body-sm)", color: "var(--text-tertiary)" }}>
            Nothing staged yet. Upload a file above and it will appear here.
          </p>
        ) : (
          <div style={{ display: "grid", gap: 12 }}>
            {batches.map((b) => (
              <StagingBatch key={b.batch_id} stageResult={b} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
