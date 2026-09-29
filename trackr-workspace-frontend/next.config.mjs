// Trackr Workspace's own Next configuration. Separate from Plus's on purpose: the two
// applications deploy independently, to different origins, and neither one's headers or
// build settings should move because the other's did.
//
// The CSP reasoning is the same as Plus's and is written out there in full
// (trackr-frontend/next.config.mjs): App Router streams RSC payload as inline
// `self.__next_f.push(...)` scripts whose content differs per request, so a hash-only
// `script-src` cannot work and nonce-based CSP would cost static generation app-wide.
// This follows Next's documented "Without Nonces" default for the same reason.
//
// `connect-src` names the API origin explicitly, plus the listed model provider origins
// (MODEL_ORIGINS below) that a person's browser calls directly with its own key. No analytics
// endpoint, no font CDN fetch, no wildcard.
const isDev = process.env.NODE_ENV === "development";
const API_ORIGIN = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// BE 23 / BT 08: the model endpoints a person's browser may call DIRECTLY with their own key.
// An explicit list of https origins -- never a wildcard -- read from the same variable that
// lib/research-agent.ts checks before starting an attempt, so an endpoint outside it is
// explained up front instead of failing as an opaque network error. Adding a provider is a
// deliberate, visible change here. Trackr+ itself never proxies these requests.
const MODEL_ORIGINS = (process.env.NEXT_PUBLIC_MODEL_ORIGINS ?? "https://api.anthropic.com https://api.openai.com")
  .split(/[\s,]+/)
  .filter((origin) => /^https:\/\/[A-Za-z0-9.-]+(:[0-9]+)?$/.test(origin));

const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self'",
  "img-src 'self' data:",
  `connect-src 'self' ${API_ORIGIN} ${MODEL_ORIGINS.join(" ")}`.trim(),
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The shared packages ship TypeScript source rather than a build artifact, so Next
  // compiles them with this app's toolchain. This is also what keeps React a single
  // instance across the app and the packages it consumes.
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
