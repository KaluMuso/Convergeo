type EnvBag = {
  NEXT_PUBLIC_API_BASE_URL?: string;
  NODE_ENV?: string;
};

/**
 * Resolve the public API origin for vendor fetches.
 *
 * Production builds must never fall back to localhost — a missing
 * `NEXT_PUBLIC_API_BASE_URL` fails closed so vendor clients never silently
 * talk to a developer loopback. Dev keeps the local FastAPI default.
 */
export function resolveApiBaseUrl(env: EnvBag = process.env): string | null {
  const configured = env.NEXT_PUBLIC_API_BASE_URL?.trim();
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
