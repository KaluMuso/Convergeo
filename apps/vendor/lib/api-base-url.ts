import { resolvePublicApiBaseUrl, type ApiBaseEnvBag } from "@vergeo/config/api-base-url";

type EnvBag = ApiBaseEnvBag;

/**
 * Resolve the public API origin for vendor fetches.
 *
 * Production and Vercel Preview builds must never fall back to localhost — a
 * missing `NEXT_PUBLIC_API_BASE_URL` fails closed so vendor clients never
 * silently talk to a developer loopback. Dev keeps the local FastAPI default.
 */
export function resolveApiBaseUrl(env: EnvBag = {}): string | null {
  return resolvePublicApiBaseUrl(env, ["NEXT_PUBLIC_API_BASE_URL"]);
}

/** Convenience for call sites that already handle empty/unreachable API. */
export function getApiBaseUrl(env: EnvBag = {}): string {
  return resolveApiBaseUrl(env) ?? "";
}
