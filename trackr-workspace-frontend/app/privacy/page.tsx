"use client";

/**
 * Workspace Privacy: export everything held about this portfolio, or have it erased.
 *
 * REACHABLE WITHOUT THE WORKSPACE CAPABILITY, AND THAT IS THE POINT. DPDP export and
 * erasure are rights, not features of a tier. `docs/PRODUCT_ARCHITECTURE.md` section 4:
 * "Loss of capability is not deletion and must not block privacy rights." A downgraded
 * account reaches this screen through the rail exactly as a Workspace account does, and
 * the export it receives still contains everything the account owns.
 *
 * It calls the SAME `/privacy/export` and `/privacy/erase` endpoints Plus does -- there
 * is deliberately no Workspace privacy surface, because a second implementation of
 * erasure is a second thing that can be incomplete.
 *
 * Erasure is irreversible, so it is gated behind a typed confirmation phrase rather than
 * a button that can be clicked by accident. A legal hold refuses it, and the reasons are
 * shown rather than collapsed into a generic failure.
 */

import { useState } from "react";
import { ApiError, api, useAuth } from "@trackr/core";
import type { EraseResultOut, PrivacyExportOut } from "@trackr/core";

/** Must be typed exactly. This is the gate in front of an irreversible delete. */
const ERASE_CONFIRM_PHRASE = "DELETE MY DATA";

function downloadJson(payload: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function Privacy() {
  const { token, investorId } = useAuth();

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [holds, setHolds] = useState<string[] | null>(null);
  const [erased, setErased] = useState<EraseResultOut | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [includeIdentifiers, setIncludeIdentifiers] = useState(false);

  async function exportData() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.get<PrivacyExportOut>("/privacy/export", {
        token,
        query: { investor_id: investorId, include_identifiers: includeIdentifiers },
      });
      downloadJson(result, `trackr-export-${investorId}.json`);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Export failed.");
    } finally {
      setBusy(false);
    }
  }

  async function erase() {
    setBusy(true);
    setError(null);
    setHolds(null);
    try {
      const result = await api.post<EraseResultOut>("/privacy/erase", {
        token,
        query: { investor_id: investorId },
      });
      setErased(result);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.reasons) setHolds(err.reasons);
      setError(err instanceof ApiError ? err.message : "Erasure failed.");
    } finally {
      setBusy(false);
    }
  }

  if (erased) {
    return (
      <div className="ws-panel" style={{ maxWidth: 560, padding: 24 }}>
        <h1 className="ws-h1">Deleted</h1>
        <p className="ws-sub">
          {erased.investors} investor record{erased.investors === 1 ? "" : "s"},{" "}
          {erased.transactions} transaction{erased.transactions === 1 ? "" : "s"} and{" "}
          {erased.documents} document{erased.documents === 1 ? "" : "s"} were erased. The
          minimum audit record required by law is retained.
        </p>
      </div>
    );
  }

  return (
    <>
      <header style={{ marginBottom: 20 }}>
        <h1 className="ws-h1">Privacy &amp; your data</h1>
        <p className="ws-sub">
          Export everything held about this portfolio, or have it deleted. Available on
          every account, whatever products it has.
        </p>
      </header>

      {!investorId && (
        <div className="ws-notice">There is no investor record attached to this sign-in.</div>
      )}

      {error && (
        <div className="ws-notice ws-notice--error" style={{ marginBottom: 18 }}>
          {error}
          {holds && (
            <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
              {holds.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {investorId && (
        <div className="ws-grid" style={{ maxWidth: 640 }}>
          <section className="ws-card">
            <p className="ws-card-title">Export</p>
            <p className="ws-sub" style={{ marginBottom: 12 }}>
              A JSON file containing the investor record, accounts, consents, legal holds,
              every transaction and every document reference.
            </p>
            <label style={{ display: "flex", alignItems: "flex-start", gap: 9, marginBottom: 14 }}>
              <input
                type="checkbox"
                checked={includeIdentifiers}
                onChange={(event) => setIncludeIdentifiers(event.target.checked)}
                style={{ marginTop: 3 }}
              />
              <span>
                Include PAN and demat identifiers
                <span className="ws-muted" style={{ display: "block" }}>
                  Decrypting these is a separately audited access event.
                </span>
              </span>
            </label>
            <button
              type="button"
              className="ws-btn ws-btn--primary"
              onClick={exportData}
              disabled={busy}
            >
              {busy ? "Working…" : "Download export"}
            </button>
          </section>

          <section className="ws-card">
            <p className="ws-card-title">Erase</p>
            <p className="ws-sub" style={{ marginBottom: 12 }}>
              Permanently deletes this investor, its transactions and its stored documents.
              This cannot be undone, and an open legal hold will refuse it.
            </p>
            <label className="ws-field">
              <span className="ws-field-label">
                Type <span className="ws-mono">{ERASE_CONFIRM_PHRASE}</span> to confirm
              </span>
              <input
                className="ws-input"
                value={confirmText}
                onChange={(event) => setConfirmText(event.target.value)}
                autoComplete="off"
              />
            </label>
            <button
              type="button"
              className="ws-btn"
              onClick={erase}
              disabled={busy || confirmText !== ERASE_CONFIRM_PHRASE}
              style={{ borderColor: "var(--ws-negative)", color: "var(--ws-negative)" }}
            >
              Erase everything
            </button>
          </section>
        </div>
      )}
    </>
  );
}
