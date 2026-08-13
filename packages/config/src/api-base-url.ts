export type ApiBaseEnvBag = {
  NEXT_PUBLIC_API_BASE_URL?: string;
  NEXT_PUBLIC_VERGEO_API_URL?: string;
  NODE_ENV?: string;
  VERCEL_ENV?: string;
};

export type PublicApiEnvKey = "NEXT_PUBLIC_API_BASE_URL" | "NEXT_PUBLIC_VERGEO_API_URL";

export const PRODUCTION_API_HOST = "api.vergeo5.com";
export const STAGING_API_HOST = "api.staging.vergeo5.com";

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

/**
 * Direct `process.env.NEXT_PUBLIC_*` / `NODE_ENV` / `VERCEL_ENV` reads so Next.js
 * can inline them into client bundles. Passing `process.env` as an object and
 * reading `env.NEXT_PUBLIC_API_BASE_URL` is NOT inlined, which previously let
 * production Vendor/Admin bundles fall through to the localhost default.
 */
function inlinedEnv(): ApiBaseEnvBag {
  return {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
    NEXT_PUBLIC_VERGEO_API_URL: process.env.NEXT_PUBLIC_VERGEO_API_URL,
    NODE_ENV: process.env.NODE_ENV,
    VERCEL_ENV: process.env.VERCEL_ENV,
  };
}

function readBag(
  env: ApiBaseEnvBag,
  key: keyof ApiBaseEnvBag,
  inlined: string | undefined,
): string | undefined {
  if (Object.prototype.hasOwnProperty.call(env, key)) {
    return env[key];
  }
  return inlined;
}

function mergeEnv(env: ApiBaseEnvBag): ApiBaseEnvBag {
  const inlined = inlinedEnv();
  return {
    NEXT_PUBLIC_API_BASE_URL: readBag(
      env,
      "NEXT_PUBLIC_API_BASE_URL",
      inlined.NEXT_PUBLIC_API_BASE_URL,
    ),
    NEXT_PUBLIC_VERGEO_API_URL: readBag(
      env,
      "NEXT_PUBLIC_VERGEO_API_URL",
      inlined.NEXT_PUBLIC_VERGEO_API_URL,
    ),
    NODE_ENV: readBag(env, "NODE_ENV", inlined.NODE_ENV),
    VERCEL_ENV: readBag(env, "VERCEL_ENV", inlined.VERCEL_ENV),
  };
}

export function isLoopbackApiOrigin(origin: string): boolean {
  try {
    const host = new URL(origin).hostname.toLowerCase();
    return LOOPBACK_HOSTS.has(host) || host.endsWith(".localhost");
  } catch {
    const lowered = origin.toLowerCase();
    return (
      lowered.includes("localhost") || lowered.includes("127.0.0.1") || lowered.includes("[::1]")
    );
  }
}

export function hostnameOfOrigin(origin: string): string | null {
  try {
    return new URL(origin).hostname.toLowerCase();
  } catch {
    return null;
  }
}

export function isProductionApiOrigin(origin: string): boolean {
  return hostnameOfOrigin(origin) === PRODUCTION_API_HOST;
}

export function isDeployedFrontendEnv(env: ApiBaseEnvBag = {}): boolean {
  const merged = mergeEnv(env);
  if (merged.VERCEL_ENV === "production" || merged.VERCEL_ENV === "preview") {
    return true;
  }
  return merged.NODE_ENV === "production";
}

function resolveDeployedConfigured(
  configured: string | undefined,
  vercelEnv: string | undefined,
): string | null {
  if (!configured) {
    return null;
  }
  if (isLoopbackApiOrigin(configured)) {
    return null;
  }
  if (vercelEnv === "preview" && isProductionApiOrigin(configured)) {
    return null;
  }
  return configured;
}

export function resolvePublicApiBaseUrl(
  env: ApiBaseEnvBag = {},
  keys: readonly PublicApiEnvKey[] = ["NEXT_PUBLIC_API_BASE_URL"],
): string | null {
  const merged = mergeEnv(env);

  let configured: string | undefined;
  for (const key of keys) {
    const value = merged[key]?.trim();
    if (value) {
      configured = value.replace(/\/$/, "");
      break;
    }
  }

  // Direct `process.env.NODE_ENV` comparison lets Next.js DCE the else branch
  // (including the localhost literal) out of production client bundles.
  if (process.env.NODE_ENV === "production") {
    return resolveDeployedConfigured(configured, merged.VERCEL_ENV ?? process.env.VERCEL_ENV);
  } else {
    if (isDeployedFrontendEnv(merged)) {
      return resolveDeployedConfigured(configured, merged.VERCEL_ENV);
    }
    return configured ?? "http://localhost:8000";
  }
}
