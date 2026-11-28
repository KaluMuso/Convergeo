#!/usr/bin/env node
/**
 * Per-route first-load JS + CSS budget guard for apps/customer.
 * Parses .next/app-build-manifest.json, sums gzip sizes of route chunks,
 * compares against budgets (lighthouserc.json → vergeo.bundle) and optional base snapshot.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "../..");
const CUSTOMER_DIR = join(ROOT, "apps/customer");
const MANIFEST_PATH = join(CUSTOMER_DIR, ".next/app-build-manifest.json");
const LIGHTHOUSE_RC = join(ROOT, "lighthouserc.json");
// 2.0 KB absorbs the one-time serwist PWA service-worker registration cost
// (M16-P02) that lifts the shared runtime chunk ~1.6 KB gz across every route.
// After M16-P02 merges, master is the new baseline, so this tolerance still
// catches genuine per-PR regressions (>2 KB) going forward.
const REGRESSION_TOLERANCE_KB = 2.0;
const CSS_REGRESSION_TOLERANCE_KB = 1.0;

/** @typedef {{ defaultMaxKbGz: number, defaultJustification: string, defaultMaxCssKbGz: number, defaultMaxCssJustification: string, routes: Record<string, { maxKbGz?: number, maxCssKbGz?: number, justification: string }>, auditRoutes?: string[] }} BundleBudgetConfig */

/**
 * @returns {BundleBudgetConfig}
 */
export function loadBudgetConfig() {
  const raw = JSON.parse(readFileSync(LIGHTHOUSE_RC, "utf8"));
  const bundle = raw.vergeo?.bundle;
  if (!bundle?.defaultMaxKbGz || !bundle.defaultJustification) {
    throw new Error(
      "lighthouserc.json missing vergeo.bundle.defaultMaxKbGz or defaultJustification",
    );
  }
  if (!bundle.defaultMaxCssKbGz || !bundle.defaultMaxCssJustification) {
    throw new Error(
      "lighthouserc.json missing vergeo.bundle.defaultMaxCssKbGz or defaultMaxCssJustification",
    );
  }
  return bundle;
}

/**
 * @param {BundleBudgetConfig} config
 * @returns {Set<string>}
 */
export function auditRouteSet(config) {
  const routes = config.auditRoutes;
  if (!Array.isArray(routes) || routes.length === 0) {
    return new Set();
  }
  return new Set(routes);
}

/**
 * @param {string} pageRoute
 * @param {Record<string, string[]>} pages
 */
export function layoutChainForPage(pageRoute, pages) {
  const base = pageRoute.replace(/\/page$/, "");
  const segments = base.split("/").filter(Boolean);
  /** @type {string[]} */
  const layouts = [];
  for (let i = 1; i <= segments.length; i += 1) {
    const candidate = `/${segments.slice(0, i).join("/")}/layout`;
    if (pages[candidate]) {
      layouts.push(candidate);
    }
  }
  return layouts;
}

/**
 * @param {string} pageRoute
 * @param {Record<string, string[]>} pages
 */
export function chunksForPageRoute(pageRoute, pages) {
  const chunks = [];
  for (const layout of layoutChainForPage(pageRoute, pages)) {
    chunks.push(...(pages[layout] ?? []));
  }
  chunks.push(...(pages[pageRoute] ?? []));
  return chunks;
}

/**
 * @param {string[]} chunks
 * @param {string} nextDir
 * @param {string} suffix
 */
export function gzipKbForChunks(chunks, nextDir, suffix) {
  const seen = new Set();
  let bytes = 0;
  for (const chunk of chunks) {
    if (!chunk.endsWith(suffix) || seen.has(chunk)) {
      continue;
    }
    seen.add(chunk);
    const filePath = join(nextDir, chunk);
    if (!existsSync(filePath)) {
      continue;
    }
    bytes += gzipSync(readFileSync(filePath)).length;
  }
  return bytes / 1024;
}

/**
 * @param {string[]} chunks
 * @param {string} nextDir
 */
export function gzipJsKbForChunks(chunks, nextDir) {
  return gzipKbForChunks(chunks, nextDir, ".js");
}

/**
 * @param {string[]} chunks
 * @param {string} nextDir
 */
export function gzipCssKbForChunks(chunks, nextDir) {
  return gzipKbForChunks(chunks, nextDir, ".css");
}

/**
 * @param {string} manifestPath
 * @param {string} [nextDir]
 * @returns {Record<string, number>}
 */
export function collectRouteSizes(
  manifestPath = MANIFEST_PATH,
  nextDir = join(CUSTOMER_DIR, ".next"),
) {
  if (!existsSync(manifestPath)) {
    throw new Error(
      `Missing Next.js build output: ${manifestPath} (run pnpm --filter customer build first)`,
    );
  }
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  const pages = manifest.pages ?? {};
  /** @type {Record<string, number>} */
  const sizes = {};
  for (const [route, chunks] of Object.entries(pages)) {
    if (!route.endsWith("/page")) {
      continue;
    }
    sizes[route] = roundKb(gzipJsKbForChunks(chunks, nextDir));
  }
  return sizes;
}

/**
 * @param {string} manifestPath
 * @param {string} [nextDir]
 * @returns {Record<string, number>}
 */
export function collectRouteCssSizes(
  manifestPath = MANIFEST_PATH,
  nextDir = join(CUSTOMER_DIR, ".next"),
) {
  if (!existsSync(manifestPath)) {
    throw new Error(
      `Missing Next.js build output: ${manifestPath} (run pnpm --filter customer build first)`,
    );
  }
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  const pages = manifest.pages ?? {};
  /** @type {Record<string, number>} */
  const sizes = {};
  for (const route of Object.keys(pages)) {
    if (!route.endsWith("/page")) {
      continue;
    }
    const chunks = chunksForPageRoute(route, pages);
    sizes[route] = roundKb(gzipCssKbForChunks(chunks, nextDir));
  }
  return sizes;
}

/** @param {number} kb */
function roundKb(kb) {
  return Math.round(kb * 10) / 10;
}

/**
 * @param {string} route
 */
export function routeToLabel(route) {
  return route
    .replace(/^\/\[locale\]/, "/{locale}")
    .replace(/\(shop\)\//, "")
    .replace(/\(marketing\)\//, "marketing/")
    .replace(/\(auth\)\//, "auth/")
    .replace(/\(dev\)\//, "dev/")
    .replace(/\/page$/, "");
}

/**
 * @param {Record<string, number>} current
 * @param {BundleBudgetConfig} config
 * @param {Record<string, number>} [baseline]
 * @param {{ kind: 'js' | 'css', defaultMaxKbGz: number, regressionToleranceKb: number }} budget
 */
export function evaluateRoutes(current, config, baseline, budget) {
  /** @type {Array<{ route: string, label: string, sizeKb: number, maxKb: number, deltaKb: number | null, reason: string, kind: 'js' | 'css' }>} */
  const violations = [];
  const audited = auditRouteSet(config);
  const kindLabel = budget.kind === "css" ? "CSS" : "JS";

  for (const [route, sizeKb] of Object.entries(current)) {
    const override = config.routes?.[route];
    const maxKb =
      budget.kind === "css"
        ? (override?.maxCssKbGz ?? budget.defaultMaxKbGz)
        : (override?.maxKbGz ?? budget.defaultMaxKbGz);
    const baseKb = baseline?.[route];

    if (sizeKb > maxKb) {
      const deltaKb = baseKb == null ? null : roundKb(sizeKb - baseKb);
      violations.push({
        route,
        label: routeToLabel(route),
        sizeKb,
        maxKb,
        deltaKb,
        kind: budget.kind,
        reason: `${kindLabel} exceeds budget ${maxKb} KB gz (actual ${sizeKb} KB gz${deltaKb != null ? `, +${deltaKb} KB vs base` : ""})`,
      });
      continue;
    }

    const trackRegression = audited.size === 0 || audited.has(route);
    if (trackRegression && baseKb != null && sizeKb > baseKb + budget.regressionToleranceKb) {
      violations.push({
        route,
        label: routeToLabel(route),
        sizeKb,
        maxKb,
        deltaKb: roundKb(sizeKb - baseKb),
        kind: budget.kind,
        reason: `${kindLabel} regression vs base (+${roundKb(sizeKb - baseKb)} KB gz; base ${baseKb} KB gz)`,
      });
    }
  }

  return violations;
}

/**
 * @param {Record<string, number>} sizes
 * @param {string} outPath
 */
export function writeSnapshot(sizes, outPath) {
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, `${JSON.stringify(sizes, null, 2)}\n`, "utf8");
}

/**
 * @param {string} snapshotPath
 * @returns {Record<string, number>}
 */
export function readSnapshot(snapshotPath) {
  return JSON.parse(readFileSync(snapshotPath, "utf8"));
}

function printViolations(violations) {
  console.error("Bundle budget violations:");
  for (const v of violations) {
    const delta =
      v.deltaKb == null
        ? ""
        : v.deltaKb > 0
          ? ` (+${v.deltaKb} KB vs base)`
          : ` (${v.deltaKb} KB vs base)`;
    const kind = v.kind === "css" ? "CSS" : "JS";
    console.error(
      `  • [${kind}] ${v.label}: ${v.sizeKb} KB gz (limit ${v.maxKb} KB gz)${delta} — ${v.reason}`,
    );
  }
}

function usage() {
  console.log(`Usage:
  node scripts/ci/bundle-guard.mjs [--baseline <snapshot.json>] [--write-baseline <snapshot.json>]
  node scripts/ci/bundle-guard.mjs --write-baseline <snapshot.json> --write-baseline-only [--manifest <path>] [--next-dir <path>]
  node scripts/ci/bundle-guard.mjs --self-test`);
}

/**
 * In-memory fixture manifests for pass/fail self-tests.
 */
function runSelfTest() {
  const config = loadBudgetConfig();

  const passSizes = { "/fixture/pass/page": 80 };
  const failSizes = { "/fixture/fail/page": 200 };
  const passViolations = evaluateRoutes(passSizes, config, { "/fixture/pass/page": 80 }, {
    kind: "js",
    defaultMaxKbGz: config.defaultMaxKbGz,
    regressionToleranceKb: REGRESSION_TOLERANCE_KB,
  });
  const failViolations = evaluateRoutes(failSizes, config, { "/fixture/fail/page": 120 }, {
    kind: "js",
    defaultMaxKbGz: config.defaultMaxKbGz,
    regressionToleranceKb: REGRESSION_TOLERANCE_KB,
  });

  const cssPassSizes = { "/fixture/pass/page": 12 };
  const cssFailSizes = { "/fixture/fail/page": 40 };
  const cssPassViolations = evaluateRoutes(cssPassSizes, config, { "/fixture/pass/page": 12 }, {
    kind: "css",
    defaultMaxKbGz: config.defaultMaxCssKbGz,
    regressionToleranceKb: CSS_REGRESSION_TOLERANCE_KB,
  });
  const cssFailViolations = evaluateRoutes(cssFailSizes, config, { "/fixture/fail/page": 20 }, {
    kind: "css",
    defaultMaxKbGz: config.defaultMaxCssKbGz,
    regressionToleranceKb: CSS_REGRESSION_TOLERANCE_KB,
  });

  let failed = false;
  if (passViolations.length !== 0) {
    console.error("SELF-TEST FAIL: expected pass fixture to be clean");
    failed = true;
  } else {
    console.log("SELF-TEST PASS: under-budget route (80 KB gz JS)");
  }

  if (failViolations.length === 0) {
    console.error("SELF-TEST FAIL: expected over-budget fixture to violate");
    failed = true;
  } else {
    const v = failViolations[0];
    console.log(
      `SELF-TEST FAIL (expected): ${v.label} ${v.sizeKb} KB gz exceeds ${v.maxKb} KB gz (+${v.deltaKb} KB vs base)`,
    );
  }

  if (cssPassViolations.length !== 0) {
    console.error("SELF-TEST FAIL: expected CSS pass fixture to be clean");
    failed = true;
  } else {
    console.log(`SELF-TEST PASS: under-budget route (12 KB gz CSS, limit ${config.defaultMaxCssKbGz})`);
  }

  if (cssFailViolations.length === 0) {
    console.error("SELF-TEST FAIL: expected CSS over-budget fixture to violate");
    failed = true;
  } else {
    const v = cssFailViolations[0];
    console.log(
      `SELF-TEST FAIL (expected): [CSS] ${v.label} ${v.sizeKb} KB gz exceeds ${v.maxKb} KB gz (+${v.deltaKb} KB vs base)`,
    );
  }

  process.exit(failed ? 1 : 0);
}

function argValue(args, flag) {
  const idx = args.indexOf(flag);
  return idx >= 0 ? args[idx + 1] : null;
}

function main() {
  const args = process.argv.slice(2);
  if (args.includes("--help") || args.includes("-h")) {
    usage();
    process.exit(0);
  }
  if (args.includes("--self-test")) {
    runSelfTest();
    return;
  }

  const manifestPath = argValue(args, "--manifest") ?? MANIFEST_PATH;
  const nextDir = argValue(args, "--next-dir") ?? join(CUSTOMER_DIR, ".next");
  const baselinePath = argValue(args, "--baseline");
  const writePath = argValue(args, "--write-baseline");
  const writeOnly = args.includes("--write-baseline-only");

  const sizes = collectRouteSizes(manifestPath, nextDir);
  const cssSizes = collectRouteCssSizes(manifestPath, nextDir);
  if (writePath) {
    writeSnapshot(sizes, resolve(writePath));
    console.log(`Wrote bundle snapshot (${Object.keys(sizes).length} routes) → ${writePath}`);
    if (writeOnly) {
      return;
    }
  }

  const config = loadBudgetConfig();
  const baseline = baselinePath && existsSync(baselinePath) ? readSnapshot(baselinePath) : null;
  const violations = [
    ...evaluateRoutes(sizes, config, baseline, {
      kind: "js",
      defaultMaxKbGz: config.defaultMaxKbGz,
      regressionToleranceKb: REGRESSION_TOLERANCE_KB,
    }),
    // CSS snapshots are not baselined in CI yet — ceiling-only until a css snapshot ships.
    ...evaluateRoutes(cssSizes, config, null, {
      kind: "css",
      defaultMaxKbGz: config.defaultMaxCssKbGz,
      regressionToleranceKb: CSS_REGRESSION_TOLERANCE_KB,
    }),
  ];

  if (violations.length > 0) {
    printViolations(violations);
    process.exit(1);
  }

  const routeCount = Object.keys(sizes).length;
  console.log(
    `Bundle guard OK — ${routeCount} routes within JS and CSS budgets (CSS max observed ${Math.max(...Object.values(cssSizes)).toFixed(1)} KB gz).`,
  );
}

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  main();
}