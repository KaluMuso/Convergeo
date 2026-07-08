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
