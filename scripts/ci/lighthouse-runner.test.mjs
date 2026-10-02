/* global structuredClone */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import process from "node:process";
import { test } from "node:test";
import { URL } from "node:url";

import {
  evaluateAssertions,
  runPerformance,
  representativeRun,
  validatePolicy,
  auditWithChrome,
} from "./lighthouse-runner.mjs";

const config = JSON.parse(
  await readFile(new URL("../../lighthouserc.json", import.meta.url), "utf8"),
);
const makeReport = (url) => ({
  requestedUrl: url,
  finalUrl: url,
  lighthouseVersion: "fixture",
  categories: {
    performance: { score: 0.8 },
    accessibility: { score: 0.95 },
    seo: { score: 0.8 },
    "best-practices": { score: 0.9 },
  },
  audits: {
    "largest-contentful-paint": { numericValue: 3000 },
    "first-contentful-paint": { numericValue: 1000 },
    interactive: { numericValue: 1500 },
  },
});
const allReports = () =>
  config.ci.collect.url.flatMap((url) => Array.from({ length: 3 }, () => makeReport(url)));
const metric = (results, url, id) =>
  results.find(
    (r) => r.url === url && (r.auditProperty ? `categories:${r.auditProperty}` : r.auditId) === id,
  );

// Explicit expected policy: changing thresholds or aggregation requires a reviewed test change.
test("all five existing URL policies, mobile profile and three-run contract remain unchanged", () => {
  assert.equal(config.ci.collect.numberOfRuns, 3);
  assert.deepEqual(
    config.ci.collect.url.map((u) => new URL(u).pathname),
    ["/en", "/en/c/electronics", "/en/p/smartphone-x1", "/en/search", "/en/checkout"],
  );
  assert.deepEqual(config.ci.collect.settings, {
    formFactor: "mobile",
    screenEmulation: {
      mobile: true,
      width: 360,
      height: 740,
      deviceScaleFactor: 2,
      disabled: false,
    },
    throttling: {
      rttMs: 150,
      throughputKbps: 1600,
      requestLatencyMs: 150,
      downloadThroughputKbps: 1600,
      uploadThroughputKbps: 750,
      cpuSlowdownMultiplier: 4,
    },
    onlyCategories: ["performance", "accessibility", "seo", "best-practices"],
  });
  for (const url of config.ci.collect.url) {
    const checkout = url.endsWith("checkout"),
      search = url.endsWith("search");
    const rows = config.ci.assert.assertMatrix.filter((r) =>
      new RegExp(r.matchingUrlPattern).test(url),
    );
    assert.equal(rows.length, 1);
    assert.deepEqual(rows[0].assertions, {
      "categories:accessibility": ["error", { minScore: 0.9 }],
      "categories:best-practices": ["error", { minScore: 0.85 }],
      "categories:seo": [
        checkout ? "warn" : "error",
        { minScore: checkout || search ? 0.4 : 0.75 },
      ],
      "categories:performance": ["error", { minScore: 0.5, aggregationMethod: "median" }],
      "largest-contentful-paint": [
        "error",
        {
          maxNumericValue: checkout ? 7200 : 6500,
          aggregationMethod: "median",
        },
      ],
    });
  }
  assert.equal(evaluateAssertions(config, allReports()).length, 25);
});

for (const url of config.ci.collect.url) {
  test(`median and optimistic aggregation, equality boundaries: ${new URL(url).pathname}`, () => {
    const reports = allReports(),
      runs = reports.filter((r) => r.requestedUrl === url);
    const ceiling = url.endsWith("checkout") ? 7200 : 6500;
    runs.forEach((r, i) => {
      r.categories.performance.score = [0.1, 0.5, 0.9][i];
      r.audits["largest-contentful-paint"].numericValue = [1, ceiling, ceiling + 500][i];
      r.categories.accessibility.score = [0, 0, 0.9][i];
    });
    let results = evaluateAssertions(config, reports);
    assert.equal(metric(results, url, "categories:performance").actual, 0.5);
    assert.equal(metric(results, url, "largest-contentful-paint").actual, ceiling);
    assert.equal(metric(results, url, "categories:accessibility").actual, 0.9);
    assert.ok(results.every((r) => r.passed));
    runs[1].categories.performance.score = 0.49;
    runs[1].audits["largest-contentful-paint"].numericValue = ceiling + 1;
    results = evaluateAssertions(config, reports);
    assert.equal(metric(results, url, "categories:performance").passed, false);
    assert.equal(metric(results, url, "largest-contentful-paint").passed, false);
  });
}

test("missing/null audit values and pessimistic aggregation preserve LHCI behavior", () => {
  let reports = allReports();
  const url = reports[0].requestedUrl;
  delete reports[0].categories.accessibility;
  const missing = metric(evaluateAssertions(config, reports), url, "categories:accessibility");
  assert.equal(missing.name, "auditRan");
  assert.equal(missing.passed, false);
  reports = allReports();
  reports[0].categories.performance.score = null;
  assert.equal(
    metric(evaluateAssertions(config, reports), url, "categories:performance").actual,
    0.8,
  );
  const pessimistic = structuredClone(config);
  pessimistic.ci.assert.assertMatrix.forEach((r) => {
    r.assertions["categories:performance"][1].aggregationMethod = "pessimistic";
  });
  assert.equal(
    metric(evaluateAssertions(pessimistic, reports), url, "categories:performance").passed,
    false,
  );
  reports.slice(0, 3).forEach((r) => {
    r.categories.performance.score = null;
  });
  assert.equal(
    metric(evaluateAssertions(config, reports), url, "categories:performance").passed,
    false,
  );
});

test("missing runs, unexpected reports, runtime errors and unmatched redirects fail closed", () => {
  assert.throws(() => evaluateAssertions(config, allReports().slice(1)), /Incomplete/);
  assert.throws(
    () => evaluateAssertions(config, [...allReports(), makeReport("http://localhost:3000/other")]),
    /Unexpected/,
  );
  const bad = allReports();
  bad[0].runtimeError = { code: "FAILED_DOCUMENT_REQUEST" };
  assert.throws(() => evaluateAssertions(config, bad), /failed collection/);
  const redirect = allReports();
  redirect.slice(0, 3).forEach((r) => {
    r.finalUrl = "http://localhost:3000/login";
  });
  assert.throws(() => evaluateAssertions(config, redirect), /No assertions/);
});

test("unsupported policy cannot silently disable assertion coverage", () => {
  for (const mutate of [
    (c) => {
      c.ci.collect.numberOfRuns = 1;
    },
    (c) => {
      c.ci.assert.assertMatrix[0].assertions["categories:performance"][0] = "off";
    },
    (c) => {
      c.ci.assert.assertMatrix[0].assertions["categories:performance"][1].maxScore = 1;
    },
    (c) => {
      c.ci.assert.assertMatrix[0].assertions["categories:performance"][1].aggregationMethod =
        "made-up";
    },
    (c) => {
      c.ci.assert.assertMatrix.pop();
    },
    (c) => {
      c.ci.upload.target = "temporary-public-storage";
    },
  ]) {
    const changed = structuredClone(config);
    mutate(changed);
    assert.throws(() => validatePolicy(changed));
  }
});

test("representative report selection follows FCP/TTI proximity, not assertion aggregation", () => {
  const runs = [makeReport("u"), makeReport("u"), makeReport("u")];
  runs.forEach((r, i) => {
    r.audits["first-contentful-paint"].numericValue = [100, 200, 300][i];
    r.audits.interactive.numericValue = [500, 600, 700][i];
  });
  assert.equal(representativeRun(runs), runs[1]);
});

for (const scenario of ["pass", "warn", "threshold", "collection", "runtime", "missing-html"]) {
  test(`orchestration / artifacts / failure exit: ${scenario}`, async () => {
    const dir = await mkdtemp(join(tmpdir(), "performance-contract-"));
    let calls = 0;
    try {
      const result = await runPerformance(config, {
        cwd: dir,
        audit: async (url, settings) => {
          calls++;
          assert.deepEqual(settings, config.ci.collect.settings);
          if (scenario === "collection") throw new Error("fixture Chrome failed");
          const lhr = makeReport(url);
          if (scenario === "warn" && url.endsWith("checkout")) lhr.categories.seo.score = 0;
          if (scenario === "threshold") lhr.categories.performance.score = 0.49;
          if (scenario === "runtime") lhr.runtimeError = { code: "FIXTURE_ERROR" };
          return {
            lhr,
            report:
              scenario === "missing-html" ? undefined : "<!doctype html><title>fixture</title>",
          };
        },
      });
      const failure = !["pass", "warn"].includes(scenario);
      assert.equal(result.exitCode, failure ? 1 : 0);
      const output = join(dir, ".lighthouseci");
      const summary = JSON.parse(await readFile(join(output, "run-summary.json")));
      const manifest = JSON.parse(await readFile(join(output, "manifest.json")));
      const assertions = JSON.parse(await readFile(join(output, "assertion-results.json")));
      assert.equal(summary.exitCode, result.exitCode);
      if (["pass", "warn", "threshold"].includes(scenario)) {
        assert.equal(calls, 15);
        assert.equal(manifest.length, 15);
        assert.equal(manifest.filter((r) => r.isRepresentativeRun).length, 5);
        assert.equal(new Set(manifest.map((r) => r.jsonPath)).size, 15);
        for (const row of manifest) {
          assert.ok((await readFile(row.htmlPath, "utf8")).startsWith("<!doctype"));
          assert.equal(JSON.parse(await readFile(row.jsonPath)).requestedUrl, row.url);
        }
      } else {
        assert.equal(calls, 1);
        assert.ok(summary.errors.length);
      }
      if (scenario === "warn")
        assert.deepEqual(
          assertions.map((a) => a.level),
          ["warn"],
        );
      if (scenario === "threshold")
        assert.equal(assertions.filter((a) => a.level === "error").length, 5);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
}

test("malformed category preserves failed-run summary and partial report artifacts", async () => {
  const dir = await mkdtemp(join(tmpdir(), "performance-malformed-category-"));
  let calls = 0;
  try {
    const result = await runPerformance(config, {
      cwd: dir,
      audit: async (url) => {
        calls++;
        const lhr = makeReport(url);
        lhr.categories.performance = null;
        return {
          lhr,
          report: "<!doctype html><title>malformed fixture</title>",
        };
      },
    });
    assert.equal(result.exitCode, 1);
    assert.equal(calls, 1);
    const output = join(dir, ".lighthouseci");
    const summary = JSON.parse(await readFile(join(output, "run-summary.json")));
    const manifest = JSON.parse(await readFile(join(output, "manifest.json")));
    assert.equal(summary.exitCode, 1);
    assert.match(summary.errors[0].message, /malformed category/);
    assert.equal(manifest.length, 1);
    assert.equal(manifest[0].isRepresentativeRun, true);
    assert.equal(manifest[0].summary.performance, null);
    assert.equal(JSON.parse(await readFile(manifest[0].jsonPath)).categories.performance, null);
    assert.match(await readFile(manifest[0].htmlPath, "utf8"), /malformed fixture/);
    assert.deepEqual(JSON.parse(await readFile(join(output, "assertion-results.json"))), []);
    assert.deepEqual(JSON.parse(await readFile(join(output, "assertion-results-all.json"))), []);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("real-engine adapter forwards settings and always cleans up Chrome without security bypass flags", async () => {
  let killed = 0,
    launched;
  const deps = [
    {
      default: async (url, flags) => {
        assert.equal(url, "http://localhost/fixture");
        assert.deepEqual(flags.screenEmulation, config.ci.collect.settings.screenEmulation);
        assert.equal(flags.port, 9999);
        throw new Error("engine fixture");
      },
    },
    {
      launch: async (options) => {
        launched = options;
        return {
          port: 9999,
          kill: async () => {
            killed++;
          },
        };
      },
    },
    { default: { executablePath: () => "/fixture/official-chrome" } },
  ];
  await assert.rejects(
    auditWithChrome("http://localhost/fixture", config.ci.collect.settings, deps),
    /engine fixture/,
  );
  assert.equal(killed, 1);
  assert.deepEqual(launched, {
    chromePath: "/fixture/official-chrome",
    chromeFlags: ["--headless=new"],
  });
});

for (const scenario of ["success", "engine failure"]) {
  test(`async executable path is resolved before launch and Chrome is cleaned up: ${scenario}`, async () => {
    const events = [];
    const url = "http://localhost/fixture";
    const result = { lhr: makeReport(url), report: "<!doctype html><title>fixture</title>" };
    const engineError = new Error("engine fixture");
    const deps = [
      {
        default: async (requestedUrl, flags) => {
          events.push("engine");
          assert.equal(requestedUrl, url);
          assert.deepEqual(flags, {
            ...config.ci.collect.settings,
            port: 9999,
            output: "html",
            logLevel: "info",
          });
          if (scenario === "engine failure") throw engineError;
          return result;
        },
      },
      {
        launch: async (options) => {
          events.push("launch");
          assert.equal(typeof options.chromePath, "string");
          assert.deepEqual(options, {
            chromePath: "/fixture/official-chrome",
            chromeFlags: ["--headless=new"],
          });
          return {
            port: 9999,
            kill: async () => {
              events.push("kill");
            },
          };
        },
      },
      {
        default: {
          executablePath: async () => {
            await Promise.resolve();
            events.push("path resolved");
            return "/fixture/official-chrome";
          },
        },
      },
    ];
    if (scenario === "engine failure") {
      await assert.rejects(auditWithChrome(url, config.ci.collect.settings, deps), engineError);
    } else {
      assert.equal(await auditWithChrome(url, config.ci.collect.settings, deps), result);
    }
    assert.deepEqual(events, ["path resolved", "launch", "engine", "kill"]);
  });
}

test("CLI invalid input exits nonzero before browser collection", () => {
  const result = spawnSync(
    process.execPath,
    [new URL("./lighthouse-runner.mjs", import.meta.url).pathname, "--unsupported"],
    { encoding: "utf8" },
  );
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Usage/);
});
