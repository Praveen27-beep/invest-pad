"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

/**
 * Compatibility only, matching Plus's `/portfolio` exactly.
 *
 * This one TRANSLATES rather than forwarding verbatim, because its `?tab=` named routes that
 * now exist in their own right. `?isin=` is carried through to whichever route it lands on.
 * An unrecognised tab goes to Transactions rather than 404ing -- the URL was valid once, and
 * the ledger is the honest default for a link that meant "my records".
 */
const TAB_ROUTES: Record<string, string> = {
  transactions: "/transactions",
  import: "/import",
  reconcile: "/reconcile",
};

export default function Portfolio() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = searchParams.get("tab") ?? "transactions";
  const isin = searchParams.get("isin");

  useEffect(() => {
    const base = TAB_ROUTES[tab] ?? "/transactions";
    router.replace(isin ? `${base}?isin=${encodeURIComponent(isin)}` : base);
  }, [tab, isin, router]);

  return null;
}
