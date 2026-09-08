"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
import { AIChatProvider } from "@/lib/ai-chat-context";
import { Ribbon } from "./Ribbon";
import { OnboardingWizard } from "./onboarding/OnboardingWizard";
import { AIChatDrawer } from "./AIChatDrawer";

/** `/terms` is public because the registration form links to it: someone deciding
 *  whether to accept the terms has not signed in yet, and redirecting them to /login
 *  would lose the half-filled form they left behind. */
const PUBLIC_PATHS = ["/login", "/register", "/terms"];

/**
 * The app shell: a sticky ribbon over a full-width main column.
 *
 * Public routes render bare — the sign-in screen has its own centred layout and no
 * business showing navigation to someone who is not signed in yet.
 */
export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/";
  const router = useRouter();
  const { token, ready } = useAuth();
  const isPublic = PUBLIC_PATHS.includes(pathname);

  useEffect(() => {
    if (ready && !token && !isPublic) router.replace("/login");
  }, [ready, token, isPublic, router]);

  if (isPublic) return <>{children}</>;

  // Auth resolves from localStorage in an effect, so the first paint always happens
  // before `ready`. Rendering a centred "Loading…" there and the real chrome a tick later
  // meant the entire app jumped into place on every single load. Reserving the ribbon's
  // exact 52px instead keeps the page's origin fixed from the first frame — the bar is
  // deliberately empty rather than a stand-in Ribbon, because the real one needs
  // AIChatProvider and a signed-in user, neither of which exists yet.
  if (!ready || !token) {
    return (
      <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh", background: "var(--page)" }}>
        <div
          aria-hidden="true"
          style={{
            height: 52,
            background: "var(--surface)",
            borderBottom: "1px solid var(--border)",
          }}
        />
        <main style={{ flex: 1, minWidth: 0 }} />
      </div>
    );
  }

  return (
    <AIChatProvider>
      <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh", background: "var(--page)" }}>
        <Ribbon pathname={pathname} />
        <main
          key={pathname}
          style={{
            flex: 1,
            minWidth: 0,
            animation: "trackr-fade-in var(--duration-base) var(--ease-smooth) both",
          }}
        >
          {children}
        </main>
        <OnboardingWizard />
        <AIChatDrawer />
      </div>
    </AIChatProvider>
  );
}

/**
 * Standard page body padding. Screens that own their header (the dashboard's headline
 * bar, say) render it flush and wrap only their content in this.
 */
export function PageBody({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ padding: "var(--page-padding-y) var(--page-padding-x)" }}>{children}</div>
  );
}
