import { resolveApiBaseUrl, type resolveApiBaseUrl as ResolveApiBaseUrlFn } from "./api-base-url";

type EnvBag = Parameters<typeof ResolveApiBaseUrlFn>[0];

/**
 * Interpret an anonymous probe of a FastAPI route.
 *
 * 404/5xx → router absent or unhealthy (fail closed).
 * 401/403 → auth required but router registered.
 * 405/422 → wrong method/body but router registered (POST-only routes).
 */
export function isApiRouteRegistered(status: number): boolean {
  if (status === 404) {
    return false;
  }
  if (status >= 500) {
    return false;
  }
  return status === 200 || status === 401 || status === 403 || status === 405 || status === 422;
}

/** Build an absolute API URL for server-side probes, or null when unset in production. */
export function absoluteApiUrl(path: string, env: EnvBag = process.env): string | null {
  const base = resolveApiBaseUrl(env);
  if (!base) {
    return null;
  }
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${base}${suffix}`;
}

/** A probe that has not answered by now is treated as "route absent" (fail closed). */
export const PROBE_TIMEOUT_MS = 1500;
/**
 * Route registration only changes on an API deploy, so a probe result is safe to
 * reuse across requests instead of re-fetching it on every vendor page render.
 */
export const PROBE_REVALIDATE_SECONDS = 300;

/**
 * Server-only: returns true when the configured API origin exposes the route.
 * Fails closed on missing base URL, network errors, 404, and 5xx.
 */
export async function probeApiRoute(path: string, env: EnvBag = process.env): Promise<boolean> {
  const url = absoluteApiUrl(path, env);
  if (!url) {
    return false;
  }

  try {
    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      next: { revalidate: PROBE_REVALIDATE_SECONDS },
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
    });
    return isApiRouteRegistered(response.status);
  } catch {
    return false;
  }
}
