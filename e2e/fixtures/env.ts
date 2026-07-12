/**
 * Central env-driven configuration for the E2E suite.
 *
 * NOTHING secret is committed here — every credential/URL is read from the
 * process environment (populated locally via a `.env`-style export or, in CI,
 * from GitHub Actions secrets). Absent flags degrade gracefully: founder-gated
 * legs (Lenco sandbox pay, WhatsApp mock assertions, deterministic seed reset)
 * are skipped with a clear annotation rather than failing.
 */

function flag(name: string): boolean {
  const raw = process.env[name];
  if (raw === undefined) return false;
  const v = raw.trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

function str(name: string, fallback = ""): string {
  return process.env[name]?.trim() ?? fallback;
}

/** Base URL of the customer app under test (staging deploy or local dev server). */
export const BASE_URL = str("E2E_BASE_URL", "http://localhost:3000");

/**
 * Vendor and admin apps run on separate origins (D18–D24). Cross-app specs
 * (vendor-sell, event scanner) target these; they default to the customer base
 * so `--list`/typecheck work without extra env, but real runs set them.
 */
export const VENDOR_BASE_URL = str("E2E_VENDOR_BASE_URL", BASE_URL);
export const ADMIN_BASE_URL = str("E2E_ADMIN_BASE_URL", BASE_URL);

/** Build a locale-prefixed absolute URL against an explicit origin. */
export function urlOn(origin: string, p: string): string {
  const clean = p.startsWith("/") ? p : `/${p}`;
  return `${origin.replace(/\/$/, "")}/${LOCALE}${clean === "/" ? "" : clean}`;
}

/** Default locale segment for `[locale]/` routing. */
export const LOCALE = str("E2E_LOCALE", "en");

/** Network throttle toggle for the Fast-3G project (default on; set 0 to disable). */
export const THROTTLE = process.env.E2E_THROTTLE !== "0";

/**
 * Lenco sandbox pay leg (founder gate F9b). Runs the live sandbox charge only
 * when the flag is set AND the reference/secret env is present. Otherwise the
 * checkout spec asserts up to the pay-initiation boundary and skips the charge.
 */
export const lenco = {
  enabled: flag("LENCO_SANDBOX"),
  publicKey: str("LENCO_SANDBOX_PUBLIC_KEY"),
  secretKey: str("LENCO_SANDBOX_SECRET_KEY"),
  /** A sandbox MoMo number Lenco auto-approves in test mode. */
  testMomoNumber: str("LENCO_SANDBOX_MOMO_NUMBER"),
};

/** True only when the sandbox flag + creds are all present. */
export function lencoSandboxReady(): boolean {
  return lenco.enabled && lenco.secretKey.length > 0;
}

/**
 * WhatsApp assertions read from the mock outbox adapter. The app must run with
 * its WhatsApp adapter in mock mode; the suite reads delivered messages from
 * `WHATSAPP_MOCK_OUTBOX_URL` (a JSON endpoint exposing the outbox rows).
 */
export const whatsapp = {
  mock: flag("WHATSAPP_MOCK"),
  outboxUrl: str("WHATSAPP_MOCK_OUTBOX_URL"),
};

export function whatsappMockReady(): boolean {
  return whatsapp.mock && whatsapp.outboxUrl.length > 0;
}

/**
 * Deterministic seed reset. When present, the reset hook POSTs to a test-only
 * endpoint (guarded server-side, staging only) that idempotently rebuilds the
 * canonical fixtures keyed by the slugs in `seed.ts`.
 */
export const seed = {
  resetUrl: str("E2E_SEED_RESET_URL"),
  token: str("E2E_SEED_TOKEN"),
};

export function seedResetReady(): boolean {
  return seed.resetUrl.length > 0 && seed.token.length > 0;
}

/**
 * OTP login. Staging is configured with a fixed test phone whose OTP is either
 * static (Supabase test OTP map) or readable from the WhatsApp/SMS mock outbox.
 * Without these, the auth spec asserts up to the "code sent" boundary and skips
 * the verify leg.
 */
export const otp = {
  testPhone: str("E2E_TEST_PHONE"),
  staticCode: str("E2E_TEST_OTP"),
};

export function otpVerifyReady(): boolean {
  return otp.testPhone.length > 0 && otp.staticCode.length > 0;
}

/** Convenience: build a locale-prefixed path. */
export function path(p: string): string {
  const clean = p.startsWith("/") ? p : `/${p}`;
  return `/${LOCALE}${clean === "/" ? "" : clean}`;
}
