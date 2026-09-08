"use client";

import { useState, type CSSProperties, type ReactNode } from "react";
import type { AccountOut } from "@/lib/api-types";
import { Banner, SegmentedControl } from "./ds";
import { CopyField } from "./CopyField";

type Provider = "gmail" | "outlook" | "yahoo";

const PROVIDERS: { value: Provider; label: string }[] = [
  { value: "gmail", label: "Gmail" },
  { value: "outlook", label: "Outlook" },
  { value: "yahoo", label: "Yahoo" },
];

/** `{code}-{broker}-{doctype}@{domain}` (app.ingest.addresses.forwarding_addresses) --
 * the last hyphen-separated segment of the local part is the document type, used only
 * as a friendly label above each address. */
function doctypeLabel(address: string): string {
  const local = address.split("@")[0] ?? address;
  const parts = local.split("-");
  return parts[parts.length - 1] || local;
}

/**
 * Per-account, per-provider copy-paste walkthrough for docs/INGESTION.md's "Setup UX" --
 * the only client-side friction in the whole ingestion pipeline.
 *
 * ADDRESSES COME FROM THE ACCOUNT, and this component never constructs one. That is what
 * makes the empty case correct rather than blank: `forwarding_addresses` is empty both
 * for a broker with no email adapter and for a deployment with no mail-receiving domain,
 * and in either case the honest thing on screen is a sentence saying so — which this
 * component already did, and which is why the backend gate was written to reuse it.
 *
 * THE CONFIRMATION-CODE STEP TELLS THE TRUTH. Gmail will not forward anything until a
 * code it emails to the address is pasted back into Gmail's settings, and nothing here
 * reads that code yet: the webhook loops over attachments and never opens the message
 * body. The wizard's version of this screen used to claim "we handle it — nothing for you
 * to click", which meant nobody could ever complete Gmail's own setup and the product
 * looked broken rather than incomplete (docs/ONBOARDING_AS_IS_VS_TO_BE.md, loophole L2).
 */
export function EmailForwardingSetup({ account }: { account: AccountOut }) {
  const [provider, setProvider] = useState<Provider>("gmail");

  if (account.forwarding_addresses.length === 0) {
    return (
      <Banner tone="info">
        No forwarding address for <strong>{account.broker}</strong> — either we have no
        email adapter for this broker yet, or inbound mail isn&apos;t configured on this
        deployment. Uploading files on the Import page works either way.
      </Banner>
    );
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      {account.forwarding_addresses.map((address) => (
        <div key={address} style={{ display: "grid", gap: 4 }}>
          <p
            style={{
              margin: 0,
              font: "var(--type-label)",
              textTransform: "uppercase",
              letterSpacing: "var(--tracking-label)",
              color: "var(--text-tertiary)",
            }}
          >
            {doctypeLabel(address)} forwarding address
          </p>
          <CopyField value={address} label={`${account.broker} ${doctypeLabel(address)} address`} />
        </div>
      ))}

      <div style={{ display: "grid", gap: 10 }}>
        <SegmentedControl
          value={provider}
          onChange={(v) => setProvider(v as Provider)}
          options={PROVIDERS}
        />
        <div style={{ font: "var(--type-body-sm)", color: "var(--text-secondary)" }}>
          {provider === "gmail" && (
            <Steps
              items={[
                <>Open a sample email from your broker in Gmail.</>,
                <>
                  Click the three-dot menu on the email and choose{" "}
                  <strong>Filter messages like this</strong> — so only your broker&apos;s
                  mail is forwarded, never your whole inbox.
                </>,
                <>
                  In the filter dialog, tick <strong>Forward it to</strong> and select the
                  address above.
                </>,
                <>
                  Click <strong>Create filter</strong>.
                </>,
                <>
                  Gmail emails a confirmation code to that address and will not forward
                  anything until it is pasted back into Gmail&apos;s forwarding settings.{" "}
                  <strong>We can&apos;t read that code for you yet</strong>, so forwarding
                  won&apos;t activate until we can — file upload is unaffected.
                </>,
              ]}
            />
          )}

          {provider === "outlook" && (
            <Steps
              items={[
                <>Open Settings → Mail → Rules.</>,
                <>
                  Add a rule with condition <strong>From</strong> your broker&apos;s sending
                  address (optionally also <strong>Subject includes</strong> &quot;Contract
                  Note&quot;).
                </>,
                <>
                  Set the action to <strong>Forward to</strong> and paste the address above.
                </>,
                <>Save the rule.</>,
              ]}
            />
          )}

          {provider === "yahoo" && (
            <div style={{ display: "grid", gap: 10 }}>
              <Banner tone="warning">
                Yahoo Mail has no selective-forwarding filter, so it cannot forward only
                your broker&apos;s messages — and forwarding everything is exactly what we
                promised not to ask for.
              </Banner>
              <Steps
                items={[
                  <>
                    In Yahoo, forward your mailbox to a Gmail account you control (Settings
                    → More Settings → Forwarding).
                  </>,
                  <>
                    In that Gmail account, follow the Gmail steps above to filter and
                    forward only the broker&apos;s emails on to the address above.
                  </>,
                ]}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Steps({ items }: { items: ReactNode[] }) {
  return (
    <ol style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 8 }}>
      {items.map((item, index) => (
        <li key={index} style={{ lineHeight: 1.55 } as CSSProperties}>
          {item}
        </li>
      ))}
    </ol>
  );
}
