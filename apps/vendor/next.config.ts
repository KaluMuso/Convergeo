import createNextIntlPlugin from "next-intl/plugin";
import {
  buildConnectSrc,
  buildStaticSecurityHeaders,
  CSP_ORIGINS,
  isDevelopmentEnv,
  PERMISSIONS_POLICY_DEFAULT,
} from "@vergeo/config/security-headers";

import type { NextConfig } from "next";

const withNextIntl = createNextIntlPlugin("../../packages/i18n/src/request.ts");

/**
 * Security headers & CSP — M15-P03 + security audit wave (vendor origin, behind Caddy on OCI).
 *
 * CSP is NONCE-based (no `unsafe-inline` for scripts). The nonce is injected per
 * request by middleware, so the full script policy ships as
 * `Content-Security-Policy-Report-Only` while the framing/hardening directives are
 * enforced now. `{{CSP_NONCE}}` = per-request substitution point.
 * No Lenco widget allowance here (payouts use the API, not the hosted widget).
 * The QR ticket scanner needs the camera, so `camera=(self)` is scoped to the scan
 * routes only; every other route denies camera.
 * Report-only → enforce runbook: docs/ops/security-headers.md.
 */
const NONCE = "'nonce-{{CSP_NONCE}}'";
const CSP_REPORTING = "report-uri /api/csp-report; report-to csp-endpoint";
const isDev = isDevelopmentEnv();

function permissionsPolicy(cameraAllowed: boolean): string {
  const camera = cameraAllowed ? "camera=(self)" : "camera=()";
  return `${camera}, microphone=(), geolocation=(), browsing-topics=(), payment=(), usb=()`;
}

const ENFORCED_CSP = [
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'self'",
  "form-action 'self'",
  ...(isDev ? [] : ["upgrade-insecure-requests"]),
].join("; ");

const connectSrc = buildConnectSrc(
  process.env,
  `${CSP_ORIGINS.ga4Connect} ${CSP_ORIGINS.sentryIngest}`,
);

const REPORT_ONLY_CSP = [
  "default-src 'self'",
  `script-src 'self' 'strict-dynamic' ${NONCE} https: ${CSP_ORIGINS.ga4Script}`,
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: ${CSP_ORIGINS.cloudinary} ${CSP_ORIGINS.ga4Img}`,
  "font-src 'self' data:",
  `connect-src ${connectSrc}`,
  "frame-src 'self'",
  "worker-src 'self' blob:",
  "manifest-src 'self'",
  "media-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'self'",
  "form-action 'self'",
  ...(isDev ? [] : ["upgrade-insecure-requests"]),
  CSP_REPORTING,
].join("; ");

const BASE_HEADERS = buildStaticSecurityHeaders({
  xFrameOptions: "DENY",
  permissionsPolicy: PERMISSIONS_POLICY_DEFAULT,
  enforcedCsp: ENFORCED_CSP,
}).filter((header) => header.key !== "Permissions-Policy");

const COMMON_HEADERS = [
  ...BASE_HEADERS,
  { key: "Content-Security-Policy-Report-Only", value: REPORT_ONLY_CSP },
  { key: "Permissions-Policy", value: permissionsPolicy(false) },
];

const cameraAllowedHeaders = [
  ...BASE_HEADERS,
  { key: "Content-Security-Policy-Report-Only", value: REPORT_ONLY_CSP },
  { key: "Permissions-Policy", value: permissionsPolicy(true) },
];

const nextConfig: NextConfig = {
  output: "standalone",
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
      // Standalone QR scanner — camera allowed.
      { source: "/:locale/scan", headers: cameraAllowedHeaders },
      // Per-event QR scanner — camera allowed.
      { source: "/:locale/events/:id/scan", headers: cameraAllowedHeaders },
      // Everything else — camera denied (scan routes excluded via lookahead).
      {
        source: "/((?!.*scan).*)",
        headers: COMMON_HEADERS,
      },
    ];
  },
};

// NOTE (M16-P06): Sentry is lazy-loaded off first-load JS (`app/sentry-init.tsx`), not
// wired via `withSentryConfig`, which would inject the SDK into every route's first-load.
export default withNextIntl(nextConfig);
