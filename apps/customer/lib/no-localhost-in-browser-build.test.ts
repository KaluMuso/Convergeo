// @vitest-environment node
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * Acceptance guard: a production browser build must never *silently* call localhost.
 *
 * `NEXT_PUBLIC_*` and `NODE_ENV` are inlined at `next build`, so any hardcoded
 * `localhost` / `127.0.0.1` literal reachable from client code can be frozen into
 * the shipped JS bundle. The customer app centralises its two cross-origin seams:
 *   - the API origin behind `resolveApiBaseUrl` (`lib/api-base-url.ts`), and
 *   - the vendor-app origin behind `getVendorAppUrl`
 *     (`app/[locale]/(marketing)/sell/_components/vendor-app.ts`).
 * BOTH fail closed in a production build (return `null`) and only fall back to a
 * loopback default when `NODE_ENV !== "production"`. Those two modules are the
 * ONLY audited homes for a loopback literal.
 *
 * This test scans every other browser-reachable source file and fails if a
 * loopback literal appears anywhere else — catching a future
 * `fetch("http://localhost:8000/…")` (or a stray dev URL in a comment) before it
 * can ship. Unlike a single unit test on the resolver, this proves the property
 * for the whole app, not just one function.
 *
 * If a new file legitimately needs a loopback literal, it must route through a
 * fail-closed resolver; only then add it here with a written justification.
 */

const CUSTOMER_ROOT = fileURLToPath(new URL("..", import.meta.url));

/** Loopback origins that must never bake into a production browser bundle. */
const LOOPBACK = /localhost|127\.0\.0\.1/i;

/** The only source files permitted to contain a (NODE_ENV-guarded) loopback default. */
const AUDITED_FAIL_CLOSED_RESOLVERS = new Set<string>([
  "lib/api-base-url.ts",
  "app/[locale]/(marketing)/sell/_components/vendor-app.ts",
]);

const SKIP_DIRS = new Set([".next", "node_modules", "__snapshots__", "public"]);

function collectSourceFiles(dir: string): string[] {
  if (!existsSync(dir)) {
    return [];
  }
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!SKIP_DIRS.has(entry.name)) {
        out.push(...collectSourceFiles(full));
      }
    } else if (/\.tsx?$/.test(entry.name) && !/\.(test|spec)\.tsx?$/.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

function toRepoRelative(absolute: string): string {
  return relative(CUSTOMER_ROOT, absolute).split(sep).join("/");
}

// Every browser-reachable source tree: React components + the client fetch libs +
// the service worker + edge middleware. (`app/` also holds server components, whose
// props can serialize into the RSC payload the browser receives — so they count too.)
const scannedFiles = [
  ...collectSourceFiles(join(CUSTOMER_ROOT, "app")),
  ...collectSourceFiles(join(CUSTOMER_ROOT, "lib")),
  ...["sw.ts", "middleware.ts"].map((f) => join(CUSTOMER_ROOT, f)).filter((f) => existsSync(f)),
];

describe("no localhost in the production browser build", () => {
  it("actually scanned the customer source tree (guard is wired, not vacuous)", () => {
    expect(scannedFiles.length).toBeGreaterThan(50);
  });

  it("no source outside the two audited fail-closed resolvers hardcodes a loopback origin", () => {
    const offenders = scannedFiles
      .filter((file) => LOOPBACK.test(readFileSync(file, "utf8")))
      .map(toRepoRelative)
      .filter((rel) => !AUDITED_FAIL_CLOSED_RESOLVERS.has(rel))
      .sort();

    // A non-empty list means a client-reachable module can freeze a loopback URL
    // into the shipped bundle. Route it through resolveApiBaseUrl/getVendorAppUrl.
    expect(offenders).toEqual([]);
  });

  it("the audited resolvers keep their loopback default NODE_ENV-guarded", () => {
    for (const rel of AUDITED_FAIL_CLOSED_RESOLVERS) {
      const source = readFileSync(join(CUSTOMER_ROOT, rel), "utf8");
      // It is the audited home for the literal…
      expect(source).toMatch(LOOPBACK);
      // …and the literal is only reachable when NODE_ENV is not production.
      expect(source).toMatch(/NODE_ENV/);
      expect(source).toMatch(/"production"/);
    }
  });
});
