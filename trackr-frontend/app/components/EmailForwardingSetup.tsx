"use client";

import { useState } from "react";
import type { AccountOut } from "@/lib/api-types";
import { CopyField } from "./CopyField";

type Provider = "gmail" | "outlook" | "yahoo";

const PROVIDERS: { id: Provider; label: string }[] = [
  { id: "gmail", label: "Gmail" },
  { id: "outlook", label: "Outlook" },
  { id: "yahoo", label: "Yahoo" },
];

/** `{code}-{broker}-{doctype}@{domain}` (app.ingest.addresses.forwarding_addresses) --
 * the last hyphen-separated segment of the local part is the document type, used only
 * as a friendly label above each address. */
function doctypeLabel(address: string): string {
  const local = address.split("@")[0] ?? address;
  const parts = local.split("-");
  return parts[parts.length - 1] || local;
}

/** Per-account, per-provider copy-paste walkthrough for docs/INGESTION.md's "Setup UX"
 * -- the only client-side friction in the whole ingestion pipeline. Addresses come
 * from the account's own `forwarding_addresses` (Session 10's onboarding response);
 * this component never constructs one. */
export function EmailForwardingSetup({ account }: { account: AccountOut }) {
  const [provider, setProvider] = useState<Provider>("gmail");

  if (account.forwarding_addresses.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-navy-100 bg-cream-50 px-4 py-3">
        <p className="text-sm text-navy-600">
          No email adapter is registered for <span className="font-medium">{account.broker}</span> yet
          — this account can still receive transactions via CSV import on the Import page.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {account.forwarding_addresses.map((address) => (
        <div key={address} className="space-y-1">
          <p className="text-[11px] font-medium uppercase tracking-wide text-navy-400">
            {doctypeLabel(address)} forwarding address
          </p>
          <CopyField value={address} label={`${account.broker} ${doctypeLabel(address)} address`} />
        </div>
      ))}

      <div>
        <div className="flex gap-1 border-b border-navy-100">
          {PROVIDERS.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setProvider(p.id)}
              className={`press-scale -mb-px rounded-t-lg px-3 py-2 text-xs font-medium transition-colors ${
                provider === p.id
                  ? "border-b-2 border-brass-500 text-navy-900"
                  : "text-navy-400 hover:text-navy-700"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="pt-3 text-sm text-navy-700">
          {provider === "gmail" && (
            <ol className="list-decimal space-y-2 pl-4">
              <li>Open a sample email from your broker in Gmail.</li>
              <li>
                Click the three-dot menu on the email and choose{" "}
                <span className="font-medium">&quot;Filter messages like this&quot;</span>.
              </li>
              <li>
                In the filter dialog, check <span className="font-medium">&quot;Forward it to&quot;</span>{" "}
                and select the address above.
              </li>
              <li>
                Click <span className="font-medium">Create filter</span>.
              </li>
              <li>
                Gmail won&apos;t forward mail until the address is verified: it emails a confirmation
                code to that address, which you have to paste back into Gmail&apos;s forwarding
                settings before forwarding activates.
              </li>
            </ol>
          )}

          {provider === "outlook" && (
            <ol className="list-decimal space-y-2 pl-4">
              <li>Open Settings → Mail → Rules.</li>
              <li>
                Add a new rule with condition <span className="font-medium">From</span> your broker&apos;s
                sending address (optionally also <span className="font-medium">Subject includes</span>{" "}
                &quot;Contract Note&quot;).
              </li>
              <li>
                Set the action to <span className="font-medium">Forward to</span> and paste the address
                above.
              </li>
              <li>Save the rule.</li>
            </ol>
          )}

          {provider === "yahoo" && (
            <div className="space-y-2">
              <p className="rounded-lg bg-brass-50 px-3 py-2 text-xs text-navy-700">
                Yahoo Mail can&apos;t forward only specific messages — there is no selective-forwarding
                filter, so this address can&apos;t be set up directly in Yahoo.
              </p>
              <ol className="list-decimal space-y-2 pl-4">
                <li>
                  In Yahoo, forward your entire mailbox to a Gmail account you control (Settings → More
                  Settings → Forwarding).
                </li>
                <li>
                  In that Gmail account, follow the Gmail steps above to filter and forward only the
                  broker&apos;s emails on to the address above.
                </li>
              </ol>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
