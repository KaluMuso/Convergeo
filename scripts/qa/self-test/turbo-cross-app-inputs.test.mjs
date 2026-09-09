import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const APPS_DIR = path.join(REPO_ROOT, "apps");

/**
 * Run #74 root cause B — the silent stale build.
 *
 * `apps/vendor` and `apps/admin` render the Customer app's shared auth
 * components through RELATIVE cross-app imports, but neither declares a
 * dependency on `customer` (it is an app, not a workspace package). Turborepo
 * hashes `vendor#build` from `apps/vendor/**` plus its declared internal
 * dependencies, so a change confined to `apps/customer/**` left the hash
 * untouched: `vendor:build: cache hit, replaying logs b0a9df56536e2d5e` on
 * BOTH sides of PR #697, i.e. byte-identical build output, i.e. the deployed
 * Vendor app never received the fix. `/health` could not detect it — the SHA
 * it reports comes from the deployment's git metadata, not from the compiled
 * bundle.
 *
 * This guard makes that class of failure impossible to reintroduce silently:
 * every cross-app source import must be matched by a `$TURBO_ROOT$` input glob
 * on the importing app's build task.
 */

const SOURCE_EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]);
const SKIP_DIRS = new Set(["node_modules", ".next", "dist", ".turbo", "coverage"]);

function appNames() {
  return readdirSync(APPS_DIR).filter((name) => statSync(path.join(APPS_DIR, name)).isDirectory());
}

function sourceFiles(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (!SKIP_DIRS.has(entry.name)) sourceFiles(path.join(dir, entry.name), out);
    } else if (SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
      out.push(path.join(dir, entry.name));
    }
  }
  return out;
}

/** Every `import ... from "<relative>"` / `import("<relative>")` specifier. */
function relativeSpecifiers(source) {
  const specs = [];
  const patterns = [
    /\bfrom\s*["'](\.[^"']*)["']/g,
    /\bimport\s*\(\s*["'](\.[^"']*)["']\s*\)/g,
    /\brequire\s*\(\s*["'](\.[^"']*)["']\s*\)/g,
  ];
  for (const pattern of patterns) {
    for (const match of source.matchAll(pattern)) specs.push(match[1]);
  }
  return specs;
}

/**
 * Cross-app imports as { importer, target, file, specifier } — a relative
 * import from apps/A that resolves inside apps/B (B !== A).
 */
function crossAppImports() {
  const apps = appNames();
  const found = [];
  for (const app of apps) {
    const appRoot = path.join(APPS_DIR, app);
    for (const file of sourceFiles(appRoot)) {
      for (const specifier of relativeSpecifiers(readFileSync(file, "utf8"))) {
        const resolved = path.resolve(path.dirname(file), specifier);
        const rel = path.relative(REPO_ROOT, resolved).split(path.sep).join("/");
        const match = /^apps\/([^/]+)\//.exec(rel);
        if (match && match[1] !== app) {
          found.push({
            importer: app,
            target: match[1],
            specifier,
            file: path.relative(REPO_ROOT, file).split(path.sep).join("/"),
            resolved: rel,
          });
        }
      }
    }
  }
  return found;
}

function packageTurboConfig(app) {
  const file = path.join(APPS_DIR, app, "turbo.json");
  if (!existsSync(file)) return null;
  return JSON.parse(readFileSync(file, "utf8"));
}

/** Literal directory prefix of a `$TURBO_ROOT$/...` glob, before any wildcard. */
function rootGlobPrefix(glob) {
  if (!glob.startsWith("$TURBO_ROOT$/")) return null;
  const rest = glob.slice("$TURBO_ROOT$/".length);
  const segments = [];
  for (const segment of rest.split("/")) {
    if (segment.includes("*")) break;
    segments.push(segment);
  }
  return segments.join("/");
}

describe("cross-app imports must invalidate the importing app's build", () => {
  it("finds the cross-app imports this guard exists for", () => {
    const imports = crossAppImports();
    assert.ok(
      imports.length > 0,
      "expected at least one cross-app import (vendor/admin render the Customer auth shell); " +
        "if these were removed, delete this guard together with them",
    );
    const importers = new Set(imports.map((entry) => entry.importer));
    assert.ok(importers.has("vendor"), "apps/vendor should still import Customer auth components");
    assert.ok(importers.has("admin"), "apps/admin should still import Customer auth components");
  });

  it("every importing app declares a $TURBO_ROOT$ input covering what it imports", () => {
    for (const entry of crossAppImports()) {
      const config = packageTurboConfig(entry.importer);
      assert.ok(
        config,
        `apps/${entry.importer}/turbo.json is missing, but ${entry.file} imports ` +
          `"${entry.specifier}" from apps/${entry.target}. Without a $TURBO_ROOT$ input, a change ` +
          `to apps/${entry.target} leaves ${entry.importer}#build's hash untouched and Turborepo ` +
          "replays a stale build — the deployed app silently keeps the old bundle (run #74).",
      );

      assert.deepEqual(
        config.extends,
        ["//"],
        `apps/${entry.importer}/turbo.json must extend the root config so dependsOn/outputs stay inherited`,
      );

      const inputs = config.tasks?.build?.inputs;
      assert.ok(
        Array.isArray(inputs),
        `apps/${entry.importer}/turbo.json must declare tasks.build.inputs`,
      );
      assert.ok(
        inputs.includes("$TURBO_DEFAULT$"),
        `apps/${entry.importer}/turbo.json must keep "$TURBO_DEFAULT$" in tasks.build.inputs, or ` +
          "declaring an external glob would DROP the app's own sources from the hash",
      );

      const covered = inputs
        .map(rootGlobPrefix)
        .filter((prefix) => prefix !== null)
        .some((prefix) => entry.resolved === prefix || entry.resolved.startsWith(`${prefix}/`));

      assert.ok(
        covered,
        `apps/${entry.importer}/turbo.json declares no $TURBO_ROOT$ input covering ` +
          `"${entry.resolved}" (imported by ${entry.file}). Add a root-relative glob that contains it.`,
      );
    }
  });

  it("the repair stays scoped to the importing apps — root build gains no inputs", () => {
    // Adding `inputs` to the ROOT build task would re-hash EVERY workspace
    // build, not just the two apps with cross-app imports.
    const root = JSON.parse(readFileSync(path.join(REPO_ROOT, "turbo.json"), "utf8"));
    assert.equal(
      root.tasks?.build?.inputs,
      undefined,
      "root turbo.json build task must not declare inputs — scope the repair to apps/*/turbo.json",
    );
    assert.deepEqual(root.tasks?.build?.dependsOn, ["^build"]);
  });

  it("apps without cross-app imports are not given external inputs", () => {
    const importers = new Set(crossAppImports().map((entry) => entry.importer));
    for (const app of appNames()) {
      if (importers.has(app)) continue;
      const config = packageTurboConfig(app);
      const inputs = config?.tasks?.build?.inputs ?? [];
      assert.ok(
        !inputs.some((glob) => typeof glob === "string" && glob.startsWith("$TURBO_ROOT$/apps/")),
        `apps/${app} has no cross-app import, so it must not declare a $TURBO_ROOT$/apps/* input`,
      );
    }
  });
});
