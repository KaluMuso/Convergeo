#!/usr/bin/env node
/**
 * Identity-aware staging E2E preflight probe.
 *
 * Proves the configured customer staging surface is reachable, is the expected
 * application, and (when requested) matches the release-candidate SHA — without
 * treating Vercel SSO / deployment-protection challenges as customer health.
 *
 * Exit codes:
 *   0 — PASS (probe succeeded; safe to run Playwright)
 *   1 — FAIL (misconfiguration, wrong app/env/SHA, unreachable host)
 *   2 — BLOCKED_EXTERNAL (SSO / protection gate; automation cannot access)
 *
 * Never logs secret values (bypass token, full base URL with query params).
 */

/** @typedef {'PASS'|'FAIL'|'BLOCKED_EXTERNAL'} ProbeVerdict */

const EXIT = { PASS: 0, FAIL: 1, BLOCKED_EXTERNAL: 2 };

const VALID_ENVS = new Set(["staging", "preview", "development"]);
/** Accepted health `env` values for integrated-staging / pre-release certification. */
const STRICT_CERT_ENVS = new Set(["staging", "preview"]);
const SSO_MARKERS = [
  "vercel.com/sso-api",
  "vercel.com/login",
  "_vercel_sso_nonce",
  "Authentication Required",
  "Log in to Vercel",
  "Sign in to Vercel",
];

/**
 * @param {string} raw
 * @returns {{ ok: true, base: string, host: string } | { ok: false, reason: string }}
 */
export function parseBaseUrl(raw) {
  const trimmed = (raw ?? "").trim();
  if (!trimmed) {
    return { ok: false, reason: "E2E_BASE_URL is not set" };
  }
  const lower = trimmed.toLowerCase();
  if (lower.includes("localhost") || lower.includes("127.0.0.1")) {
    return { ok: false, reason: "E2E_BASE_URL must be a deployed staging surface, not localhost" };
  }
  let url;
  try {
    url = new URL(trimmed.endsWith("/") ? trimmed : `${trimmed}/`);
  } catch {
    return { ok: false, reason: "E2E_BASE_URL is not a valid URL" };
  }
  if (!["http:", "https:"].includes(url.protocol)) {
    return { ok: false, reason: "E2E_BASE_URL must use http or https" };
  }
  const base = `${url.origin}`;
  return { ok: true, base, host: url.hostname };
}

/**
 * @param {Response} response
 * @param {string} bodyText
 */
export function detectProtectionChallenge(response, bodyText) {
  const location = response.headers.get("location") ?? "";
  const combined = `${location}\n${bodyText}`.toLowerCase();
  if (SSO_MARKERS.some((m) => combined.includes(m.toLowerCase()))) {
    return true;
  }
  if (response.status === 401 || response.status === 403) {
    if (combined.includes("vercel") && (combined.includes("login") || combined.includes("sso"))) {
      return true;
    }
  }
  if (response.redirected && location.includes("vercel.com")) {
    return true;
  }
  return false;
}

/**
 * @param {unknown} body
 * @param {{ expectedApp?: string, strictEnv?: boolean }} opts
 */
export function validateHealthPayload(body, opts = {}) {
  const expectedApp = opts.expectedApp ?? "customer";
  if (!body || typeof body !== "object") {
    return { ok: false, reason: "health response is not JSON object" };
  }
  const doc = /** @type {Record<string, unknown>} */ (body);
  if (doc.status !== "ok") {
    return { ok: false, reason: `health status=${String(doc.status)}` };
  }
  if (doc.app !== expectedApp) {
    return { ok: false, reason: `health app=${String(doc.app)} want ${expectedApp}` };
  }
  const env = String(doc.env ?? "").trim();
  const strictEnv = opts.strictEnv ?? false;
  if (strictEnv) {
    if (!env) {
      return {
        ok: false,
        reason: "health env missing in strict integrated-staging certification mode",
      };
    }
    if (!STRICT_CERT_ENVS.has(env)) {
      return {
        ok: false,
        reason: `health env=${env} not accepted for integrated-staging (want staging|preview)`,
      };
    }
  } else if (env && !VALID_ENVS.has(env)) {
    return { ok: false, reason: `health env=${env} not staging/preview/development` };
  }
  const buildId = String(doc.buildId ?? "");
  return { ok: true, buildId, env, envMissing: !env };
}

/**
 * Compare deployment buildId against an expected git SHA (prefix-safe).
 *
 * @param {string} buildId
 * @param {string} expectedSha
 * @param {{ strict?: boolean }} opts
 */
export function validateBuildSha(buildId, expectedSha, opts = {}) {
  const strict = opts.strict ?? false;
  const normBuild = buildId.trim().toLowerCase();
  const normExpected = expectedSha.trim().toLowerCase();
  if (!normExpected) {
    return { ok: true, skipped: true };
  }
  if (!/^[0-9a-f]{7,40}$/.test(normExpected)) {
    return { ok: false, reason: "expected SHA is not a valid git commit hash" };
  }
  if (!normBuild || normBuild === "unknown") {
    if (strict) {
      return { ok: false, reason: "health buildId missing in strict SHA mode" };
    }
    return { ok: true, skipped: true, warning: "buildId missing — SHA not verified" };
  }
  if (normBuild.startsWith(normExpected) || normExpected.startsWith(normBuild)) {
    return { ok: true, matched: true };
  }
  // Allow shortened Vercel build ids that share a prefix with the full SHA.
  const minLen = Math.min(normBuild.length, normExpected.length, 12);
  if (minLen >= 7 && normBuild.slice(0, minLen) === normExpected.slice(0, minLen)) {
    return { ok: true, matched: true, prefixLen: minLen };
  }
  return {
    ok: false,
    reason: `buildId prefix mismatch (got ${normBuild.slice(0, 12)}…, want ${normExpected.slice(0, 12)}…)`,
  };
}

/**
 * @param {string} healthUrl
 * @param {{ bypassSecret?: string, timeoutMs?: number, fetchImpl?: typeof fetch }} opts
 */
export async function fetchHealth(healthUrl, opts = {}) {
  const timeoutMs = opts.timeoutMs ?? 45_000;
  const fetchImpl = opts.fetchImpl ?? fetch;
  const headers = { Accept: "application/json" };
  if (opts.bypassSecret) {
    headers["x-vercel-protection-bypass"] = opts.bypassSecret;
    headers["x-vercel-set-bypass-cookie"] = "true";
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(healthUrl, {
      method: "GET",
      headers,
      redirect: "manual",
      signal: controller.signal,
    });
    const bodyText = await response.text();
    let json = null;
    try {
      json = JSON.parse(bodyText);
    } catch {
      // non-JSON — may be SSO HTML
    }
    return { response, bodyText, json };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * @param {Record<string, string | undefined>} env
 * @param {{ fetchImpl?: typeof fetch }} opts
 */
export async function probeStagingAccess(env, opts = {}) {
  const baseParse = parseBaseUrl(env.E2E_BASE_URL ?? "");
  if (!baseParse.ok) {
    return /** @type {const} */ ({ verdict: "FAIL", detail: baseParse.reason });
  }

  const locale = (env.E2E_LOCALE ?? "en").trim() || "en";
  const healthUrl = `${baseParse.base}/${locale}/health`;
  // This probe targets the CUSTOMER surface only (E2E_BASE_URL). Vercel issues
  // a bypass secret per project, so prefer the customer project's own secret
  // and keep the repository-wide one as a backward-compatible fallback.
  const bypassSecret = (
    env.VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER ??
    env.VERCEL_AUTOMATION_BYPASS_SECRET ??
    ""
  ).trim();
  const expectedSha = (env.E2E_EXPECT_SHA ?? env.GITHUB_SHA ?? "").trim();
  const strictSha =
    (env.E2E_STRICT_SHA ?? "").trim().toLowerCase() === "1" ||
    (env.E2E_STRICT_SHA ?? "").trim().toLowerCase() === "true" ||
    (env.CERTIFICATION_MODE ?? "").trim().toLowerCase() === "integrated-staging";

  let fetchResult;
  try {
    fetchResult = await fetchHealth(healthUrl, {
      bypassSecret: bypassSecret || undefined,
      fetchImpl: opts.fetchImpl,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { verdict: "FAIL", detail: `health probe network error: ${msg}`, host: baseParse.host };
  }

  const { response, bodyText, json } = fetchResult;

  if (detectProtectionChallenge(response, bodyText)) {
    const hint = bypassSecret
      ? "protection challenge despite bypass header — the secret is invalid, expired, or was issued for a different Vercel project (verify VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER, else VERCEL_AUTOMATION_BYPASS_SECRET)"
      : "set VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER (or VERCEL_AUTOMATION_BYPASS_SECRET) from the convergeo-customer project's Protection Bypass for Automation";
    return {
      verdict: "BLOCKED_EXTERNAL",
      detail: `deployment protection / SSO challenge (HTTP ${response.status}); ${hint}`,
      host: baseParse.host,
      httpStatus: response.status,
    };
  }

  if (response.status < 200 || response.status >= 300) {
    return {
      verdict: "FAIL",
      detail: `health HTTP ${response.status}`,
      host: baseParse.host,
      httpStatus: response.status,
    };
  }

  if (!json) {
    return {
      verdict: "FAIL",
      detail: "health response is not JSON (wrong app or HTML page)",
      host: baseParse.host,
    };
  }

  const health = validateHealthPayload(json, { strictEnv: strictSha });
  if (!health.ok) {
    return { verdict: "FAIL", detail: health.reason, host: baseParse.host };
  }

  const envWarning =
    !strictSha && health.envMissing
      ? "health env missing — nightly probe did not certify staging identity"
      : undefined;

  const sha = validateBuildSha(health.buildId ?? "", expectedSha, { strict: strictSha });
  if (!sha.ok) {
    return { verdict: "FAIL", detail: sha.reason, host: baseParse.host, buildId: health.buildId };
  }

  return {
    verdict: "PASS",
    detail: "staging customer health verified",
    host: baseParse.host,
    env: health.env,
    buildIdPrefix: (health.buildId ?? "").slice(0, 12),
    shaVerified: sha.matched === true,
    shaSkipped: sha.skipped === true,
    shaWarning: sha.warning,
    envWarning,
  };
}

/**
 * @param {ProbeVerdict} verdict
 */
export function exitCodeForProbeVerdict(verdict) {
  if (verdict === "PASS") return EXIT.PASS;
  if (verdict === "BLOCKED_EXTERNAL") return EXIT.BLOCKED_EXTERNAL;
  return EXIT.FAIL;
}

function emitGithubAnnotation(verdict, detail, host) {
  const scope = host ? ` host=${host}` : "";
  if (verdict === "BLOCKED_EXTERNAL") {
    console.error(`::error::E2E staging probe BLOCKED_EXTERNAL — ${detail}${scope}`);
  } else if (verdict === "FAIL") {
    console.error(`::error::E2E staging probe FAIL — ${detail}${scope}`);
  }
}

async function main() {
  const result = await probeStagingAccess(process.env);
  const code = exitCodeForProbeVerdict(result.verdict);
  const out = {
    verdict: result.verdict,
    detail: result.detail,
    host: result.host ?? null,
    env: result.env ?? null,
    buildIdPrefix: result.buildIdPrefix ?? null,
    shaVerified: result.shaVerified ?? false,
    httpStatus: result.httpStatus ?? null,
  };
  console.log(JSON.stringify(out));
  if (result.verdict !== "PASS") {
    emitGithubAnnotation(result.verdict, result.detail, result.host);
    if (result.shaWarning) {
      console.warn(`::warning::${result.shaWarning}`);
    }
  } else {
    if (result.envWarning) {
      console.warn(`::warning::${result.envWarning}`);
    }
    if (result.shaWarning) {
      console.warn(`::warning::${result.shaWarning}`);
    }
  }
  process.exit(code);
}

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, "/"));

if (isMain) {
  main().catch((err) => {
    console.error(
      `::error::E2E staging probe crashed: ${err instanceof Error ? err.message : err}`,
    );
    process.exit(EXIT.FAIL);
  });
}
