// Pre-deployment audit (2026-08-30), finding #6: no security headers at all -- Vercel's
// own edge does not add a CSP or frame-ancestors policy for you. The auth token lives in
// localStorage (lib/auth-context.tsx), so a CSP that actually restricts script-src is
// the one thing standing between an XSS bug and a stolen session.
//
// Corrected 2026-08-30, same day: the original version allowed app/layout.tsx's one
// inline theme script by exact sha256 hash and nothing else, on the assumption that was
// the only inline script in the page. Wrong for a Next.js App Router app on two counts,
// both confirmed live in the browser console (five DIFFERENT hashes reported at the
// same line): (1) Next's dev runtime injects several inline bootstrap scripts of its
// own (HMR client, dev overlay) that this app doesn't control and can't pin by hash;
// (2) App Router streams RSC payload chunks as inline `self.__next_f.push(...)` scripts
// even in production, with content that differs per request, so no static hash can ever
// cover them. A hash-only script-src is only viable with Pages Router or fully static
// export -- this is App Router, so it isn't an option here without switching to
// nonce-based CSP (https://nextjs.org/docs/app/guides/content-security-policy), which
// requires every page to opt into dynamic rendering and gives up static
// generation/ISR/CDN caching app-wide. Not worth that trade-off for this app's threat
// model, so this follows Next's own documented "Without Nonces" default instead:
// 'unsafe-inline' for scripts, same as their example. This CSP still blocks the things
// that matter most given the JWT-in-localStorage design -- third-party script origins,
// framing, exfiltration via connect-src -- just not inline-script injection specifically.
//
// 'unsafe-eval' is added in development ONLY (also Next's documented requirement --
// React's dev build uses eval() for enhanced error stacks). Production never uses eval.
const isDev = process.env.NODE_ENV === "development";
const API_ORIGIN = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com",
  "img-src 'self' data:",
  `connect-src 'self' ${API_ORIGIN}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The shared packages ship TypeScript source, not a build artifact -- there is no
  // separate compile step to keep in sync and no stale `dist/` to debug. Next compiles
  // them with this app's own toolchain, which is also what keeps React a single
  // instance across app and packages.
  // https://nextjs.org/docs/app/api-reference/config/next-config-js/transpilePackages
  transpilePackages: ["@trackr/core", "@trackr/portfolio"],
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: CSP },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
