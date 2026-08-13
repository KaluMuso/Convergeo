#!/usr/bin/env node
/**
 * Release guard: production-like frontend bundles must never ship a loopback
 * API origin, and Preview/staging must never target the production API.
 *
 * Scans built Next.js client/server JS for:
 *   - http://localhost:8000 / 127.0.0.1:8000 / [::1]:8000
 *   - wrong-plane API hosts (preview/staging → api.vergeo5.com,
 *     production → api.staging.vergeo5.com)
 *
 * Affected-app scoping:
 *   --require-affected --filter='...[base]'  (CI) — turbo dry-run decides
 *     which of customer/vendor/admin must have been built. Missing .next
 *     for a required app is a failure. Unrelated PRs with no frontend apps
 *     in the turbo graph pass without scanning.
 *   --require-apps=customer,vendor           — explicit list
 *   no flags                                 — all three apps required
 *
 * Missing .next is never a silent SKIP for a required app.
 */
import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

export const FRONTEND_APPS = ["customer", "vendor", "admin"];
export const LOOPBACK_API = /https?:\/\/(?:localhost|127\.0\.0\.1|\[::1\]):8000\b/i;
export const PRODUCTION_API = /https:\/\/api\.vergeo5\.com\b/i;
export const STAGING_API = /https:\/\/api\.staging\.vergeo5\.com\b/i;
export const PLANE_MARKER = /vergeo5-deployment-plane=([a-z]+|unset)/;

const SKIP_DIRS = new Set(["cache", "types", "node_modules"]);
const ROOT = join(fileURLToPath(new URL(".", import.meta.url)), "../..");

export function normalizePlane(value) {
  return (value ?? "").trim().toLowerCase();
}

export function parseCliArgs(argv, env = process.env) {
  /** @type {{
   *   requireAffected: boolean,
   *   requireApps: string[] | null,
   *   filter: string | null,
   *   root: string,
   *   expectedPlane: string | null,
   * }} */
  const args = {
    requireAffected: false,
    requireApps: null,
    filter: null,
    root: ROOT,
    expectedPlane: null,
  };
  for (const arg of argv) {
    if (arg === "--require-affected") {
      args.requireAffected = true;
    } else if (arg.startsWith("--require-apps=")) {
      args.requireApps = arg
        .slice("--require-apps=".length)
        .split(",")
        .map((name) => name.trim())
        .filter(Boolean);
    } else if (arg.startsWith("--filter=")) {
      args.filter = arg.slice("--filter=".length);
    } else if (arg.startsWith("--root=")) {
      args.root = arg.slice("--root=".length);
    } else if (arg.startsWith("--expected-plane=")) {
      args.expectedPlane = arg.slice("--expected-plane=".length).trim().toLowerCase();
    }
  }
  if (env.REQUIRE_FRONTEND_BUILD === "1" && args.requireApps === null && !args.requireAffected) {
    args.requireApps = [...FRONTEND_APPS];
  }
  return args;
}

export function frontendAppsFromTurboDryRun(jsonText) {
  const start = jsonText.indexOf("{");
  const parsed = JSON.parse(start >= 0 ? jsonText.slice(start) : jsonText);
  const tasks = Array.isArray(parsed.tasks) ? parsed.tasks : [];
  const names = new Set();
  for (const task of tasks) {
    const pkg = String(task.package ?? task.packageName ?? "");
    const taskId = String(task.taskId ?? "");
    for (const app of FRONTEND_APPS) {
      if (pkg === app || taskId.startsWith(`${app}#`)) {
        names.add(app);
      }
    }
  }
  return [...names];
}

export function resolveRequiredApps(args, { turboDryRunJson } = {}) {
  if (Array.isArray(args.requireApps)) {
    return args.requireApps.filter((app) => FRONTEND_APPS.includes(app));
  }
  if (args.requireAffected) {
    if (typeof turboDryRunJson === "string") {
      return frontendAppsFromTurboDryRun(turboDryRunJson);
    }
    return null;
  }
  return [...FRONTEND_APPS];
}

export function planeApiMismatch(env = {}) {
  const plane = normalizePlane(env.NEXT_PUBLIC_DEPLOYMENT_PLANE);
  const configured = (env.NEXT_PUBLIC_API_BASE_URL || env.NEXT_PUBLIC_VERGEO_API_URL || "")
    .trim()
    .replace(/\/$/, "");
  if (!configured) {
    return null;
  }
  if ((plane === "preview" || plane === "staging") && PRODUCTION_API.test(configured)) {
    return "staging_or_preview_targets_production_api";
  }
  if (plane === "production" && STAGING_API.test(configured)) {
    return "production_targets_staging_api";
  }
  if (plane && plane !== "development" && LOOPBACK_API.test(configured)) {
    return "deployed_plane_targets_loopback";
  }
  return null;
}

export function inspectBundleSource(source, { expectedPlane, envPlane, loopbackOnly } = {}) {
  /** @type {{ kind: string, match: string }[]} */
  const hits = [];
  const loopback = source.match(LOOPBACK_API);
  if (loopback) {
    hits.push({ kind: "loopback", match: loopback[0] });
  }
  if (loopbackOnly) {
    return hits;
  }
  const marker = source.match(PLANE_MARKER);
  const plane = expectedPlane || marker?.[1] || envPlane || "";
  if ((plane === "preview" || plane === "staging") && PRODUCTION_API.test(source)) {
    hits.push({ kind: "preview_or_staging_targets_production", match: "https://api.vergeo5.com" });
  }
  if (plane === "production" && STAGING_API.test(source)) {
    hits.push({
      kind: "production_targets_staging",
      match: "https://api.staging.vergeo5.com",
    });
  }
  return hits;
}

export function collectJsFiles(dir) {
  if (!existsSync(dir)) {
    return [];
  }
  /** @type {string[]} */
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!SKIP_DIRS.has(entry.name)) {
        out.push(...collectJsFiles(full));
      }
    } else if (entry.name.endsWith(".js")) {
      out.push(full);
    }
  }
  return out;
}

export function inspectApp(root, app, { required, expectedPlane, envPlane } = {}) {
  const nextDir = join(root, "apps", app, ".next");
  if (!existsSync(nextDir)) {
    return {
      app,
      missing: true,
      ok: required === false,
      hits: [],
      reason: required === false ? "not_required" : "missing_build",
    };
  }

  const files = [
    ...collectJsFiles(join(nextDir, "static")),
    ...collectJsFiles(join(nextDir, "server", "chunks")),
    ...collectJsFiles(join(nextDir, "server", "app")),
  ];
  const middleware = join(nextDir, "server", "middleware.js");
  /** @type {{ file: string, kind: string, match: string }[]} */
  const hits = [];
  for (const file of files) {
    const source = readFileSync(file, "utf8");
    for (const hit of inspectBundleSource(source, { expectedPlane, envPlane })) {
      hits.push({ file: relative(root, file), ...hit });
    }
  }
  // Middleware CSP allowlists both API hosts; scan it for loopback only.
  if (existsSync(middleware)) {
    const source = readFileSync(middleware, "utf8");
    for (const hit of inspectBundleSource(source, { loopbackOnly: true })) {
      hits.push({ file: relative(root, middleware), ...hit });
    }
  }
  return {
    app,
    missing: false,
    ok: hits.length === 0,
    hits,
    reason: hits.length === 0 ? "ok" : "bundle_violation",
  };
}

function runTurboDryRun(root, filter) {
  const output = execFileSync(
    "pnpm",
    ["exec", "turbo", "run", "build", "--dry-run=json", `--filter=${filter}`],
    { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
  );
  return output;
}

export function evaluateGuard({ root = ROOT, requiredApps, env = {}, expectedPlane = null } = {}) {
  /** @type {string[]} */
  const failures = [];
  /** @type {string[]} */
  const messages = [];
  const envMismatch = planeApiMismatch(env);
  if (envMismatch) {
    failures.push(envMismatch);
    messages.push(`FAIL: deployment-plane env mismatch (${envMismatch})`);
  }

  const required = new Set(requiredApps ?? FRONTEND_APPS);
  if (required.size === 0) {
    messages.push("OK: no customer/vendor/admin apps in the affected turbo graph");
    return { ok: failures.length === 0, failures, messages, results: [] };
  }

  const envPlane = normalizePlane(env.NEXT_PUBLIC_DEPLOYMENT_PLANE);
  /** @type {ReturnType<typeof inspectApp>[]} */
  const results = [];
  for (const app of FRONTEND_APPS) {
    if (!required.has(app)) {
      continue;
    }
    const result = inspectApp(root, app, {
      required: true,
      expectedPlane,
      envPlane,
    });
    results.push(result);
    if (result.missing) {
      failures.push(`missing_build:${app}`);
      messages.push(`FAIL: apps/${app}/.next is missing (affected frontend must be built)`);
    } else if (!result.ok) {
      failures.push(`bundle:${app}`);
      messages.push(`FAIL: apps/${app} bundle contains a forbidden API origin:`);
      for (const hit of result.hits.slice(0, 20)) {
        messages.push(`  ${hit.file}: ${hit.kind} ${hit.match}`);
      }
    } else {
      messages.push(`OK: apps/${app} bundle matches the API-plane contract`);
    }
  }

  return { ok: failures.length === 0, failures, messages, results };
}

function main() {
  const args = parseCliArgs(process.argv.slice(2));
  let requiredApps = resolveRequiredApps(args);
  if (requiredApps === null) {
    const filter = args.filter;
    if (!filter) {
      console.error("FAIL: --require-affected needs --filter='...[baseSha]'");
      process.exit(1);
    }
    try {
      const dryRun = runTurboDryRun(args.root, filter);
      requiredApps = frontendAppsFromTurboDryRun(dryRun);
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      console.error(`FAIL: turbo dry-run for affected frontends failed: ${detail}`);
      process.exit(1);
    }
  }

  const result = evaluateGuard({
    root: args.root,
    requiredApps,
    env: process.env,
    expectedPlane: args.expectedPlane,
  });
  for (const line of result.messages) {
    if (line.startsWith("FAIL:")) {
      console.error(line);
    } else {
      console.log(line);
    }
  }
  if (!result.ok) {
    process.exit(1);
  }
}

const invokedDirectly = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (invokedDirectly) {
  main();
}
