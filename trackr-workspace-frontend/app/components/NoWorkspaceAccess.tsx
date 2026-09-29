"use client";

/**
 * What a signed-in account without the Workspace capability sees on a research route.
 *
 * RARE SINCE 2026-09-27, AND KEPT ANYWAY. Signup now grants both products, so the ordinary way
 * to reach this screen is gone. It remains reachable for exactly one reason: Workspace can still
 * be REVOKED (`app/db/grant_capability.py`), and revocation is what makes "capabilities are read
 * per request, so a change takes effect on the next one" a testable property rather than a claim.
 * Deleting this component would leave that path rendering nothing.
 *
 * THE HONESTY RULE THIS SCREEN EXISTS FOR. It says what is true: the account works, the
 * portfolio is intact, and this one product is not enabled. It does not offer a checkout
 * button, because there is no checkout; it does not offer a "request access" form,
 * because nothing would receive it; and it does not pretend the research features are
 * loading. A screen that invents a next step the product cannot honour is worse than one
 * that says plainly where to go.
 *
 * It is not a security boundary and must never be treated as one. The server refuses
 * these routes independently on every request (`require_workspace_access`), so removing
 * this component in a devtools console reveals an empty page that immediately 403s, not
 * research data.
 *
 * Settings and Privacy stay reachable from the rail throughout. Losing a product tier
 * must never take away the ability to see or erase your own data.
 */

import Link from "next/link";
import { useAuth, useCapabilities } from "@trackr/core";
import { Icon } from "./Icon";

export function NoWorkspaceAccess() {
  const { user } = useAuth();
  const { refresh } = useCapabilities();

  return (
    <div className="ws-centred">
      <div className="ws-centred-card">
        <div
          className="ws-crumb"
          style={{ display: "flex", alignItems: "center", gap: 7, color: "var(--ws-brass)" }}
        >
          <Icon name="lock" size={12} />
          Access
        </div>

        <h1 className="ws-h1" style={{ fontSize: 26 }}>Workspace isn&rsquo;t enabled on this account</h1>
        <p className="ws-sub">
          {user?.email ? <span className="ws-mono">{user.email}</span> : "This account"} is
          signed in and working. Research &mdash; companies, notes, theses, monitors and
          agents &mdash; is a separate product capability that has not been granted.
        </p>

        <div className="ws-notice" style={{ margin: "20px 0" }}>
          Your portfolio is unaffected. Everything you already have is open in Trackr+,
          and Settings and Privacy remain available here.
        </div>

        <div style={{ display: "flex", gap: 9, flexWrap: "wrap" }}>
          <Link href="/" className="ws-btn ws-btn--primary">
            Go to Portfolio
          </Link>
          <button type="button" className="ws-btn" onClick={refresh}>
            Check again
          </button>
        </div>

        <p className="ws-muted" style={{ marginTop: 20, lineHeight: 1.6 }}>
          New accounts get both products, so seeing this usually means research access was
          withdrawn from this one. Nothing you saved has been deleted, and your export and
          erasure rights are unaffected. If it has since been restored, check again above
          &mdash; a change takes effect on the next request and does not wait for you to sign
          in again.
        </p>
      </div>
    </div>
  );
}
