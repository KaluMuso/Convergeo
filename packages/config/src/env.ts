import { z } from "zod";

const SERVER_ENV_KEYS = [
  "SUPABASE_SERVICE_ROLE_KEY",
  "LENCO_API_TOKEN",
  "OPENROUTER_API_KEY",
  "WHATSAPP_TOKEN",
  "AT_API_KEY",
  "AT_USERNAME",
  "AT_SENDER_ID",
  "SEND_SMS_HOOK_SECRET",
  "RESEND_API_KEY",
  "CLOUDINARY_URL",
] as const;

const PUBLIC_ENV_KEYS = ["SUPABASE_URL", "SUPABASE_ANON_KEY", "LENCO_BASE_URL"] as const;

const serverEnvSchema = z.object({
  SUPABASE_SERVICE_ROLE_KEY: z.string().min(1),
  LENCO_API_TOKEN: z.string().min(1),
  OPENROUTER_API_KEY: z.string().min(1),
  WHATSAPP_TOKEN: z.string().min(1),
  AT_API_KEY: z.string().min(1),
  AT_USERNAME: z.string().min(1),
  AT_SENDER_ID: z.string().min(1),
  SEND_SMS_HOOK_SECRET: z.string().min(1),
  RESEND_API_KEY: z.string().min(1),
  CLOUDINARY_URL: z.string().min(1),
});

const publicEnvSchema = z.object({
  SUPABASE_URL: z.string().url(),
  SUPABASE_ANON_KEY: z.string().min(1),
  LENCO_BASE_URL: z.string().url(),
});

export type ServerEnv = z.infer<typeof serverEnvSchema>;
export type PublicEnv = z.infer<typeof publicEnvSchema>;

export type LoadedEnv = {
  server: ServerEnv;
  public: PublicEnv;
};

export type EnvSource = Record<string, string | undefined>;

const SECRET_KEYS = new Set<string>(SERVER_ENV_KEYS);

function readProcessEnv(): EnvSource {
  const env = (globalThis as { process?: { env?: EnvSource } }).process?.env;
  return env ?? {};
}

function pickEnv(source: EnvSource, keys: readonly string[]): EnvSource {
  return Object.fromEntries(keys.map((key) => [key, source[key]]));
}

function formatEnvError(error: z.ZodError): string {
  return error.issues
    .map((issue) => {
      const key = issue.path.join(".");
      if (SECRET_KEYS.has(key)) {
        return `Missing or invalid required environment variable: ${key} (value redacted)`;
      }
      return `Missing or invalid required environment variable: ${key}`;
    })
    .join("\n");
}

function parseEnv<T extends z.ZodTypeAny>(schema: T, source: EnvSource): z.infer<T> {
  const result = schema.safeParse(source);
  if (!result.success) {
    throw new Error(formatEnvError(result.error));
  }
  return result.data;
}

export function loadServerEnv(source: EnvSource = readProcessEnv()): ServerEnv {
  return parseEnv(serverEnvSchema, pickEnv(source, SERVER_ENV_KEYS));
}

export function loadPublicEnv(source: EnvSource = readProcessEnv()): PublicEnv {
  return parseEnv(publicEnvSchema, pickEnv(source, PUBLIC_ENV_KEYS));
}

export function loadEnv(source: EnvSource = readProcessEnv()): LoadedEnv {
  return {
    server: loadServerEnv(source),
    public: loadPublicEnv(source),
  };
}

const VERCEL_PUBLIC_SUPABASE_URL_KEY = "NEXT_PUBLIC_SUPABASE_URL";
const VERCEL_PUBLIC_SUPABASE_ANON_KEY_KEY = "NEXT_PUBLIC_SUPABASE_ANON_KEY";

function isHttpsUrl(value: string): boolean {
  try {
    return new URL(value).protocol === "https:";
  } catch {
    return false;
  }
}

type VercelPublicSupabaseProblem = { key: string; reason: "missing" | "invalid" };

function describeVercelPublicSupabaseProblem(problem: VercelPublicSupabaseProblem): string {
  return problem.reason === "missing" ? problem.key : `${problem.key} (must be a valid HTTPS URL)`;
}

/**
 * Fail Vercel Preview/Production builds closed when the public Supabase
 * config every portal depends on at runtime (`getSupabaseUrl` /
 * `getSupabaseAnonKey` in packages/auth/src/env.ts) is missing or malformed
 * — instead of shipping a build that only fails once a real visitor hits an
 * auth code path.
 *
 * Inactive outside Vercel: GitHub Actions CI and local `next build` never
 * set `VERCEL=1`, so this is strictly additive — it never makes CI or local
 * dev depend on Vercel-only environment variables, and it never weakens the
 * existing runtime checks it duplicates at build time.
 *
 * Reports variable NAMES and a reason only — never the anon key value, and
 * never the URL value even when malformed (a malformed value can still carry
 * an accidental credential in a query string).
 */
export function assertVercelPublicSupabaseEnv(source: EnvSource = readProcessEnv()): void {
  if (source.VERCEL !== "1") {
    return;
  }

  const url = source[VERCEL_PUBLIC_SUPABASE_URL_KEY]?.trim();
  const anonKey = source[VERCEL_PUBLIC_SUPABASE_ANON_KEY_KEY]?.trim();

  const problems: VercelPublicSupabaseProblem[] = [];
  if (!url) {
    problems.push({ key: VERCEL_PUBLIC_SUPABASE_URL_KEY, reason: "missing" });
  } else if (!isHttpsUrl(url)) {
    problems.push({ key: VERCEL_PUBLIC_SUPABASE_URL_KEY, reason: "invalid" });
  }
  if (!anonKey) {
    problems.push({ key: VERCEL_PUBLIC_SUPABASE_ANON_KEY_KEY, reason: "missing" });
  }

  if (problems.length === 0) {
    return;
  }

  throw new Error(
    `Missing or invalid required Vercel public Supabase environment variable${problems.length > 1 ? "s" : ""}: ${problems.map(describeVercelPublicSupabaseProblem).join(", ")}`,
  );
}
