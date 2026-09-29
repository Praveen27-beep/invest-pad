"use client";

/**
 * A client-side compatibility redirect that keeps the query string.
 *
 * WHY THESE ROUTES EXIST IN WORKSPACE AT ALL. `docs/PRODUCT_ARCHITECTURE.md` requires route
 * parity: the same path works in either deployment, so a link someone saved from Plus resolves
 * here too. `@trackr/portfolio`'s `REDIRECTS` is the shared list of which paths forward where;
 * this is the local React glue, because routing is each app's own.
 *
 * THE QUERY SURVIVES. A compatibility redirect that dropped the parameters would land a saved
 * `/performance?range=1y` on an unfiltered Dashboard -- discarding the only part of the
 * bookmark worth keeping. Forwarded verbatim: the destination reads what it understands and
 * ignores the rest, which beats a hand-maintained parameter mapping that needs editing whenever
 * either page grows a parameter.
 *
 * `replace`, not `push`, so Back returns to wherever the user came from rather than to the
 * redirect, which would bounce them forward again.
 */

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export function Redirect({ to }: { to: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const query = searchParams.toString();
    router.replace(query ? `${to}?${query}` : to);
  }, [router, searchParams, to]);

  return null;
}
