import { resolvePublicApiBaseUrl, type ApiBaseEnvBag } from "@vergeo/config/api-base-url";

type EnvBag = ApiBaseEnvBag;

/**
 * Resolve the public API origin for customer fetches.
 *
 * Deployed planes (`NEXT_PUBLIC_DEPLOYMENT_PLANE=production|staging|preview`)
 * never fall back to a loopback origin. A missing plane fails closed so
 * checkout never silently talks to a developer machine. Local `next dev`
 * must set `NEXT_PUBLIC_DEPLOYMENT_PLANE=development`.
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
