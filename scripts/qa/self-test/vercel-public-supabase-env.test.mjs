import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

/**
 * PR-E, Part A: every portal must fail its Vercel build closed on missing or
 * invalid public Supabase config (packages/config/src/env.ts's
 * `assertVercelPublicSupabaseEnv`), not just Customer.
 *
 * Directly `import()`-ing a next.config.ts standalone does not work — Next's
 * own bundler resolves the app-relative imports each config file makes (e.g.
 * `./lib/api-base-url`), and a bare Node ESM loader cannot (confirmed: it
 * throws a MODULE_NOT_FOUND unrelated to this assertion). So this is the
 * structural/guard test the task calls for: it proves each config file wires
 * the ONE shared assertion — never a duplicated per-app copy of the
 * validation logic — and that the call is unconditional (not hidden behind a
 * dev-only branch that would never run in a real Vercel build).
 */
const PORTAL_NEXT_CONFIGS = [
  "apps/customer/next.config.ts",
  "apps/vendor/next.config.ts",
  "apps/admin/next.config.ts",
];

describe("Vercel public Supabase env — every portal wires the shared assertion", () => {
  for (const relativePath of PORTAL_NEXT_CONFIGS) {
    const source = readFileSync(path.join(REPO_ROOT, relativePath), "utf8");

    it(`${relativePath} imports assertVercelPublicSupabaseEnv from @vergeo/config`, () => {
      assert.match(
        source,
        /import\s*\{[^}]*\bassertVercelPublicSupabaseEnv\b[^}]*\}\s*from\s*["']@vergeo\/config["']/,
        `${relativePath} must import assertVercelPublicSupabaseEnv from the shared @vergeo/config package — no per-app duplicate of the validation logic`,
      );
    });

    it(`${relativePath} calls assertVercelPublicSupabaseEnv() unconditionally at module scope`, () => {
      const lines = source.split("\n");
      const callLineIndex = lines.findIndex((line) =>
        /^\s*assertVercelPublicSupabaseEnv\(\s*\)\s*;?\s*$/.test(line),
      );
      assert.notEqual(
        callLineIndex,
        -1,
        `${relativePath} must call assertVercelPublicSupabaseEnv() on its own line at module scope — a call wrapped in a conditional or nested inside a function would never run when Next.js loads the config`,
      );

      // Not inside an `if (...)`/function body: the call line's indentation is
      // column 0 (module top level), matching every import/const above it.
      const callLine = lines[callLineIndex];
      assert.equal(
        callLine,
        callLine.trimStart(),
        `${relativePath}'s assertVercelPublicSupabaseEnv() call must be at module top level (column 0), not nested inside a conditional or function`,
      );
    });

    it(`${relativePath} calls the assertion before composing the heavy plugin chain`, () => {
      const callIndex = source.search(/^\s*assertVercelPublicSupabaseEnv\(\s*\)\s*;?\s*$/m);
      const exportIndex = source.search(/^export default /m);
      assert.ok(
        callIndex !== -1 && exportIndex !== -1 && callIndex < exportIndex,
        `${relativePath} must call assertVercelPublicSupabaseEnv() before the config's default export — a Vercel build must fail before any Next.js plugin work happens, not after`,
      );
    });
  }
});
