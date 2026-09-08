"use client";

import { useEffect } from "react";

/**
 * Cross-component signals for the setup flow, and the only two things about it that are
 * genuinely per-browser.
 *
 * WHAT USED TO LIVE HERE AND NO LONGER DOES. "They finished setup" was a localStorage
 * key. That made a fact about an ACCOUNT into a fact about a BROWSER, and the two came
 * apart the moment anyone opened the app anywhere else:
 *
 *     laptop ──► onboarding_done = "1"  → no wizard          ✅
 *     phone  ──► (key absent)           → wizard reopens     ❌
 *                                         …and offers to create a SECOND account
 *
 * It was also set on "Finish" regardless of what had actually happened, so skipping the
 * file step and pressing Finish left an empty dashboard with the banner permanently
 * suppressed and no way back in short of clearing site data. That was the worst outcome
 * in the whole flow: the product deciding someone was finished at the exact moment they
 * had nothing (docs/ONBOARDING_AS_IS_VS_TO_BE.md, loopholes L4 and L13).
 *
 * Completion is now DERIVED — `GET /investors/{id}/onboarding`, computed from consent,
 * accounts and transactions on every read (see useOnboardingState below). There is no
 * client-side "done" to get out of sync, because there is no client-side "done".
 *
 * WHAT REMAINS, and why each one belongs in a browser rather than in the database:
 *
 *   1. **Dismissed this session** (sessionStorage). Suppresses the auto-open. Closing a
 *      modal is not a decision to never see it again, so a new session for a still-empty
 *      portfolio offers the wizard once more.
 *   2. **Not interested in forwarding** (localStorage). The one genuine preference in
 *      the list: a durable "stop offering me this", which is about being asked, not
 *      about the account's state. Never nags again once set.
 *
 * Every key is namespaced by investor id: one browser can hold sessions for more than
 * one investor, and one investor's preference must never silence another's prompt.
 */

const DISMISSED_SESSION_KEY = "trackr.onboarding_dismissed_session";
const FORWARDING_DECLINED_KEY = "trackr.onboarding_forwarding_declined";
const BANNER_HIDDEN_KEY = "trackr.onboarding_banner_hidden";

/** Storage access throws outright in some privacy modes; every value here is a
 * convenience, never a correctness requirement, so a failed read degrades to
 * "we don't know yet" — which shows the prompt, the safe direction to be wrong in. */
function read(storage: "local" | "session", key: string): string | null {
  try {
    return (storage === "local" ? window.localStorage : window.sessionStorage).getItem(key);
  } catch {
    return null;
  }
}

function write(storage: "local" | "session", key: string, value: string | null): void {
  try {
    const store = storage === "local" ? window.localStorage : window.sessionStorage;
    if (value === null) store.removeItem(key);
    else store.setItem(key, value);
  } catch {
    // Nothing here is worth failing a render over.
  }
}

const scoped = (key: string, investorId: string) => `${key}:${investorId}`;

export function isDismissedThisSession(investorId: string): boolean {
  return read("session", scoped(DISMISSED_SESSION_KEY, investorId)) === "1";
}

/** Closed the wizard. Suppresses the auto-open for this session only — the dashboard
 * checklist stays, because that is the cheap way back in that makes skipping safe. */
export function markDismissed(investorId: string): void {
  write("session", scoped(DISMISSED_SESSION_KEY, investorId), "1");
}

/**
 * "Not interested" in email forwarding — the only durable per-browser preference.
 *
 * Forwarding is optional forever and may genuinely never happen: uploading a file once a
 * quarter is a legitimate way to use this product. So declining is a real answer that is
 * remembered, not a step left unfinished, and it is never counted towards completion.
 */
export function declineForwarding(investorId: string): void {
  write("local", scoped(FORWARDING_DECLINED_KEY, investorId), "1");
}

export function isForwardingDeclined(investorId: string): boolean {
  return read("local", scoped(FORWARDING_DECLINED_KEY, investorId)) === "1";
}

/** The checklist's "not now" — hides it for this session only, so it is a nudge that can
 * be waved off rather than one that has to be permanently answered. */
export function hideBannerForSession(investorId: string): void {
  write("session", scoped(BANNER_HIDDEN_KEY, investorId), "1");
}

export function isBannerHiddenThisSession(investorId: string): boolean {
  return read("session", scoped(BANNER_HIDDEN_KEY, investorId)) === "1";
}

// ---------------------------------------------------------------------------
// Signals
// ---------------------------------------------------------------------------

const OPEN_EVENT = "trackr:open-onboarding";
const REFRESH_EVENT = "trackr:portfolio-refresh";

/** Which step to open on. `undefined` means "wherever the server says they are". */
export type OnboardingStep = "access" | "brokers" | "files" | "align" | "forward";

/**
 * Ask the wizard to open — from the dashboard checklist, which does not own it.
 *
 * The optional step is what makes the checklist a set of DEEP LINKS rather than a
 * restart button: adding a fourth broker two months later is one click from the
 * dashboard and does not mean re-granting permission and re-uploading files.
 */
export function openOnboarding(step?: OnboardingStep): void {
  window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: step ?? null }));
}

export function useOnboardingOpenRequest(handler: (step: OnboardingStep | null) => void): void {
  useEffect(() => {
    const listener = (event: Event) => {
      const detail = (event as CustomEvent<OnboardingStep | null>).detail ?? null;
      handler(detail);
    };
    window.addEventListener(OPEN_EVENT, listener);
    return () => window.removeEventListener(OPEN_EVENT, listener);
  }, [handler]);
}

/**
 * "New transactions exist — re-read everything derived from them."
 *
 * Every figure in this product is computed from the ledger on read (CLAUDE.md's one
 * architectural rule), so a finished import invalidates every screen at once and there is
 * nothing to patch locally: the honest response is to re-fetch. A window event rather
 * than shared React state because the publisher (a modal portalled to document.body) and
 * the subscribers (whatever page is mounted behind it) have no common provider, and
 * threading one through the tree to move a boolean would be the larger change.
 */
export function broadcastPortfolioRefresh(): void {
  window.dispatchEvent(new CustomEvent(REFRESH_EVENT));
}

export function usePortfolioRefresh(handler: () => void): void {
  useEffect(() => {
    const listener = () => handler();
    window.addEventListener(REFRESH_EVENT, listener);
    return () => window.removeEventListener(REFRESH_EVENT, listener);
  }, [handler]);
}
