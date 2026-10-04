#!/usr/bin/env node
/** Local filesystem-only performance runner. Policy remains in lighthouserc.json. */
/* global structuredClone */
import { Buffer } from "node:buffer";
import { execFile } from "node:child_process";
import console from "node:console";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, open, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import process from "node:process";
import { URL, pathToFileURL } from "node:url";
import { promisify } from "node:util";

import { inspectMeasuredContent } from "./perf-content-readiness.mjs";

const execute = promisify(execFile);
const sha = (value) => (typeof value === "string" && /^[0-9a-f]{40}$/.test(value) ? value : null);
export const INCOMPLETE_LOAD_WARNING =
  "The page loaded too slowly to finish within the time limit. Results may be incomplete.";

export function incompleteLoadWarning(lhr) {
  return (lhr.runWarnings ?? []).some(
    (warning) =>
      typeof warning === "string" &&
      warning.replace(/\s+/g, " ").trim() === INCOMPLETE_LOAD_WARNING,
  );
}
const securityBypass = (flag) =>
  /^--(?:no-sandbox|disable-(?:setuid|namespace|seccomp-filter|gpu)-sandbox|disable-web-security|ignore-certificate-errors(?:-spki-list)?|allow-insecure-localhost)(?:=|$)/.test(
    flag,
  );

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

export function classifyChromeStderr(stderr) {
  const reasons = [];
  for (const [reason, pattern] of [
    [
      "missing_shared_library",
      /error while loading shared libraries|cannot open shared object file/i,
    ],
    ["sandbox_unavailable", /No usable sandbox|Failed to move to new namespace/i],
    ["user_namespace_policy", /apparmor|user.?namespace.*denied|userns.*denied/i],
    ["root_without_sandbox", /Running as root without/i],
    ["profile_lock", /SingletonLock|ProcessSingleton/],
    ["disk_exhaustion", /No space left on device/i],
    ["devtools_listening", /DevTools listening on ws:/],
  ])
    if (pattern.test(stderr)) reasons.push(reason);
  return reasons.length ? reasons : ["unknown"];
}

async function startupStderr(profile) {
  let file;
  try {
    file = await open(join(profile, "chrome-err.log"), "r");
    const buffer = Buffer.alloc(16384);
    const { bytesRead } = await file.read(buffer, 0, buffer.length, 0);
    return classifyChromeStderr(buffer.toString("utf8", 0, bytesRead));
  } catch {
    return ["unknown"];
  } finally {
    await file?.close().catch(() => {});
  }
}

async function browserVersion(chromePath) {
  try {
    const { stdout } = await execute(chromePath, ["--version"], {
      timeout: 5000,
      maxBuffer: 4096,
    });
    return (
      stdout.match(/(?:Google Chrome(?: for Testing)?|Chromium) ([0-9]+(?:\.[0-9]+){3})/)?.[1] ??
      null
    );
  } catch {
    return null;
  }
}

const finite = (n) => typeof n === "number" && Number.isFinite(n);
const median = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};

export function validatePolicy(config) {
  const { collect, assert, upload } = config.ci ?? {};
  if (!collect || !Number.isInteger(collect.numberOfRuns) || collect.numberOfRuns < 3)
    throw new Error("At least three integer runs are required");
  if (
    !Array.isArray(collect.url) ||
    !collect.url.length ||
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
    for (const [id, spec] of Object.entries(row.assertions)) {
      if (!Array.isArray(spec) || spec.length !== 2 || !["error", "warn"].includes(spec[0]))
        throw new Error(`Unsupported assertion: ${id}`);
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
      for (const key of ["minScore", "maxNumericValue"])
        if (key in options && !finite(options[key])) throw new Error(`Invalid threshold: ${id}`);
      if (id.includes(":") && (!/^categories:[a-z-]+$/.test(id) || "maxNumericValue" in options))
        throw new Error(`Unsupported category assertion: ${id}`);
    }
  }
  for (const url of collect.url)
    if (!assert.assertMatrix.some((row) => new RegExp(row.matchingUrlPattern).test(url)))
      throw new Error(`No assertions match ${url}`);
  if (
    upload?.target !== "filesystem" ||
    !upload.outputDir ||
    Object.keys(upload).some((key) => !["target", "outputDir"].includes(key))
  )
    throw new Error("Only filesystem report output is supported");
}

/** LHCI 0.15.1 semantics for the explicitly supported assertion subset. */
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
    const finalUrls = new Set(runs.map((lhr) => lhr.finalUrl));
    if (finalUrls.size !== 1 || !runs[0].finalUrl)
      throw new Error(`Inconsistent final URL: ${requestedUrl}`);
    const url = runs[0].finalUrl;
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

export async function auditWithChrome(url, settings, dependencies, context = {}) {
  const [{ default: lighthouse }, chromeLauncher, { default: puppeteer }] =
    dependencies ??
    (await Promise.all([import("lighthouse"), import("chrome-launcher"), import("puppeteer")]));
  const profile = await mkdtemp(join(tmpdir(), "vergeo-lighthouse-"));
  const started = Date.now();
  let chrome,
    browser,
    measuredPage,
    result,
    failure,
    version = null,
    unsafeFlags = false,
    stage = "resolve_browser";
  try {
    const chromePath = await puppeteer.executablePath();
    version = await browserVersion(chromePath);
    stage = "validate_flags";
    // Preserve the pinned benchmark defaults without the launcher's implicit
    // Linux --disable-setuid-sandbox. No sandbox or TLS fallback is permitted.
    const chromeFlags = [...chromeLauncher.Launcher.defaultFlags(), "--headless=new"];
    unsafeFlags = chromeFlags.some(securityBypass);
    if (unsafeFlags) throw new Error("Unsafe Chrome flag");
    chrome = new chromeLauncher.Launcher({
      chromePath,
      chromeFlags,
      ignoreDefaultFlags: true,
      userDataDir: profile,
    });
    unsafeFlags = chrome.flags.some(securityBypass);
    if (unsafeFlags) throw new Error("Unsafe effective Chrome flag");
    stage = "launch";
    await chrome.launch();
    if (context.verifyContent) {
      stage = "attach_measurement_page";
      browser = await puppeteer.connect({
        browserURL: `http://127.0.0.1:${chrome.port}`,
        defaultViewport: null,
      });
      measuredPage = await browser.newPage();
    }
    stage = "audit";
    const flags = {
      ...settings,
      port: chrome.port,
      output: "html",
      logLevel: "info",
    };
    // The supported fourth argument keeps ownership of this exact page here;
    // Lighthouse otherwise closes its own page before returning the reports.
    result = measuredPage
      ? await lighthouse(url, flags, undefined, measuredPage)
      : await lighthouse(url, flags);
    if (
      context.verifyContent &&
      result?.lhr &&
      !result.lhr.runtimeError &&
      !incompleteLoadWarning(result.lhr)
    ) {
      stage = "content_readiness";
      result.contentReadiness = await inspectMeasuredContent(url, measuredPage);
    }
    stage = "complete";
  } catch (error) {
    failure =
      stage === "audit" ? error : new Error(`Chrome ${stage} failed; inspect startup diagnostics`);
  } finally {
    const reasons = await startupStderr(profile);
    const chromeProcess = chrome?.chromeProcess;
    const exitCode = Number.isInteger(chromeProcess?.exitCode) ? chromeProcess.exitCode : null;
    const signal = /^SIG[A-Z0-9]{1,12}$/.test(chromeProcess?.signalCode ?? "")
      ? chromeProcess.signalCode
      : null;
    let cleanupFailed = false;
    try {
      await measuredPage?.close();
    } catch {
      cleanupFailed = true;
    }
    try {
      await browser?.disconnect();
    } catch {
      cleanupFailed = true;
    }
    try {
      await chrome?.kill();
    } catch {
      cleanupFailed = true;
    }
    try {
      await rm(profile, { recursive: true, force: true });
    } catch {
      cleanupFailed = true;
    }
    if (cleanupFailed) failure ??= new Error("Chrome cleanup failed");
    if (context.diagnosticsPath) {
      try {
        const identity = context.source ?? {};
        const number = (v) => (/^[1-9][0-9]{0,19}$/.test(v ?? "") ? String(v) : null);
        await writeFile(
          context.diagnosticsPath,
          JSON.stringify(
            {
              schema_version: 1,
              checkout_sha: sha(identity.checkout_sha),
              checkout_tree: sha(identity.checkout_tree),
              candidate_sha: sha(identity.candidate_sha),
              run_id: number(identity.run_id),
              run_attempt: number(identity.run_attempt),
              config_sha256: /^[0-9a-f]{64}$/.test(identity.config_sha256 ?? "")
                ? identity.config_sha256
                : null,
              url_index: Number.isInteger(context.urlIndex) ? context.urlIndex : null,
              run: Number.isInteger(context.run) ? context.run : null,
              stage,
              collection_completed: stage === "complete" && !cleanupFailed,
              cleanup_failed: cleanupFailed,
              elapsed_ms: Date.now() - started,
              browser_version: version,
              exit_code: exitCode,
              signal,
              security_flags_rejected: unsafeFlags,
              stderr_reasons: reasons,
            },
            null,
            2,
          ) + "\n",
          { mode: 0o600 },
        );
      } catch {
        failure ??= new Error("Chrome startup diagnostics could not be saved");
      }
    }
  }
  if (failure) throw failure;
  return result;
}

/** Injectable audit boundary is for offline contract tests; CLI always uses the real engine. */
export async function runPerformance(
  config,
  { audit = auditWithChrome, cwd = process.cwd(), configSha256 = null } = {},
) {
  validatePolicy(config);
  const output = resolve(cwd, config.ci.upload.outputDir);
  await mkdir(output, { recursive: true });
  const source = {
    ...(await sourceIdentity(cwd)),
    config_sha256: /^[0-9a-f]{64}$/.test(configSha256 ?? "") ? configSha256 : null,
  };
  const reports = [],
    manifest = [],
    errors = [],
    warnings = [],
    contentReadiness = [];
  let assertions = [];
  const invocation = Date.now();
  await writeFile(join(output, "manifest.json"), "[]\n");
  await writeFile(join(output, "assertion-results.json"), "[]\n");
  collection: for (const [urlIndex, url] of config.ci.collect.url.entries()) {
    for (let run = 0; run < config.ci.collect.numberOfRuns; run++) {
      try {
        const result = await audit(
          url,
          structuredClone(config.ci.collect.settings ?? {}),
          undefined,
          {
            diagnosticsPath: join(output, `chrome-startup-${urlIndex + 1}-${run + 1}.json`),
            source,
            urlIndex: urlIndex + 1,
            run: run + 1,
            verifyContent: process.env.CI_PERF_HARNESS === "1",
          },
        );
        if (!result?.lhr || typeof result.report !== "string" || !result.report.length)
          throw new Error("Lighthouse did not produce both JSON and HTML reports");
        const lhr = result.lhr;
        const stem = `lhr-${invocation + urlIndex * config.ci.collect.numberOfRuns + run}`;
        const jsonPath = join(output, `${stem}.json`),
          htmlPath = join(output, `${stem}.html`);
        await writeFile(jsonPath, JSON.stringify(lhr, null, 2) + "\n");
        await writeFile(htmlPath, result.report);
        reports.push(lhr);
        if (Array.isArray(lhr.runWarnings) && lhr.runWarnings.length)
          warnings.push({ url, run: run + 1, messages: lhr.runWarnings });
        manifest.push({
          url,
          isRepresentativeRun: false,
          htmlPath,
          jsonPath,
          summary: Object.fromEntries(
            Object.entries(lhr.categories ?? {}).map(([id, category]) => [
              id,
              category?.score ?? null,
            ]),
          ),
        });
        if (
          Object.values(lhr.categories ?? {}).some(
            (category) => !category || typeof category !== "object" || Array.isArray(category),
          )
        )
          throw new Error("Lighthouse produced a malformed category");
        if (lhr.requestedUrl !== url || lhr.runtimeError)
          throw new Error(
            `Invalid collection: ${JSON.stringify(lhr.runtimeError ?? lhr.requestedUrl)}`,
          );
        if (incompleteLoadWarning(lhr))
          throw new Error("Incomplete collection: Lighthouse page-load timeout warning");
        if (process.env.CI_PERF_HARNESS === "1") {
          contentReadiness.push({ url, run: run + 1, ...result.contentReadiness });
          if (result.contentReadiness?.passed !== true)
            throw new Error("Measured content readiness failed");
        }
      } catch (error) {
        errors.push({ url, run: run + 1, message: error.message });
        break collection; // Infrastructure failure: preserve partial evidence, never retry/reroute.
      }
    }
  }
  for (const url of config.ci.collect.url) {
    const representative = representativeRun(reports.filter((lhr) => lhr.requestedUrl === url));
    if (representative) manifest[reports.indexOf(representative)].isRepresentativeRun = true;
  }
  try {
    assertions = evaluateAssertions(config, reports);
  } catch (error) {
    errors.push({ message: error.message });
  }
  await writeFile(join(output, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
  await writeFile(
    join(output, "content-readiness.json"),
    JSON.stringify(contentReadiness, null, 2) + "\n",
  );
  // Keep LHCI's failure/warning-only assertion-results contract; retain full results separately.
  await writeFile(
    join(output, "assertion-results.json"),
    JSON.stringify(
      assertions.filter((a) => !a.passed),
      null,
      2,
    ) + "\n",
  );
  await writeFile(
    join(output, "assertion-results-all.json"),
    JSON.stringify(assertions, null, 2) + "\n",
  );
  const exitCode =
    errors.length || assertions.some((a) => !a.passed && a.level === "error") ? 1 : 0;
  await writeFile(
    join(output, "run-summary.json"),
    JSON.stringify(
      {
        exitCode,
        source_identity: source,
        errors,
        warnings,
        numberOfRuns: config.ci.collect.numberOfRuns,
        urls: config.ci.collect.url,
        settings: config.ci.collect.settings,
        lighthouseVersions: [...new Set(reports.map((lhr) => lhr.lighthouseVersion))],
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
      throw new Error("Usage: lighthouse-runner.mjs [--config=lighthouserc.json]");
    const configBytes = await readFile(args[0]?.slice("--config=".length) || "lighthouserc.json");
    const config = JSON.parse(configBytes.toString("utf8"));
    const result = await runPerformance(config, {
      configSha256: createHash("sha256").update(configBytes).digest("hex"),
    });
    for (const assertion of result.assertions.filter((a) => !a.passed))
      console.error(
        `${assertion.level}: ${assertion.url} ${assertion.auditId} ${assertion.actual} ${assertion.operator} ${assertion.expected}`,
      );
    for (const error of result.errors) console.error(error);
    process.exitCode = result.exitCode;
  } catch (error) {
    console.error(error);
    process.exitCode = 1;
  }
}
