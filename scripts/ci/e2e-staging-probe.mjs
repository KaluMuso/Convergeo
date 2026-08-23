#!/usr/bin/env node
/**
 * Identity-aware staging E2E preflight probe.
 *
 * Proves that a portal surface Playwright will DIRECTLY NAVIGATE is reachable,
 * is the expected application, is on a staging/preview plane, and (when
 * requested) matches the release-candidate SHA — without treating Vercel SSO /
 * deployment-protection challenges as application health.
 *
 * Usage:
 *   node scripts/ci/e2e-staging-probe.mjs            # customer (default)
 *   node scripts/ci/e2e-staging-probe.mjs customer
 *   node scripts/ci/e2e-staging-probe.mjs vendor
 *
 * There is deliberately NO admin portal here: no current Playwright spec
 * navigates the admin origin, and admin identity is proven independently by
 * Deploy staging's own Vercel Preview proof. Add a portal entry below only when
 * a spec actually navigates it.
 *
 * Exit codes:
 *   0 — PASS (probe succeeded; safe to run Playwright)
 *   0 — SKIPPED (non-strict run with no target configured for this portal)
 *   1 — FAIL (misconfiguration, wrong app/env/SHA, unreachable host)
 *   2 — BLOCKED_EXTERNAL (SSO / protection gate; automation cannot access)
 *
 * Never logs secret values (bypass token, configured base URLs, query params).
 * Only hostnames — which are derived, non-secret routing facts — are printed.
 */

/** @typedef {'PASS'|'FAIL'|'BLOCKED_EXTERNAL'|'SKIPPED'} ProbeVerdict */

const EXIT = { PASS: 0, SKIPPED: 0, FAIL: 1, BLOCKED_EXTERNAL: 2 };

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
 * Every portal Playwright navigates directly, and how to reach + identify it.
 *
 * A Vercel "Protection Bypass for Automation" secret is issued PER PROJECT and
 * the portals are separate projects, so each prefers its own secret and falls
 * back to the repository-wide one only for backward compatibility.
 */
export const PORTALS = {
  customer: {
    portal: "customer",
    baseUrlVar: "E2E_BASE_URL",
    expectedApp: "customer",
    bypassVars: ["VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER", "VERCEL_AUTOMATION_BYPASS_SECRET"],
    /** The customer origin is the reference origin every other portal must differ from. */
    isReferenceOrigin: true,
  },
  vendor: {
    portal: "vendor",
    baseUrlVar: "E2E_VENDOR_BASE_URL",
    expectedApp: "vendor",
    bypassVars: ["VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR", "VERCEL_AUTOMATION_BYPASS_SECRET"],
    isReferenceOrigin: false,
  },
};

/**
 * @param {string} name
 * @returns {typeof PORTALS[keyof typeof PORTALS] | null}
 */
export function resolvePortal(name) {
  const key = (name ?? "customer").trim().toLowerCase() || "customer";
  return Object.prototype.hasOwnProperty.call(PORTALS, key)
    ? PORTALS[/** @type {keyof typeof PORTALS} */ (key)]
    : null;
}

/**
 * @param {string} raw
 * @param {{ varName?: string }} opts
 * @returns {{ ok: true, base: string, host: string } | { ok: false, reason: string, missing?: boolean }}
 */
export function parseBaseUrl(raw, opts = {}) {
  const varName = opts.varName ?? "E2E_BASE_URL";
  const trimmed = (raw ?? "").trim();
  if (!trimmed) {
    return { ok: false, reason: `${varName} is not set`, missing: true };
  }
  const lower = trimmed.toLowerCase();
  if (lower.includes("localhost") || lower.includes("127.0.0.1")) {
    return { ok: false, reason: `${varName} must be a deployed staging surface, not localhost` };
  }
  let url;
  try {
    url = new URL(trimmed.endsWith("/") ? trimmed : `${trimmed}/`);
  } catch {
    return { ok: false, reason: `${varName} is not a valid URL` };
  }
  if (!["http:", "https:"].includes(url.protocol)) {
    return { ok: false, reason: `${varName} must use http or https` };
  }
  const base = `${url.origin}`;
  return { ok: true, base, host: url.hostname };
}

/**
 * Pick this portal's bypass secret. Presence-based, in declared precedence
 * order — secret VALUES are never compared to each other, logged, or returned.
 *
 * @param {Record<string, string | undefined>} env
 * @param {{ bypassVars: string[] }} portalConfig
 * @returns {{ secret: string, sourceVar: string | null }}
 */
export function resolveBypassSecret(env, portalConfig) {
  for (const name of portalConfig.bypassVars) {
    const value = (env[name] ?? "").trim();
    if (value) {
      return { secret: value, sourceVar: name };
    }
  }
  return { secret: "", sourceVar: null };
}

/** Lowercased origin of a URL, or "" when unparseable. */
function originOf(raw) {
  try {
    return new URL((raw ?? "").trim()).origin.toLowerCase();
  } catch {
    return "";
  }
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
  // One-shot probe: this makes a single request that already carries the
  // bypass header, and it runs `redirect: "manual"`. Vercel documents
  // `x-vercel-set-bypass-cookie` as OPTIONAL, for maintaining authorization
  // "across multiple requests or within iframes" — Playwright keeps it for
  // exactly that reason, and its browser context is a separate process that
  // never inherits a cookie set here. Asking for a cookie on a single
  // manual-redirect request only invites the redirect that failed
  // deploy-staging run #33 on all three portals.
  const headers = { Accept: "application/json" };
  if (opts.bypassSecret) {
    headers["x-vercel-protection-bypass"] = opts.bypassSecret;
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
 * @param {{ fetchImpl?: typeof fetch, portal?: string }} opts
 */
export async function probeStagingAccess(env, opts = {}) {
  const portalConfig = resolvePortal(opts.portal ?? "customer");
  if (!portalConfig) {
    return /** @type {const} */ ({
      verdict: "FAIL",
      detail: `unknown portal '${opts.portal}' — expected one of ${Object.keys(PORTALS).join("|")}`,
    });
  }

  const strictSha =
    (env.E2E_STRICT_SHA ?? "").trim().toLowerCase() === "1" ||
    (env.E2E_STRICT_SHA ?? "").trim().toLowerCase() === "true" ||
    (env.CERTIFICATION_MODE ?? "").trim().toLowerCase() === "integrated-staging";

  const baseParse = parseBaseUrl(env[portalConfig.baseUrlVar] ?? "", {
    varName: portalConfig.baseUrlVar,
  });
  if (!baseParse.ok) {
    // A target that is simply absent is a hard failure for release
    // certification, but must not break non-strict nightly runs that never
    // configured this portal. A target that is PRESENT and malformed always
    // fails, in either mode.
    if (baseParse.missing && !strictSha) {
      return {
        verdict: "SKIPPED",
        detail: `${portalConfig.baseUrlVar} not set — ${portalConfig.portal} identity not verified (non-strict run)`,
        portal: portalConfig.portal,
      };
    }
    if (baseParse.missing) {
      return {
        verdict: "FAIL",
        detail: `${portalConfig.baseUrlVar} is not set — integrated-staging certification cannot navigate the ${portalConfig.portal} portal on an unproven origin`,
        portal: portalConfig.portal,
      };
    }
    return { verdict: "FAIL", detail: baseParse.reason, portal: portalConfig.portal };
  }

  // Origin collapse: e2e/fixtures/env.ts defaults VENDOR_BASE_URL/ADMIN_BASE_URL
  // to BASE_URL, so an unset secondary target silently sends that portal's specs
  // at the customer app. Convenient locally; fatal for certification.
  if (!portalConfig.isReferenceOrigin) {
    const referenceVar = PORTALS.customer.baseUrlVar;
    const referenceOrigin = originOf(env[referenceVar] ?? "");
    if (referenceOrigin && originOf(baseParse.base) === referenceOrigin) {
      const detail = `${portalConfig.baseUrlVar} resolves to the same origin as ${referenceVar} — ${portalConfig.portal} specs would navigate the customer app`;
      if (strictSha) {
        return { verdict: "FAIL", detail, portal: portalConfig.portal, host: baseParse.host };
      }
      return {
        verdict: "SKIPPED",
        detail: `${detail} (non-strict run — ${portalConfig.portal} identity not verified)`,
        portal: portalConfig.portal,
        host: baseParse.host,
      };
    }
  }

  const locale = (env.E2E_LOCALE ?? "en").trim() || "en";
  const healthUrl = `${baseParse.base}/${locale}/health`;
  const { secret: bypassSecret, sourceVar: bypassSourceVar } = resolveBypassSecret(
    env,
    portalConfig,
  );
  const expectedSha = (env.E2E_EXPECT_SHA ?? env.GITHUB_SHA ?? "").trim();

  let fetchResult;
  try {
    fetchResult = await fetchHealth(healthUrl, {
      bypassSecret: bypassSecret || undefined,
      fetchImpl: opts.fetchImpl,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      verdict: "FAIL",
      detail: `health probe network error: ${msg}`,
      host: baseParse.host,
      portal: portalConfig.portal,
    };
  }

  const { response, bodyText, json } = fetchResult;

  if (detectProtectionChallenge(response, bodyText)) {
    const primaryVar = portalConfig.bypassVars[0];
    const fallbackVar = portalConfig.bypassVars[portalConfig.bypassVars.length - 1];
    const hint = bypassSecret
      ? `protection challenge despite bypass header — the secret is invalid, expired, or was issued for a different Vercel project (verify ${primaryVar}, else ${fallbackVar})`
      : `set ${primaryVar} (or ${fallbackVar}) from the convergeo-${portalConfig.portal} project's Protection Bypass for Automation`;
    return {
      verdict: "BLOCKED_EXTERNAL",
      detail: `deployment protection / SSO challenge (HTTP ${response.status}); ${hint}`,
      host: baseParse.host,
      httpStatus: response.status,
      portal: portalConfig.portal,
    };
  }

  if (response.status < 200 || response.status >= 300) {
    return {
      verdict: "FAIL",
      detail: `health HTTP ${response.status}`,
      host: baseParse.host,
      httpStatus: response.status,
      portal: portalConfig.portal,
    };
  }

  if (!json) {
    return {
      verdict: "FAIL",
      detail: "health response is not JSON (wrong app or HTML page)",
      host: baseParse.host,
      portal: portalConfig.portal,
    };
  }

  const health = validateHealthPayload(json, {
    expectedApp: portalConfig.expectedApp,
    strictEnv: strictSha,
  });
  if (!health.ok) {
    return {
      verdict: "FAIL",
      detail: health.reason,
      host: baseParse.host,
      portal: portalConfig.portal,
    };
  }

  const envWarning =
    !strictSha && health.envMissing
      ? "health env missing — nightly probe did not certify staging identity"
      : undefined;

  const sha = validateBuildSha(health.buildId ?? "", expectedSha, { strict: strictSha });
  if (!sha.ok) {
    return {
      verdict: "FAIL",
      detail: sha.reason,
      host: baseParse.host,
      buildId: health.buildId,
      portal: portalConfig.portal,
    };
  }

  return {
    verdict: "PASS",
    detail: `staging ${portalConfig.portal} health verified`,
    host: baseParse.host,
    portal: portalConfig.portal,
    env: health.env,
    buildIdPrefix: (health.buildId ?? "").slice(0, 12),
    shaVerified: sha.matched === true,
    shaSkipped: sha.skipped === true,
    shaWarning: sha.warning,
    envWarning,
    // Variable NAME only — never the secret value, and never a comparison
    // between two secrets.
    bypassSourceVar: bypassSourceVar,
  };
}

/**
 * @param {ProbeVerdict} verdict
 */
export function exitCodeForProbeVerdict(verdict) {
  if (verdict === "PASS") return EXIT.PASS;
  if (verdict === "SKIPPED") return EXIT.SKIPPED;
  if (verdict === "BLOCKED_EXTERNAL") return EXIT.BLOCKED_EXTERNAL;
  return EXIT.FAIL;
}

function emitGithubAnnotation(verdict, detail, host, portal) {
  const scope = `${portal ? ` portal=${portal}` : ""}${host ? ` host=${host}` : ""}`;
  if (verdict === "BLOCKED_EXTERNAL") {
    console.error(`::error::E2E staging probe BLOCKED_EXTERNAL — ${detail}${scope}`);
  } else if (verdict === "FAIL") {
    console.error(`::error::E2E staging probe FAIL — ${detail}${scope}`);
  }
}

async function main() {
  const portal = (process.argv[2] ?? "customer").trim().toLowerCase() || "customer";
  const result = await probeStagingAccess(process.env, { portal });
  const code = exitCodeForProbeVerdict(result.verdict);
  const out = {
    portal: result.portal ?? portal,
    verdict: result.verdict,
    detail: result.detail,
    host: result.host ?? null,
    env: result.env ?? null,
    buildIdPrefix: result.buildIdPrefix ?? null,
    shaVerified: result.shaVerified ?? false,
    httpStatus: result.httpStatus ?? null,
    bypassSourceVar: result.bypassSourceVar ?? null,
  };
  console.log(JSON.stringify(out));
  if (result.verdict !== "PASS") {
    emitGithubAnnotation(result.verdict, result.detail, result.host, result.portal ?? portal);
    if (result.verdict === "SKIPPED") {
      console.warn(`::warning::E2E staging probe SKIPPED — ${result.detail}`);
    }
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
