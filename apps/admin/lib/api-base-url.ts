import {
  hostnameOfOrigin,
  resolvePublicApiBaseUrl,
  type ApiBaseEnvBag,
} from "@vergeo/config/api-base-url";

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

/**
 * Host-only form of {@link resolveApiBaseUrl} for `/health` — the same
 * effective configuration the app itself fetches with, reduced to a
 * hostname so the deploy-staging verifier can prove what a deployed
 * artifact actually resolves without needing the full URL. `null` on a
 * missing/malformed origin (fail-closed, never substitutes a default).
 */
export function resolveApiHost(env: EnvBag = {}): string | null {
  const base = resolveApiBaseUrl(env);
  return base ? hostnameOfOrigin(base) : null;
}
