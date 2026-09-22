import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { PrivacyProvider } from "@/lib/privacy-context";
import { Shell } from "./components/Shell";

export const metadata: Metadata = {
  title: "Trackr+ Portfolio Intelligence",
  description: "Holdings, performance and XIRR, replayed from your transaction ledger.",
};

// The marketing page at "/" is part of the prerendered HTML so the route is indexable
// (auth resolves in an effect, so anything gated on it is invisible to a crawler). The
// cost is that a signed-in user would see the landing for the one paint before that
// effect runs. Marking the document here -- synchronously, ahead of hydration -- lets
// landing.css hide it from the very first frame.
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
    // `dark` is set here, statically, and there is no way to turn it off. Trackr+ is a
    // dark-only product by decision, so the theme is a constant rather than state: no
    // stored preference, no OS query, no toggle. Putting the class in the server-rendered
    // markup also removes the class of bug a runtime theme has -- the light-mode flash
    // before hydration -- because the very first paint already carries it.
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_SESSION_SCRIPT }} />
      </head>
      <body>
        <PrivacyProvider>
          <AuthProvider>
            <Shell>{children}</Shell>
          </AuthProvider>
        </PrivacyProvider>
      </body>
    </html>
  );
}
