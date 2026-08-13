export type ApiBaseEnvBag = {
  NEXT_PUBLIC_API_BASE_URL?: string;
  NEXT_PUBLIC_VERGEO_API_URL?: string;
  NEXT_PUBLIC_DEPLOYMENT_PLANE?: string;
  NODE_ENV?: string;
};

export type PublicApiEnvKey = "NEXT_PUBLIC_API_BASE_URL" | "NEXT_PUBLIC_VERGEO_API_URL";

export type DeploymentPlane = "production" | "staging" | "preview" | "development";

export const PRODUCTION_API_HOST = "api.vergeo5.com";
export const STAGING_API_HOST = "api.staging.vergeo5.com";

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

/**
 * Direct `process.env.NEXT_PUBLIC_*` / `NODE_ENV` reads so Next.js can inline
 * them into client bundles. `VERCEL_ENV` is NOT a `NEXT_PUBLIC_*` variable and
 * is not reliably present in the browser — plane selection uses
 * `NEXT_PUBLIC_DEPLOYMENT_PLANE` instead.
 *
 * Passing `process.env` as an object and reading `env.NEXT_PUBLIC_API_BASE_URL`
 * is NOT inlined, which previously let production Vendor/Admin bundles fall
 * through to a loopback default.
 */
function inlinedEnv(): ApiBaseEnvBag {
  return {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
    NEXT_PUBLIC_VERGEO_API_URL: process.env.NEXT_PUBLIC_VERGEO_API_URL,
    NEXT_PUBLIC_DEPLOYMENT_PLANE: process.env.NEXT_PUBLIC_DEPLOYMENT_PLANE,
    NODE_ENV: process.env.NODE_ENV,
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
    NEXT_PUBLIC_DEPLOYMENT_PLANE: readBag(
      env,
      "NEXT_PUBLIC_DEPLOYMENT_PLANE",
      inlined.NEXT_PUBLIC_DEPLOYMENT_PLANE,
    ),
    NODE_ENV: readBag(env, "NODE_ENV", inlined.NODE_ENV),
  };
}

export function normalizeDeploymentPlane(value: string | undefined): DeploymentPlane | "unset" {
  const plane = (value ?? "").trim().toLowerCase();
  if (
    plane === "production" ||
    plane === "staging" ||
    plane === "preview" ||
    plane === "development"
  ) {
    return plane;
  }
  return "unset";
}

export function isLoopbackApiOrigin(origin: string): boolean {
  try {
    const host = new URL(origin).hostname.toLowerCase();
    return LOOPBACK_HOSTS.has(host) || host.endsWith(".localhost");
  } catch {
    const lowered = origin.toLowerCase();
    return (
      lowered.includes("127.0.0.1") || lowered.includes("[::1]") || lowered.includes("localhost")
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

export function isStagingApiOrigin(origin: string): boolean {
  return hostnameOfOrigin(origin) === STAGING_API_HOST;
}

export function isDeployedFrontendEnv(env: ApiBaseEnvBag = {}): boolean {
  const merged = mergeEnv(env);
  const plane = normalizeDeploymentPlane(merged.NEXT_PUBLIC_DEPLOYMENT_PLANE);
  if (plane === "production" || plane === "staging" || plane === "preview") {
    return true;
  }
  return merged.NODE_ENV === "production";
}

function pickConfigured(env: ApiBaseEnvBag, keys: readonly PublicApiEnvKey[]): string | undefined {
  for (const key of keys) {
    const value = env[key]?.trim();
    if (value) {
      return value.replace(/\/$/, "");
    }
  }
  return undefined;
}

function allowOnlyProductionApi(configured: string | undefined): string | null {
  if (!configured) {
    return `https://${PRODUCTION_API_HOST}`;
  }
  if (isLoopbackApiOrigin(configured) || isStagingApiOrigin(configured)) {
    return null;
  }
  return configured;
}

function allowOnlyStagingApi(configured: string | undefined): string | null {
  if (!configured) {
    return `https://${STAGING_API_HOST}`;
  }
  if (isLoopbackApiOrigin(configured) || isProductionApiOrigin(configured)) {
    return null;
  }
  return configured;
}

function allowDevelopmentApi(configured: string | undefined): string | null {
  if (!configured) {
    return "http://localhost:8000";
  }
  if (isLoopbackApiOrigin(configured)) {
    return configured;
  }
  if (isProductionApiOrigin(configured)) {
    return null;
  }
  if (isStagingApiOrigin(configured)) {
    return configured;
  }
  return null;
}

function resolveByPlane(
  plane: DeploymentPlane | "unset",
  configured: string | undefined,
): string | null {
  if (plane === "production") {
    return allowOnlyProductionApi(configured);
  }
  if (plane === "staging" || plane === "preview") {
    return allowOnlyStagingApi(configured);
  }
  if (plane === "development") {
    return allowDevelopmentApi(configured);
  }
  return null;
}

export function resolvePublicApiBaseUrl(
  env: ApiBaseEnvBag = {},
  keys: readonly PublicApiEnvKey[] = ["NEXT_PUBLIC_API_BASE_URL"],
): string | null {
  const merged = mergeEnv(env);
  const configured = pickConfigured(merged, keys);

  // Direct `process.env.NODE_ENV` comparison lets Next.js DCE the else branch
  // (including the loopback literal) out of production client bundles.
  if (process.env.NODE_ENV === "production") {
    // Direct `NEXT_PUBLIC_DEPLOYMENT_PLANE` comparisons so a production-plane
    // build can DCE staging/development origin literals.
    if (process.env.NEXT_PUBLIC_DEPLOYMENT_PLANE === "production") {
      return allowOnlyProductionApi(configured);
    }
    if (
      process.env.NEXT_PUBLIC_DEPLOYMENT_PLANE === "staging" ||
      process.env.NEXT_PUBLIC_DEPLOYMENT_PLANE === "preview"
    ) {
      return allowOnlyStagingApi(configured);
    }
    return null;
  } else {
    const plane = normalizeDeploymentPlane(merged.NEXT_PUBLIC_DEPLOYMENT_PLANE);
    return resolveByPlane(plane, configured);
  }
}
