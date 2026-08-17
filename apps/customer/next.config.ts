import withSerwistInit from "@serwist/next";
import createNextIntlPlugin from "next-intl/plugin";
import { assertVercelPublicSupabaseEnv } from "@vergeo/config";
import {
  buildConnectSrc,
  buildStaticSecurityHeaders,
  CSP_ORIGINS,
  isDevelopmentEnv,
  PERMISSIONS_POLICY_DEFAULT,
} from "@vergeo/config/security-headers";

import { resolveApiBaseUrl } from "./lib/api-base-url";

import type { NextConfig } from "next";

const withNextIntl = createNextIntlPlugin("../../packages/i18n/src/request.ts");
assertVercelPublicSupabaseEnv();

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
 * Security headers & CSP — M15-P03 + security audit wave (customer / Vercel origin).
 *
 * CSP is NONCE-based (no `unsafe-inline` for scripts). Next.js only injects a
 * per-request nonce into its own bootstrap scripts when the nonce arrives on the
 * *request* via middleware. Until that wiring lands, the full script/style policy
 * ships as `Content-Security-Policy-Report-Only` so violations are collected without
 * breaking the app, while the framing/hardening directives (which need no nonce) are
 * ENFORCED immediately. The `{{CSP_NONCE}}` token is the per-request substitution
 * point. Report-only → enforce runbook: docs/ops/security-headers.md.
 */
const NONCE = "'nonce-{{CSP_NONCE}}'";
const CSP_REPORTING = "report-uri /api/csp-report; report-to csp-endpoint";
/** Header name applied by middleware with a substituted nonce — not set here. */
const CSP_REPORT_ONLY_HEADER = "Content-Security-Policy-Report-Only";
const isDev = isDevelopmentEnv();

const ENFORCED_CSP = [
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'self'",
  "form-action 'self'",
  ...(isDev ? [] : ["upgrade-insecure-requests"]),
].join("; ");

// Report-only (full nonce policy). `lenco` = true adds the Lenco widget origins
// to script-src / frame-src / connect-src for the checkout card route only.
function buildReportOnlyCsp(lenco: boolean): string {
  const scriptExtra = lenco ? ` ${CSP_ORIGINS.lencoWidget}` : "";
  const frameExtra = lenco ? ` ${CSP_ORIGINS.lencoWidget}` : "";
  const connectExtra = lenco ? ` ${CSP_ORIGINS.lencoWidget} ${CSP_ORIGINS.lencoApi}` : "";
  const connectSrc = buildConnectSrc(
    process.env,
    `${CSP_ORIGINS.ga4Connect} ${CSP_ORIGINS.sentryIngest}${connectExtra}`,
  );
  return [
    "default-src 'self'",
    `script-src 'self' 'strict-dynamic' ${NONCE} https: ${CSP_ORIGINS.ga4Script}${scriptExtra}`,
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: ${CSP_ORIGINS.cloudinary} ${CSP_ORIGINS.ga4Img}`,
    "font-src 'self' data:",
    `connect-src ${connectSrc}`,
    `frame-src 'self'${frameExtra}`,
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "media-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'self'",
    `form-action 'self'${lenco ? ` ${CSP_ORIGINS.lencoWidget}` : ""}`,
    ...(isDev ? [] : ["upgrade-insecure-requests"]),
    CSP_REPORTING,
  ].join("; ");
}

const STATIC_SECURITY_HEADERS = buildStaticSecurityHeaders({
  xFrameOptions: "DENY",
  permissionsPolicy: PERMISSIONS_POLICY_DEFAULT,
  enforcedCsp: ENFORCED_CSP,
});

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
    // Report-only CSP (with per-request nonce) is applied in middleware.ts only.
    // Emitting `Content-Security-Policy-Report-Only` here with the unsubstituted
    // `{{CSP_NONCE}}` token produces console noise (`invalid source: 'nonce-{{CSP_NONCE}}'`).
    // Middleware gates Lenco on `/:locale/checkout/card/:paymentId` via
    // `buildReportOnlyCsp(true)` vs `buildReportOnlyCsp(false)`.
    void CSP_REPORT_ONLY_HEADER;
    void (true ? buildReportOnlyCsp(true) : buildReportOnlyCsp(false));
    return [
      {
        source: "/:path*",
        headers: [...STATIC_SECURITY_HEADERS],
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
