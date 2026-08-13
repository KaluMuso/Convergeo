import { resolvePublicApiBaseUrl, type ApiBaseEnvBag } from "@vergeo/config/api-base-url";

type EnvBag = ApiBaseEnvBag;

/**
 * Resolve the public API origin for admin fetches.
 *
 * Admin Vercel projects use `NEXT_PUBLIC_VERGEO_API_URL`. Deployed planes
 * never fall back to a loopback origin when unset. Local `next dev` must set
 * `NEXT_PUBLIC_DEPLOYMENT_PLANE=development`.
 */
export function resolveApiBaseUrl(env: EnvBag = {}): string | null {
  return resolvePublicApiBaseUrl(env, ["NEXT_PUBLIC_VERGEO_API_URL"]);
}

/** Convenience for call sites that already handle empty/unreachable API. */
export function getApiBaseUrl(env: EnvBag = {}): string {
  return resolveApiBaseUrl(env) ?? "";
}
