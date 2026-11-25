// Loopback-only Supabase Auth + Convergeo API stand-in for local screenshots.
// Mirrors packages/auth/src/session-routing.integration.test.ts: the real
// @supabase/ssr SDK verifies an RS256 token against this JWKS, so the portal
// middleware gates run unmodified. Never point a deployed build at this.
import { generateKeyPairSync, sign } from "node:crypto";
import { createServer } from "node:http";

import { fixtures } from "./fixtures.mjs";

export const SUBJECT = "00000000-0000-4000-8000-000000000001";

const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
// supabase-js caches a JWKS per key id inside the dev server for minutes, and
// every run mints a new key pair, so the id must change with the key.
const KID = `screenshot-fixture-key-${Date.now()}`;
const jwk = { ...keys.publicKey.export({ format: "jwk" }), alg: "RS256", kid: KID, use: "sig" };

const b64 = (value) => Buffer.from(JSON.stringify(value)).toString("base64url");

export function startMockBackend({ port = 54321, log = false } = {}) {
  const origin = `http://127.0.0.1:${port}`;
  const issuer = `${origin}/auth/v1`;
  const unhandled = new Map();
  let roles = [];
  let emptyApi = false;

  const user = () => ({
    id: SUBJECT,
    aud: "authenticated",
    role: "authenticated",
    email: "mwila.banda@example.invalid",
    phone: "260971234567",
    app_metadata: { roles, provider: "phone" },
    user_metadata: { full_name: "Mwila Banda" },
    created_at: "2026-03-02T08:00:00Z",
  });

  function token() {
    const now = Math.floor(Date.now() / 1000);
    const header = b64({ alg: "RS256", typ: "JWT", kid: KID });
    const payload = b64({
      iss: issuer,
      aud: "authenticated",
      sub: SUBJECT,
      iat: now - 10,
      exp: now + 6 * 3600,
      role: "authenticated",
      email: user().email,
      app_metadata: { roles },
      user_metadata: {},
    });
    const signature = sign("RSA-SHA256", Buffer.from(`${header}.${payload}`), keys.privateKey);
    return `${header}.${payload}.${signature.toString("base64url")}`;
  }

  /** Cookie value @supabase/ssr reads from `sb-127-auth-token`. */
  function sessionCookie() {
    const accessToken = token();
    const session = {
      access_token: accessToken,
      refresh_token: "screenshot-fixture-nonrenewable",
      token_type: "bearer",
      expires_in: 6 * 3600,
      expires_at: Math.floor(Date.now() / 1000) + 6 * 3600,
      user: user(),
    };
    return { name: "sb-127-auth-token", value: `base64-${b64(session)}` };
  }

  const server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", origin);
    const path = url.pathname;
    res.setHeader("access-control-allow-origin", req.headers.origin ?? "*");
    res.setHeader("access-control-allow-credentials", "true");
    res.setHeader("access-control-allow-headers", req.headers["access-control-request-headers"] ?? "*");
    res.setHeader("access-control-allow-methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS");
    if (req.method === "OPTIONS") {
      res.statusCode = 204;
      res.end();
      return;
    }
    const reply = (status, body) => {
      res.statusCode = status;
      res.setHeader("content-type", "application/json");
      res.end(JSON.stringify(body));
    };

    if (path === "/auth/v1/.well-known/jwks.json") return reply(200, { keys: [jwk] });
    if (path === "/auth/v1/user") return reply(200, user());
    if (path.startsWith("/auth/v1/token")) {
      return reply(200, {
        access_token: token(),
        refresh_token: "screenshot-fixture-nonrenewable",
        token_type: "bearer",
        expires_in: 6 * 3600,
        expires_at: Math.floor(Date.now() / 1000) + 6 * 3600,
        user: user(),
      });
    }
    if (path.startsWith("/auth/v1/")) return reply(200, {});

    const key = `${req.method} ${path}`;
    for (const [method, route, handler] of emptyApi ? [] : fixtures) {
      if (method !== req.method && method !== "*") continue;
      const match = route instanceof RegExp ? path.match(route) : null;
      const exact = typeof route === "string" && route === path;
      if (!exact && !match) continue;
      const signedIn = Boolean(req.headers.authorization?.startsWith("Bearer ey"));
      const body = typeof handler === "function" ? handler({ url, match, signedIn }) : handler;
      if (log) console.log(`[mock] 200 ${key}`);
      return reply(200, body);
    }
    if (path.startsWith("/rest/v1/")) return reply(200, []);
    if (!emptyApi) unhandled.set(key, (unhandled.get(key) ?? 0) + 1);
    if (log) console.log(`[mock] 404 ${key}${url.search}`);
    return reply(404, {
      error: { code: "not_found", message: "No screenshot fixture", request_id: "fixture" },
    });
  });

  return new Promise((resolve) => {
    server.listen(port, "127.0.0.1", () =>
      resolve({
        origin,
        setRoles: (next) => {
          roles = next;
        },
        /** Answer every API path with 404 / empty rows (API down or empty catalogue). */
        setEmptyApi: (next) => {
          emptyApi = next;
        },
        sessionCookie,
        unhandled,
        close: () =>
          new Promise((done) => {
            server.closeAllConnections();
            server.close(() => done());
          }),
      }),
    );
  });
}
