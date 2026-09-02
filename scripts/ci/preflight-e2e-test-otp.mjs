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

const STRICT_CERT_MODES = new Set(["integrated-staging", "production-readiness"]);

const CANONICAL_PERSONAS = [
  { label: "customer", phone: SEED.personas.customer.phone, otpEnv: "E2E_CUSTOMER_TEST_OTP" },
  { label: "vendor", phone: SEED.personas.vendor.phone, otpEnv: "E2E_VENDOR_TEST_OTP" },
];

function str(name, env = process.env) {
  return (env[name] ?? "").trim();
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
  const trimmed = phone.trim();
  if (trimmed.startsWith("+")) return trimmed;
  if (/^\d+$/.test(trimmed)) return `+${trimmed}`;
  throw new Error("phone is not in international format");
}

function resolvePersonas(env = process.env) {
  return CANONICAL_PERSONAS.map((persona) => ({
    label: persona.label,
    phone: persona.phone,
    otp: str(persona.otpEnv, env),
    otpEnv: persona.otpEnv,
  }));
}

export function evaluatePreflightConfig(personas, { strict }) {
  const missingOtps = personas.filter((persona) => !persona.otp).map((persona) => persona.otpEnv);
  const configured = personas.filter((persona) => persona.otp);

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

async function verifyTestOtpPersona({
  label,
  phone,
  otp,
  supabaseUrl,
  anonKey,
  fetchImpl = fetch,
}) {
  const authPhone = toAuthPhone(phone);
  const sendRes = await fetchImpl(`${supabaseUrl}/auth/v1/otp`, {
    method: "POST",
    headers: {
      apikey: anonKey,
      Authorization: `Bearer ${anonKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ phone: authPhone, create_user: false }),
  });

  if (!sendRes.ok) {
    const body = await sendRes.text();
    return {
      ok: false,
      label,
      reason: `otp send failed (HTTP ${sendRes.status})`,
      detail: body.slice(0, 200),
      phoneTail: maskPhoneTail(authPhone),
    };
  }

  const verifyRes = await fetchImpl(`${supabaseUrl}/auth/v1/verify`, {
    method: "POST",
    headers: {
      apikey: anonKey,
      Authorization: `Bearer ${anonKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      phone: authPhone,
      token: otp,
      type: "sms",
    }),
  });

  if (!verifyRes.ok) {
    const body = await verifyRes.text();
    return {
      ok: false,
      label,
      reason: "test-OTP verify failed — hosted Auth test_otp mapping likely missing or wrong",
      detail: body.slice(0, 200),
      phoneTail: maskPhoneTail(authPhone),
    };
  }

  return { ok: true, label, phoneTail: maskPhoneTail(authPhone) };
}

export async function runPreflight(env = process.env, options = {}) {
  const fetchImpl = options.fetchImpl ?? fetch;
  const supabaseUrl = str("SUPABASE_URL", env) || str("STAGING_SUPABASE_URL", env);
  const anonKey = str("SUPABASE_ANON_KEY", env) || str("STAGING_SUPABASE_ANON_KEY", env);
  const personas = resolvePersonas(env);
  const strict = options.strict ?? strictRequired(env);
  const config = evaluatePreflightConfig(personas, { strict });

  if (config.verdict === "FAIL" || config.verdict === "SKIPPED") {
    return config;
  }

  if (!supabaseUrl || !anonKey) {
    return {
      verdict: "FAIL",
      detail:
        "SUPABASE_URL and SUPABASE_ANON_KEY (or STAGING_* equivalents) are required for test-OTP preflight",
    };
  }

  const results = [];
  for (const persona of config.configured) {
    results.push(
      await verifyTestOtpPersona({
        label: persona.label,
        phone: persona.phone,
        otp: persona.otp,
        supabaseUrl,
        anonKey,
        fetchImpl,
      }),
    );
  }

  const failed = results.filter((result) => !result.ok);
  if (failed.length > 0) {
    return {
      verdict: "FAIL",
      detail: failed.map((result) => `${result.label}: ${result.reason}`).join("; "),
      results,
    };
  }

  return {
    verdict: "PASS",
    detail: `verified ${results.length} synthetic test-OTP persona(s)`,
    results,
  };
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
  main().catch((err) => {
    console.error(
      `::error::E2E test-OTP preflight crashed: ${err instanceof Error ? err.message : err}`,
    );
    process.exit(1);
  });
}
