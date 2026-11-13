import createNextIntlPlugin from "next-intl/plugin";
import { assertVercelPublicSupabaseEnv } from "@vergeo/config";
import {
  buildConnectSrc,
  buildStaticSecurityHeaders,
  CSP_ORIGINS,
  isDevelopmentEnv,
  PERMISSIONS_POLICY_ADMIN,
} from "@vergeo/config/security-headers";

import type { NextConfig } from "next";

// Fail Vercel Preview/Production builds closed on missing/invalid public
// Supabase config — inactive off Vercel (GitHub CI, local `next build`,
// or the OCI/Caddy standalone build). See packages/config/src/env.ts.
assertVercelPublicSupabaseEnv();

const withNextIntl = createNextIntlPlugin("../../packages/i18n/src/request.ts");

/**
 * Security headers & CSP — M15-P03 + security audit wave (admin origin — STRICTEST).
 *
 * The admin origin is hardened (D20 / M13-P01): separate origin + IP allowlist +
 * Cloudflare Access. CSP is nonce-based (no `unsafe-inline` for scripts); the nonce
 * is injected per request by middleware, so the full script policy ships as
 * `Content-Security-Policy-Report-Only` while the framing/hardening directives are
 * enforced now. `{{CSP_NONCE}}` = per-request substitution point.
 * Strictest posture vs customer/vendor: `frame-ancestors 'none'` (never framed),
 * no Lenco widget, no GA4 / no third-party script origins, all Permissions-Policy
 * features denied. Report-only → enforce runbook: docs/ops/security-headers.md.
 */
const NONCE = "'nonce-{{CSP_NONCE}}'";
const CSP_REPORTING = "report-uri /api/csp-report; report-to csp-endpoint";
const isDev = isDevelopmentEnv();

// Enforced now: framing/hardening directives (no nonce required). Admin is never
// allowed to be framed → `frame-ancestors 'none'`.
const ENFORCED_CSP = [
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  ...(isDev ? [] : ["upgrade-insecure-requests"]),
].join("; ");

const connectSrc = buildConnectSrc(process.env, CSP_ORIGINS.sentryIngest);

// Report-only full nonce policy — no third-party script/frame origins.
const REPORT_ONLY_CSP = [
  "default-src 'self'",
  `script-src 'self' 'strict-dynamic' ${NONCE}`,
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: ${CSP_ORIGINS.cloudinary}`,
  "font-src 'self' data:",
  `connect-src ${connectSrc}`,
  "frame-src 'none'",
  "worker-src 'self' blob:",
  "manifest-src 'self'",
  "media-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  ...(isDev ? [] : ["upgrade-insecure-requests"]),
  CSP_REPORTING,
].join("; ");

const SECURITY_HEADERS = [
  ...buildStaticSecurityHeaders({
    xFrameOptions: "DENY",
    permissionsPolicy: PERMISSIONS_POLICY_ADMIN,
    enforcedCsp: ENFORCED_CSP,
  }),
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
  { key: "Content-Security-Policy-Report-Only", value: REPORT_ONLY_CSP },
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
      {
        source: "/:path*",
        headers: SECURITY_HEADERS,
      },
    ];
  },
};

// NOTE (M16-P06): Sentry is lazy-loaded off first-load JS (`app/sentry-init.tsx`), not
// wired via `withSentryConfig`, which would inject the SDK into every route's first-load.
export default withNextIntl(nextConfig);
