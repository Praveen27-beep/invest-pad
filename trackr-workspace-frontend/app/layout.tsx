import type { Metadata } from "next";
import { Suspense } from "react";
import "./globals.css";
import "./studio.css";
import "./public.css";
import { Inter, Newsreader } from "next/font/google";
import { Providers } from "./components/Providers";

export const metadata: Metadata = {
  title: "Invest-pad | Your investment research workspace",
  description:
    "A writing-first research workspace for Indian equities. Keep your questions, evidence, notes and thesis history beside your portfolio.",
};

/* Self-hosted at build time by next/font: no runtime request to a font CDN. */
const inter = Inter({ subsets: ["latin"], variable: "--ip-font-sans", display: "swap" });
const newsreader = Newsreader({
  subsets: ["latin"],
  weight: ["300", "400"],
  style: ["normal", "italic"],
  variable: "--ip-font-display",
  display: "swap",
});

/** One auth owner and theme. */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${newsreader.variable}`}>
      <body>
        <Suspense fallback={<div className="ws-empty" role="status">Opening Invest-pad…</div>}>
          <Providers>{children}</Providers>
        </Suspense>
      </body>
    </html>
  );
}
