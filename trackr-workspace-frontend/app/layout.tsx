import type { Metadata } from "next";
import { Suspense } from "react";
import "./globals.css";
import { Providers } from "./components/Providers";

export const metadata: Metadata = {
  title: "Invest-pad | Your investment research workspace",
  description:
    "A writing-first research workspace for Indian equities. Keep your questions, evidence, notes and thesis history beside your portfolio.",
};

/** One auth owner and theme. System fonts make the build independent of a font CDN. */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Suspense fallback={<div className="ws-empty" role="status">Opening Invest-pad…</div>}>
          <Providers>{children}</Providers>
        </Suspense>
      </body>
    </html>
  );
}
