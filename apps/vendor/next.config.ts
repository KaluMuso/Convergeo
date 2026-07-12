import { withSentryConfig } from "@sentry/nextjs";
import createNextIntlPlugin from "next-intl/plugin";

import type { NextConfig } from "next";

const withNextIntl = createNextIntlPlugin("../../packages/i18n/src/request.ts");

/**
 * Security headers & CSP — M15-P03 (vendor origin, behind Caddy on OCI).
 *
 * CSP is NONCE-based (no `unsafe-inline` for scripts). The nonce is injected per
 * request by middleware (owned/locked elsewhere this wave), so the full script
 * policy ships as `Content-Security-Policy-Report-Only` while the framing/hardening
 * directives are enforced now. `{{CSP_NONCE}}` = per-request substitution point.
 * No Lenco widget allowance here (payouts use the API, not the hosted widget).
 * The QR ticket scanner needs the camera, so `camera=(self)` is scoped to the scan
 * routes only; every other route denies camera.
 * Report-only → enforce runbook: docs/ops/security-headers.md.
 */
const NONCE = "'nonce-{{CSP_NONCE}}'";

const CLOUDINARY = "https://res.cloudinary.com";
const SUPABASE = "https://*.supabase.co";
const SUPABASE_WS = "wss://*.supabase.co";
// GA4 allowed in CSP now; M16-P05 wires the actual tag (not wired here).
const GA4_SCRIPT = "https://*.googletagmanager.com";
const GA4_CONNECT =
  "https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com";
const GA4_IMG = "https://*.google-analytics.com https://*.googletagmanager.com";
// Sentry ingest (M16-P06) — browser SDK POSTs events here. Scoped to the ingest
// subdomains only (incl. region variants), NOT a blanket sentry.io allowance.
const SENTRY_INGEST =
  "https://*.ingest.sentry.io https://*.ingest.us.sentry.io https://*.ingest.de.sentry.io";

const HSTS = "max-age=63072000; includeSubDomains; preload";

function permissionsPolicy(cameraAllowed: boolean): string {
  const camera = cameraAllowed ? "camera=(self)" : "camera=()";
  return `${camera}, microphone=(), geolocation=(), browsing-topics=(), payment=(), usb=()`;
}

const ENFORCED_CSP = [
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'self'",
  "form-action 'self'",
  "upgrade-insecure-requests",
].join("; ");

const REPORT_ONLY_CSP = [
  "default-src 'self'",
  `script-src 'self' 'strict-dynamic' ${NONCE} https: ${GA4_SCRIPT}`,
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: ${CLOUDINARY} ${GA4_IMG}`,
  "font-src 'self' data:",
  `connect-src 'self' ${SUPABASE} ${SUPABASE_WS} ${GA4_CONNECT} ${SENTRY_INGEST}`,
  "frame-src 'self'",
  "worker-src 'self' blob:",
  "manifest-src 'self'",
  "media-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'self'",
  "form-action 'self'",
  "upgrade-insecure-requests",
].join("; ");

// Headers common to every route (nonce/framing/transport). Permissions-Policy is
// added per route so camera can be scoped to the scanner.
const COMMON_HEADERS = [
  { key: "Strict-Transport-Security", value: HSTS },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Content-Security-Policy", value: ENFORCED_CSP },
  { key: "Content-Security-Policy-Report-Only", value: REPORT_ONLY_CSP },
];

const cameraAllowedHeaders = [
  ...COMMON_HEADERS,
  { key: "Permissions-Policy", value: permissionsPolicy(true) },
];

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@vergeo/config", "@vergeo/i18n", "@vergeo/types", "@vergeo/ui"],
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
      // Standalone QR scanner — camera allowed.
      { source: "/:locale/scan", headers: cameraAllowedHeaders },
      // Per-event QR scanner — camera allowed.
      { source: "/:locale/events/:id/scan", headers: cameraAllowedHeaders },
      // Everything else — camera denied (scan routes excluded via lookahead).
      {
        source: "/((?!.*scan).*)",
        headers: [
          ...COMMON_HEADERS,
          { key: "Permissions-Policy", value: permissionsPolicy(false) },
        ],
      },
    ];
  },
};

/**
 * Sentry build wiring — M16-P06. Composed OUTERMOST, around `withNextIntl(...)`,
 * so the M15-P03 `headers()`/CSP block is preserved untouched. Source-map upload is
 * gated on `SENTRY_AUTH_TOKEN` so a missing token never fails the build.
 */
const sentryBuildOptions = {
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  silent: true,
  telemetry: false,
  widenClientFileUpload: true,
  disableLogger: true,
  sourcemaps: { disable: !process.env.SENTRY_AUTH_TOKEN },
};

export default withSentryConfig(withNextIntl(nextConfig), sentryBuildOptions);
