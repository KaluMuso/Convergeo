/**
 * Shared security-header constants and CSP helpers (M15-P03 + security audit wave).
 *
 * Used by Next.js `next.config.ts` (build-time headers) and `middleware.ts`
 * (per-request report-only CSP). Keeps API / CDN / Vercel allowlists in one place.
 */

export type EnvBag = Record<string, string | undefined>;

export const HSTS_VALUE = "max-age=63072000; includeSubDomains; preload";

export const CSP_ORIGINS = {
  cloudinary: "https://res.cloudinary.com",
  supabase: "https://*.supabase.co",
  supabaseWs: "wss://*.supabase.co",
  ga4Script: "https://*.googletagmanager.com",
  ga4Connect:
    "https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com",
  ga4Img: "https://*.google-analytics.com https://*.googletagmanager.com",
  lencoWidget: "https://pay.lenco.co https://pay.sandbox.lenco.co",
  lencoApi: "https://api.lenco.co https://api.sandbox.lenco.co",
  sentryIngest:
    "https://*.ingest.sentry.io https://*.ingest.us.sentry.io https://*.ingest.de.sentry.io",
  vercel: "https://*.vercel.app https://vitals.vercel-insights.com https://vercel.live",
  apiProduction: "https://api.vergeo5.com",
  apiStaging: "https://api.staging.vergeo5.com",
} as const;

export const PERMISSIONS_POLICY_DEFAULT =
  "camera=(), microphone=(), geolocation=(), browsing-topics=(), payment=(), usb=()";

export const PERMISSIONS_POLICY_ADMIN =
  "camera=(), microphone=(), geolocation=(), browsing-topics=(), payment=(), usb=(), " +
  "accelerometer=(), gyroscope=(), magnetometer=(), fullscreen=(self)";

export function isDevelopmentEnv(env: EnvBag = process.env): boolean {
  return env.NODE_ENV !== "production";
}

/**
 * Origins the browser may `fetch()` against (cross-origin API + local dev).
 * Includes configured `NEXT_PUBLIC_API_BASE_URL` / `NEXT_PUBLIC_VERGEO_API_URL`
 * plus known prod/staging API hosts so preview builds stay functional.
 */
export function resolveApiConnectOrigins(env: EnvBag = process.env): string {
  const origins = new Set<string>([CSP_ORIGINS.apiProduction, CSP_ORIGINS.apiStaging]);

  for (const key of ["NEXT_PUBLIC_API_BASE_URL", "NEXT_PUBLIC_VERGEO_API_URL"] as const) {
    const trimmed = env[key]?.trim();
    if (trimmed) {
      origins.add(trimmed.replace(/\/$/, ""));
    }
  }

  // Direct `process.env.NODE_ENV` comparison so production Next.js builds DCE
  // the loopback literal out of middleware / CSP helpers. Passing `env` into
  // `isDevelopmentEnv` is not enough for Terser to drop the string.
  if (process.env.NODE_ENV !== "production") {
    if (isDevelopmentEnv(env)) {
      origins.add("http://localhost:8000");
    }
  }

  return [...origins].join(" ");
}

export function buildConnectSrc(env: EnvBag = process.env, extra = ""): string {
  const api = resolveApiConnectOrigins(env);
  const vercel = isDevelopmentEnv(env) ? "" : ` ${CSP_ORIGINS.vercel}`;
  const suffix = extra ? ` ${extra}` : "";
  return `'self' ${api} ${CSP_ORIGINS.supabase} ${CSP_ORIGINS.supabaseWs}${vercel}${suffix}`
    .replace(/\s+/g, " ")
    .trim();
}

export type StaticSecurityHeader = { key: string; value: string };

/** Baseline headers applied on every route (HSTS omitted in development). */
export function buildStaticSecurityHeaders(options: {
  xFrameOptions: "DENY" | "SAMEORIGIN";
  permissionsPolicy: string;
  enforcedCsp: string;
  env?: EnvBag;
}): StaticSecurityHeader[] {
  const env = options.env ?? process.env;
  const headers: StaticSecurityHeader[] = [];

  if (!isDevelopmentEnv(env)) {
    headers.push({ key: "Strict-Transport-Security", value: HSTS_VALUE });
  }

  headers.push(
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: options.xFrameOptions },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    { key: "Permissions-Policy", value: options.permissionsPolicy },
    { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
    { key: "Content-Security-Policy", value: options.enforcedCsp },
  );

  return headers;
}
