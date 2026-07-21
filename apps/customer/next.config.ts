import withSerwistInit from "@serwist/next";
import createNextIntlPlugin from "next-intl/plugin";

import { resolveApiBaseUrl } from "./lib/api-base-url";

import type { NextConfig } from "next";

const withNextIntl = createNextIntlPlugin("../../packages/i18n/src/request.ts");

/**
 * PWA / serwist — M16-P02. Compiles the unified `sw.ts` to `public/sw.js` and
 * auto-registers it. Disabled in dev so HMR is not shadowed by a cached shell.
 * Composed AROUND `nextConfig` and UNDER `withNextIntl` so the M15-P03
 * `headers()`/CSP block is preserved untouched (CSP already allows
 * `worker-src 'self' blob:` + `manifest-src 'self'`).
 */
const withSerwist = withSerwistInit({
  swSrc: "sw.ts",
  swDest: "public/sw.js",
  cacheOnNavigation: true,
  reloadOnOnline: true,
  // Compile the real worker, but do not auto-register. Registration is gated
  // by `ServiceWorkerRegister` after a same-origin probe of `/sw.js` so a
  // missing deploy artifact never produces a failing SW registration.
  register: false,
  disable: process.env.NODE_ENV === "development",
});

/**
 * Security headers & CSP — M15-P03 (customer / Vercel origin).
 *
 * CSP is NONCE-based (no `unsafe-inline` for scripts). Next.js only injects a
 * per-request nonce into its own bootstrap scripts when the nonce arrives on the
 * *request* via middleware (owned/locked elsewhere this wave). Until that wiring
 * lands, the full script/style policy ships as `Content-Security-Policy-Report-Only`
 * so violations are collected without breaking the app, while the framing/hardening
 * directives (which need no nonce) are ENFORCED immediately. The `{{CSP_NONCE}}`
 * token is the per-request substitution point.
 * Report-only → enforce runbook: docs/ops/security-headers.md.
 */
const NONCE = "'nonce-{{CSP_NONCE}}'";

// Third-party origins allowed by policy (spec §1).
const CLOUDINARY = "https://res.cloudinary.com";
const SUPABASE = "https://*.supabase.co";
const SUPABASE_WS = "wss://*.supabase.co";
// GA4 is allowed in CSP now; M16-P05 wires the actual tag (not wired here).
const GA4_SCRIPT = "https://*.googletagmanager.com";
const GA4_CONNECT =
  "https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com";
const GA4_IMG = "https://*.google-analytics.com https://*.googletagmanager.com";
// Lenco hosted card widget — customer checkout card route ONLY (prod + sandbox).
const LENCO_WIDGET = "https://pay.lenco.co https://pay.sandbox.lenco.co";
const LENCO_API = "https://api.lenco.co https://api.sandbox.lenco.co";
// Sentry ingest (M16-P06) — browser SDK POSTs events here. Scoped to the ingest
// subdomains only (incl. region variants), NOT a blanket sentry.io allowance.
const SENTRY_INGEST =
  "https://*.ingest.sentry.io https://*.ingest.us.sentry.io https://*.ingest.de.sentry.io";

const HSTS = "max-age=63072000; includeSubDomains; preload";
const PERMISSIONS_POLICY =
  "camera=(), microphone=(), geolocation=(), browsing-topics=(), payment=(), usb=()";

// Enforced now: framing/hardening directives that do NOT govern Next's inline
// bootstrap scripts, so they are safe to enforce without a live nonce.
const ENFORCED_CSP = [
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'self'",
  "form-action 'self'",
  "upgrade-insecure-requests",
].join("; ");

// Report-only (full nonce policy). `lenco` = true adds the Lenco widget origins
// to script-src / frame-src / connect-src for the checkout card route only.
function buildReportOnlyCsp(lenco: boolean): string {
  const scriptExtra = lenco ? ` ${LENCO_WIDGET}` : "";
  const frameExtra = lenco ? ` ${LENCO_WIDGET}` : "";
  const connectExtra = lenco ? ` ${LENCO_WIDGET} ${LENCO_API}` : "";
  return [
    "default-src 'self'",
    `script-src 'self' 'strict-dynamic' ${NONCE} https: ${GA4_SCRIPT}${scriptExtra}`,
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: ${CLOUDINARY} ${GA4_IMG}`,
    "font-src 'self' data:",
    `connect-src 'self' ${SUPABASE} ${SUPABASE_WS} ${GA4_CONNECT} ${SENTRY_INGEST}${connectExtra}`,
    `frame-src 'self'${frameExtra}`,
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "media-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'self'",
    `form-action 'self'${lenco ? ` ${LENCO_WIDGET}` : ""}`,
    "upgrade-insecure-requests",
  ].join("; ");
}

const STATIC_SECURITY_HEADERS = [
  { key: "Strict-Transport-Security", value: HSTS },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: PERMISSIONS_POLICY },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Content-Security-Policy", value: ENFORCED_CSP },
];

const nextConfig: NextConfig = {
  transpilePackages: [
    "@vergeo/config",
    "@vergeo/i18n",
    "@vergeo/observability",
    "@vergeo/types",
    "@vergeo/ui",
  ],
  eslint: {
    dirs: ["app"],
  },
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "res.cloudinary.com",
      },
    ],
  },
  async headers() {
    return [
      // Lenco widget CSP scoped to the checkout card route ONLY.
      {
        source: "/:locale/checkout/card/:paymentId",
        headers: [
          ...STATIC_SECURITY_HEADERS,
          { key: "Content-Security-Policy-Report-Only", value: buildReportOnlyCsp(true) },
        ],
      },
      // Everything else: no Lenco allowance. Negative lookahead keeps the card
      // route from also receiving this (report-only) CSP so it is not intersected.
      {
        source: "/((?!.*checkout/card/).*)",
        headers: [
          ...STATIC_SECURITY_HEADERS,
          { key: "Content-Security-Policy-Report-Only", value: buildReportOnlyCsp(false) },
        ],
      },
    ];
  },
  async rewrites() {
    // Same-origin proxy for the analytics beacon: navigator.sendBeacon posts to
    // /api/analytics/collect (same origin -> no CORS/preflight), which Next forwards
    // to the FastAPI ingest. Keeps the beacon cheap and CORS-free on 3G.
    const apiBase = resolveApiBaseUrl();
    if (!apiBase) {
      return [];
    }
    return [
      {
        source: "/api/analytics/collect",
        destination: `${apiBase}/analytics/collect`,
      },
    ];
  },
};

// Compose: next-intl(serwist(config)). withSerwist preserves `headers()`/CSP.
// NOTE (M16-P06): Sentry is deliberately NOT wired via `withSentryConfig` here — that
// plugin injects the browser SDK into every route's FIRST-LOAD JS (~+63 KB gz), which
// breaks CLAUDE.md #7 (customer routes ≤150 KB gz). Instead the SDK is lazy-loaded in
// an async chunk (`app/sentry-init.tsx` → dynamic `import('@sentry/nextjs')`). Client
// source-map upload runs as a separate gated build step — see docs/ops/observability.md.
export default withNextIntl(withSerwist(nextConfig));
