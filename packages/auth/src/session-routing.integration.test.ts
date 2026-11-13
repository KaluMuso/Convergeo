// @vitest-environment node
// Exercises the installed Supabase SSR/Auth SDK against a loopback-only auth
// fixture. No SDK mocks, E2E session injection, hosted users, or database writes.
import { generateKeyPairSync, sign, verify, type KeyObject } from "node:crypto";
import { createServer, type Server } from "node:http";

import { createServerClient } from "@supabase/ssr";
import { NextRequest } from "next/server";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveGatedRedirect, updateSession } from "./middleware";
import { getRolesFromUser } from "./roles";

const subject = "00000000-0000-4000-8000-000000000001";
const locales = ["en", "fr"] as const;
let server: Server;
let origin: string;
let signingKey: KeyObject;
let verifyingKey: KeyObject;
let userMetadataRoles: string[];
let denyUser: boolean;
let calls: string[];

function encode(value: unknown): string {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

function token(roles: unknown, options: { expired?: boolean; key?: KeyObject } = {}): string {
  const now = Math.floor(Date.now() / 1000);
  const header = encode({ alg: "RS256", typ: "JWT", kid: "loopback-fixture-key" });
  const payload = encode({
    iss: `${origin}/auth/v1`,
    aud: "authenticated",
    sub: subject,
    iat: now - 10,
    exp: options.expired ? now - 60 : now + 1200,
    role: "authenticated",
    app_metadata: { roles },
    // User-editable claims must never confer a portal role.
    user_metadata: { roles: ["admin", "vendor"] },
  });
  const signature = sign(
    "RSA-SHA256",
    Buffer.from(`${header}.${payload}`),
    options.key ?? signingKey,
  );
  return `${header}.${payload}.${signature.toString("base64url")}`;
}

function request(accessToken?: string, expiredCookie = false): NextRequest {
  const headers = new Headers();
  if (accessToken) {
    const session = {
      access_token: accessToken,
      refresh_token: "loopback-only-nonrenewable",
      token_type: "bearer",
      expires_in: 1200,
      expires_at: Math.floor(Date.now() / 1000) + (expiredCookie ? -60 : 1200),
      user: { id: subject, app_metadata: { roles: ["admin", "vendor"] }, user_metadata: {} },
    };
    headers.set("cookie", `sb-127-auth-token=base64-${encode(session)}`);
  }
  return new NextRequest("http://localhost:3001/en/listings", { headers });
}

beforeAll(async () => {
  const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
  signingKey = keys.privateKey;
  verifyingKey = keys.publicKey;
  const jwk = {
    ...verifyingKey.export({ format: "jwk" }),
    alg: "RS256",
    kid: "loopback-fixture-key",
    use: "sig",
  };
  server = createServer((req, res) => {
    calls.push(`${req.method} ${req.url?.split("?")[0]}`);
    res.setHeader("content-type", "application/json");
    const reply = (status: number, body: unknown) => {
      res.statusCode = status;
      res.end(JSON.stringify(body));
    };
    if (req.url === "/auth/v1/.well-known/jwks.json") {
      reply(200, { keys: [jwk] });
      return;
    }
    if (req.url?.startsWith("/auth/v1/token")) {
      reply(400, {
        error_code: "refresh_token_not_found",
        msg: "Local fixture does not renew sessions",
      });
      return;
    }
    if (req.url === "/auth/v1/user") {
      try {
        const raw = req.headers.authorization?.replace(/^Bearer /, "") ?? "";
        const [header, payload, signature] = raw.split(".");
        if (!header || !payload || !signature || denyUser) throw new Error("Denied");
        const claims = JSON.parse(Buffer.from(payload, "base64url").toString()) as {
          exp: number;
          iss: string;
          aud: string;
          sub: string;
        };
        if (
          !verify(
            "RSA-SHA256",
            Buffer.from(`${header}.${payload}`),
            verifyingKey,
            Buffer.from(signature, "base64url"),
          ) ||
          claims.exp <= Date.now() / 1000 ||
          claims.iss !== `${origin}/auth/v1` ||
          claims.aud !== "authenticated" ||
          claims.sub !== subject
        )
          throw new Error("Denied");
        // The token hook changes JWT app_metadata, not the User record.
        reply(200, {
          id: subject,
          aud: "authenticated",
          role: "authenticated",
          email: "fixture@example.invalid",
          app_metadata: { roles: userMetadataRoles },
          user_metadata: { roles: ["admin", "vendor"] },
          created_at: "2026-01-01T00:00:00Z",
        });
      } catch {
        reply(401, { error_code: "bad_jwt", msg: "Local fixture rejected authentication" });
      }
      return;
    }
    reply(404, { msg: "No fixture endpoint" });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Local fixture did not start");
  origin = `http://127.0.0.1:${address.port}`;
});

beforeEach(() => {
  calls = [];
  userMetadataRoles = [];
  denyUser = false;
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", origin);
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "loopback-only-publishable-fixture");
  vi.stubEnv("NEXT_PUBLIC_ADMIN_BYPASS", "false");
  vi.stubEnv("NEXT_PUBLIC_E2E_MOCK_SESSION", "0");
});
afterEach(() => vi.unstubAllEnvs());
afterAll(async () => {
  server.closeAllConnections();
  await new Promise<void>((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve())),
  );
});

function gate(portal: "vendor" | "admin", session: Awaited<ReturnType<typeof updateSession>>) {
  return resolveGatedRedirect(
    portal,
    portal === "vendor" ? "/en/listings" : "/en",
    locales,
    session.user,
    session.roles,
  );
}

describe("verified local SDK sessions and portal routing", () => {
  it.each(["vendor", "admin"] as const)(
    "routes a signed %s token-hook role despite absent User metadata",
    async (portal) => {
      const session = await updateSession(request(token([portal])));
      expect(session.user?.id).toBe(subject);
      expect(getRolesFromUser(session.user)).toEqual([]); // historical source risk
      expect(session.roles).toEqual([portal]);
      expect(gate(portal, session)).toBeNull();
      expect(calls).toContain("GET /auth/v1/user");
    },
  );

  it("keeps a signed customer out of vendor/admin tools", async () => {
    const session = await updateSession(request(token(["customer"])));
    expect(session.roles).toEqual(["customer"]);
    expect(gate("vendor", session)).toBe("onboarding");
    expect(gate("admin", session)).toBe("permission-denied");
    expect(
      resolveGatedRedirect("none", "/en/account", locales, session.user, session.roles),
    ).toBeNull();
  });

  it("ignores privileged User metadata and user-editable claims when the verified token has no role", async () => {
    userMetadataRoles = ["admin", "vendor"];
    const session = await updateSession(request(token([])));
    expect(session.roles).toEqual([]);
    expect(gate("vendor", session)).toBe("onboarding");
    expect(gate("admin", session)).toBe("permission-denied");
  });

  it("does not derive roles from malformed or unknown signed role claims", async () => {
    const session = await updateSession(request(token(["root", 42, null])));
    expect(session.roles).toEqual([]);
    expect(gate("admin", session)).toBe("permission-denied");
  });

  it("requires a real accepted User as well as a signed role token", async () => {
    denyUser = true;
    const session = await updateSession(request(token(["admin"])));
    expect(session.user).toBeNull();
    expect(gate("admin", session)).toBe("login");
  });

  it("denies an expired signed token even if the cookie expiry looks current", async () => {
    const session = await updateSession(request(token(["admin"], { expired: true })));
    expect(session.roles).toEqual([]);
    expect(gate("admin", session)).toBe("login");
    expect(gate("vendor", session)).toBe("login");
  });

  it("denies an expired nonrenewable session and propagates cookie removal", async () => {
    const session = await updateSession(request(token(["admin"], { expired: true }), true));
    expect(session.roles).toEqual([]);
    expect(gate("admin", session)).toBe("login");
    expect(calls).toContain("POST /auth/v1/token");
    expect(
      session.response.cookies
        .getAll()
        .some((cookie) => cookie.name.startsWith("sb-127-auth-token") && cookie.value === ""),
    ).toBe(true);
  });

  it("denies a forged role token signed by a different key with the same key id", async () => {
    const forgedKey = generateKeyPairSync("rsa", { modulusLength: 2048 }).privateKey;
    const session = await updateSession(request(token(["admin", "vendor"], { key: forgedKey })));
    expect(session.roles).toEqual([]);
    expect(gate("admin", session)).toBe("login");
    expect(gate("vendor", session)).toBe("login");
  });

  it("denies a logged-out request without contacting auth", async () => {
    const session = await updateSession(request());
    expect(session.user).toBeNull();
    expect(session.roles).toEqual([]);
    expect(gate("admin", session)).toBe("login");
    expect(gate("vendor", session)).toBe("login");
    expect(calls).toEqual([]);
  });
});

describe("installed SDK JWT verification independent of Auth user acceptance", () => {
  function claimsClient() {
    return createServerClient(origin, "loopback-only-publishable-fixture", {
      cookies: { getAll: () => [], setAll: () => {} },
    });
  }

  it("verifies a locally signed role token without calling the User endpoint", async () => {
    const result = await claimsClient().auth.getClaims(token(["vendor"]));
    expect(result.error).toBeNull();
    expect(result.data?.claims.app_metadata?.roles).toEqual(["vendor"]);
    expect(calls).not.toContain("GET /auth/v1/user");
  });

  it("rejects an expired signed token before returning claims", async () => {
    const result = await claimsClient().auth.getClaims(token(["admin"], { expired: true }));
    expect(Boolean(result.error)).toBe(true);
    expect(result.data).toBeNull();
    expect(calls).not.toContain("GET /auth/v1/user");
  });

  it("rejects a forged same-key-id signature using the fixture JWKS", async () => {
    const forgedKey = generateKeyPairSync("rsa", { modulusLength: 2048 }).privateKey;
    const result = await claimsClient().auth.getClaims(token(["admin"], { key: forgedKey }));
    expect(Boolean(result.error)).toBe(true);
    expect(result.data).toBeNull();
    expect(calls).not.toContain("GET /auth/v1/user");
  });
});
