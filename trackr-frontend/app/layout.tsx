import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { ThemeProvider } from "@/lib/theme-context";
import { Shell } from "./components/Shell";

export const metadata: Metadata = {
  title: "Trackr+ Portfolio Intelligence",
  description: "Holdings, performance and XIRR, replayed from your transaction ledger.",
};

// Runs before React hydrates, so <html> already carries the right class on first
// paint -- otherwise the page would flash light mode for a moving-target instant on
// every load for anyone who has picked dark, which is the one failure mode a theme
// toggle exists to prevent. Reads localStorage directly rather than through
// lib/theme-context.tsx because it must execute synchronously in <head>, before any
// script tag Next.js hydrates. `suppressHydrationWarning` on <html> is required
// alongside this: the class this script sets can differ from the class React's server
// render produced, and that specific, expected mismatch is what the prop opts out of
// warning about (nothing else under <html> is affected).
const NO_FLASH_THEME_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem("trackr.theme");
    var dark = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle("dark", dark);
  } catch (e) {}
})();
`;

// The marketing page at "/" is part of the prerendered HTML so the route is indexable
// (auth resolves in an effect, so anything gated on it is invisible to a crawler). The
// cost is that a signed-in user would see the landing for the one paint before that
// effect runs. Marking the document here -- synchronously, ahead of hydration, the same
// way the theme script does -- lets landing.css hide it from the very first frame.
// Reads the key written by lib/auth-context.tsx; presence is a hint about which view to
// paint, never a claim that the token is still valid.
const NO_FLASH_SESSION_SCRIPT = `
(function () {
  try {
    if (localStorage.getItem("trackr.token")) document.documentElement.dataset.session = "1";
  } catch (e) {}
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME_SCRIPT }} />
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_SESSION_SCRIPT }} />
      </head>
      <body>
        <ThemeProvider>
          <AuthProvider>
            <Shell>{children}</Shell>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
