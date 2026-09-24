"use client";

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError } from "@/lib/api-client";
import type { AccountOut, BrokerOut } from "@/lib/api-types";
import { Banner, Checkbox, Input } from "../ds";

/**
 * Step 2 — where do you trade? A screen that did not exist.
 *
 * WHAT USED TO HAPPEN INSTEAD. Nothing asked. The permission step silently created one
 * account with `broker: "ZERODHA"`, so a Groww user was handed a Zerodha account and
 * never told, every file landed in it, and a multi-broker investor had to find the raw
 * form on the Settings page by themselves — the wizard never mentioned that more than one
 * account was possible (docs/ONBOARDING_AS_IS_VS_TO_BE.md, loopholes L7 and L15).
 *
 * NOTHING IN THE DATABASE HAD TO CHANGE for this. `account` has always been a plain
 * many-to-one on `investor`, PDF passwords have always been per-broker, and forwarding
 * addresses have always been derived from the adapter registry. What was missing was a
 * question, and honesty about the answers.
 *
 * KEPT TO NAMES ONLY. Per-broker capability badges (notes/book/files/email) used to sit
 * beside each row; this list is just "which brokers do you use", so it now shows only the
 * broker name and its checkbox. What each broker can parse still comes from `GET /brokers`
 * and still drives the ingestion behaviour elsewhere — it just isn't restated here.
 *
 * ADDING, NEVER REMOVING. Unticking a broker you already have an account with does not
 * delete it. Accounts own transactions, and a checkbox is not a safe place to put "erase
 * a broker's entire history" — deleting one is a deliberate act that belongs on the
 * Privacy page, where it is spelled out. Existing accounts render ticked and locked.
 */
export function BrokerPickerStep({
  onAccountsChanged,
  onReadyChange,
}: {
  /** Fires after accounts are created, so the wizard can advance and the next step can
   * see them. */
  onAccountsChanged: (accounts: AccountOut[]) => void;
  onReadyChange?: (state: { busy: boolean; canContinue: boolean; save: () => void }) => void;
}) {
  const { investorId, token } = useAuth();
  const [brokers, setBrokers] = useState<BrokerOut[] | null>(null);
  const [existing, setExisting] = useState<AccountOut[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [otherName, setOtherName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!investorId) return;
    let cancelled = false;
    Promise.all([
      api.get<BrokerOut[]>("/brokers", { token }),
      api.get<AccountOut[]>(`/investors/${investorId}/accounts`, { token }),
    ])
      .then(([registry, accounts]) => {
        if (cancelled) return;
        setBrokers(registry);
        setExisting(accounts);
      })
      .catch((err) => {
        if (!cancelled) setError(friendly(err));
      });
    return () => {
      cancelled = true;
    };
  }, [investorId, token]);

  /** Broker codes this investor already has an account for. Compared case-insensitively:
   *  `account.broker` is free text and older rows were written by a form that did not
   *  normalise it. */
  const owned = useMemo(
    () => new Set(existing.map((a) => a.broker.trim().toUpperCase())),
    [existing]
  );

  const trimmedOther = otherName.trim().toUpperCase();
  const canContinue = picked.size > 0 || trimmedOther.length > 0 || owned.size > 0;

  const save = useCallback(async () => {
    if (!investorId) return;
    const wanted = [...picked, ...(trimmedOther ? [trimmedOther] : [])].filter(
      (code) => !owned.has(code)
    );
    if (wanted.length === 0) {
      // Everything ticked already exists. Nothing to write, and writing anyway would
      // leave a second account for the same broker that nothing could tell apart.
      onAccountsChanged(existing);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created: AccountOut[] = [];
      for (const broker of wanted) {
        created.push(
          await api.post<AccountOut>(`/investors/${investorId}/accounts`, {
            token,
            // client_id is left null on purpose. It is the broker's own code for this
            // account (Zerodha calls it UCC), and asking a person to go and look one up
            // before they have seen anything would be the worst possible first question.
            // It fills itself in from the first document that states it.
            json: { broker, dp_id: null, client_id: null, is_advised: true, label: null },
          })
        );
      }
      const all = [...existing, ...created];
      setExisting(all);
      setPicked(new Set());
      setOtherName("");
      onAccountsChanged(all);
    } catch (err) {
      setError(friendly(err));
    } finally {
      setBusy(false);
    }
  }, [investorId, token, picked, trimmedOther, owned, existing, onAccountsChanged]);

  useEffect(() => {
    onReadyChange?.({ busy, canContinue, save: () => void save() });
  }, [busy, canContinue, save, onReadyChange]);

  if (!investorId) return null;

  if (error && brokers === null) {
    return (
      <Banner tone="negative" title="We couldn't load the broker list">
        {error}
      </Banner>
    );
  }

  if (brokers === null) {
    return (
      <p style={{ margin: 0, font: "var(--type-body)", color: "var(--text-tertiary)" }}>
        Loading brokers…
      </p>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {error && (
        <Banner tone="negative" title="We couldn't add that">
          {error}
        </Banner>
      )}

      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
        {brokers.map((broker) => {
          const already = owned.has(broker.code);
          return (
            <li
              key={broker.code}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                flexWrap: "wrap",
                padding: "10px 12px",
                border: "1px solid var(--border)",
                background: already ? "var(--surface-sunken)" : "var(--surface)",
              }}
            >
              <Checkbox
                id={`broker-${broker.code}`}
                checked={already || picked.has(broker.code)}
                onChange={
                  already
                    ? undefined
                    : (on) =>
                        setPicked((current) => {
                          const next = new Set(current);
                          if (on) next.add(broker.code);
                          else next.delete(broker.code);
                          return next;
                        })
                }
                label={
                  <span
                    style={{
                      font: "var(--type-body)",
                      fontWeight: "var(--weight-medium)" as CSSProperties["fontWeight"],
                      color: "var(--text-primary)",
                    }}
                  >
                    {broker.name}
                  </span>
                }
                style={{ flex: 1, minWidth: 140 }}
              />
              {already && (
                <span style={{ font: "var(--type-label)", color: "var(--text-tertiary)" }}>
                  already added
                </span>
              )}
            </li>
          );
        })}

        <li
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
            padding: "10px 12px",
            border: "1px solid var(--border)",
            background: "var(--surface)",
          }}
        >
          <span
            style={{
              font: "var(--type-body)",
              fontWeight: "var(--weight-medium)" as CSSProperties["fontWeight"],
              color: "var(--text-primary)",
              minWidth: 140,
              flex: 1,
            }}
          >
            Someone else
          </span>
          <Input
            id="broker-other"
            value={otherName}
            onChange={setOtherName}
            placeholder="Name your broker"
            style={{ maxWidth: 200, textTransform: "uppercase" }}
          />
        </li>
      </ul>
    </div>
  );
}

function friendly(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401 || err.status === 403) {
      return "Your session looks stale. Sign out and back in, then try again.";
    }
    if (err.status >= 500) return "Our server had a problem with that. Try again in a moment.";
    return err.message;
  }
  return "We couldn't reach the server. Check your connection and try again.";
}
