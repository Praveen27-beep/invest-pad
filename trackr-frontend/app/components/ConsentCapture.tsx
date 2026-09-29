"use client";

import { useEffect, useState, type CSSProperties } from "react";
import { api, ApiError } from "@/lib/api-client";
import { CONSENT_NOTICE_TEXT } from "@/lib/consent";
import { openOnboarding } from "@/lib/onboarding";
import type { ConsentStatusOut } from "@/lib/api-types";
import { Banner, Button, Icon, Skeleton } from "./ds";

/**
 * Consent, in Settings: status and withdrawal. Never a second way to grant it.
 *
 * WHY THIS NO LONGER GRANTS. There were two consent user interfaces — this one and the
 * wizard's permission step — each with its own checkbox, its own copy of the notice text
 * and its own copy of the version string. Two surfaces recording the same legal fact will
 * drift, and a drifted notice version makes the consent record invalid rather than merely
 * inconsistent (docs/ONBOARDING_AS_IS_VS_TO_BE.md, loophole L10). So there is now exactly
 * one place in this product that grants consent: the setup flow. This screen shows what is
 * on file, offers withdrawal, and sends anyone who needs to grant it to the one surface
 * that does that — which is a link, not a duplicate implementation.
 *
 * WITHDRAWAL STAYS HERE, and belongs here. It is a management action on an existing
 * record, not a second copy of the grant: it needs no notice text, no version and no
 * checkbox, so there is nothing for it to drift against.
 *
 * WITHDRAWING IS NOT ERASING, and the copy below says so plainly rather than letting the
 * more comfortable reading stand. Processing stops immediately; what is already stored is
 * removed from the Privacy page, deliberately as a separate, deliberate act.
 */
export function ConsentCapture({
  investorId,
  token,
  onStatusChange,
}: {
  investorId: string;
  token: string | null;
  /** Lets a hosting page react (e.g. hide its own "consent required" banner) the
   * moment consent is withdrawn here, without re-fetching. */
  onStatusChange?: (hasLiveConsent: boolean) => void;
}) {
  const [status, setStatus] = useState<ConsentStatusOut | null>(null);
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
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load consent status");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [investorId, token]);

  async function handleWithdraw() {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/investors/${investorId}/consent/withdraw`, { token });
      setStatus({ has_live_consent: false });
      onStatusChange?.(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not withdraw consent");
    } finally {
      setBusy(false);
    }
  }

  if (!investorId) {
    return (
      <p style={{ margin: 0, font: "var(--type-body-sm)", color: "var(--text-tertiary)" }}>
        Create an investor above before capturing consent.
      </p>
    );
  }

  if (status === null) {
    // A placeholder the shape of the panel that replaces it, rather than a line of text:
    // the sentence was a different height from the panel, so the card around this resized
    // the instant the status arrived. Shape first, content a moment later -- the same thing
    // the dashboard does with its figures.
    return error ? <Banner tone="negative">{error}</Banner> : <Skeleton height={64} />;
  }

  return (
    <div style={{ display: "grid", gap: 12 }}>
      {error && <Banner tone="negative">{error}</Banner>}

      {status.has_live_consent ? (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            flexWrap: "wrap",
            padding: "12px 14px",
            border: "1px solid var(--border)",
            borderLeft: "2px solid var(--positive)",
            background: "var(--surface)",
          }}
        >
          <div style={{ minWidth: 200, flex: 1 }}>
            <p
              style={{
                margin: 0,
                display: "flex",
                alignItems: "center",
                gap: 6,
                font: "var(--type-body)",
                fontWeight: "var(--weight-medium)" as CSSProperties["fontWeight"],
                color: "var(--text-primary)",
              }}
            >
              <span style={{ color: "var(--positive)", display: "inline-flex" }}>
                <Icon name="check" size={14} />
              </span>
              Permission granted
            </p>
            <p style={{ margin: "2px 0 0", font: "var(--type-body-sm)", color: "var(--text-tertiary)" }}>
              Withdrawing stops us processing anything new, immediately. It does not delete
              what is already stored. That is on the Privacy page, on purpose.
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => void handleWithdraw()} disabled={busy}>
            {busy ? "Withdrawing…" : "Withdraw"}
          </Button>
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gap: 10,
            padding: "12px 14px",
            border: "1px solid var(--border)",
            borderLeft: "2px solid var(--warning)",
            background: "var(--surface)",
          }}
        >
          <p
            style={{
              margin: 0,
              font: "var(--type-body)",
              fontWeight: "var(--weight-medium)" as CSSProperties["fontWeight"],
              color: "var(--text-primary)",
            }}
          >
            No permission on file
          </p>
          <p style={{ margin: 0, font: "var(--type-body-sm)", color: "var(--text-secondary)" }}>
            Nothing can be imported or entered for this investor until this is granted.
          </p>
          <p
            style={{
              margin: 0,
              font: "var(--type-body-sm)",
              color: "var(--text-secondary)",
              background: "var(--surface-sunken)",
              border: "1px solid var(--border)",
              padding: "10px 12px",
            }}
          >
            {CONSENT_NOTICE_TEXT}
          </p>
          <div>
            <Button size="sm" onClick={() => openOnboarding("access")}>
              Grant permission
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
