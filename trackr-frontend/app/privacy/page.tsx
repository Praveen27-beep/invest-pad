"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError } from "@/lib/api-client";
import type { EraseResultOut, PrivacyExportOut } from "@/lib/api-types";
import { Card, NoInvestorState } from "../components/PageState";
import { PageBody } from "../components/Shell";

// Must be typed exactly, not just any non-empty text -- this is the type-to-confirm
// gate in front of an irreversible delete (app/db/privacy.py erase_investor).
const ERASE_CONFIRM_PHRASE = "DELETE MY DATA";

function downloadJson(payload: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function PrivacyPage() {
  const { investorId, token, setInvestorId } = useAuth();

  const [exporting, setExporting] = useState(false);
  const [exportingIdentifiers, setExportingIdentifiers] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportResult, setExportResult] = useState<PrivacyExportOut | null>(null);
  const [exportedIdentifiers, setExportedIdentifiers] = useState(false);
  const [showJson, setShowJson] = useState(false);

  const [identifiersPanelOpen, setIdentifiersPanelOpen] = useState(false);
  const [identifiersAck, setIdentifiersAck] = useState(false);

  const [erasePanelOpen, setErasePanelOpen] = useState(false);
  const [eraseConfirmText, setEraseConfirmText] = useState("");
  const [erasing, setErasing] = useState(false);
  const [eraseError, setEraseError] = useState<string | null>(null);
  const [legalHoldReasons, setLegalHoldReasons] = useState<string[] | null>(null);
  const [eraseResult, setEraseResult] = useState<EraseResultOut | null>(null);

  // Erasure clears investorId (the record no longer exists), so the success screen
  // below must render even though the "no investor" guard would otherwise fire.
  if (!investorId && !eraseResult) return <NoInvestorState />;

  async function runExport(includeIdentifiers: boolean) {
    const setBusy = includeIdentifiers ? setExportingIdentifiers : setExporting;
    setBusy(true);
    setExportError(null);
    try {
      const res = await api.get<PrivacyExportOut>("/privacy/export", {
        token,
        query: { investor_id: investorId, include_identifiers: includeIdentifiers },
      });
      setExportResult(res);
      setExportedIdentifiers(includeIdentifiers);
      setShowJson(false);
      setIdentifiersPanelOpen(false);
      setIdentifiersAck(false);
    } catch (err) {
      setExportError(err instanceof ApiError ? err.message : "Export failed");
    } finally {
      setBusy(false);
    }
  }

  async function runErase() {
    if (eraseConfirmText !== ERASE_CONFIRM_PHRASE) return;
    setErasing(true);
    setEraseError(null);
    setLegalHoldReasons(null);
    try {
      const res = await api.post<EraseResultOut>("/privacy/erase", {
        token,
        query: { investor_id: investorId },
      });
      setEraseResult(res);
      setErasePanelOpen(false);
      setInvestorId("");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && err.reasons) {
        // Legal-hold refusal -- named reasons, not a generic failure toast.
        setLegalHoldReasons(err.reasons);
      } else {
        setEraseError(err instanceof ApiError ? err.message : "Erasure failed");
      }
    } finally {
      setErasing(false);
    }
  }

  if (eraseResult) {
    return (
      <PageBody>
      <div className="max-w-2xl space-y-6">
        <Card title="Account erased">
          <p className="text-sm text-navy-700">
            This investor&apos;s data has been permanently deleted: {eraseResult.investors}{" "}
            investor record, {eraseResult.transactions} transaction
            {eraseResult.transactions === 1 ? "" : "s"} and {eraseResult.documents} stored
            document{eraseResult.documents === 1 ? "" : "s"} removed.
          </p>
          <p className="mt-2 text-xs text-navy-400">
            The audit trail of this erasure is kept, as DPDP and SEBI both require, but
            it no longer carries any of the investor&apos;s data, only the fact that a
            deletion happened.
          </p>
          <p className="mt-4 text-xs text-navy-400">
            This browser no longer has an investor selected. Set a different investor ID
            in{" "}
            <a href="/settings" className="text-brass-600 underline">
              Settings
            </a>{" "}
            to continue.
          </p>
        </Card>
      </div>
      </PageBody>
    );
  }

  return (
    <PageBody>
      <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="font-heading text-2xl text-navy-900">Privacy &amp; your data</h1>
        <p className="mt-1 text-sm text-navy-400">
          Your rights under the DPDP Act, 2023, for investor{" "}
          <span className="font-mono text-navy-600">{investorId}</span>. See and export
          everything held about them, or have it permanently deleted.
        </p>
      </div>

      <Card title="Export your data">
        <p className="mb-4 text-sm text-navy-600">
          Downloads a full copy of everything held about this investor: accounts,
          consents, the full transaction ledger, legal holds and stored-document
          references, as JSON. This is a record of holdings and performance, not
          investment advice.
        </p>

        {exportError && (
          <p className="mb-4 rounded-lg bg-negative/10 px-3 py-2 text-sm text-negative">
            {exportError}
          </p>
        )}

        <button
          type="button"
          onClick={() => runExport(false)}
          disabled={exporting}
          className="press-scale rounded-lg bg-navy-700 transition-colors px-4 py-2 text-sm font-medium text-cream-50 hover:bg-navy-600 disabled:opacity-60"
        >
          {exporting ? "Exporting…" : "Export my data"}
        </button>

        {exportResult && (
          <div className="mt-5 space-y-3 rounded-lg border border-navy-100 bg-cream-50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium text-navy-900">
                Export ready{exportedIdentifiers ? ", includes PAN & demat" : ""}
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowJson((v) => !v)}
                  className="text-xs text-brass-600 underline"
                >
                  {showJson ? "Hide JSON" : "View JSON"}
                </button>
                <button
                  type="button"
                  onClick={() => downloadJson(exportResult, `trackr-export-${investorId}.json`)}
                  className="press-scale rounded-lg border border-navy-100 px-3 py-1.5 text-xs font-medium text-navy-700 hover:bg-cream-200"
                >
                  Download JSON
                </button>
              </div>
            </div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs text-navy-600 sm:grid-cols-4">
              <div>
                <dt className="text-navy-400">Accounts</dt>
                <dd className="tabular-nums">{exportResult.accounts.length}</dd>
              </div>
              <div>
                <dt className="text-navy-400">Transactions</dt>
                <dd className="tabular-nums">{exportResult.transactions.length}</dd>
              </div>
              <div>
                <dt className="text-navy-400">Documents</dt>
                <dd className="tabular-nums">{exportResult.documents.length}</dd>
              </div>
              <div>
                <dt className="text-navy-400">Consents</dt>
                <dd className="tabular-nums">{exportResult.consents.length}</dd>
              </div>
            </dl>
            {showJson && (
              <pre className="max-h-96 overflow-auto rounded-lg bg-navy-900 p-3 text-[11px] leading-relaxed text-cream-100">
                {JSON.stringify(exportResult, null, 2)}
              </pre>
            )}
          </div>
        )}

        <div className="mt-6 border-t border-dashed border-navy-100 pt-4">
          {!identifiersPanelOpen ? (
            <button
              type="button"
              onClick={() => setIdentifiersPanelOpen(true)}
              className="text-xs text-navy-500 underline decoration-dotted"
            >
              Include PAN &amp; demat number in the export
            </button>
          ) : (
            <div className="space-y-3 rounded-lg border border-brass-500/40 bg-brass-50 p-4">
              <p className="text-xs text-navy-700">
                This decrypts and includes the investor&apos;s PAN and demat number in the
                exported file. It is logged as a separate, audited access event every time
                it&apos;s used, distinct from the plain export above. Only do this if the
                identifiers are actually needed in the file (e.g. moving records to
                another adviser).
              </p>
              <label className="flex items-start gap-2 text-xs text-navy-700">
                <input
                  type="checkbox"
                  checked={identifiersAck}
                  onChange={(e) => setIdentifiersAck(e.target.checked)}
                  className="mt-0.5"
                />
                I understand this decrypts the PAN and demat number and is separately
                audited.
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={!identifiersAck || exportingIdentifiers}
                  onClick={() => runExport(true)}
                  className="press-scale rounded-lg bg-brass-600 transition-colors px-4 py-2 text-xs font-medium text-cream-50 hover:bg-brass-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {exportingIdentifiers ? "Exporting…" : "Export with PAN & demat"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIdentifiersPanelOpen(false);
                    setIdentifiersAck(false);
                  }}
                  className="px-3 py-2 text-xs text-navy-400 hover:text-navy-700"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </Card>

      <Card title="Delete your account">
        <p className="mb-4 text-sm text-navy-600">
          Permanently deletes this investor&apos;s accounts, stored documents and full
          transaction ledger. This cannot be undone, and there will be nothing left to
          reverse a mistake against.
        </p>

        {eraseError && (
          <p className="mb-4 rounded-lg bg-negative/10 px-3 py-2 text-sm text-negative">
            {eraseError}
          </p>
        )}

        {legalHoldReasons && (
          <div className="mb-4 rounded-lg border border-negative/30 bg-negative/10 p-4">
            <p className="text-sm font-medium text-negative">
              Erasure refused: open legal hold
            </p>
            <p className="mt-1 text-xs text-navy-600">
              This investor&apos;s records are under a legal hold and can&apos;t be
              self-service deleted right now. Where a dispute has been raised, records are
              kept until it resolves or SEBI directs otherwise.
            </p>
            <ul className="mt-2 list-inside list-disc text-xs text-navy-700">
              {legalHoldReasons.map((reason, i) => (
                <li key={i}>{reason}</li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-navy-500">
              Contact your adviser if you believe this hold should be reviewed or
              released.
            </p>
          </div>
        )}

        {!erasePanelOpen ? (
          <button
            type="button"
            onClick={() => setErasePanelOpen(true)}
            className="press-scale rounded-lg bg-negative transition-colors px-4 py-2 text-sm font-medium text-cream-50 hover:opacity-90"
          >
            Delete my account
          </button>
        ) : (
          <div className="space-y-3 rounded-lg border border-negative/30 bg-negative/5 p-4">
            <p className="text-sm text-navy-700">
              Type <span className="font-mono font-semibold">{ERASE_CONFIRM_PHRASE}</span>{" "}
              to confirm. This deletes investor{" "}
              <span className="font-mono">{investorId}</span> and everything linked to it,
              right now.
            </p>
            <input
              value={eraseConfirmText}
              onChange={(e) => setEraseConfirmText(e.target.value)}
              placeholder={ERASE_CONFIRM_PHRASE}
              className="w-full rounded-lg border border-negative/40 bg-surface px-3 py-2 text-sm font-mono focus:border-negative focus:outline-none"
            />
            <div className="flex gap-2">
              <button
                type="button"
                disabled={eraseConfirmText !== ERASE_CONFIRM_PHRASE || erasing}
                onClick={runErase}
                className="press-scale rounded-lg bg-negative transition-colors px-4 py-2 text-sm font-medium text-cream-50 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {erasing ? "Deleting…" : "Permanently delete"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setErasePanelOpen(false);
                  setEraseConfirmText("");
                }}
                className="px-3 py-2 text-sm text-navy-400 hover:text-navy-700"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </Card>
    </div>
    </PageBody>
  );
}
