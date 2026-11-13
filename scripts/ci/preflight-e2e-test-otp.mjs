#!/usr/bin/env node
/**
 * Fail-closed preflight for the synthetic E2E OTP contract.
 *
 * Phones are public canonical fixture data (seed.generated.ts). Only OTP codes
 * are secrets (E2E_CUSTOMER_TEST_OTP / E2E_VENDOR_TEST_OTP).
 *
 * Never logs OTP codes, tokens, or full phone numbers.
 */

import { SEED } from "../../e2e/fixtures/seed.generated.ts";
import { missingOutboundApproval } from "../../e2e/fixtures/outbound-approval.ts";

const STAGING_AUTH_URL = "https://iyasmrmbcrvlfxpzescb.supabase.co";
const runs = new WeakMap();

const STRICT_CERT_MODES = new Set(["integrated-staging", "production-readiness"]);

const CANONICAL_PERSONAS = [
  {
    label: "customer",
    phone: SEED.personas.customer.phone,
    userId: "a1000000-0000-4000-8000-000000000001",
    role: "customer",
    otpEnv: "E2E_CUSTOMER_TEST_OTP",
  },
  {
    label: "vendor",
    phone: SEED.personas.vendor.phone,
    userId: "a1000000-0000-4000-8000-000000000004",
    role: "vendor",
    otpEnv: "E2E_VENDOR_TEST_OTP",
  },
];

function str(name, env = process.env) {
  return typeof env[name] === "string" ? env[name].trim() : "";
}

function certificationMode(env = process.env) {
  const raw = str("CERTIFICATION_MODE", env).toLowerCase();
  if (raw === "staging") return "integrated-staging";
  return raw || "local-development";
}

function strictRequired(env = process.env) {
  return STRICT_CERT_MODES.has(certificationMode(env));
}

function maskPhoneTail(phone) {
  const digits = phone.replace(/\D/g, "");
  if (digits.length < 4) return "****";
  return `***${digits.slice(-4)}`;
}

function toAuthPhone(phone) {
  const value = typeof phone === "string" ? phone.trim() : "";
  const normalized = value.startsWith("+") ? value : `+${value}`;
  if (!/^\+260[79]\d{8}$/.test(normalized)) throw new Error("invalid synthetic phone");
  return normalized;
}

function sameCanonicalAuthPhone(actual, expected) {
  // Hosted Auth may store E.164 without its leading '+'. Match only that
  // observed normalization; reject spaces, punctuation, and local formats.
  const pattern = /^\+?[0-9]+$/;
  return (
    typeof actual === "string" &&
    pattern.test(actual) &&
    pattern.test(expected) &&
    actual.replace(/^\+/, "") === expected.replace(/^\+/, "")
  );
}

function resolvePersonas(env = process.env) {
  return CANONICAL_PERSONAS.map((persona) => ({
    label: persona.label,
    phone: persona.phone,
    userId: persona.userId,
    role: persona.role,
    otp: str(persona.otpEnv, env),
    otpEnv: persona.otpEnv,
  }));
}

export function evaluatePreflightConfig(personas, { strict }) {
  try {
    for (const persona of personas) toAuthPhone(persona.phone);
  } catch {
    return { verdict: "FAIL", detail: "invalid synthetic phone fixture" };
  }
  const missingOtps = personas.filter((persona) => !persona.otp).map((persona) => persona.otpEnv);
  const configured = personas
    .filter((persona) => persona.otp)
    .map(({ label, otpEnv }) => ({ label, otpEnv }));
  if (personas.some((persona) => persona.otp && !/^\d{6}$/.test(persona.otp))) {
    return { verdict: "FAIL", detail: "test OTP must contain exactly six digits" };
  }

  if (strict) {
    if (missingOtps.length > 0) {
      return {
        verdict: "FAIL",
        detail: `strict certification requires both OTP secrets: missing ${missingOtps.join(", ")}`,
        configured,
      };
    }
    return { verdict: "READY", configured };
  }

  if (configured.length === 0) {
    return {
      verdict: "SKIPPED",
      detail: "no E2E test-OTP secrets configured",
      configured,
    };
  }

  if (configured.length !== personas.length) {
    return {
      verdict: "FAIL",
      detail: `partial OTP configuration is not allowed: missing ${missingOtps.join(", ")}`,
      configured,
    };
  }

  return { verdict: "READY", configured };
}

export function evaluatePhoneOtpSafety(env = process.env) {
  if (
    str("SMS_OTP_TRANSPORT", env).toLowerCase() !== "waha" ||
    str("WAHA_OTP_ENABLED", env).toLowerCase() !== "true"
  ) {
    return {
      verdict: "FAIL",
      detail: "phone OTP requires an explicit enabled WAHA transport declaration",
    };
  }
  const missing = ["STAGING_SMS_SANDBOX_ATTESTED", "STAGING_TEST_OTP_MAP_ATTESTED"].filter(
    (name) => str(name, env).toLowerCase() !== "true",
  );
  return missing.length === 0
    ? { verdict: "READY" }
    : {
        verdict: "FAIL",
        detail: `phone OTP may reach the SMS hook: owner attestations required: ${missing.join(", ")}`,
      };
}

function safeErrorCode(body) {
  const code = body && typeof body === "object" ? (body.error_code ?? body.code) : undefined;
  if (code === "otp_expired") return "expired";
  if (code === "invalid_credentials" || code === "invalid_otp") return "invalid";
  if (code === "over_sms_send_rate_limit" || code === "over_request_rate_limit") return "throttled";
  return "rejected";
}

async function readMetadata(response) {
  const text = await response.text();
  if (text.length > 16384) throw new Error("metadata limit");
  return JSON.parse(text);
}

// A 200 alone can be the wrong synthetic account or a token minted without the
// role hook. Decode only the TLS Auth response to check its identity contract;
// no token or claim value is retained in the result.
function canonicalSessionIdentity(session, { userId, role, authPhone }) {
  try {
    const segments = session.access_token.split(".");
    const claims =
      segments.length === 3
        ? JSON.parse(Buffer.from(segments[1], "base64url").toString("utf8"))
        : null;
    const roles = claims?.app_metadata?.roles;
    return (
      session.user.id === userId &&
      sameCanonicalAuthPhone(session.user.phone, authPhone) &&
      claims?.sub === userId &&
      sameCanonicalAuthPhone(claims?.phone, authPhone) &&
      claims?.aud === "authenticated" &&
      Array.isArray(roles) &&
      roles.includes(role) &&
      !roles.includes("admin") &&
      (role !== "customer" || !roles.includes("vendor"))
    );
  } catch {
    // Malformed session bodies fail closed without reflecting token material.
    return false;
  }
}

async function verifyTestOtpPersona({
  label,
  phone,
  userId,
  role,
  otp,
  supabaseUrl,
  anonKey,
  fetchImpl,
}) {
  const authPhone = toAuthPhone(phone);
  let deliveryAccepted = false;
  const result = { label, phoneTail: maskPhoneTail(authPhone) };
  const request = (endpoint, body) =>
    fetchImpl(`${supabaseUrl}/auth/v1/${endpoint}`, {
      method: "POST",
      redirect: "error",
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
      headers: {
        apikey: anonKey,
        Authorization: `Bearer ${anonKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
  try {
    const sendRes = await request("otp", { phone: authPhone, create_user: false });
    if (sendRes.redirected || !sendRes.ok) {
      return {
        ...result,
        ok: false,
        deliveryAccepted: false,
        confirmed: false,
        reason: "otp send failed",
        errorCode: "rejected",
      };
    }
    deliveryAccepted = true;
    const verifyRes = await request("verify", { phone: authPhone, token: otp, type: "sms" });
    if (verifyRes.redirected || !verifyRes.ok) {
      let errorCode = "rejected";
      try {
        errorCode = safeErrorCode(await readMetadata(verifyRes));
      } catch {
        /* No raw body. */
      }
      return {
        ...result,
        ok: false,
        deliveryAccepted,
        confirmed: false,
        reason: "test-OTP verify failed",
        errorCode,
      };
    }
    const data = await readMetadata(verifyRes);
    const user = data?.user;
    if (
      typeof data?.access_token !== "string" ||
      !data.access_token.trim() ||
      typeof user?.id !== "string" ||
      !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(user.id) ||
      typeof user?.phone !== "string" ||
      toAuthPhone(user.phone) !== authPhone ||
      !canonicalSessionIdentity(data, { userId, role, authPhone })
    ) {
      return {
        ...result,
        ok: false,
        deliveryAccepted,
        confirmed: false,
        reason: "test-OTP verify failed: session confirmation missing",
        errorCode: "rejected",
      };
    }
    return { ...result, ok: true, deliveryAccepted, confirmed: true };
  } catch {
    return {
      ...result,
      ok: false,
      deliveryAccepted,
      confirmed: false,
      reason: "phone OTP interrupted; inspect state before another attempt",
      errorCode: "interrupted",
    };
  }
}

export async function runPreflight(env = process.env, options = {}) {
  const personas = resolvePersonas(env);
  const config = evaluatePreflightConfig(personas, {
    strict: options.strict ?? strictRequired(env),
  });
  if (config.verdict !== "READY") return config;
  const safety = evaluatePhoneOtpSafety(env);
  if (safety.verdict !== "READY") return safety;
  const supabaseUrl = (str("SUPABASE_URL", env) || str("STAGING_SUPABASE_URL", env)).replace(
    /\/$/,
    "",
  );
  const anonKey = str("SUPABASE_ANON_KEY", env) || str("STAGING_SUPABASE_ANON_KEY", env);
  if (supabaseUrl !== STAGING_AUTH_URL || !anonKey) {
    return { verdict: "FAIL", detail: "approved staging Auth target and anon key are required" };
  }
  // Validate the complete approved recipient set and sandbox target before
  // the first /auth/v1/otp POST. Test-OTP credentials do not imply consent.
  const missingApproval = [
    ...new Set(
      personas.flatMap((persona) =>
        missingOutboundApproval("otp", env, {
          persona: persona.label,
          recipientPhone: persona.phone,
          authOrigin: supabaseUrl,
        }),
      ),
    ),
  ];
  if (missingApproval.length) {
    return {
      verdict: "FAIL",
      detail: `outbound OTP approval required: ${missingApproval.join(", ")}`,
    };
  }
  // Repeated calls in this process share the attempt and its sanitized result.
  // Neither acceptance nor an interrupted request authorizes a resend/retry.
  if (runs.has(env)) return runs.get(env);
  const attempt = Promise.resolve().then(async () => {
    const results = [];
    for (const persona of personas) {
      const result = await verifyTestOtpPersona({
        ...persona,
        supabaseUrl,
        anonKey,
        fetchImpl: options.fetchImpl ?? fetch,
      });
      results.push(result);
      if (!result.ok)
        return { verdict: "FAIL", detail: `${result.label}: ${result.reason}`, results };
    }
    return {
      verdict: "PASS",
      detail: `verified ${results.length} synthetic test-OTP persona(s)`,
      results,
    };
  });
  runs.set(env, attempt);
  return attempt;
}

async function main() {
  const result = await runPreflight(process.env);
  const out = {
    verdict: result.verdict,
    detail: result.detail,
    personas: (result.results ?? []).map((entry) => ({
      label: entry.label,
      phoneTail: entry.phoneTail,
      ok: entry.ok ?? true,
    })),
  };
  console.log(JSON.stringify(out));

  if (result.verdict === "FAIL") {
    console.error(`::error::E2E test-OTP preflight FAIL — ${result.detail}`);
    process.exit(1);
  }
  if (result.verdict === "SKIPPED") {
    console.warn(`::warning::E2E test-OTP preflight SKIPPED — ${result.detail}`);
  }
}

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, "/"));
if (isMain) {
  main().catch(() => {
    console.error("::error::E2E test-OTP preflight stopped; details suppressed");
    process.exit(1);
  });
}
