import { combineChunks, stringFromBase64URL } from "@supabase/ssr";
import { createRemoteJWKSet, jwtVerify, type JWTVerifyGetKey } from "jose";

import { getRolesFromClaims, type AppRole } from "./roles";

import type { NextRequest } from "next/server";

/**
 * Local (no per-request network) verification of the Supabase session access
 * token, for PUBLIC pages only. Anything authenticated (account, checkout,
 * payment, orders, mutations) keeps the full server `getUser()` check in
 * `updateSession`. Any doubt resolves to anonymous, never to a user.
 *
 * Keys: the project JWKS (fetched once per instance and cached in memory by
 * jose, so steady-state requests do no I/O) or, for HS256 projects, the
 * server-side `SUPABASE_JWT_SECRET`. Checks signature, `exp`, `iss`, `aud`, `sub`.
 */

const COOKIE_RE = /^(sb-.+-auth-token)(?:\.\d+)?$/;
const BASE64_PREFIX = "base64-";
const CLOCK_TOLERANCE_S = 5;

export type LocalSession = { userId: string; roles: AppRole[] };

export type LocalVerifyOptions = {
  /** Supabase project URL (issuer is `${url}/auth/v1`). */
  supabaseUrl: string;
  /** Test seam / custom key resolver. Defaults to the project's remote JWKS. */
  keys?: JWTVerifyGetKey;
  /** HS256 shared secret (server-side only). */
  jwtSecret?: string;
  now?: Date;
};

const jwksCache = new Map<string, JWTVerifyGetKey>();

function remoteJwks(supabaseUrl: string): JWTVerifyGetKey {
  const base = supabaseUrl.replace(/\/+$/, "");
  let keys = jwksCache.get(base);
  if (!keys) {
    keys = createRemoteJWKSet(new URL(`${base}/auth/v1/.well-known/jwks.json`), {
      cooldownDuration: 30_000,
      timeoutDuration: 2_000,
    });
    jwksCache.set(base, keys);
  }
  return keys;
}

/** Reassembles the (possibly chunked, base64-prefixed) Supabase auth cookie. */
export async function readAccessTokenFromCookies(request: NextRequest): Promise<string | null> {
  const all = request.cookies.getAll();
  const base = all.map((c) => COOKIE_RE.exec(c.name)?.[1]).find((n): n is string => Boolean(n));
  if (!base) return null;
  try {
    const raw = await combineChunks(base, (name) => request.cookies.get(name)?.value);
    if (!raw) return null;
    const json = raw.startsWith(BASE64_PREFIX)
      ? stringFromBase64URL(raw.slice(BASE64_PREFIX.length))
      : raw;
    const session = JSON.parse(json) as { access_token?: unknown };
    return typeof session.access_token === "string" ? session.access_token : null;
  } catch {
    return null;
  }
}

export async function verifyLocalSession(
  request: NextRequest,
  options: LocalVerifyOptions,
): Promise<LocalSession | null> {
  try {
    const token = await readAccessTokenFromCookies(request);
    if (!token) return null;
    const header = JSON.parse(stringFromBase64URL(token.split(".")[0] ?? "")) as { alg?: string };
    const issuer = `${options.supabaseUrl.replace(/\/+$/, "")}/auth/v1`;
    const verifyOptions = {
      issuer,
      audience: "authenticated",
      clockTolerance: CLOCK_TOLERANCE_S,
      currentDate: options.now,
      requiredClaims: ["exp", "sub"],
    };

    let payload;
    if (header.alg === "HS256") {
      if (!options.jwtSecret) return null;
      ({ payload } = await jwtVerify(token, new TextEncoder().encode(options.jwtSecret), {
        ...verifyOptions,
        algorithms: ["HS256"],
      }));
    } else {
      ({ payload } = await jwtVerify(token, options.keys ?? remoteJwks(options.supabaseUrl), {
        ...verifyOptions,
        algorithms: ["RS256", "ES256", "EdDSA"],
      }));
    }
    if (typeof payload.sub !== "string" || payload.sub.length === 0) return null;
    return { userId: payload.sub, roles: getRolesFromClaims(payload as Record<string, unknown>) };
  } catch {
    return null;
  }
}
