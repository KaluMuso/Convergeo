import { resolvePublicApiBaseUrl, type ApiBaseEnvBag } from "@vergeo/config/api-base-url";

type EnvBag = ApiBaseEnvBag;

/**
 * Resolve the public API origin for customer fetches.
 *
 * Production and Vercel Preview builds must never fall back to localhost — a
 * missing `NEXT_PUBLIC_API_BASE_URL` fails closed so checkout/payment never
 * silently talk to a developer loopback. Dev keeps the local FastAPI default.
 */
export function resolveApiBaseUrl(env: EnvBag = {}): string | null {
  return resolvePublicApiBaseUrl(env, ["NEXT_PUBLIC_API_BASE_URL"]);
}

/** Convenience for call sites that already handle empty/unreachable API. */
export function getApiBaseUrl(env: EnvBag = {}): string {
  return resolveApiBaseUrl(env) ?? "";
}

/**
 * Absolute API URL for server/client fetches.
 *
 * Returns null when the base is unset so callers never `fetch("/relative…")`
 * during production builds without env (relative URLs hang Next.js SSG).
 */
export function absoluteApiUrl(path: string, env: EnvBag = {}): string | null {
  const base = resolveApiBaseUrl(env);
  if (!base) {
    return null;
  }
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${base}${suffix}`;
}
