"use client";

/**
 * Workspace Settings.
 *
 * REACHABLE WITHOUT THE WORKSPACE CAPABILITY, deliberately. A downgraded account must
 * still be able to see who it is, what it can do and where its data is -- the shell's
 * `CAPABILITY_FREE_PREFIXES` is what guarantees that, and this screen is why it exists.
 *
 * The capability panel reports the SERVER's answer verbatim and offers a re-check. It is
 * a status display, not a control: there is no upgrade button here because there is no
 * self-serve upgrade. Signup now grants both products (2026-09-27), and a button
 * that implied otherwise would be a promise the product cannot keep.
 */

import {
  CAPABILITY_WORKSPACE,
  useAuth,
  useCapabilities,
} from "@trackr/core";

export default function Settings() {
  const { user, investorId, asOf, setAsOf, advisedOnly, setAdvisedOnly } = useAuth();
  const { capabilities, status, error, refresh } = useCapabilities();

  return (
    <>
      <header style={{ marginBottom: 20 }}>
        <h1 className="ws-h1">Settings</h1>
        <p className="ws-sub">This account, and the scope every figure is computed at.</p>
      </header>

      <div className="ws-grid" style={{ maxWidth: 640 }}>
        <section className="ws-card">
          <p className="ws-card-title">Account</p>
          <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "auto 1fr", gap: "8px 18px" }}>
            <dt className="ws-muted">Email</dt>
            <dd style={{ margin: 0 }} className="ws-mono">
              {user?.email ?? "—"}
            </dd>
            <dt className="ws-muted">Name</dt>
            <dd style={{ margin: 0 }}>{user?.display_name ?? "—"}</dd>
            <dt className="ws-muted">Investor</dt>
            <dd style={{ margin: 0 }} className="ws-mono">
              {investorId || "—"}
            </dd>
          </dl>
          <p className="ws-muted" style={{ marginTop: 12 }}>
            The same account and the same investor records as Trackr+. Using Workspace
            creates no second portfolio and copies nothing.
          </p>
        </section>

        <section className="ws-card">
          <p className="ws-card-title">Product access</p>
          {status === "loading" || status === "unknown" ? (
            <p className="ws-sub" style={{ margin: 0 }}>
              Checking&hellip;
            </p>
          ) : status === "error" ? (
            <div className="ws-notice ws-notice--error">
              {error ?? "The server did not answer."}
            </div>
          ) : (
            <>
              <ul style={{ margin: "0 0 10px", paddingLeft: 18 }}>
                {capabilities.map((capability) => (
                  <li key={capability}>
                    <span className="ws-mono">{capability}</span>
                    {capability === CAPABILITY_WORKSPACE && " — research, monitors and agents"}
                  </li>
                ))}
              </ul>
              {capabilities.length === 0 && (
                <p className="ws-sub" style={{ margin: "0 0 10px" }}>
                  No capabilities are recorded for this account.
                </p>
              )}
            </>
          )}
          <button type="button" className="ws-btn" onClick={refresh}>
            Re-check
          </button>
          <p className="ws-muted" style={{ marginTop: 12 }}>
            Read from the server on every check, never from your sign-in token, so a
            change takes effect immediately rather than when the token expires.
          </p>
        </section>

        <section className="ws-card">
          <p className="ws-card-title">Reporting scope</p>
          <label className="ws-field">
            <span className="ws-field-label">As at</span>
            <input
              className="ws-input"
              type="date"
              value={asOf}
              onChange={(event) => setAsOf(event.target.value)}
            />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <input
              type="checkbox"
              checked={advisedOnly}
              onChange={(event) => setAdvisedOnly(event.target.checked)}
            />
            <span>Advised accounts only</span>
          </label>
          <p className="ws-muted" style={{ marginTop: 12 }}>
            These are the <span className="ws-mono">as_of</span> and{" "}
            <span className="ws-mono">advised_only</span> query parameters every portfolio
            endpoint takes. The same scope produces the same figures in both applications.
          </p>
        </section>
      </div>
    </>
  );
}
