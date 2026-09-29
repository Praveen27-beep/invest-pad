"use client";

/**
 * Workspace's sign-in AND create-account form, in one component with two modes.
 *
 * WHY REGISTRATION IS HERE NOW. It used to say "a new account is created in Trackr+" and link
 * nowhere -- which meant a visitor who landed on this origin with no account had no way forward
 * at all, and no way to find out why. That is not a boundary, it is a dead end. Both products
 * sit on one backend, one `app_user` table and one `/auth/register` endpoint; a second front door
 * to the same endpoint is not a second registration system.
 *
 * SAME CREDENTIALS, SAME BACKEND, SAME ACCOUNT as Trackr+. There is no Workspace account, no
 * separate registration and no migration on upgrade: one login owns one set of investors, and
 * which application it is used from changes nothing about that.
 *
 * THE TERMS VERSION IS SENT, NOT ASSUMED. `tos_version` is required by the server and it rejects
 * any value other than the one this build serves -- an acceptance of a version nobody was shown
 * is a false record, which is worse than no record. The checkbox links to this app's own
 * `/terms`, which renders the same text from `@trackr/core` that Plus renders, so the version
 * string and the words a person read cannot come apart.
 *
 * REGISTERING GRANTS BOTH PRODUCTS, since the owner's 2026-09-27 decision that there is no
 * operator gate on Workspace (`docs/PRODUCT_ARCHITECTURE.md` section 4). So there is nothing to
 * warn about here any more, and the note that used to explain the gate has gone with it.
 *
 * The server grants both regardless of which origin this form is served from -- that part did not
 * change. This component sends an email, a password and a terms version, and claims nothing
 * about which product it belongs to, because a client saying so would not be evidence.
 *
 * SESSIONS ARE ORIGIN-LOCAL, DELIBERATELY. Signing in to Plus does not sign you in here and vice
 * versa; cross-origin SSO is explicitly not part of this launch
 * (`docs/PRODUCT_ARCHITECTURE.md` section 4). No token is ever put in a link or copied between
 * domains to paper over that.
 */

import { useState } from "react";
import Link from "next/link";
import { ApiError, CURRENT_TOS_VERSION, useAuth } from "@trackr/core";

type Mode = "signin" | "register";

export function SignIn() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const registering = mode === "register";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (registering) {
        await register({
          email,
          password,
          display_name: displayName.trim() || null,
          tos_version: CURRENT_TOS_VERSION,
        });
      } else {
        await login({ email, password });
      }
    } catch (err: unknown) {
      // THREE DIFFERENT FAILURES, THREE DIFFERENT MESSAGES. This used to collapse everything
      // that was not an ApiError into "Could not create the account.", which threw away the only
      // useful information in the two cases that actually happen:
      //
      //   ApiError   -- the server answered and refused. It says why ("password must be at
      //                 least 8 characters"), so show exactly that and nothing of our own.
      //   TypeError  -- `fetch` rejected: the request never completed. A blocked CORS preflight
      //                 looks exactly like this, and so does a backend that is not running.
      //                 Both are configuration, not something the person typed, and telling them
      //                 "could not create the account" sends them to re-check their password.
      //   anything else -- report it rather than replacing it with a guess.
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof TypeError) {
        setError(
          "Could not reach the server. The API may not be running, or this origin may not be " +
            "in its CORS_ORIGINS list — the request did not complete, so nothing was submitted."
        );
      } else {
        setError(String(err) || "Something went wrong.");
      }
    } finally {
      setBusy(false);
    }
  }

  function switchTo(next: Mode) {
    setMode(next);
    // The error belonged to the other mode's attempt. Leaving "incorrect password" on screen
    // above a create-account form is just confusing.
    setError(null);
  }

  return (
    <div className="ws-auth">
      <div className="ws-auth-card">
        <div className="ws-auth-tabs" role="tablist" aria-label="Sign in or create an account">
          <button
            type="button"
            role="tab"
            aria-selected={!registering}
            className="ws-auth-tab"
            data-active={!registering}
            onClick={() => switchTo("signin")}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={registering}
            className="ws-auth-tab"
            data-active={registering}
            onClick={() => switchTo("register")}
          >
            Create account
          </button>
        </div>

        <form onSubmit={submit} className="ws-auth-form">
          {registering && (
            <label className="ws-field">
              <span className="ws-field-label">Name</span>
              <input
                className="ws-input"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                autoComplete="name"
                placeholder="Optional"
              />
            </label>
          )}

          <label className="ws-field">
            <span className="ws-field-label">Email</span>
            <input
              className="ws-input"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </label>

          <label className="ws-field">
            <span className="ws-field-label">
              Password
              {/*
                THE RULE IS STATED BEFORE IT IS ENFORCED. The server requires 8 characters
                (`app/auth/schemas.py`). Learning that by submitting and being refused is a
                worse experience than being told, and `minLength` lets the browser say so
                inline -- while the server stays the thing that actually decides.
              */}
              {registering && <span className="ws-field-hint"> &middot; at least 8 characters</span>}
            </span>
            <input
              className="ws-input"
              type="password"
              required
              minLength={registering ? 8 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              // `new-password` on the register form is what stops a password manager offering the
              // existing password for this origin when the intent is to create a new account.
              autoComplete={registering ? "new-password" : "current-password"}
            />
          </label>

          {registering && (
            <label className="ws-check">
              <input
                type="checkbox"
                required
                checked={accepted}
                onChange={(e) => setAccepted(e.target.checked)}
              />
              <span>
                I accept the <Link href="/terms">Terms &amp; Privacy Policy</Link>.
              </span>
            </label>
          )}

          {error && (
            <p className="ws-auth-error" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            className="ws-btn ws-btn--primary ws-btn--wide"
            disabled={busy || (registering && !accepted)}
          >
            {busy
              ? registering
                ? "Creating account…"
                : "Signing in…"
              : registering
                ? "Create account"
                : "Sign in"}
          </button>
        </form>

        {registering && (
          <p className="ws-auth-note">
            One account, both products. You get the portfolio and the research workspace &mdash;
            same login, same ledger, same investors. Start by importing a contract note or a
            tradebook; nothing here shows a figure it cannot derive from what you gave it.
          </p>
        )}
      </div>
    </div>
  );
}
