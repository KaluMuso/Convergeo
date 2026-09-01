#!/usr/bin/env node
/**
 * Fail-closed preflight for the synthetic E2E OTP contract.
 *
 * Proves that hosted Supabase Auth test-OTP mapping is active for the canonical
 * synthetic personas. When configured, Supabase short-circuits SMS delivery and
 * accepts the mapped static code without invoking the Send SMS hook.
 *
 * Never logs OTP codes, tokens, or full phone numbers.
 *
 * Usage:
 *   SUPABASE_URL=... SUPABASE_ANON_KEY=... \
 *   E2E_CUSTOMER_TEST_PHONE=... E2E_CUSTOMER_TEST_OTP=... \
 *   E2E_VENDOR_TEST_PHONE=... E2E_VENDOR_TEST_OTP=... \
 *   node scripts/ci/preflight-e2e-test-otp.mjs
 *
 * Exit codes:
 *   0 — PASS (all configured personas verified)
 *   0 — SKIPPED (no OTP secrets configured; non-strict runs only)
 *   1 — FAIL (misconfiguration or test-OTP contract not functioning)
 */

const STRICT_CERT_MODES = new Set(["integrated-staging", "production-readiness"]);

function str(name) {
  return (process.env[name] ?? "").trim();
}

function certificationMode() {
  const raw = str("CERTIFICATION_MODE").toLowerCase();
  if (raw === "staging") return "integrated-staging";
  return raw || "local-development";
}

function strictRequired() {
  return STRICT_CERT_MODES.has(certificationMode());
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

async function verifyTestOtpPersona({ label, phone, otp, supabaseUrl, anonKey }) {
  const authPhone = toAuthPhone(phone);
  const sendRes = await fetch(`${supabaseUrl}/auth/v1/otp`, {
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

  const verifyRes = await fetch(`${supabaseUrl}/auth/v1/verify`, {
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

export async function runPreflight(env = process.env) {
  const supabaseUrl = str("SUPABASE_URL") || str("STAGING_SUPABASE_URL");
  const anonKey = str("SUPABASE_ANON_KEY") || str("STAGING_SUPABASE_ANON_KEY");

  const personas = [
    { label: "customer", phone: str("E2E_CUSTOMER_TEST_PHONE"), otp: str("E2E_CUSTOMER_TEST_OTP") },
    { label: "vendor", phone: str("E2E_VENDOR_TEST_PHONE"), otp: str("E2E_VENDOR_TEST_OTP") },
  ];

  const configured = personas.filter((persona) => persona.phone && persona.otp);
  if (configured.length === 0) {
    if (strictRequired()) {
      return {
        verdict: "FAIL",
        detail:
          "E2E_CUSTOMER_TEST_PHONE/E2E_CUSTOMER_TEST_OTP (and vendor equivalents) are required in strict certification mode",
      };
    }
    return {
      verdict: "SKIPPED",
      detail: "no E2E test-OTP secrets configured",
    };
  }

  if (!supabaseUrl || !anonKey) {
    return {
      verdict: "FAIL",
      detail:
        "SUPABASE_URL and SUPABASE_ANON_KEY (or STAGING_* equivalents) are required for test-OTP preflight",
    };
  }

  const results = [];
  for (const persona of configured) {
    results.push(
      await verifyTestOtpPersona({
        label: persona.label,
        phone: persona.phone,
        otp: persona.otp,
        supabaseUrl,
        anonKey,
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
