"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import type { AccountOut } from "@/lib/api-types";
import { useFetch } from "@/lib/use-fetch";

/** MProfit's "Set up Auto-import" step (Mprofit auto forward Gmail.png) -- the
 * ongoing path, as opposed to HistoricalImportStep's one-time backfill. Every new
 * Zerodha contract note that lands in the client's inbox from now on forwards here
 * automatically, no manual upload ever again. */
export function GmailForwardStep() {
  const { investorId, token } = useAuth();
  const [copied, setCopied] = useState(false);

  const accounts = useFetch<AccountOut[]>(
    investorId ? `/investors/${investorId}/accounts` : null,
    undefined,
    token
  );
  const zerodhaAccount = accounts.data?.find((a) => a.broker.toLowerCase() === "zerodha");
  const address = zerodhaAccount?.forwarding_addresses[0];

  function copy() {
    if (!address) return;
    navigator.clipboard
      .writeText(address)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {
        // Some browser contexts restrict clipboard access outright -- the address is
        // still selectable/copyable by hand from the <code> element either way, so
        // this is a silent no-op rather than an error the user needs to see.
      });
  }

  if (!investorId) return null;

  if (accounts.loading) {
    return <p className="text-sm text-navy-400">Loading your forwarding address…</p>;
  }

  if (!address) {
    return (
      <p className="text-sm text-navy-400">
        Add a Zerodha broker account in Settings first — your personal forwarding address
        is generated from it.
      </p>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <label className="mb-1 block text-xs font-medium text-navy-600">Your forwarding address</label>
        <div className="flex items-center gap-2 rounded-lg border border-navy-100 bg-cream-50 px-3 py-2">
          <code className="flex-1 truncate text-sm text-navy-900">{address}</code>
          <button
            type="button"
            onClick={copy}
            className="press-scale shrink-0 rounded-md bg-navy-700 px-3 py-1.5 text-xs font-medium text-cream-50 hover:bg-navy-600"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>
      </div>

      <ol className="space-y-3 text-sm text-navy-600">
        <li className="flex gap-3">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-navy-100 text-[11px] font-medium text-navy-700">
            1
          </span>
          <span>
            In Gmail, open <span className="font-medium">Settings → See all settings → Forwarding and POP/IMAP</span>.
          </span>
        </li>
        <li className="flex gap-3">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-navy-100 text-[11px] font-medium text-navy-700">
            2
          </span>
          <span>
            Click <span className="font-medium">Add a forwarding address</span> and paste the address above.
          </span>
        </li>
        <li className="flex gap-3">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-navy-100 text-[11px] font-medium text-navy-700">
            3
          </span>
          <span>Gmail sends a confirmation to that address automatically — no action needed from you there.</span>
        </li>
        <li className="flex gap-3">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-navy-100 text-[11px] font-medium text-navy-700">
            4
          </span>
          <span>
            Back in Gmail settings, select <span className="font-medium">Forward a copy of incoming mail to</span> this
            address, then Save Changes.
          </span>
        </li>
      </ol>

      <p className="text-[11px] text-navy-400">
        Once set up, every future Zerodha contract-note email lands here automatically —
        nothing more to upload.
      </p>
    </div>
  );
}
