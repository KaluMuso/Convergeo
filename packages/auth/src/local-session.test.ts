import { stringToBase64URL } from "@supabase/ssr";
import { createLocalJWKSet, exportJWK, generateKeyPair, SignJWT, type KeyLike } from "jose";
import { NextRequest } from "next/server";
import { beforeAll, describe, expect, it } from "vitest";

import { readAccessTokenFromCookies, verifyLocalSession } from "./local-session";

const URL_ = "https://abc.supabase.co";
const ISS = `${URL_}/auth/v1`;
const NAME = "sb-abc-auth-token";

let priv: KeyLike;
let evilPriv: KeyLike;
let keys: ReturnType<typeof createLocalJWKSet>;

beforeAll(async () => {
  const good = await generateKeyPair("ES256");
  const evil = await generateKeyPair("ES256");
  priv = good.privateKey;
  evilPriv = evil.privateKey;
  keys = createLocalJWKSet({
    keys: [{ ...(await exportJWK(good.publicKey)), kid: "k1", alg: "ES256" }],
  });
});

async function token(
  over: { key?: KeyLike; exp?: number; iss?: string; aud?: string; roles?: string[] } = {},
) {
  return new SignJWT({ app_metadata: { roles: over.roles ?? ["customer"] } })
    .setProtectedHeader({ alg: "ES256", kid: "k1" })
    .setSubject("user-1")
    .setIssuer(over.iss ?? ISS)
    .setAudience(over.aud ?? "authenticated")
    .setExpirationTime(over.exp ?? Math.floor(Date.now() / 1000) + 3600)
    .sign(over.key ?? priv);
}

function req(access: string | null, chunked = false) {
  const headers: Record<string, string> = {};
  if (access) {
    const value = `base64-${stringToBase64URL(JSON.stringify({ access_token: access, refresh_token: "r" }))}`;
    headers.cookie = chunked
      ? `${NAME}.0=${value.slice(0, 40)}; ${NAME}.1=${value.slice(40)}`
      : `${NAME}=${value}`;
  }
  return new NextRequest("http://localhost/en", { headers });
}

const opts = {
  supabaseUrl: URL_,
  get keys() {
    return keys;
  },
};

describe("verifyLocalSession", () => {
  it("accepts a valid token and reads roles from verified claims", async () => {
    expect(await verifyLocalSession(req(await token({ roles: ["vendor"] })), opts)).toEqual({
      userId: "user-1",
      roles: ["vendor"],
    });
  });

  it("reassembles chunked cookies", async () => {
    expect(await readAccessTokenFromCookies(req(await token(), true))).toMatch(/^eyJ/);
    expect(await verifyLocalSession(req(await token(), true), opts)).not.toBeNull();
  });

  it("is anonymous without a cookie or with a garbage cookie", async () => {
    expect(await verifyLocalSession(req(null), opts)).toBeNull();
    const bad = new NextRequest("http://localhost/en", { headers: { cookie: `${NAME}=not-json` } });
    expect(await verifyLocalSession(bad, opts)).toBeNull();
  });

  it("rejects an expired token", async () => {
    const exp = Math.floor(Date.now() / 1000) - 60;
    expect(await verifyLocalSession(req(await token({ exp })), opts)).toBeNull();
  });

  it("rejects a token signed by an unknown key (forged)", async () => {
    expect(await verifyLocalSession(req(await token({ key: evilPriv })), opts)).toBeNull();
  });

  it("rejects a tampered payload", async () => {
    const [h, , s] = (await token()).split(".");
    const payload = stringToBase64URL(
      JSON.stringify({
        sub: "admin",
        iss: ISS,
        aud: "authenticated",
        exp: 9999999999,
        app_metadata: { roles: ["admin"] },
      }),
    );
    expect(await verifyLocalSession(req(`${h}.${payload}.${s}`), opts)).toBeNull();
  });

  it("rejects wrong issuer and wrong audience", async () => {
    expect(
      await verifyLocalSession(req(await token({ iss: "https://evil.example/auth/v1" })), opts),
    ).toBeNull();
    expect(await verifyLocalSession(req(await token({ aud: "anon" })), opts)).toBeNull();
  });

  it("rejects alg=none and HS256 without a configured secret", async () => {
    const none = `${stringToBase64URL(JSON.stringify({ alg: "none" }))}.${stringToBase64URL(
      JSON.stringify({ sub: "u", iss: ISS, aud: "authenticated", exp: 9999999999 }),
    )}.`;
    expect(await verifyLocalSession(req(none), opts)).toBeNull();
    const hs = await new SignJWT({})
      .setProtectedHeader({ alg: "HS256" })
      .setSubject("u")
      .setIssuer(ISS)
      .setAudience("authenticated")
      .setExpirationTime("1h")
      .sign(new TextEncoder().encode("secret"));
    expect(await verifyLocalSession(req(hs), opts)).toBeNull();
    expect(await verifyLocalSession(req(hs), { ...opts, jwtSecret: "secret" })).not.toBeNull();
    expect(await verifyLocalSession(req(hs), { ...opts, jwtSecret: "other" })).toBeNull();
  });

  it("is anonymous when the key set is unavailable", async () => {
    const down = async () => {
      throw new Error("jwks down");
    };
    expect(
      await verifyLocalSession(req(await token()), { supabaseUrl: URL_, keys: down as never }),
    ).toBeNull();
  });
});
