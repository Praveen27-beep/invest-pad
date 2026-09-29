"use client";

/**
 * Workspace's session bootstrap. Mounted once, at the root, and nowhere else.
 *
 * ONE AUTH OWNER PER APPLICATION. Both `AuthProvider` and `AuthedCapabilityProvider`
 * come from `@trackr/core`, so Plus and Workspace run the same implementation -- but
 * each app mounts its own single instance. Two providers in one tree would mean two
 * token states racing each other over the same `localStorage` key.
 *
 * The order matters: capabilities are derived from the session, so the capability
 * provider sits inside the auth provider and resets when the token goes away.
 *
 * THE TWO PROVIDERS BELOW ARE PORTFOLIO CONTRACTS, NOT DECORATION. The shared portfolio
 * screens depend on both, and `useAIChat` THROWS without its provider rather than degrading
 * -- so a Workspace tree missing it would crash the Dashboard the moment a holding failed to
 * reconcile and rendered its "Ask AI about this" entry point. Mounted here, once, for the
 * same reason auth is.
 *
 *   `AIChatProvider` -- the SUPPORT assistant's open/close state. Support, not Butler:
 *   research chat is a separate Workspace surface with its own transport and its own
 *   validated-card presentation, and it must never be wired to this context or this
 *   endpoint (`docs/BUTLER_ARCHITECTURE.md`; BE-Q02 gates retiring the support assistant).
 *
 *   `PrivacyProvider` -- the blur-every-rupee mask. Its contract is that every money figure
 *   renders through `<Figure>`, and the figures on these screens are the same ones; a
 *   Workspace without it would be a product where the mask silently does nothing.
 */

import { AIChatProvider, AuthProvider, AuthedCapabilityProvider, PrivacyProvider } from "@trackr/core";
import { KeyGuard } from "./research/KeyGuard";
import { Shell } from "./Shell";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AuthedCapabilityProvider>
        <PrivacyProvider>
          <AIChatProvider>
            <KeyGuard />
            <Shell>{children}</Shell>
          </AIChatProvider>
        </PrivacyProvider>
      </AuthedCapabilityProvider>
    </AuthProvider>
  );
}
