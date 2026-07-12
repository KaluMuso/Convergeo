import { withSentryConfig } from "@sentry/nextjs";
import createNextIntlPlugin from "next-intl/plugin";

import type { NextConfig } from "next";

const withNextIntl = createNextIntlPlugin("../../packages/i18n/src/request.ts");

/**
 * Security headers & CSP — M15-P03 (admin origin — STRICTEST).
 *
 * The admin origin is hardened (D20 / M13-P01): separate origin + IP allowlist +
 * Cloudflare Access. CSP is nonce-based (no `unsafe-inline` for scripts); the nonce
 * is injected per request by middleware (owned/locked elsewhere this wave), so the
 * full script policy ships as `Content-Security-Policy-Report-Only` while the
 * framing/hardening directives are enforced now. `{{CSP_NONCE}}` = per-request
 * substitution point.
 * Strictest posture vs customer/vendor: `frame-ancestors 'none'` (never framed),
 * no Lenco widget, no GA4 / no third-party script origins, all Permissions-Policy
 * features denied. Report-only → enforce runbook: docs/ops/security-headers.md.
 */
const NONCE = "'nonce-{{CSP_NONCE}}'";

const CLOUDINARY = "https://res.cloudinary.com";
const SUPABASE = "https://*.supabase.co";
const SUPABASE_WS = "wss://*.supabase.co";
// Sentry ingest (M16-P06) — browser SDK POSTs events here. Scoped to the ingest
// subdomains only (incl. region variants), NOT a blanket sentry.io allowance.
const SENTRY_INGEST =
  "https://*.ingest.sentry.io https://*.ingest.us.sentry.io https://*.ingest.de.sentry.io";

const HSTS = "max-age=63072000; includeSubDomains; preload";
// Strictest: deny every powerful feature outright.
const PERMISSIONS_POLICY =
  "camera=(), microphone=(), geolocation=(), browsing-topics=(), payment=(), usb=(), " +
  "accelerometer=(), gyroscope=(), magnetometer=(), fullscreen=(self)";

// Enforced now: framing/hardening directives (no nonce required). Admin is never
// allowed to be framed → `frame-ancestors 'none'`.
const ENFORCED_CSP = [
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "upgrade-insecure-requests",
].join("; ");

// Report-only full nonce policy — no third-party script/frame origins.
const REPORT_ONLY_CSP = [
  "default-src 'self'",
  `script-src 'self' 'strict-dynamic' ${NONCE}`,
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: ${CLOUDINARY}`,
  "font-src 'self' data:",
  `connect-src 'self' ${SUPABASE} ${SUPABASE_WS} ${SENTRY_INGEST}`,
  "frame-src 'none'",
  "worker-src 'self' blob:",
  "manifest-src 'self'",
  "media-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "upgrade-insecure-requests",
].join("; ");

const SECURITY_HEADERS = [
  { key: "Strict-Transport-Security", value: HSTS },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: PERMISSIONS_POLICY },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
  { key: "Content-Security-Policy", value: ENFORCED_CSP },
  { key: "Content-Security-Policy-Report-Only", value: REPORT_ONLY_CSP },
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
      {
        source: "/:path*",
        headers: SECURITY_HEADERS,
      },
    ];
  },
};

/**
 * Sentry build wiring — M16-P06 (admin — strictest client init). Composed
 * OUTERMOST, around `withNextIntl(...)`, so the M15-P03 `headers()`/CSP block is
 * preserved untouched. Source-map upload is gated on `SENTRY_AUTH_TOKEN` so a
 * missing token never fails the build.
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
