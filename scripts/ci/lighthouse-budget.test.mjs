/* global structuredClone */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import process from "node:process";
import test from "node:test";
import { fileURLToPath, URL } from "node:url";

import {
  auditWithChrome,
  evaluateAssertions,
  INCOMPLETE_LOAD_WARNING,
  representativeRun,
  runPerformance,
  validatePolicy,
} from "./lighthouse-budget.mjs";

const config = JSON.parse(
  await readFile(new URL("../../lighthouserc.json", import.meta.url), "utf8"),
);
const report = (url) => ({
  requestedUrl: url,
  finalUrl: url,
  lighthouseVersion: "13.5.0",
  categories: {
    performance: { score: 0.8 },
    accessibility: { score: 0.95 },
    seo: { score: 0.95 },
    "best-practices": { score: 0.95 },
  },
  audits: {
    "largest-contentful-paint": { numericValue: 2000 },
    "first-contentful-paint": { numericValue: 1000 },
    interactive: { numericValue: 2000 },
  },
});
const reports = () =>
  config.ci.collect.url.flatMap((url) => Array.from({ length: 3 }, () => report(url)));
const metric = (rows, url, id) =>
  rows.find(
    (row) =>
      row.url === url &&
      (row.auditProperty ? `categories:${row.auditProperty}` : row.auditId) === id,
  );

test("the unchanged five-URL/three-run mobile policy and all 25 thresholds are retained", () => {
  assert.equal(config.ci.collect.numberOfRuns, 3);
  assert.deepEqual(
    config.ci.collect.url.map((url) => new URL(url).pathname),
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
    const [row] = config.ci.assert.assertMatrix.filter((entry) =>
      new RegExp(entry.matchingUrlPattern).test(url),
    );
    const checkout = url.endsWith("checkout"),
      search = url.endsWith("search");
    assert.deepEqual(row.assertions, {
      "categories:accessibility": ["error", { minScore: 0.9 }],
      "categories:best-practices": ["error", { minScore: 0.85 }],
      "categories:seo": [
        checkout ? "warn" : "error",
        { minScore: checkout || search ? 0.4 : 0.75 },
      ],
      "categories:performance": ["error", { minScore: 0.5, aggregationMethod: "median" }],
      "largest-contentful-paint": [
        "error",
        { maxNumericValue: checkout ? 7200 : 6500, aggregationMethod: "median" },
      ],
    });
  }
  assert.equal(evaluateAssertions(config, reports()).length, 25);
});
for (const url of config.ci.collect.url)
  test(`median/equality boundaries and optimistic scores: ${url}`, () => {
    const rows = reports(),
      runs = rows.filter((row) => row.requestedUrl === url),
      limit = url.endsWith("checkout") ? 7200 : 6500;
    runs.forEach((row, i) => {
      row.categories.performance.score = [0.1, 0.5, 0.9][i];
      row.audits["largest-contentful-paint"].numericValue = [1, limit, limit + 1][i];
      row.categories.accessibility.score = [0, 0, 0.9][i];
    });
    assert.ok(evaluateAssertions(config, rows).every((row) => row.passed));
    runs[1].categories.performance.score = 0.49;
    assert.equal(
      metric(evaluateAssertions(config, rows), url, "categories:performance").passed,
      false,
    );
    runs[1].audits["largest-contentful-paint"].numericValue = limit + 1;
    assert.equal(
      metric(evaluateAssertions(config, rows), url, "largest-contentful-paint").passed,
      false,
    );
  });
test("LHCI missing-audit and null-score semantics remain fail-closed with pessimistic aggregation", () => {
  let rows = reports();
  const url = rows[0].requestedUrl;
  delete rows[0].categories.accessibility;
  assert.equal(
    metric(evaluateAssertions(config, rows), url, "categories:accessibility").name,
    "auditRan",
  );
  rows = reports();
  rows[0].categories.accessibility.score = null;
  assert.equal(
    metric(evaluateAssertions(config, rows), url, "categories:accessibility").passed,
    true,
  );
  const cfg = structuredClone(config);
  cfg.ci.assert.assertMatrix.forEach((row) => {
    row.assertions["categories:accessibility"][1].aggregationMethod = "pessimistic";
  });
  assert.equal(
    metric(evaluateAssertions(cfg, rows), url, "categories:accessibility").passed,
    false,
  );
  rows.slice(0, 3).forEach((row) => {
    row.categories.performance.score = NaN;
  });
  assert.throws(() => evaluateAssertions(config, rows), /Incomplete required/);
});
for (const [name, mutate] of [
  ["one null required performance score", (lhr) => (lhr.categories.performance.score = null)],
  ["one NaN required performance score", (lhr) => (lhr.categories.performance.score = NaN)],
  ["one omitted required performance score", (lhr) => delete lhr.categories.performance.score],
  [
    "one infinite required performance score",
    (lhr) => (lhr.categories.performance.score = Infinity),
  ],
  [
    "one null required LCP value",
    (lhr) => (lhr.audits["largest-contentful-paint"].numericValue = null),
  ],
  [
    "one NaN required LCP value",
    (lhr) => (lhr.audits["largest-contentful-paint"].numericValue = NaN),
  ],
  [
    "one omitted required LCP value",
    (lhr) => delete lhr.audits["largest-contentful-paint"].numericValue,
  ],
  [
    "one infinite required LCP value",
    (lhr) => (lhr.audits["largest-contentful-paint"].numericValue = Infinity),
  ],
])
  test(`${name} blocks evaluation and collection without retry`, async () => {
    const rows = reports();
    mutate(rows[1]);
    assert.throws(() => evaluateAssertions(config, rows), /Incomplete required/);
    const cwd = await mkdtemp(join(tmpdir(), "lighthouse-required-metric-"));
    let calls = 0;
    try {
      const result = await runPerformance(config, {
        cwd,
        audit: async (url) => {
          const lhr = report(url);
          if (++calls === 2) mutate(lhr);
          return { lhr, report: ["{}", "<!doctype html>"] };
        },
      });
      assert.equal(result.exitCode, 1);
      assert.equal(calls, 2);
      const summary = JSON.parse(await readFile(join(cwd, ".lighthouseci/run-summary.json")));
      assert.equal(summary.exitCode, 1);
      assert.equal(summary.collectedReports, 1);
      assert.equal(summary.errors.length, 1);
      assert.match(summary.errors[0].message, /Incomplete required/);
      const manifest = JSON.parse(await readFile(join(cwd, ".lighthouseci/manifest.json")));
      assert.equal(manifest.length, 2);
      assert.equal(manifest[0].validCollection, true);
      assert.equal(manifest[1].validCollection, false);
      assert.equal(manifest[1].isRepresentativeRun, false);
      assert.equal(
        JSON.parse(await readFile(manifest[1].jsonPath)).requestedUrl,
        rows[1].requestedUrl,
      );
      assert.match(await readFile(manifest[1].htmlPath, "utf8"), /doctype/);
    } finally {
      await rm(cwd, { recursive: true, force: true });
    }
  });
test("finite zero samples and equality medians complete all fifteen runs", async () => {
  const rows = reports();
  rows.forEach((lhr, i) => {
    const limit = lhr.requestedUrl.endsWith("checkout") ? 7200 : 6500;
    lhr.categories.performance.score = [0, 0.5, 1][i % 3];
    lhr.audits["largest-contentful-paint"].numericValue = [0, limit, limit + 1][i % 3];
  });
  const assertions = evaluateAssertions(config, rows);
  assert.ok(assertions.every((row) => row.passed));
  for (const url of config.ci.collect.url) {
    const performance = metric(assertions, url, "categories:performance"),
      lcp = metric(assertions, url, "largest-contentful-paint");
    assert.ok(performance.values.includes(0));
    assert.ok(lcp.values.includes(0));
    assert.equal(performance.actual, performance.expected);
    assert.equal(lcp.actual, lcp.expected);
  }
  const cwd = await mkdtemp(join(tmpdir(), "lighthouse-zero-boundary-"));
  let calls = 0;
  try {
    const result = await runPerformance(config, {
      cwd,
      audit: async () => ({
        lhr: rows[calls++],
        report: ["{}", "<!doctype html>"],
      }),
    });
    assert.equal(result.exitCode, 0);
    assert.equal(calls, 15);
    assert.equal(result.manifest.length, 15);
    assert.ok(result.manifest.every((row) => row.validCollection));
    const summary = JSON.parse(await readFile(join(cwd, ".lighthouseci/run-summary.json")));
    assert.equal(summary.collectedReports, 15);
    assert.deepEqual(summary.errors, []);
  } finally {
    await rm(cwd, { recursive: true, force: true });
  }
});
for (const [name, mutate] of [
  ["missing sample", (rows) => rows.pop()],
  [
    "duplicate URL",
    (rows) => {
      rows[0].requestedUrl = rows[3].requestedUrl;
    },
  ],
  ["unexpected sample", (rows) => rows.push(report("http://localhost:3000/other"))],
  [
    "redirect to login",
    (rows) =>
      rows.forEach((row) => {
        row.finalUrl = "http://localhost:3000/en/login";
      }),
  ],
  [
    "redirect within matching category pattern",
    (rows) =>
      rows
        .filter((row) => row.requestedUrl.includes("/c/"))
        .forEach((row) => {
          row.finalUrl = "http://localhost:3000/en/c/other";
        }),
  ],
  [
    "runtime failure",
    (rows) => {
      rows[0].runtimeError = { code: "FAILED_DOCUMENT_REQUEST" };
    },
  ],
  [
    "incomplete load",
    (rows) => {
      rows[0].runWarnings = [INCOMPLETE_LOAD_WARNING];
    },
  ],
])
  test(`rejects invalid collection: ${name}`, () => {
    const rows = reports();
    mutate(rows);
    assert.throws(() => evaluateAssertions(config, rows));
  });
for (const [name, mutate] of [
  [
    "single run",
    (cfg) => {
      cfg.ci.collect.numberOfRuns = 1;
    },
  ],
  ["removed URL", (cfg) => cfg.ci.collect.url.pop()],
  [
    "unforwarded setting",
    (cfg) => {
      cfg.ci.collect.settings.chromeFlags = "--no-sandbox";
    },
  ],
  [
    "disabled assertion",
    (cfg) => {
      cfg.ci.assert.assertMatrix[0].assertions["categories:performance"][0] = "off";
    },
  ],
  [
    "additional waiver",
    (cfg) => {
      cfg.ci.assert.assertMatrix[1].assertions["categories:performance"][0] = "warn";
    },
  ],
  [
    "removed metric",
    (cfg) => {
      delete cfg.ci.assert.assertMatrix[0].assertions["categories:performance"];
    },
  ],
  [
    "unsupported metric",
    (cfg) => {
      cfg.ci.assert.assertMatrix[0].assertions.unknown = ["error", { minScore: 1 }];
    },
  ],
  [
    "unsupported aggregation",
    (cfg) => {
      cfg.ci.assert.assertMatrix[0].assertions["categories:performance"][1].aggregationMethod =
        "optimistic";
    },
  ],
  [
    "invalid threshold",
    (cfg) => {
      cfg.ci.assert.assertMatrix[0].assertions["categories:performance"][1].minScore = NaN;
    },
  ],
  [
    "remote upload",
    (cfg) => {
      cfg.ci.upload.target = "temporary-public-storage";
    },
  ],
  [
    "broad output",
    (cfg) => {
      cfg.ci.upload.outputDir = ".";
    },
  ],
])
  test(`rejects policy drift: ${name}`, () => {
    const cfg = structuredClone(config);
    mutate(cfg);
    assert.throws(() => validatePolicy(cfg));
  });
test("representative report is selected independently from each metric's median", () => {
  const rows = [report("u"), report("u"), report("u")];
  rows.forEach((row, i) => {
    row.audits["first-contentful-paint"].numericValue = [100, 200, 300][i];
    row.audits.interactive.numericValue = [500, 600, 700][i];
  });
  assert.equal(representativeRun(rows), rows[1]);
});
for (const scenario of [
  "pass",
  "warn",
  "threshold",
  "redirect",
  "incomplete",
  "runtime",
  "no-result",
  "missing-html",
  "wrong-version",
  "throw",
])
  test(`collection exits and retained artifacts: ${scenario}`, async () => {
    const cwd = await mkdtemp(join(tmpdir(), "lighthouse-contract-"));
    let calls = 0;
    try {
      const result = await runPerformance(config, {
        cwd,
        audit: async (url, settings) => {
          calls++;
          assert.deepEqual(settings, config.ci.collect.settings);
          if (scenario === "throw") throw new Error("mock Chrome unavailable");
          if (scenario === "no-result") return undefined;
          const lhr = report(url);
          if (scenario === "warn" && url.endsWith("checkout")) lhr.categories.seo.score = 0;
          if (scenario === "threshold") lhr.categories.performance.score = 0.49;
          if (scenario === "redirect") lhr.finalUrl = "http://localhost:3000/en/login";
          if (scenario === "incomplete") lhr.runWarnings = [INCOMPLETE_LOAD_WARNING];
          if (scenario === "runtime") lhr.runtimeError = { code: "FIXTURE" };
          if (scenario === "wrong-version") lhr.lighthouseVersion = "12.6.1";
          return {
            lhr,
            report: scenario === "missing-html" ? undefined : ["{}", "<!doctype html>"],
          };
        },
      });
      assert.equal(result.exitCode, ["pass", "warn"].includes(scenario) ? 0 : 1);
      const summary = JSON.parse(await readFile(join(cwd, ".lighthouseci/run-summary.json")));
      assert.equal(summary.exitCode, result.exitCode);
      const manifest = JSON.parse(await readFile(join(cwd, ".lighthouseci/manifest.json")));
      const assertions = JSON.parse(
        await readFile(join(cwd, ".lighthouseci/assertion-results.json")),
      );
      if (["pass", "warn", "threshold"].includes(scenario)) {
        assert.equal(calls, 15);
        assert.equal(manifest.length, 15);
        assert.equal(manifest.filter((row) => row.isRepresentativeRun).length, 5);
      } else {
        assert.equal(calls, 1);
        assert.equal(summary.errors.length, 1);
      }
      for (const row of manifest) {
        if (row.jsonPath)
          assert.equal(JSON.parse(await readFile(row.jsonPath)).requestedUrl, row.url);
        if (row.htmlPath) assert.match(await readFile(row.htmlPath, "utf8"), /doctype/);
      }
      if (scenario === "warn")
        assert.deepEqual(
          assertions.map((row) => row.level),
          ["warn"],
        );
    } finally {
      await rm(cwd, { recursive: true, force: true });
    }
  });
function adapterFixture(mode = "pass") {
  const state = { launches: 0, kills: 0 };
  class Launcher {
    static defaultFlags() {
      return mode === "default-bypass" ? ["--no-sandbox"] : ["--disable-background-networking"];
    }
    constructor(options) {
      state.options = options;
      this.flags =
        mode === "effective-bypass" ? ["--ignore-certificate-errors"] : options.chromeFlags;
      this.port = 9222;
    }
    async launch() {
      state.launches++;
      if (mode === "launch-failure") throw new Error("launch failed");
    }
    async kill() {
      state.kills++;
      if (mode === "cleanup-failure") throw new Error("cleanup failed");
    }
  }
  const lighthouse = async (url, flags) => {
    state.flags = flags;
    if (mode === "audit-failure") throw new Error("audit failed");
    return { lhr: report(url), report: ["{}", "<!doctype html>"] };
  };
  return {
    state,
    dependencies: {
      chromePath: process.execPath,
      modules: [{ default: lighthouse }, { Launcher }],
    },
  };
}
for (const mode of [
  "pass",
  "default-bypass",
  "effective-bypass",
  "launch-failure",
  "audit-failure",
  "cleanup-failure",
])
  test(`launcher security and cleanup: ${mode}`, async () => {
    const { state, dependencies } = adapterFixture(mode),
      url = config.ci.collect.url[0];
    if (mode === "pass") {
      const result = await auditWithChrome(url, config.ci.collect.settings, dependencies);
      assert.equal(result.lhr.requestedUrl, url);
      assert.equal(state.options.ignoreDefaultFlags, true);
      assert.equal(state.options.chromePath, process.execPath);
      assert.deepEqual(state.flags.output, ["json", "html"]);
      assert.equal(state.flags.port, 9222);
      for (const [key, value] of Object.entries(config.ci.collect.settings))
        assert.deepEqual(state.flags[key], value);
    } else await assert.rejects(auditWithChrome(url, config.ci.collect.settings, dependencies));
    assert.equal(state.launches, ["default-bypass", "effective-bypass"].includes(mode) ? 0 : 1);
    if (state.options) {
      assert.equal(state.kills, 1);
      assert.equal(existsSync(state.options.userDataDir), false);
    }
  });
test("explicit missing/relative browser path fails before a launcher is constructed", async () => {
  for (const chromePath of ["relative/chrome", "/nonexistent/vergeo-chrome"]) {
    const { state, dependencies } = adapterFixture();
    await assert.rejects(auditWithChrome("u", {}, { ...dependencies, chromePath }));
    assert.equal(state.options, undefined);
  }
});
test("cleanup failure retains the completed sample and fails collection", async () => {
  const cwd = await mkdtemp(join(tmpdir(), "lighthouse-cleanup-")),
    { dependencies } = adapterFixture("cleanup-failure");
  try {
    const result = await runPerformance(config, {
      cwd,
      audit: (url, settings) => auditWithChrome(url, settings, dependencies),
    });
    assert.equal(result.exitCode, 1);
    assert.equal(result.manifest.length, 1);
    assert.match(await readFile(result.manifest[0].htmlPath, "utf8"), /doctype/);
  } finally {
    await rm(cwd, { recursive: true, force: true });
  }
});

test("actual CLI fails on a missing explicit browser and retains failure evidence", async () => {
  const cwd = await mkdtemp(join(tmpdir(), "lighthouse-cli-"));
  try {
    const path = join(cwd, "policy.json");
    await writeFile(path, JSON.stringify(config));
    const result = spawnSync(
      process.execPath,
      [fileURLToPath(new URL("./lighthouse-budget.mjs", import.meta.url)), `--config=${path}`],
      {
        cwd,
        env: { PATH: "/usr/bin:/bin", CHROME_PATH: "/nonexistent/vergeo-chrome" },
        encoding: "utf8",
        timeout: 10000,
      },
    );
    assert.equal(result.error, undefined);
    assert.equal(result.status, 1);
    const summary = JSON.parse(await readFile(join(cwd, ".lighthouseci/run-summary.json")));
    assert.equal(summary.exitCode, 1);
    assert.equal(summary.collectedReports, 0);
    assert.equal(summary.errors.length, 1);
    assert.equal(JSON.parse(await readFile(join(cwd, ".lighthouseci/manifest.json"))).length, 1);
  } finally {
    await rm(cwd, { recursive: true, force: true });
  }
});
test("invalid policy is retained as failure and never starts collection", async () => {
  const cwd = await mkdtemp(join(tmpdir(), "lighthouse-policy-"));
  try {
    const cfg = structuredClone(config);
    cfg.ci.collect.numberOfRuns = 1;
    let calls = 0;
    const result = await runPerformance(cfg, {
      cwd,
      audit: async () => {
        calls++;
      },
    });
    assert.equal(result.exitCode, 1);
    assert.equal(calls, 0);
    assert.equal(
      JSON.parse(await readFile(join(cwd, ".lighthouseci/run-summary.json"))).errors.length,
      1,
    );
  } finally {
    await rm(cwd, { recursive: true, force: true });
  }
});
