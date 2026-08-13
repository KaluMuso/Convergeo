#!/usr/bin/env node
/**
 * Release guard: production-like frontend bundles must never ship a loopback
 * API origin, and Vercel Preview must never target the production API.
 *
 * Scans built Next.js client chunks for:
 *   - http://localhost:8000
 *   - http://127.0.0.1:8000
 *   - http://[::1]:8000
 * and, when VERCEL_ENV=preview, for https://api.vergeo5.com.
 *
 * Exit 1 on any hit. Missing .next directories are skipped unless
 * REQUIRE_FRONTEND_BUILD=1.
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(fileURLToPath(new URL(".", import.meta.url)), "../..");
const APPS = ["customer", "vendor", "admin"];
const LOOPBACK_API = /https?:\/\/(?:localhost|127\.0\.0\.1|\[::1\]):8000\b/i;
const PRODUCTION_API = /https:\/\/api\.vergeo5\.com\b/i;
const SKIP_DIRS = new Set(["cache", "types", "node_modules"]);

function collectJsFiles(dir) {
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

function scanApp(app) {
  const nextDir = join(ROOT, "apps", app, ".next");
  if (!existsSync(nextDir)) {
    return { skipped: true, hits: [] };
  }

  const files = [
    ...collectJsFiles(join(nextDir, "static")),
    ...collectJsFiles(join(nextDir, "server", "chunks")),
    ...collectJsFiles(join(nextDir, "server", "app")),
  ];
  /** @type {{ file: string, match: string }[]} */
  const hits = [];
  for (const file of files) {
    const source = readFileSync(file, "utf8");
    const loopback = source.match(LOOPBACK_API);
    if (loopback) {
      hits.push({ file: relative(ROOT, file), match: loopback[0] });
    }
  }
  return { skipped: false, hits };
}

export function previewTargetsProductionApi(env = process.env) {
  if (env.VERCEL_ENV !== "preview") {
    return false;
  }
  const configured = (env.NEXT_PUBLIC_API_BASE_URL || env.NEXT_PUBLIC_VERGEO_API_URL || "")
    .trim()
    .replace(/\/$/, "");
  return PRODUCTION_API.test(configured);
}

function main() {
  const requireBuild = process.env.REQUIRE_FRONTEND_BUILD === "1";
  let failures = 0;
  let scanned = 0;

  if (previewTargetsProductionApi()) {
    console.error(
      "FAIL: Vercel Preview is configured with the production API host api.vergeo5.com",
    );
    failures += 1;
  }

  for (const app of APPS) {
    const result = scanApp(app);
    if (result.skipped) {
      if (requireBuild) {
        console.error(`FAIL: apps/${app}/.next is missing (REQUIRE_FRONTEND_BUILD=1)`);
        failures += 1;
      } else {
        console.log(`SKIP: apps/${app}/.next not present`);
      }
      continue;
    }
    scanned += 1;
    if (result.hits.length > 0) {
      console.error(`FAIL: apps/${app} client/server bundle contains a loopback API origin:`);
      for (const hit of result.hits.slice(0, 20)) {
        console.error(`  ${hit.file}: ${hit.match}`);
      }
      failures += 1;
    } else {
      console.log(`OK: apps/${app} has no loopback API origin in the built bundle`);
    }
  }

  if (scanned === 0 && !requireBuild) {
    console.log("OK: no frontend builds present to scan");
  }

  if (failures > 0) {
    process.exit(1);
  }
}

const invokedDirectly = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (invokedDirectly) {
  main();
}
