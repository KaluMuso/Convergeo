#!/usr/bin/env node
/* global structuredClone */
/** Filesystem-only Lighthouse adapter; policy stays in lighthouserc.json.
 * Collection derives from #723 at 8e2e84d6; assertion semantics/security guards
 * derive from #746 at 843d10c3. No browser download or installation is performed.
 */
import { execFile } from "node:child_process";
import console from "node:console";
import { createHash } from "node:crypto";
import { constants } from "node:fs";
import { access, lstat, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { isAbsolute, join, resolve } from "node:path";
import process from "node:process";
import { URL, pathToFileURL } from "node:url";
import { promisify } from "node:util";

const execute = promisify(execFile);
const sha = (value) => (typeof value === "string" && /^[0-9a-f]{40}$/.test(value) ? value : null);

export async function sourceIdentity(cwd, env = process.env) {
  let checkoutSha = null,
    checkoutTree = null,
    candidateSha = null;
  try {
    const { stdout } = await execute("git", ["rev-parse", "HEAD", "HEAD^{tree}"], {
      cwd,
      timeout: 5000,
      maxBuffer: 4096,
    });
    [checkoutSha, checkoutTree] = stdout.trim().split("\n").map(sha);
  } catch {
    // Local contract fixtures are intentionally outside Git; identity stays unknown.
  }
  if (env.GITHUB_EVENT_PATH) {
    try {
      const event = JSON.parse(await readFile(env.GITHUB_EVENT_PATH, "utf8"));
      if (env.GITHUB_EVENT_NAME === "pull_request")
        candidateSha = sha(event.pull_request?.head?.sha);
      else if (env.GITHUB_EVENT_NAME === "push" && sha(event.after) === sha(env.GITHUB_SHA))
        candidateSha = sha(event.after);
    } catch {
      // Never serialize the event, environment, or parsing error.
    }
  } else if (env.GITHUB_ACTIONS !== "true") {
    candidateSha = checkoutSha;
  }
  const number = (value) => (/^[1-9][0-9]{0,19}$/.test(value ?? "") ? value : null);
  const identity = {
    checkout_sha: checkoutSha,
    checkout_tree: checkoutTree,
    candidate_sha: candidateSha,
    run_id: number(env.GITHUB_RUN_ID),
    run_attempt: number(env.GITHUB_RUN_ATTEMPT),
  };
  if (
    env.GITHUB_ACTIONS === "true" &&
    (!checkoutSha ||
      !checkoutTree ||
      !candidateSha ||
      !identity.run_id ||
      !identity.run_attempt ||
      checkoutSha !== sha(env.GITHUB_SHA))
  )
    throw new Error("Hosted source identity is missing or inconsistent");
  return identity;
}

export const INCOMPLETE_LOAD_WARNING =
  "The page loaded too slowly to finish within the time limit. Results may be incomplete.";
export const incompleteLoadWarning = (lhr) =>
  (lhr.runWarnings ?? []).some(
    (warning) =>
      typeof warning === "string" &&
      warning.replace(/\s+/g, " ").trim() === INCOMPLETE_LOAD_WARNING,
  );
const finite = (n) => typeof n === "number" && Number.isFinite(n);
function validateRequiredMeasurements(lhr) {
  if (
    !finite(lhr.categories?.performance?.score) ||
    !finite(lhr.audits?.["largest-contentful-paint"]?.numericValue)
  )
    throw new Error(`Incomplete required performance/LCP measurements: ${lhr.requestedUrl}`);
}
const median = (values) => {
  const sorted = [...values].sort((a, b) => a - b),
    middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};
const canonicalUrl = (value) => {
  const url = new URL(value);
  url.pathname = url.pathname.replace(/\/$/, "") || "/";
  return url.href;
};
const securityBypass = (flag) =>
  /^--(?:no-sandbox|disable-(?:setuid|namespace|seccomp-filter|gpu)-sandbox|disable-web-security|ignore-certificate-errors(?:-spki-list)?|allow-insecure-localhost)(?:=|$)/.test(
    flag,
  );

export function validatePolicy(config) {
  const { collect, assert, upload } = config.ci ?? {};
  if (!collect || !Number.isInteger(collect.numberOfRuns) || collect.numberOfRuns < 3)
    throw new Error("At least three integer runs are required");
  if (
    !Array.isArray(collect.url) ||
    collect.url.length !== 5 ||
    new Set(collect.url).size !== collect.url.length
  )
    throw new Error("Unique collect URLs are required");
  for (const url of collect.url) {
    const parsed = new URL(url);
    if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password)
      throw new Error("Invalid collect URL");
  }
  if (
    Object.keys(collect.settings ?? {}).some(
      (key) =>
        ![
          "formFactor",
          "screenEmulation",
          "throttling",
          "throttlingMethod",
          "onlyCategories",
        ].includes(key),
    )
  )
    throw new Error("Unsupported Lighthouse setting; review adapter forwarding before use");
  if (Object.keys(collect).some((key) => !["url", "numberOfRuns", "settings"].includes(key)))
    throw new Error("Unsupported collect option; implement and test it before use");
  if (
    !assert ||
    Object.keys(assert).some((key) => key !== "assertMatrix") ||
    !assert.assertMatrix?.length
  )
    throw new Error("Only explicit assertMatrix policy is supported");
  for (const row of assert.assertMatrix) {
    if (Object.keys(row).some((key) => !["matchingUrlPattern", "assertions"].includes(key)))
      throw new Error("Unsupported assertion row option");
    new RegExp(row.matchingUrlPattern);
    if (!row.matchingUrlPattern || !Object.keys(row.assertions ?? {}).length)
      throw new Error("Assertion row must have a pattern and assertions");
    if (Object.keys(row.assertions).length !== 5)
      throw new Error("Every policy row must retain all five assertions");
    for (const [id, spec] of Object.entries(row.assertions)) {
      if (
        ![
          "categories:performance",
          "categories:accessibility",
          "categories:best-practices",
          "categories:seo",
          "largest-contentful-paint",
        ].includes(id)
      )
        throw new Error(`Unsupported metric: ${id}`);
      if (!Array.isArray(spec) || spec.length !== 2 || !["error", "warn"].includes(spec[0]))
        throw new Error(`Unsupported assertion: ${id}`);
      if (
        spec[0] === "warn" &&
        (id !== "categories:seo" || !/checkout/.test(row.matchingUrlPattern))
      )
        throw new Error("Only checkout SEO may be warning-only");
      const options = spec[1];
      if (
        !options ||
        Object.keys(options).some(
          (key) => !["minScore", "maxNumericValue", "aggregationMethod"].includes(key),
        )
      )
        throw new Error(`Unsupported assertion options: ${id}`);
      if (
        !["optimistic", "pessimistic", "median"].includes(options.aggregationMethod ?? "optimistic")
      )
        throw new Error(`Unsupported aggregation: ${id}`);
      if (!Object.keys(options).some((key) => ["minScore", "maxNumericValue"].includes(key)))
        throw new Error(`Explicit assertion threshold required: ${id}`);
      if (
        (id.startsWith("categories:") &&
          ("maxNumericValue" in options || !("minScore" in options))) ||
        (id === "largest-contentful-paint" &&
          ("minScore" in options || !("maxNumericValue" in options)))
      )
        throw new Error(`Unsupported threshold kind: ${id}`);
      if (
        ["categories:performance", "largest-contentful-paint"].includes(id) &&
        options.aggregationMethod !== "median"
      )
        throw new Error("Performance and LCP require median aggregation");
      for (const key of ["minScore", "maxNumericValue"])
        if (key in options && !finite(options[key])) throw new Error(`Invalid threshold: ${id}`);
      if (id.includes(":") && (!/^categories:[a-z-]+$/.test(id) || "maxNumericValue" in options))
        throw new Error(`Unsupported category assertion: ${id}`);
    }
  }
  for (const url of collect.url)
    if (
      assert.assertMatrix.filter((row) => new RegExp(row.matchingUrlPattern).test(url)).length !== 1
    )
      throw new Error(`No assertions match ${url}`);
  if (
    upload?.target !== "filesystem" ||
    upload.outputDir !== ".lighthouseci" ||
    Object.keys(upload).some((key) => !["target", "outputDir"].includes(key))
  )
    throw new Error("Only filesystem report output is supported");
}

/** LHCI assertion semantics, with complete required performance/LCP samples. */
export function evaluateAssertions(config, reports) {
  validatePolicy(config);
  const results = [];
  for (const requestedUrl of config.ci.collect.url) {
    const runs = reports.filter((lhr) => lhr.requestedUrl === requestedUrl);
    if (
      runs.length !== config.ci.collect.numberOfRuns ||
      runs.some((lhr) => lhr.runtimeError || incompleteLoadWarning(lhr))
    )
      throw new Error(`Incomplete or failed collection for ${requestedUrl}`);
    runs.forEach(validateRequiredMeasurements);
    const finalUrls = new Set(runs.map((lhr) => lhr.finalUrl));
    if (finalUrls.size !== 1 || !runs[0].finalUrl)
      throw new Error(`Inconsistent final URL: ${requestedUrl}`);
    const url = runs[0].finalUrl;
    if (canonicalUrl(url) !== canonicalUrl(requestedUrl))
      throw new Error(`Wrong final URL: ${requestedUrl}`);
    const rows = config.ci.assert.assertMatrix.filter((row) =>
      new RegExp(row.matchingUrlPattern).test(url),
    );
    if (!rows.length) throw new Error(`No assertions match final URL ${url}`);
    for (const row of rows) {
      for (const [id, [level, options]] of Object.entries(row.assertions)) {
        const [auditId, category] = id.split(":");
        const audits = runs.map((lhr) =>
          category ? lhr.categories?.[category] : lhr.audits?.[auditId],
        );
        const base = {
          auditId,
          ...(category ? { auditProperty: category } : {}),
          level,
          url,
        };
        if (audits.some((audit) => !audit)) {
          results.push({
            ...base,
            name: "auditRan",
            expected: 1,
            actual: 0,
            values: audits.map((audit) => (audit ? 1 : 0)),
            operator: ">=",
            passed: false,
          });
          continue;
        }
        for (const name of ["minScore", "maxNumericValue"]) {
          if (!(name in options)) continue;
          const values = audits.map((audit) =>
            name === "maxNumericValue"
              ? audit.numericValue
              : typeof audit.score === "number"
                ? audit.score
                : !category && audit.scoreDisplayMode === "notApplicable"
                  ? 1
                  : !category && audit.scoreDisplayMode === "informative"
                    ? 0
                    : undefined,
          );
          const valid = values.filter(finite);
          const aggregation = options.aggregationMethod ?? "optimistic";
          const min = name === "minScore";
          let actual = NaN;
          if (valid.length && (aggregation !== "pessimistic" || valid.length === values.length)) {
            actual =
              aggregation === "median"
                ? median(valid)
                : (aggregation === "optimistic" ? min : !min)
                  ? Math.max(...valid)
                  : Math.min(...valid);
          }
          const expected = options[name];
          results.push({
            ...base,
            name,
            expected,
            actual,
            values:
              valid.length && finite(actual)
                ? valid
                : values.map((value) => (finite(value) ? value : NaN)),
            operator: min ? ">=" : "<=",
            passed: finite(actual) && (min ? actual >= expected : actual <= expected),
          });
        }
      }
    }
  }
  if (reports.length !== config.ci.collect.url.length * config.ci.collect.numberOfRuns)
    throw new Error("Unexpected reports outside configured collection");
  return results;
}

// Same representative-report selection as LHCI: closest to median FCP and TTI.
// This is independent of the per-metric median assertions above.
export function representativeRun(runs) {
  const value = (run, name) => run.audits?.[name]?.numericValue || 0;
  const middle = (name) =>
    [...runs].map((r) => value(r, name)).sort((a, b) => a - b)[Math.floor(runs.length / 2)];
  const fcp = middle("first-contentful-paint"),
    tti = middle("interactive");
  const distance = (r) =>
    (fcp - value(r, "first-contentful-paint")) ** 2 + (tti - value(r, "interactive")) ** 2;
  return [...runs].sort((a, b) => distance(a) - distance(b))[0];
}

/** Injectable modules are for offline tests; CLI uses the real engine/launcher. */
export async function auditWithChrome(url, settings, dependencies) {
  const chromePath = dependencies?.chromePath ?? process.env.CHROME_PATH;
  if (!chromePath || !isAbsolute(chromePath))
    throw new Error("CHROME_PATH must name an explicit existing Chrome executable");
  await access(chromePath, constants.X_OK);
  const [{ default: lighthouse }, launcher] =
    dependencies?.modules ?? (await Promise.all([import("lighthouse"), import("chrome-launcher")]));
  const profile = await mkdtemp(join(tmpdir(), "vergeo-lighthouse-"));
  let chrome, result, failure;
  const cleanupErrors = [];
  try {
    const chromeFlags = [...launcher.Launcher.defaultFlags(), "--headless=new"];
    if (chromeFlags.some(securityBypass)) throw new Error("Unsafe Chrome flag");
    // The convenience launch() adds an implicit Linux sandbox bypass. Use the
    // reviewed constructor path and inspect the actual effective flags instead.
    chrome = new launcher.Launcher({
      chromePath,
      chromeFlags,
      ignoreDefaultFlags: true,
      userDataDir: profile,
    });
    if (!Array.isArray(chrome.flags) || chrome.flags.some(securityBypass))
      throw new Error("Unsafe effective Chrome flag");
    await chrome.launch();
    result = await lighthouse(url, {
      ...settings,
      port: chrome.port,
      output: ["json", "html"],
      logLevel: "error",
    });
  } catch (error) {
    failure = error;
  } finally {
    try {
      await chrome?.kill();
    } catch (error) {
      cleanupErrors.push(error);
    }
    try {
      await rm(profile, { recursive: true, force: true });
    } catch (error) {
      cleanupErrors.push(error);
    }
  }
  if (failure || cleanupErrors.length) {
    const error = new AggregateError(
      [failure, ...cleanupErrors].filter(Boolean),
      [failure?.message, ...cleanupErrors.map((item) => item.message)].filter(Boolean).join("; "),
    );
    error.result = result;
    throw error;
  }
  return result;
}

/** No collection retry: an invalid/incomplete sample remains a blocking failure. */
export async function runPerformance(
  config,
  { audit = auditWithChrome, cwd = process.cwd() } = {},
) {
  const output = resolve(cwd, ".lighthouseci");
  await mkdir(output, { recursive: true });
  if ((await lstat(output)).isSymbolicLink()) throw new Error("Report directory is a symlink");
  const reports = [],
    manifest = [],
    errors = [];
  let assertions = [],
    source = null;
  const invocation = Date.now();
  await writeFile(join(output, "manifest.json"), "[]\n");
  await writeFile(join(output, "assertion-results.json"), "[]\n");
  try {
    source = await sourceIdentity(cwd);
    validatePolicy(config);
    for (const [index, url] of config.ci.collect.url.entries()) {
      for (let run = 0; run < config.ci.collect.numberOfRuns; run++) {
        let result, auditFailure;
        try {
          result = await audit(url, structuredClone(config.ci.collect.settings ?? {}));
        } catch (error) {
          result = error.result;
          auditFailure = error;
        }
        const lhr = result?.lhr;
        const html = Array.isArray(result?.report) ? result.report[1] : result?.report;
        const stem = `lhr-${invocation}-${index + 1}-${run + 1}`;
        const jsonPath = join(output, `${stem}.json`),
          htmlPath = join(output, `${stem}.html`);
        if (lhr) await writeFile(jsonPath, JSON.stringify(lhr, null, 2) + "\n");
        if (typeof html === "string") await writeFile(htmlPath, html);
        const entry = {
          url,
          run: run + 1,
          jsonPath: lhr ? jsonPath : null,
          htmlPath: typeof html === "string" ? htmlPath : null,
          isRepresentativeRun: false,
          validCollection: false,
        };
        manifest.push(entry);
        // Persist even the failing sample before checking its contents.
        await writeFile(join(output, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
        if (auditFailure) throw auditFailure;
        if (
          !lhr ||
          lhr.requestedUrl !== url ||
          !lhr.finalUrl ||
          canonicalUrl(lhr.finalUrl) !== canonicalUrl(url) ||
          lhr.runtimeError
        )
          throw new Error(`Invalid collection or final URL: ${url}`);
        if (incompleteLoadWarning(lhr)) throw new Error(`Incomplete load: ${url}`);
        if (typeof html !== "string" || !html.trim())
          throw new Error(`Missing HTML report: ${url}`);
        if (lhr.lighthouseVersion !== "13.5.0") throw new Error("Unexpected Lighthouse version");
        validateRequiredMeasurements(lhr);
        reports.push(lhr);
        entry.validCollection = true;
      }
    }
    assertions = evaluateAssertions(config, reports);
  } catch (error) {
    errors.push({ message: error.message });
  }
  for (const url of config?.ci?.collect?.url ?? []) {
    const representative = representativeRun(reports.filter((lhr) => lhr.requestedUrl === url));
    if (representative) {
      const entries = manifest.filter((entry) => entry.url === url && entry.validCollection);
      const runs = reports.filter((lhr) => lhr.requestedUrl === url);
      entries[runs.indexOf(representative)].isRepresentativeRun = true;
    }
  }
  const exitCode =
    errors.length || assertions.some((row) => !row.passed && row.level === "error") ? 1 : 0;
  await writeFile(join(output, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
  await writeFile(
    join(output, "assertion-results.json"),
    JSON.stringify(
      assertions.filter((row) => !row.passed),
      null,
      2,
    ) + "\n",
  );
  await writeFile(
    join(output, "assertion-results-all.json"),
    JSON.stringify(assertions, null, 2) + "\n",
  );
  await writeFile(
    join(output, "run-summary.json"),
    JSON.stringify(
      {
        exitCode,
        errors,
        source_identity: source,
        expectedReports:
          (config?.ci?.collect?.url?.length ?? 0) * (config?.ci?.collect?.numberOfRuns ?? 0),
        collectedReports: reports.length,
        nodeVersion: process.version,
        lighthouseVersions: [...new Set(reports.map((lhr) => lhr.lighthouseVersion))],
        configSha256: createHash("sha256").update(JSON.stringify(config)).digest("hex"),
        urls: config?.ci?.collect?.url,
        settings: config?.ci?.collect?.settings,
      },
      null,
      2,
    ) + "\n",
  );
  return { exitCode, assertions, errors, manifest };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const args = process.argv.slice(2);
    if (args.length > 1 || (args.length && !args[0].startsWith("--config=")))
      throw new Error("Usage: lighthouse-budget.mjs [--config=lighthouserc.json]");
    const config = JSON.parse(await readFile(args[0]?.slice(9) ?? "lighthouserc.json", "utf8"));
    process.exitCode = (await runPerformance(config)).exitCode;
  } catch (error) {
    console.error(error.message);
    process.exitCode = 2;
  }
}
