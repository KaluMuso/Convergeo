import {
  SignJWT,
  createLocalJWKSet,
  exportJWK,
  generateKeyPair,
  type JWK,
  type JWTVerifyGetKey,
  type KeyLike,
} from "jose";
import { beforeAll, describe, expect, it } from "vitest";

import {
  CF_ACCESS_AUD_ENV,
  CF_ACCESS_TEAM_DOMAIN_ENV,
  getCfAccessConfig,
  isJwtShaped,
  verifyCfAccessAssertion,
  verifyCfAccessJwt,
  type CfAccessConfig,
} from "./cf-access";

const TEAM_DOMAIN = "vergeo5team.cloudflareaccess.com";
const AUD = "0123456789abcdef-access-application-aud-tag";
const ISSUER = `https://${TEAM_DOMAIN}`;
const KID = "test-signing-key-1";

const CONFIG: CfAccessConfig = {
  teamDomain: TEAM_DOMAIN,
  aud: AUD,
  issuer: ISSUER,
  jwksUrl: `https://${TEAM_DOMAIN}/cdn-cgi/access/certs`,
};

// The key pair whose public half lives in the JWKS the verifier trusts.
let signingKey: KeyLike;
// A second, unrelated key pair — used to forge tokens the JWKS does not know about.
let foreignKey: KeyLike;
// The local JWKS resolver injected in place of Cloudflare's remote certs endpoint.
let jwks: JWTVerifyGetKey;

type TokenOptions = {
  aud?: string;
  issuer?: string;
  kid?: string;
  key?: KeyLike;
  /** jose duration string or absolute unix-seconds expiry. */
  expiresIn?: string | number;
};

async function makeToken(options: TokenOptions = {}): Promise<string> {
  return new SignJWT({ email: "founder@vergeo5.com" })
    .setProtectedHeader({ alg: "RS256", kid: options.kid ?? KID })
    .setSubject("cf-user-123")
    .setIssuedAt()
    .setIssuer(options.issuer ?? ISSUER)
    .setAudience(options.aud ?? AUD)
    .setExpirationTime(options.expiresIn ?? "2h")
    .sign(options.key ?? signingKey);
}

function base64url(value: string): string {
  return Buffer.from(value, "utf8").toString("base64url");
}

beforeAll(async () => {
  const trusted = await generateKeyPair("RS256");
  signingKey = trusted.privateKey;
  const publicJwk: JWK = {
    ...(await exportJWK(trusted.publicKey)),
    kid: KID,
    alg: "RS256",
    use: "sig",
  };
  jwks = createLocalJWKSet({ keys: [publicJwk] });

  const foreign = await generateKeyPair("RS256");
  foreignKey = foreign.privateKey;
});

describe("getCfAccessConfig", () => {
  it("derives issuer and JWKS URL from the team domain + audience", () => {
    const config = getCfAccessConfig({
      [CF_ACCESS_TEAM_DOMAIN_ENV]: TEAM_DOMAIN,
      [CF_ACCESS_AUD_ENV]: AUD,
    });

    expect(config).toEqual(CONFIG);
  });

  it("normalizes a bare team name and a full URL", () => {
    expect(
      getCfAccessConfig({
        [CF_ACCESS_TEAM_DOMAIN_ENV]: "vergeo5team",
        [CF_ACCESS_AUD_ENV]: AUD,
      })?.teamDomain,
    ).toBe(TEAM_DOMAIN);

    expect(
      getCfAccessConfig({
        [CF_ACCESS_TEAM_DOMAIN_ENV]: `https://${TEAM_DOMAIN}/`,
        [CF_ACCESS_AUD_ENV]: AUD,
      })?.jwksUrl,
    ).toBe(CONFIG.jwksUrl);
  });

  it("returns null when either variable is missing or blank", () => {
    expect(getCfAccessConfig({})).toBeNull();
    expect(getCfAccessConfig({ [CF_ACCESS_TEAM_DOMAIN_ENV]: TEAM_DOMAIN })).toBeNull();
    expect(getCfAccessConfig({ [CF_ACCESS_AUD_ENV]: AUD })).toBeNull();
    expect(
      getCfAccessConfig({ [CF_ACCESS_TEAM_DOMAIN_ENV]: "  ", [CF_ACCESS_AUD_ENV]: "  " }),
    ).toBeNull();
  });
});

describe("isJwtShaped", () => {
  it("accepts three non-empty segments only", () => {
    expect(isJwtShaped("aaa.bbb.ccc")).toBe(true);
    expect(isJwtShaped("aaa.bbb")).toBe(false);
    expect(isJwtShaped("aaa.bbb.")).toBe(false);
    expect(isJwtShaped("not-a-jwt")).toBe(false);
    expect(isJwtShaped("")).toBe(false);
    expect(isJwtShaped(null)).toBe(false);
    expect(isJwtShaped(undefined)).toBe(false);
  });
});

describe("verifyCfAccessJwt — valid assertions", () => {
  it("accepts a correctly signed, audience-scoped, unexpired token", async () => {
    const token = await makeToken();
    const result = await verifyCfAccessJwt(token, CONFIG, jwks);

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.payload.sub).toBe("cf-user-123");
      expect(result.payload.email).toBe("founder@vergeo5.com");
      expect(result.payload.aud).toBe(AUD);
    }
  });
});

describe("verifyCfAccessJwt — rejected assertions", () => {
  it("rejects an absent assertion", async () => {
    expect(await verifyCfAccessJwt(null, CONFIG, jwks)).toEqual({
      ok: false,
      reason: "assertion_missing",
    });
    expect(await verifyCfAccessJwt("   ", CONFIG, jwks)).toEqual({
      ok: false,
      reason: "assertion_missing",
    });
  });

  it("rejects a malformed (non-three-segment) assertion", async () => {
    expect(await verifyCfAccessJwt("only.two", CONFIG, jwks)).toEqual({
      ok: false,
      reason: "assertion_malformed",
    });
  });

  it("rejects a token signed by a key absent from the JWKS (wrong key / unknown kid)", async () => {
    const wrongSignature = await makeToken({ key: foreignKey });
    expect((await verifyCfAccessJwt(wrongSignature, CONFIG, jwks)).ok).toBe(false);

    const unknownKid = await makeToken({ key: foreignKey, kid: "kid-not-in-jwks" });
    expect((await verifyCfAccessJwt(unknownKid, CONFIG, jwks)).ok).toBe(false);
  });

  it("rejects a token for the wrong audience", async () => {
    const token = await makeToken({ aud: "some-other-application-aud" });
    expect(await verifyCfAccessJwt(token, CONFIG, jwks)).toEqual({
      ok: false,
      reason: "verification_failed",
    });
  });

  it("rejects a token from the wrong issuer", async () => {
    const token = await makeToken({ issuer: "https://evil.cloudflareaccess.com" });
    expect(await verifyCfAccessJwt(token, CONFIG, jwks)).toEqual({
      ok: false,
      reason: "verification_failed",
    });
  });

  it("rejects an expired token", async () => {
    const token = await makeToken({ expiresIn: Math.floor(Date.now() / 1000) - 60 });
    expect(await verifyCfAccessJwt(token, CONFIG, jwks)).toEqual({
      ok: false,
      reason: "verification_failed",
    });
  });

  it("rejects an unsigned (alg: none) token", async () => {
    const header = base64url(JSON.stringify({ alg: "none", typ: "JWT" }));
    const payload = base64url(
      JSON.stringify({ sub: "cf-user-123", aud: AUD, iss: ISSUER, exp: 9999999999 }),
    );
    const noneToken = `${header}.${payload}.c2ln`;

    expect(await verifyCfAccessJwt(noneToken, CONFIG, jwks)).toEqual({
      ok: false,
      reason: "verification_failed",
    });
  });
});

describe("verifyCfAccessAssertion — env-driven wiring", () => {
  it("verifies against config resolved from environment variables", async () => {
    const token = await makeToken();
    const result = await verifyCfAccessAssertion(token, {
      env: { [CF_ACCESS_TEAM_DOMAIN_ENV]: TEAM_DOMAIN, [CF_ACCESS_AUD_ENV]: AUD },
      getKey: jwks,
    });

    expect(result.ok).toBe(true);
  });

  it("fails closed with config_missing when the verifier is not configured", async () => {
    const token = await makeToken();
    const result = await verifyCfAccessAssertion(token, { env: {}, getKey: jwks });

    expect(result).toEqual({ ok: false, reason: "config_missing" });
  });

  it("still rejects a bad token when config is present", async () => {
    const token = await makeToken({ aud: "wrong" });
    const result = await verifyCfAccessAssertion(token, { config: CONFIG, getKey: jwks });

    expect(result.ok).toBe(false);
  });
});
