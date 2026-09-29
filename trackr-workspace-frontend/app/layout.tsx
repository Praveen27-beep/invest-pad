import type { Metadata } from "next";
import { Suspense } from "react";
import { Inter, JetBrains_Mono, Newsreader } from "next/font/google";
import "./globals.css";
import { Providers } from "./components/Providers";

/*
 * THE THREE FAMILIES, SELF-HOSTED.
 *
 * demo.html pulls these from `fonts.googleapis.com` with a <link>. This app cannot: its CSP
 * (see `next.config.mjs`) is `font-src 'self'` with no font CDN in `style-src` either, and
 * that restriction is deliberate -- "no analytics endpoint, no font CDN fetch, no model
 * provider" is written into that file as a property worth keeping.
 *
 * `next/font/google` resolves it without relaxing anything: it downloads the files at BUILD
 * time and serves them from this origin, so the browser makes no third-party request and the
 * CSP needs no exception. It also inlines the `@font-face` rules and self-hosts the fallback
 * metrics, which is what removes the layout shift a <link> to a CDN would cause.
 *
 * Each exposes a CSS variable rather than a class, because `globals.css` composes them into
 * `--ws-font-heading` / `-body` / `-mono` with their fallback stacks. A component never names
 * a font family; it names a role.
 */

/*
 * Newsreader sets headings AND every figure in the application. `display: "swap"` matters
 * more here than for the other two: this is the family a market value is set in, and a
 * blocked figure is worse than one that reflows.
 */
const newsreader = Newsreader({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  // Italic is load-bearing, not decorative: an interpretation -- as opposed to a fact -- is
  // marked by being set in the serif italic, which is the design's way of showing that two
  // blocks are different KINDS of claim rather than differently coloured.
  style: ["normal", "italic"],
  display: "swap",
  variable: "--ws-font-newsreader",
});

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
  variable: "--ws-font-inter",
});

/* Identifiers only: symbols, ISINs, dates, provenance lines, key counts. */
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
  variable: "--ws-font-jetbrains",
});

/**
 * App-owned metadata. Plus has its own; neither app describes the other, and this string is
 * what appears in a browser tab and a link preview for this deployment alone.
 */
export const metadata: Metadata = {
  title: "Trackr Workspace",
  description:
    "Research, theses and monitors alongside your portfolio, built on the same ledger.",
};

/**
 * Workspace's own root layout. Separate from Plus's by design: each application owns its
 * layout, theme bootstrap, CSS entry and marketing, and neither imports the other's.
 *
 * THE THEME IS A CONSTANT, NOT STATE. Workspace is a dark-only product by decision, so
 * `color-scheme: dark` lives in `globals.css` and there is nothing to read, store or race. A
 * light palette and a toggle existed briefly and were removed on the owner's instruction; with
 * them went the pre-paint bootstrap script, the `data-theme` attribute and
 * `suppressHydrationWarning` -- none of which is needed once the theme cannot change.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${newsreader.variable} ${inter.variable} ${jetbrainsMono.variable}`}
    >
      <body>
        {/*
          `Suspense` is required, not decorative: the shell reads `useSearchParams` to
          remember the last portfolio URL with its query, and Next requires a suspense
          boundary above any component that does. Without it the whole route opts out of
          static rendering at build time.
        */}
        <Suspense fallback={null}>
          <Providers>{children}</Providers>
        </Suspense>
      </body>
    </html>
  );
}
