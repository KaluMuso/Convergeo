import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

import {
  BYPASS_HEADER,
  SET_BYPASS_COOKIE_HEADER,
  applyPortalBypass,
  isPortalOrigin,
  originOf,
  portalOrigins,
  resolveBypassSecret,
  withBypassHeaders,
} from "../../../e2e/fixtures/portal-bypass.ts";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

/**
 * Staging E2E run #70 root causes, both in the portal-bypass request boundary.
 *
 * Every "secret" below is an obvious NON-secret label ("customer-credential").
 * Nothing in this file reads process.env, and nothing prints or compares a real
 * credential — the contracts under test are "which slot was chosen" and "which
 * headers survived", neither of which needs a real value.
 */
const CONFIG = {
  customer: { baseUrl: "https://customer.staging.test", secret: "customer-credential" },
  vendor: { baseUrl: "https://vendor.staging.test", secret: "vendor-credential" },
  admin: { baseUrl: "https://admin.staging.test", secret: "admin-credential" },
};

describe("resolveBypassSecret — fails closed on every unmatched origin", () => {
  it("customer URL resolves the customer credential", () => {
    assert.equal(
      resolveBypassSecret("https://customer.staging.test/en/cart", CONFIG),
      "customer-credential",
    );
  });

  it("vendor URL resolves the vendor credential", () => {
    assert.equal(
      resolveBypassSecret("https://vendor.staging.test/en/login?next=%2Fen%2Fservices", CONFIG),
      "vendor-credential",
    );
  });

  it("admin URL resolves the admin credential", () => {
    assert.equal(
      resolveBypassSecret("https://admin.staging.test/en/disputes", CONFIG),
      "admin-credential",
    );
  });

  /**
   * THE run #70 credential-exposure condition. Before this fix an unmatched
   * origin fell through to the CUSTOMER secret, so every Supabase auth call,
   * every staging API call and every third-party asset fetch the suite made
   * was rewritten to carry a Vercel bypass credential for a project none of
   * them belong to.
   */
  it("Supabase URL resolves NOTHING", () => {
    assert.equal(resolveBypassSecret("https://abcdefgh.supabase.co/auth/v1/verify", CONFIG), "");
  });

  it("staging FastAPI URL resolves NOTHING", () => {
    assert.equal(resolveBypassSecret("https://api.staging.test/v1/orders", CONFIG), "");
  });

  it("arbitrary third-party URL resolves NOTHING", () => {
    for (const url of [
      "https://res.cloudinary.com/demo/image/upload/x.webp",
      "https://fonts.gstatic.com/s/inter.woff2",
      "https://evil.example/collect",
      "http://localhost:9999/anything",
    ]) {
      assert.equal(resolveBypassSecret(url, CONFIG), "", `expected no credential for ${url}`);
    }
  });

  it("malformed URL resolves NOTHING (fails closed, not to customer)", () => {
    for (const url of ["", "   ", "not-a-url", "/en/cart", "://missing-scheme", "javascript:x"]) {
      assert.equal(
        resolveBypassSecret(url, CONFIG),
        "",
        `expected an unparseable URL (${JSON.stringify(url)}) to resolve no credential`,
      );
    }
  });

  it("matches on origin only — a path or query that names another portal changes nothing", () => {
    assert.equal(
      resolveBypassSecret("https://evil.example/https://vendor.staging.test/x", CONFIG),
      "",
    );
    assert.equal(
      resolveBypassSecret("https://customer.staging.test/x?to=https://admin.staging.test", CONFIG),
      "customer-credential",
    );
  });

  it("is port- and scheme-sensitive (a different origin is a different origin)", () => {
    assert.equal(resolveBypassSecret("https://customer.staging.test:8443/en", CONFIG), "");
    assert.equal(resolveBypassSecret("http://customer.staging.test/en", CONFIG), "");
  });

  it("keeps customer precedence when a portal is not separately configured", () => {
    // VENDOR_BASE_URL/ADMIN_BASE_URL default to the customer base for --list
    // and typecheck; on that collision the origin genuinely IS the customer app.
    const collapsed = {
      customer: { baseUrl: "https://one.staging.test", secret: "customer-credential" },
      vendor: { baseUrl: "https://one.staging.test", secret: "vendor-credential" },
      admin: { baseUrl: "https://one.staging.test", secret: "admin-credential" },
    };
    assert.equal(
      resolveBypassSecret("https://one.staging.test/en", collapsed),
      "customer-credential",
    );
    assert.equal(resolveBypassSecret("https://two.staging.test/en", collapsed), "");
  });

  it("an unconfigured portal origin cannot borrow another portal's credential", () => {
    const partial = {
      customer: { baseUrl: "https://customer.staging.test", secret: "customer-credential" },
      vendor: { baseUrl: "", secret: "" },
      admin: { baseUrl: "", secret: "" },
    };
    assert.equal(resolveBypassSecret("https://vendor.staging.test/en", partial), "");
    assert.equal(resolveBypassSecret("", partial), "");
  });
});

describe("route matcher — only portal origins are intercepted at all", () => {
  it("recognizes exactly the three configured portal origins", () => {
    assert.deepEqual(portalOrigins(CONFIG), [
      "https://customer.staging.test",
      "https://vendor.staging.test",
      "https://admin.staging.test",
    ]);
    assert.ok(isPortalOrigin("https://vendor.staging.test/en/login", CONFIG));
    assert.ok(isPortalOrigin("https://admin.staging.test/", CONFIG));
  });

  it("does not match Supabase, the API, third parties or an unparseable URL", () => {
    assert.equal(isPortalOrigin("https://abcdefgh.supabase.co/auth/v1/token", CONFIG), false);
    assert.equal(isPortalOrigin("https://api.staging.test/v1/health", CONFIG), false);
    assert.equal(isPortalOrigin("https://evil.example/", CONFIG), false);
    assert.equal(isPortalOrigin("not-a-url", CONFIG), false);
  });

  it("de-duplicates collapsed origins and drops unparseable ones", () => {
    assert.deepEqual(
      portalOrigins({
        customer: { baseUrl: "https://one.staging.test", secret: "c" },
        vendor: { baseUrl: "https://one.staging.test", secret: "v" },
        admin: { baseUrl: "", secret: "" },
      }),
      ["https://one.staging.test"],
    );
  });

  it("originOf lower-cases and never throws", () => {
    assert.equal(originOf("HTTPS://Customer.Staging.TEST/EN"), "https://customer.staging.test");
    assert.equal(originOf("garbage"), "");
  });
});

/**
 * A Playwright `Route` double that reproduces the exact accessor split that
 * caused the defect: `headers()` is the synchronous accessor that OMITS
 * security-sensitive headers (Cookie, Authorization), `allHeaders()` is the
 * async one that includes them.
 */
function fakeRoute(url, { safeHeaders, sensitiveHeaders }) {
  const calls = { fallback: [] };
  return {
    calls,
    request() {
      return {
        url: () => url,
        headers: () => ({ ...safeHeaders }),
        allHeaders: async () => ({ ...safeHeaders, ...sensitiveHeaders }),
      };
    },
    async fallback(options) {
      calls.fallback.push(options);
    },
  };
}

const SAFE_HEADERS = {
  accept: "text/html",
  "accept-language": "en-ZM,en;q=0.9",
  "user-agent": "Mozilla/5.0 (Pixel 7)",
  referer: "https://vendor.staging.test/en/login",
};

const SENSITIVE_HEADERS = {
  cookie: "sb-abcdefgh-auth-token=session-value; sb-refresh=refresh-value",
  authorization: "Bearer header-value",
};

describe("applyPortalBypass — the complete header set survives the rewrite", () => {
  it("preserves Cookie (and every other original header) while injecting the bypass headers", async () => {
    const route = fakeRoute("https://vendor.staging.test/en/services", {
      safeHeaders: SAFE_HEADERS,
      sensitiveHeaders: SENSITIVE_HEADERS,
    });

    await applyPortalBypass(route, (url) => resolveBypassSecret(url, CONFIG));

    assert.equal(route.calls.fallback.length, 1);
    const sent = route.calls.fallback[0].headers;

    // 1A regression: `request().headers()` omits Cookie, so rebuilding the
    // request from it dropped the Supabase session on every rewritten request.
    // `route.fallback({ headers })` REPLACES the map, so the drop was total.
    assert.equal(
      sent.cookie,
      SENSITIVE_HEADERS.cookie,
      "Cookie must survive the rewrite unchanged",
    );
    assert.equal(sent.authorization, SENSITIVE_HEADERS.authorization);

    // The bypass headers are present.
    assert.equal(sent[BYPASS_HEADER], "vendor-credential");
    assert.equal(sent[SET_BYPASS_COOKIE_HEADER], "true");

    // And every unrelated original header is still there, unchanged.
    for (const [name, value] of Object.entries(SAFE_HEADERS)) {
      assert.equal(sent[name], value, `original header "${name}" must be preserved`);
    }
  });

  it("never reads the cookie-stripping synchronous accessor", async () => {
    const route = fakeRoute("https://customer.staging.test/en", {
      safeHeaders: SAFE_HEADERS,
      sensitiveHeaders: SENSITIVE_HEADERS,
    });
    const request = route.request();
    request.headers = () => {
      throw new Error("applyPortalBypass must not call request().headers() when rewriting");
    };
    route.request = () => request;

    await applyPortalBypass(route, (url) => resolveBypassSecret(url, CONFIG));
    assert.equal(route.calls.fallback[0].headers[BYPASS_HEADER], "customer-credential");
  });

  it("passes an unmatched origin through UNTOUCHED — no headers argument at all", async () => {
    for (const url of [
      "https://abcdefgh.supabase.co/auth/v1/verify",
      "https://api.staging.test/v1/orders",
      "https://res.cloudinary.com/demo/image/upload/x.webp",
      "not-a-url",
    ]) {
      const route = fakeRoute(url, {
        safeHeaders: SAFE_HEADERS,
        sensitiveHeaders: SENSITIVE_HEADERS,
      });
      await applyPortalBypass(route, (target) => resolveBypassSecret(target, CONFIG));
      assert.deepEqual(
        route.calls.fallback,
        [undefined],
        `${url} must be forwarded unmodified (no headers replacement)`,
      );
    }
  });

  it("withBypassHeaders adds exactly two headers and mutates nothing else", () => {
    const original = Object.freeze({ ...SAFE_HEADERS, ...SENSITIVE_HEADERS });
    const result = withBypassHeaders(original, "vendor-credential");
    assert.deepEqual(
      Object.keys(result).sort(),
      [...Object.keys(original), BYPASS_HEADER, SET_BYPASS_COOKIE_HEADER].sort(),
    );
    assert.deepEqual(original, { ...SAFE_HEADERS, ...SENSITIVE_HEADERS });
  });

  it("an origin's own bypass header wins over one already on the request", () => {
    const result = withBypassHeaders(
      { [BYPASS_HEADER]: "stale-credential", accept: "text/html" },
      "vendor-credential",
    );
    assert.equal(result[BYPASS_HEADER], "vendor-credential");
    assert.equal(result.accept, "text/html");
  });
});

/**
 * Focused source guard for the ONE unsafe shape, not a blanket ban on
 * `headers()`. Read-only diagnostic use (`const h = req.headers(); log(h.x)`)
 * stays legal; SPREADING a header map into a replacement passed to
 * fallback()/continue() is what silently drops Cookie, and that is what fails
 * here.
 */
describe("request-rewriting guard", () => {
  /**
   * Comments removed line-wise, so prose about the trap is not itself the trap.
   *
   * Deliberately NOT a `/* … *\/` regex: a route glob such as "**\/*" contains
   * a comment-open sequence, and a naive block matcher pairs it with a later
   * close and swallows real code — including the exact spread this guard
   * exists to catch.
   */
  function stripComments(source) {
    return source
      .split("\n")
      .map((line) => {
        const trimmed = line.trim();
        if (trimmed.startsWith("*") || trimmed.startsWith("/*") || trimmed.startsWith("//")) {
          return "";
        }
        return line.replace(/\s\/\/.*$/, "");
      })
      .join("\n");
  }

  function e2eSources() {
    const dirs = ["e2e/fixtures", "e2e/specs"];
    const files = [];
    for (const dir of dirs) {
      for (const name of readdirSync(path.join(REPO_ROOT, dir))) {
        if (name.endsWith(".ts")) {
          files.push(path.join(dir, name));
        }
      }
    }
    return files;
  }

  it("no E2E source spreads a synchronous .headers() map into a rewritten request", () => {
    // Matches a spread whose source is a synchronous `.headers()` call —
    // `...route.request().headers()`, `...(await route.request()).headers()`,
    // and the same chain broken across lines. The `[^;{},]` run stops at the
    // first statement/property boundary, so a read-only `const h =
    // req.headers()` elsewhere in the file, or a `...allHeaders` spread, is
    // NOT a match; `.allHeaders()` is a different identifier and never matches.
    const spreadSyncHeaders = /\.\.\.[^;{},]{0,200}\.headers\(\)/;
    for (const file of e2eSources()) {
      const source = stripComments(readFileSync(path.join(REPO_ROOT, file), "utf8"));
      assert.ok(
        !spreadSyncHeaders.test(source),
        `${file} spreads a synchronous .headers() map — it omits Cookie/Authorization, and ` +
          "route.fallback({ headers }) REPLACES the whole map, so the session cookie is dropped. " +
          "Use `await request.allHeaders()` (see e2e/fixtures/portal-bypass.ts).",
      );
    }
  });

  it("portal-bypass.ts builds the replacement from awaited allHeaders()", () => {
    const source = readFileSync(path.join(REPO_ROOT, "e2e/fixtures/portal-bypass.ts"), "utf8");
    assert.ok(
      /await\s+request\.allHeaders\(\)/.test(source),
      "portal-bypass.ts must await request.allHeaders() before rewriting a request",
    );
    // Comments are stripped first: the file DOCUMENTS why `request.headers()`
    // is wrong, and explaining the trap must not trip the guard against it.
    assert.ok(
      !/\.headers\(\)/.test(stripComments(source)),
      "portal-bypass.ts must not call the cookie-stripping .headers() accessor",
    );
  });

  it("the BypassRoute type does not expose the unsafe accessor to rewriting code", () => {
    const source = readFileSync(path.join(REPO_ROOT, "e2e/fixtures/portal-bypass.ts"), "utf8");
    const requestType = source.slice(
      source.indexOf("export type BypassRouteRequest"),
      source.indexOf("export type BypassRoute ="),
    );
    assert.ok(requestType.includes("allHeaders()"));
    assert.ok(!/\bheaders\(\)/.test(requestType.replace(/allHeaders\(\)/g, "")));
  });

  it("test-base.ts routes only portal origins — no `**/*` catch-all interception", () => {
    const source = readFileSync(path.join(REPO_ROOT, "e2e/fixtures/test-base.ts"), "utf8");
    assert.ok(
      !/context\.route\(\s*["'`]\*\*\/\*["'`]/.test(source),
      "test-base.ts must not intercept every origin — route only the configured portal origins",
    );
    assert.ok(
      source.includes("isPortalOrigin"),
      "test-base.ts must use isPortalOrigin as the route matcher",
    );
    assert.ok(
      source.includes("applyPortalBypass"),
      "test-base.ts must delegate the header rewrite to the unit-tested helper",
    );
  });

  it("env.ts's bypassSecretForUrl no longer falls through to the customer credential", () => {
    const source = readFileSync(path.join(REPO_ROOT, "e2e/fixtures/env.ts"), "utf8");
    const fn = source.slice(
      source.indexOf("export function bypassSecretForUrl"),
      source.indexOf("/** Build a locale-prefixed absolute URL"),
    );
    assert.ok(fn.length > 0, "bypassSecretForUrl must still exist in e2e/fixtures/env.ts");
    assert.ok(
      !/return\s+BYPASS_SECRET_CUSTOMER\s*;/.test(fn),
      "bypassSecretForUrl must not return a portal credential for an unmatched origin",
    );
    assert.ok(
      fn.includes("resolveBypassSecret"),
      "bypassSecretForUrl must delegate to the guarded resolver",
    );
  });
});
