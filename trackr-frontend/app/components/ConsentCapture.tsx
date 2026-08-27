"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import type { ConsentGrantOut, ConsentStatusOut } from "@/lib/api-types";

/** Must match trackr-backend/app/db/consent.py's CURRENT_NOTICE_VERSION -- bump both
 * together whenever the sentence below changes. */
const NOTICE_VERSION = "2026-08-consent-v1";

/** docs/COMPLIANCE.md §3, "The consent language that carries the legal weight" --
 * verbatim, not paraphrased. That sentence is what makes this a document-processing
 * service rather than a regulated data intermediary. */
const NOTICE_TEXT =
  "You will provide your own account statements (CAS, contract notes, broker exports) " +
  "to me for portfolio tracking. I do not access your broker, depository or registrar " +
  "accounts directly, and I do not hold your login credentials.";

/** Required before POST /ingest/csv, POST /ingest/email or manual transaction entry
 * will process anything for this investor -- app.db.consent.require_consent refuses
 * with a 403 otherwise (CLAUDE.md rule 6 / docs/COMPLIANCE.md §1's consent-first
 * requirement). Mirrors AccountOnboarding.tsx's shape, but unlike accounts a real
 * GET endpoint exists here, so status is read fresh rather than cached client-side. */
export function ConsentCapture({
  investorId,
  token,
  onStatusChange,
}: {
  investorId: string;
  token: string | null;
  /** Lets a hosting page react (e.g. hide its own "consent required" banner) the
   * moment consent is granted or withdrawn here, without re-fetching. */
  onStatusChange?: (hasLiveConsent: boolean) => void;
}) {
  const [status, setStatus] = useState<ConsentStatusOut | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!investorId) {
      setStatus(null);
      return;
    }
    setError(null);
    let cancelled = false;
    api
      .get<ConsentStatusOut>(`/investors/${investorId}/consent`, { token })
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof ApiError ? err.message : "Could not load consent status"
          );
      });
    return () => {
      cancelled = true;
    };
  }, [investorId, token]);

  async function handleGrant() {
    setBusy(true);
    setError(null);
    try {
      await api.post<ConsentGrantOut>(`/investors/${investorId}/consent`, {
        token,
        json: {
          notice_version: NOTICE_VERSION,
          evidence_ref: "in-app consent checkbox",
        },
      });
      setStatus({ has_live_consent: true });
      onStatusChange?.(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record consent");
    } finally {
      setBusy(false);
    }
  }

  async function handleWithdraw() {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/investors/${investorId}/consent/withdraw`, { token });
      setAcknowledged(false);
      setStatus({ has_live_consent: false });
      onStatusChange?.(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not withdraw consent");
    } finally {
      setBusy(false);
    }
  }

  if (!investorId) {
    return <p className="text-sm text-navy-400">Save an investor ID above before capturing consent.</p>;
  }

  if (status === null) {
    return (
      <div className="space-y-2">
        {error ? (
          <p className="rounded-lg bg-negative/10 px-3 py-2 text-sm text-negative">{error}</p>
        ) : (
          <p className="text-sm text-navy-400">Checking consent status…</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {error && <p className="rounded-lg bg-negative/10 px-3 py-2 text-sm text-negative">{error}</p>}

      {status.has_live_consent ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-positive/30 bg-positive/10 px-4 py-3">
          <div>
            <p className="text-sm font-medium text-navy-900">Consent granted</p>
            <p className="mt-0.5 text-xs text-navy-500">
              Required for ingestion and manual transaction entry to process this investor&apos;s data.
            </p>
          </div>
          <button
            type="button"
            onClick={handleWithdraw}
            disabled={busy}
            className="press-scale rounded-lg border border-navy-100 px-3 py-1.5 text-xs font-medium text-navy-700 hover:bg-cream-200 disabled:opacity-60"
          >
            {busy ? "Withdrawing…" : "Withdraw consent"}
          </button>
        </div>
      ) : (
        <div className="space-y-3 rounded-lg border border-brass-500/40 bg-brass-50 p-4">
          <p className="text-xs text-navy-700">{NOTICE_TEXT}</p>
          <label className="flex items-start gap-2 text-xs text-navy-700">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
              className="mt-0.5"
            />
            I have read and agree to the above.
          </label>
          <button
            type="button"
            onClick={handleGrant}
            disabled={!acknowledged || busy}
            className="press-scale rounded-lg bg-navy-700 transition-colors px-4 py-2 text-sm font-medium text-cream-50 hover:bg-navy-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Recording…" : "Grant consent"}
          </button>
          <p className="text-xs text-navy-400">
            No client data can be imported or entered for this investor until this is granted --
            docs/COMPLIANCE.md, consent-first.
          </p>
        </div>
      )}
    </div>
  );
}
