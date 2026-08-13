import { resolvePublicApiBaseUrl, type ApiBaseEnvBag } from "@vergeo/config/api-base-url";

type EnvBag = ApiBaseEnvBag;

/**
 * Resolve the public API origin for vendor fetches.
 *
 * Deployed planes (`NEXT_PUBLIC_DEPLOYMENT_PLANE=production|staging|preview`)
 * never fall back to a loopback origin. A missing plane fails closed so vendor
 * clients never silently talk to a developer machine. Local `next dev` must
 * set `NEXT_PUBLIC_DEPLOYMENT_PLANE=development`.
 */
export function resolveApiBaseUrl(env: EnvBag = {}): string | null {
  return resolvePublicApiBaseUrl(env, ["NEXT_PUBLIC_API_BASE_URL"]);
}

/** Convenience for call sites that already handle empty/unreachable API. */
export function getApiBaseUrl(env: EnvBag = {}): string {
  return resolveApiBaseUrl(env) ?? "";
}
