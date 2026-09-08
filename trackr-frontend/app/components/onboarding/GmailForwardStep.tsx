"use client";

import { useState, type CSSProperties, type ReactNode } from "react";
import type { AccountOut } from "@/lib/api-types";
import { Banner, Icon } from "../ds";

/**
 * Gmail's own steps, honestly.
 *
 * TWO OF THE OLD FOUR WERE FALSE, and both mattered. Step 3 said "Gmail sends a
 * confirmation. We handle it — nothing for you to click", and nothing handled it: the
 * webhook loops over attachments and never reads the message body, so the confirmation
 * code is silently discarded and forwarding cannot be completed by anyone, ever. Saying
 * so is not a nice admission, but a person who follows an instruction that cannot work
 * concludes the product is broken rather than that the instruction was wrong.
 *
 * Step 4 said "Forward a copy of INCOMING MAIL", which is the entire inbox — flatly
 * contradicting the promise made two screens earlier that you decide what reaches us.
 * The filter route forwards only the broker's mail, which is what we actually want and
 * what we actually said (docs/ONBOARDING_AS_IS_VS_TO_BE.md, loopholes L2 and L3).
 */
const INSTRUCTIONS: ReactNode[] = [
  <>Open an email your broker sent you, in Gmail.</>,
  <>
    Click the three-dot menu on that email and choose{" "}
    <strong>Filter messages like this</strong> — so only your broker&apos;s mail is ever
    forwarded, not your inbox.
  </>,
  <>
    Tick <strong>Forward it to</strong>, add the address above, and create the filter.
  </>,
  <>
    Gmail emails a confirmation code to that address before it will forward anything.{" "}
    <strong>We can&apos;t collect that code for you yet</strong>, so forwarding will not
    activate until we can. Everything else here works today.
  </>,
];

/**
 * The last step, which is optional and may never happen — and that is a finished setup.
 *
 * IT IS NOT SHOWN AT ALL when this deployment has no mail-receiving domain. That is
 * decided by one backend condition in the one place addresses are derived
 * (`app.ingest.addresses.forwarding_addresses` returns `[]` for an unset or RFC 2606
 * reserved domain), so the wizard, Settings and the broker picker's "email" badge all
 * switch off together and none of them can show a `@ingest.example.com` address that by
 * definition can never receive mail. The day a real INGEST_DOMAIN is configured, they all
 * come back on their own — no feature flag to remember to flip.
 *
 * IT ITERATES ACCOUNTS rather than looking for Zerodha. Three brokers is three addresses,
 * each with its own Gmail verification. That is a real cost of the per-(broker, doctype)
 * scheme and the reason a single per-investor inbox address is the named next step; until
 * that exists, showing all of them beats showing one and calling it "your address".
 */
export function GmailForwardStep({ accounts }: { accounts: AccountOut[] }) {
  const withAddresses = accounts.filter((a) => a.forwarding_addresses.length > 0);

  if (withAddresses.length === 0) {
    return (
      <Banner tone="info" title="No forwarding address for your brokers yet">
        Forwarding only works for brokers we can read email from, and none of yours is one
        today. Uploading files works exactly as well — this step is a convenience, not a
        requirement.
      </Banner>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "grid", gap: 12 }}>
        {withAddresses.map((account) => (
          <AccountAddresses key={account.id} account={account} />
        ))}
      </div>

      {withAddresses.length > 1 && (
        <p style={{ margin: 0, font: "var(--type-body-sm)", color: "var(--text-tertiary)" }}>
          Gmail verifies each address separately, so this is one filter and one
          confirmation per broker.
        </p>
      )}

      <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 10 }}>
        {INSTRUCTIONS.map((instruction, index) => (
          <li key={index} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: 18,
                height: 18,
                flexShrink: 0,
                border: "1px solid var(--border-strong)",
                borderRadius: "var(--radius-full)",
                font: "var(--type-label)",
                color: "var(--text-secondary)",
              }}
            >
              {index + 1}
            </span>
            <span style={{ font: "var(--type-body)", color: "var(--text-secondary)" }}>
              {instruction}
            </span>
          </li>
        ))}
      </ol>

      <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
        <p
          style={{
            margin: "0 0 4px",
            font: "var(--type-body-sm)",
            fontWeight: "var(--weight-medium)" as CSSProperties["fontWeight"],
            color: "var(--text-primary)",
          }}
        >
          And your past mail
        </p>
        <p style={{ margin: 0, font: "var(--type-body-sm)", color: "var(--text-tertiary)" }}>
          Forwarding only catches new mail. For everything before today, download from your
          broker&apos;s console and upload it on the Import page — that is the complete and
          reliable route.
        </p>
      </div>
    </div>
  );
}

function AccountAddresses({ account }: { account: AccountOut }) {
  return (
    <div>
      <p
        style={{
          margin: "0 0 6px",
          font: "var(--type-label)",
          textTransform: "uppercase",
          letterSpacing: "var(--tracking-label)",
          color: "var(--text-tertiary)",
        }}
      >
        {account.label ?? account.broker}
      </p>
      <div style={{ display: "grid", gap: 6 }}>
        {account.forwarding_addresses.map((address) => (
          <CopyableAddress key={address} address={address} />
        ))}
      </div>
    </div>
  );
}

function CopyableAddress({ address }: { address: string }) {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard
      .writeText(address)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {
        // Clipboard access is blocked outright in some contexts. The address sits in a
        // selectable element either way, so this is a silent no-op rather than an error
        // the person has to dismiss.
      });
  }

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        border: "1px solid var(--border)",
        background: "var(--surface-sunken)",
        padding: "8px 8px 8px 12px",
      }}
    >
      <code
        style={{
          flex: 1,
          minWidth: 0,
          font: "var(--type-mono)",
          color: "var(--text-primary)",
          overflowWrap: "anywhere",
        }}
      >
        {address}
      </code>
      <button
        type="button"
        onClick={copy}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          flexShrink: 0,
          padding: "6px 12px",
          border: "1px solid var(--border-strong)",
          borderRadius: "var(--radius-sm)",
          background: "var(--surface)",
          color: "var(--text-primary)",
          font: "var(--type-body-sm)",
          fontWeight: "var(--weight-medium)" as CSSProperties["fontWeight"],
          cursor: "pointer",
        }}
      >
        <Icon name={copied ? "check" : "document"} size={13} />
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
