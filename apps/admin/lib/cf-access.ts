/**
 * Cloudflare Access JWT verification — Edge-runtime compatible.
 *
 * Cloudflare Access authenticates a user at the edge and forwards a signed JWT in the
 * `Cf-Access-Jwt-Assertion` header. This module cryptographically verifies that
 * assertion against the team's JWKS (RS256) and checks the expected application
 * audience, the derived issuer, and token expiry, so the hardened admin origin can
 * trust it. Built on `jose`, which runs entirely on the Web Crypto API + global
 * `fetch` and therefore works inside the Next.js Edge middleware runtime (no Node-only
 * crypto).
 *
 * Configuration is supplied via environment variables (names only — the values live in
 * the deployment environment, never in the repo):
 *   - CF_ACCESS_TEAM_DOMAIN: the Cloudflare team domain (e.g. `myteam.cloudflareaccess.com`
 *     or the bare team name `myteam`). Used to derive the issuer and JWKS URL.
 *   - CF_ACCESS_AUD: the Access application audience (AUD) tag the token must target.
 *
 * This is an edge gate only. Authoritative admin RBAC still happens in the API against
 * `public.user_roles` — never from these JWT claims alone.
 */
import { createRemoteJWKSet, jwtVerify, type JWTPayload, type JWTVerifyGetKey } from "jose";

export const CF_ACCESS_TEAM_DOMAIN_ENV = "CF_ACCESS_TEAM_DOMAIN";
export const CF_ACCESS_AUD_ENV = "CF_ACCESS_AUD";

/**
 * Cloudflare Access signs Access JWTs with RS256. Pinning the algorithm blocks
 * algorithm-confusion attacks (`none`, or HS256 forged with the public key as secret).
 */
const CF_ACCESS_ALGORITHMS = ["RS256"] as const;

export type CfAccessConfig = {
  /** Normalized team domain host, e.g. `myteam.cloudflareaccess.com`. */
  teamDomain: string;
  /** Access application audience (AUD) tag the token must target. */
  aud: string;
  /** Expected token issuer, `https://<teamDomain>`. */
  issuer: string;
  /** JWKS endpoint, `https://<teamDomain>/cdn-cgi/access/certs`. */
  jwksUrl: string;
};

export type CfAccessFailureReason =
  "config_missing" | "assertion_missing" | "assertion_malformed" | "verification_failed";

export type CfAccessVerifyResult =
  { ok: true; payload: JWTPayload } | { ok: false; reason: CfAccessFailureReason };

type EnvSource = Record<string, string | undefined>;

/**
 * Read the raw CF Access env values. The default (production) branch uses static
 * `process.env.<NAME>` references so Next.js exposes them to the Edge middleware runtime
 * — dynamic/computed-key access into `process.env` is not reliably bundled for Edge.
 * Tests inject `env` to resolve config hermetically.
 */
function readCfAccessEnv(env?: EnvSource): { teamDomain?: string; aud?: string } {
  if (env) {
    return { teamDomain: env[CF_ACCESS_TEAM_DOMAIN_ENV], aud: env[CF_ACCESS_AUD_ENV] };
  }
  return { teamDomain: process.env.CF_ACCESS_TEAM_DOMAIN, aud: process.env.CF_ACCESS_AUD };
}

/**
 * Normalize a configured team domain into a bare host. Accepts a full URL
 * (`https://myteam.cloudflareaccess.com`), a host (`myteam.cloudflareaccess.com`), or a
 * bare team name (`myteam`, mapped to the canonical Cloudflare Access domain). Returns
 * null when the value is blank.
 */
function normalizeTeamDomain(raw: string): string | null {
  let value = raw.trim();
  if (!value) {
    return null;
  }

  // Strip scheme and any path/query/whitespace, keeping just the host.
  value = value.replace(/^https?:\/\//i, "");
  value = value.replace(/\/.*$/, "");
  value = value.replace(/\s+/g, "");
  if (!value) {
    return null;
  }

  // A bare team name (no dot) maps to the canonical Cloudflare Access domain.
  if (!value.includes(".")) {
    value = `${value}.cloudflareaccess.com`;
  }

  return value.toLowerCase();
}

/**
 * Build the CF Access config from environment variables. Returns null when either
 * required variable is absent/blank, so callers can fail closed rather than trusting an
 * unverifiable assertion.
 */
export function getCfAccessConfig(env?: EnvSource): CfAccessConfig | null {
  const raw = readCfAccessEnv(env);
  const teamDomain = normalizeTeamDomain(raw.teamDomain ?? "");
  const aud = (raw.aud ?? "").trim();

  if (!teamDomain || !aud) {
    return null;
  }

  return {
    teamDomain,
    aud,
    issuer: `https://${teamDomain}`,
    jwksUrl: `https://${teamDomain}/cdn-cgi/access/certs`,
  };
}

/** JWT-shape pre-check: three non-empty dot-separated segments. */
export function isJwtShaped(assertion: string | null | undefined): assertion is string {
  if (typeof assertion !== "string") {
    return false;
  }
  const parts = assertion.trim().split(".");
  return parts.length === 3 && parts.every((part) => part.length > 0);
}

/**
 * Cache one remote JWKS resolver per JWKS URL. `createRemoteJWKSet` handles key caching,
 * `kid` rotation, and refetch cooldowns internally; reusing it across requests keeps the
 * Edge isolate from refetching Cloudflare's certs on every request.
 */
const remoteJwksCache = new Map<string, JWTVerifyGetKey>();

function getRemoteJwks(jwksUrl: string): JWTVerifyGetKey {
  let jwks = remoteJwksCache.get(jwksUrl);
  if (!jwks) {
    jwks = createRemoteJWKSet(new URL(jwksUrl));
    remoteJwksCache.set(jwksUrl, jwks);
  }
  return jwks;
}

/**
 * Cryptographically verify a Cloudflare Access assertion against a resolved key set.
 * Enforces RS256, the configured audience, and the derived issuer, and rejects expired
 * tokens (jose validates `exp`/`nbf` automatically). Any failure — absent, malformed,
 * unsigned, wrong key, wrong audience, wrong issuer, expired, or an unreachable JWKS —
 * resolves to `{ ok: false }`. This never throws.
 */
export async function verifyCfAccessJwt(
  assertion: string | null | undefined,
  config: CfAccessConfig,
  getKey: JWTVerifyGetKey,
): Promise<CfAccessVerifyResult> {
  if (assertion == null || assertion.trim().length === 0) {
    return { ok: false, reason: "assertion_missing" };
  }
  if (!isJwtShaped(assertion)) {
    return { ok: false, reason: "assertion_malformed" };
  }

  try {
    const { payload } = await jwtVerify(assertion.trim(), getKey, {
      algorithms: [...CF_ACCESS_ALGORITHMS],
      issuer: config.issuer,
      audience: config.aud,
    });
    return { ok: true, payload };
  } catch {
    return { ok: false, reason: "verification_failed" };
  }
}

export type VerifyCfAccessAssertionOptions = {
  /** Pre-resolved config (defaults to environment-derived config). */
  config?: CfAccessConfig;
  /** JWKS resolver override (defaults to a cached remote JWKS). Used by tests. */
  getKey?: JWTVerifyGetKey;
  /** Environment source for config resolution (defaults to process.env). */
  env?: EnvSource;
};

/**
 * Middleware entry point: resolve config from the environment (fail closed when it is
 * missing) and verify the assertion against Cloudflare's remote JWKS. Tests inject
 * `config`/`getKey` to run hermetically without network access.
 */
export async function verifyCfAccessAssertion(
  assertion: string | null | undefined,
  options: VerifyCfAccessAssertionOptions = {},
): Promise<CfAccessVerifyResult> {
  const config = options.config ?? getCfAccessConfig(options.env);
  if (!config) {
    // Fail closed: without a team domain + audience we cannot verify anything.
    return { ok: false, reason: "config_missing" };
  }

  const getKey = options.getKey ?? getRemoteJwks(config.jwksUrl);
  return verifyCfAccessJwt(assertion, config, getKey);
}
