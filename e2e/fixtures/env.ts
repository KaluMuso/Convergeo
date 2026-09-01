/**
 * Central env-driven configuration for the E2E suite.
 *
 * NOTHING secret is committed here — every credential/URL is read from the
 * process environment (populated locally via a `.env`-style export or, in CI,
 * from GitHub Actions secrets). Absent flags degrade gracefully: founder-gated
 * legs (Lenco sandbox pay, WhatsApp mock assertions, deterministic seed reset)
 * are skipped with a clear annotation rather than failing.
 */

import { SEED } from "./seed.generated";

export function flag(name: string): boolean {
  const raw = process.env[name];
  if (raw === undefined) return false;
  const v = raw.trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

export function str(name: string, fallback = ""): string {
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

/**
 * Vercel "Protection Bypass for Automation" secrets.
 *
 * A bypass secret is issued PER VERCEL PROJECT, and the three portals are
 * three separate projects (convergeo-customer/-vendor/-admin), so a secret
 * generated for one is NOT assumed to work on another. Specs navigate the
 * vendor origin directly (vendor-sell, event-ticket), so when the vendor app
 * runs on its own origin it needs its own secret.
 *
 * Each resolves portal-specific first, then the pre-existing repository-wide
 * secret as a backward-compatible fallback. Presence is checked per source;
 * values are never compared to each other.
 */
export const BYPASS_SECRET_FALLBACK = str("VERCEL_AUTOMATION_BYPASS_SECRET");
export const BYPASS_SECRET_CUSTOMER = str(
  "VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER",
  BYPASS_SECRET_FALLBACK,
);
export const BYPASS_SECRET_VENDOR = str(
  "VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR",
  BYPASS_SECRET_FALLBACK,
);
export const BYPASS_SECRET_ADMIN = str(
  "VERCEL_AUTOMATION_BYPASS_SECRET_ADMIN",
  BYPASS_SECRET_FALLBACK,
);

/**
 * True when at least one portal-specific secret is configured. Only then does
 * the suite need per-origin header injection; otherwise the single global
 * `extraHTTPHeaders` in playwright.config.ts is already correct and behavior
 * is unchanged. Presence-based — never compares two secret values.
 */
export function hasPortalSpecificBypass(): boolean {
  return (
    str("VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER").length > 0 ||
    str("VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR").length > 0 ||
    str("VERCEL_AUTOMATION_BYPASS_SECRET_ADMIN").length > 0
  );
}

function originOf(raw: string): string {
  try {
    return new URL(raw).origin.toLowerCase();
  } catch {
    return "";
  }
}

/**
 * Pick the bypass secret for whichever portal origin a request targets.
 * Returns "" when nothing is configured for that origin (caller then leaves
 * the request's headers untouched).
 */
export function bypassSecretForUrl(url: string): string {
  const target = originOf(url);
  if (!target) return BYPASS_SECRET_CUSTOMER;
  // Customer is matched FIRST: VENDOR_BASE_URL/ADMIN_BASE_URL default to the
  // customer base, so on a collision (portal origin not separately configured)
  // the origin is genuinely the customer app and must get the customer secret.
  if (target === originOf(BASE_URL)) return BYPASS_SECRET_CUSTOMER;
  if (target === originOf(VENDOR_BASE_URL)) return BYPASS_SECRET_VENDOR;
  if (target === originOf(ADMIN_BASE_URL)) return BYPASS_SECRET_ADMIN;
  return BYPASS_SECRET_CUSTOMER;
}

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
 * Fixture generation the staging database was seeded from.
 *
 * Published by the canonical seed step in the workflow. There is deliberately no
 * `E2E_SEED_RESET_URL`/`E2E_SEED_TOKEN` any more: the reset is a guarded,
 * once-per-run CLI step against the protected staging environment, not a
 * remotely callable mutation endpoint.
 */
export function expectedFixtureVersion(): string {
  return str("E2E_FIXTURE_VERSION");
}

/**
 * OTP login identities.
 *
 * The canonical personas carry DISTINCT database roles — `customer` vs `vendor`
 * — so one account provably cannot drive both the customer auth journey and the
 * vendor-portal journeys. Phones come from the generated fixture contract (they
 * are public synthetic identifiers, already committed in the Python source);
 * only the CODES are secrets.
 */
export const customerOtp = {
  testPhone: SEED.personas.customer.phone,
  staticCode: str("E2E_CUSTOMER_TEST_OTP"),
};

export const vendorOtp = {
  testPhone: SEED.personas.vendor.phone,
  staticCode: str("E2E_VENDOR_TEST_OTP"),
};

export function customerOtpReady(): boolean {
  return customerOtp.staticCode.length > 0;
}

export function vendorOtpReady(): boolean {
  return vendorOtp.staticCode.length > 0;
}

/**
 * Organiser scanner credential for the seeded ticket.
 *
 * This is the stable PIN fallback, not the rotating QR: the real QR window code
 * changes every 60 seconds (`services/tickets/qr.py`), so no stored value could
 * stay valid. It is minted per run by the canonical seed step, masked, and
 * exported into the job — never committed. `E2E_TICKET_QR` remains a temporary
 * backward-compatible alias.
 */
export function ticketPin(): string {
  return str("E2E_TICKET_PIN") || str("E2E_TICKET_QR");
}

export function ticketPinReady(): boolean {
  return ticketPin().length > 0;
}

/** Convenience: build a locale-prefixed path. */
export function path(p: string): string {
  const clean = p.startsWith("/") ? p : `/${p}`;
  return `/${LOCALE}${clean === "/" ? "" : clean}`;
}

/**
 * Certification mode from the release-certify orchestrator.
 * Strict staging/production modes require synthetic fixtures — skipped
 * assertions must never count as PASS.
 */
export type CertificationMode =
  "local-development" | "ci" | "integrated-staging" | "production-readiness";

export function certificationMode(): CertificationMode {
  const raw = str("CERTIFICATION_MODE", "local-development").toLowerCase();
  if (
    raw === "ci" ||
    raw === "integrated-staging" ||
    raw === "production-readiness" ||
    raw === "local-development"
  ) {
    return raw;
  }
  if (raw === "staging") return "integrated-staging";
  if (raw === "local" || raw === "report-only") return "local-development";
  return "local-development";
}

/**
 * True when this run is a release-certification run (integrated staging or
 * production readiness) rather than local exploration or a nightly smoke.
 */
export function strictCertificationRequired(): boolean {
  const mode = certificationMode();
  return mode === "integrated-staging" || mode === "production-readiness";
}

/** True when absent seed/fixtures must FAIL (not soft-skip). */
export function strictSyntheticRequired(): boolean {
  return strictCertificationRequired();
}

/**
 * Origin for specs that navigate the VENDOR app directly (vendor-sell,
 * event-ticket).
 *
 * `VENDOR_BASE_URL` deliberately falls back to `BASE_URL` so `--list` and
 * typecheck work with no extra env, but that fallback silently points vendor
 * specs at the CUSTOMER app. Convenient locally; unacceptable for
 * certification, where a "pass" against the wrong origin is worse than a
 * failure. In a strict run the target must be configured and must be a
 * genuinely different origin — otherwise fail closed, loudly.
 */
export function requireVendorBaseUrl(): string {
  if (!strictCertificationRequired()) {
    return VENDOR_BASE_URL;
  }
  const configured = str("E2E_VENDOR_BASE_URL");
  if (!configured) {
    throw new Error(
      "strictCertification: E2E_VENDOR_BASE_URL is not set — vendor specs would navigate the customer origin; a release baseline cannot certify the vendor portal on an unproven target",
    );
  }
  if (originOf(configured) === originOf(BASE_URL)) {
    throw new Error(
      "strictCertification: E2E_VENDOR_BASE_URL resolves to the same origin as E2E_BASE_URL — vendor specs would navigate the customer app",
    );
  }
  return configured;
}
