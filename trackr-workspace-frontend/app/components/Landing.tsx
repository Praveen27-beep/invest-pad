"use client";

/**
 * Workspace's signed-out front door: what this product is, and the sign-in beside it.
 *
 * APP-OWNED MARKETING. Plus has its own landing and its own copy; neither app describes the
 * other and neither imports the other's. There is deliberately no link to the Plus origin here:
 * Workspace serves the portfolio itself, so sending a visitor to another domain to see their
 * holdings would make this a menu in front of Plus rather than an application.
 *
 * NO DASHBOARD FETCH, AND THAT IS STRUCTURAL RATHER THAN CAREFUL. `Shell` returns this component
 * instead of `children` when there is no session, so `app/page.tsx` -- which is where the
 * summary and performance reads live -- never mounts. There is no request to cancel because
 * there is no component to issue one.
 *
 * EVERY CLAIM BELOW IS ABOUT SOMETHING THAT EXISTS. No feature is described in the present tense
 * that is not built: the research surfaces say plainly that they are coming, because a landing
 * page promising monitors that do not run yet is the same lie as a mock screen, told earlier.
 */

import { SignIn } from "./SignIn";

export function Landing() {
  return (
    <main className="ws-landing">
      <div className="ws-landing-copy">
        <p className="ws-eyebrow">Trackr Workspace</p>
        <h1 className="ws-h1" style={{ fontSize: 30, marginTop: 10 }}>
          Your portfolio, and the thinking behind it, in one place.
        </h1>
        <p className="ws-sub" style={{ marginTop: 14, maxWidth: "46ch" }}>
          Workspace is Trackr+ with a research surface beside it. The same ledger, the same
          figures, the same account &mdash; computed from your transactions every time they are
          shown, never stored and never estimated.
        </p>

        <ul className="ws-landing-list">
          <li>
            <strong>The complete portfolio.</strong> Holdings, performance, imports and
            reconciliation, reading the same endpoints Trackr+ reads.
          </li>
          <li>
            <strong>Research that is kept, not cached.</strong> Notes, the questions you made
            yourself answer, and a thesis recorded as a dated version you cannot quietly edit.
          </li>
          <li>
            <strong>Nothing invented.</strong> An unpriced holding is reported as unpriced. A
            monitor that could not run says so. Model output is a proposal until you accept it.
          </li>
        </ul>

        <p className="ws-sub" style={{ marginTop: 18, color: "var(--ws-text-faint)" }}>
          One account covers both products. The research surfaces are being built now, and the
          screens that are not ready say so rather than showing a sample.
        </p>
      </div>

      <div className="ws-landing-form">
        <SignIn />
      </div>
    </main>
  );
}
