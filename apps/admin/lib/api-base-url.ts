type EnvBag = {
  NEXT_PUBLIC_VERGEO_API_URL?: string;
  NODE_ENV?: string;
};

/**
 * Resolve the public API origin for admin fetches.
 *
 * Admin Vercel projects use `NEXT_PUBLIC_VERGEO_API_URL`. Production builds
 * must never fall back to localhost when unset.
 */
export function resolveApiBaseUrl(env: EnvBag = process.env): string | null {
  const configured = env.NEXT_PUBLIC_VERGEO_API_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, "");
  }
  if (env.NODE_ENV === "production") {
    return null;
  }
  return "http://localhost:8000";
}

/** Convenience for call sites that already handle empty/unreachable API. */
export function getApiBaseUrl(env: EnvBag = process.env): string {
  return resolveApiBaseUrl(env) ?? "";
}
