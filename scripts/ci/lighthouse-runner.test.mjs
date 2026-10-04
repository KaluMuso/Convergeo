/* global structuredClone */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
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
  classifyChromeStderr,
  sourceIdentity,
  INCOMPLETE_LOAD_WARNING,
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
// Read source identity from the real checkout, including in hosted CI. Only
// fixture output moves to a private temporary directory; runtime checks stay strict.
const fixtureConfig = (dir) => {
  const fixture = structuredClone(config);
  fixture.ci.upload.outputDir = join(dir, ".lighthouseci");
  return fixture;
};
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

test("a complete report count with a load-timeout warning cannot qualify assertions", () => {
  const reports = allReports();
  reports[8].runWarnings = [INCOMPLETE_LOAD_WARNING];
  assert.throws(() => evaluateAssertions(config, reports), /failed collection/);
});

for (const scenario of [
  "pass",
  "warn",
  "notice",
  "incomplete-load",
  "threshold",
  "collection",
  "runtime",
  "missing-html",
]) {
  test(`orchestration / artifacts / failure exit: ${scenario}`, async () => {
    const dir = await mkdtemp(join(tmpdir(), "performance-contract-"));
    let calls = 0;
    try {
      const result = await runPerformance(fixtureConfig(dir), {
        audit: async (url, settings) => {
          calls++;
          assert.deepEqual(settings, config.ci.collect.settings);
          if (scenario === "collection") throw new Error("fixture Chrome failed");
          const lhr = makeReport(url);
          if (scenario === "warn" && url.endsWith("checkout")) lhr.categories.seo.score = 0;
          if (scenario === "threshold") lhr.categories.performance.score = 0.49;
          if (scenario === "runtime") lhr.runtimeError = { code: "FIXTURE_ERROR" };
          if (scenario === "notice") lhr.runWarnings = ["Informational fixture notice"];
          if (scenario === "incomplete-load") lhr.runWarnings = [INCOMPLETE_LOAD_WARNING];
          return {
            lhr,
            contentReadiness: { passed: true, reason: "explicit_synthetic_fixture" },
            report:
              scenario === "missing-html" ? undefined : "<!doctype html><title>fixture</title>",
          };
        },
      });
      const failure = !["pass", "warn", "notice"].includes(scenario);
      assert.equal(result.exitCode, failure ? 1 : 0);
      const output = join(dir, ".lighthouseci");
      const summary = JSON.parse(await readFile(join(output, "run-summary.json")));
      const manifest = JSON.parse(await readFile(join(output, "manifest.json")));
      const assertions = JSON.parse(await readFile(join(output, "assertion-results.json")));
      assert.equal(summary.exitCode, result.exitCode);
      if (["pass", "warn", "notice", "threshold"].includes(scenario)) {
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
      if (scenario === "notice") {
        assert.equal(summary.warnings.length, 15);
        assert.deepEqual(summary.warnings[0], {
          url: config.ci.collect.url[0],
          run: 1,
          messages: ["Informational fixture notice"],
        });
      }
      if (scenario === "incomplete-load") {
        assert.equal(manifest.length, 1);
        assert.equal(manifest[0].url, config.ci.collect.url[0]);
        assert.deepEqual(summary.warnings, [
          {
            url: config.ci.collect.url[0],
            run: 1,
            messages: [INCOMPLETE_LOAD_WARNING],
          },
        ]);
        assert.deepEqual(JSON.parse(await readFile(manifest[0].jsonPath)).runWarnings, [
          INCOMPLETE_LOAD_WARNING,
        ]);
        assert.ok((await readFile(manifest[0].htmlPath, "utf8")).startsWith("<!doctype"));
        assert.match(summary.errors[0].message, /Incomplete collection/);
        assert.deepEqual(assertions, []);
      }
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
}

test("malformed category preserves failed-run summary and partial report artifacts", async () => {
  const dir = await mkdtemp(join(tmpdir(), "performance-malformed-category-"));
  let calls = 0;
  try {
    const result = await runPerformance(fixtureConfig(dir), {
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

const safeDefaults = ["--disable-background-networking", "--no-first-run"];
for (const ready of [true, false]) {
  test(`CI content qualification retains genuine reports: ready=${ready}`, async () => {
    const dir = await mkdtemp(join(tmpdir(), "ci-content-qualification-"));
    const previous = process.env.CI_PERF_HARNESS;
    process.env.CI_PERF_HARNESS = "1";
    let calls = 0;
    try {
      const result = await runPerformance(fixtureConfig(dir), {
        audit: async (url, _settings, _dependencies, context) => {
          calls++;
          assert.equal(context.verifyContent, true);
          return {
            lhr: makeReport(url),
            report: "<!doctype html><title>retained fixture</title>",
            contentReadiness: {
              passed: ready,
              reason: ready
                ? "exact_fixture_content_and_loaded_media"
                : "unexpected_page_or_fallback",
            },
          };
        },
      });
      assert.equal(result.exitCode, ready ? 0 : 1);
      assert.equal(calls, ready ? 15 : 1);
      const output = join(dir, ".lighthouseci");
      const readiness = JSON.parse(await readFile(join(output, "content-readiness.json")));
      assert.equal(readiness.length, calls);
      assert.equal(readiness[0].passed, ready);
      const manifest = JSON.parse(await readFile(join(output, "manifest.json")));
      assert.equal(manifest.length, calls);
      assert.match(await readFile(manifest[0].htmlPath, "utf8"), /retained fixture/);
    } finally {
      if (previous === undefined) delete process.env.CI_PERF_HARNESS;
      else process.env.CI_PERF_HARNESS = previous;
      await rm(dir, { recursive: true, force: true });
    }
  });
}
function fakeChrome({ events, scenario, stderr = "", capture }) {
  return class {
    static defaultFlags() {
      return safeDefaults;
    }
    constructor(options) {
      capture.options = options;
      this.options = options;
      this.port = 9999;
      this.chromeProcess = {
        exitCode: scenario === "launch failure" ? 17 : null,
        signalCode: null,
      };
    }
    get flags() {
      return [...this.options.chromeFlags, "--remote-debugging-port=0"];
    }
    async launch() {
      events.push("launch");
      await writeFile(join(this.options.userDataDir, "chrome-err.log"), stderr);
      if (scenario === "launch failure") throw new Error("PRIVATE_ERROR_SENTINEL");
    }
    async kill() {
      events.push("kill");
      if (scenario === "cleanup failure") throw new Error("PRIVATE_CLEANUP_SENTINEL");
    }
  };
}

for (const failure of [false, true]) {
  test(`CI owns the supplied Lighthouse page and closes it on engine failure=${failure}`, async () => {
    const events = [],
      capture = {};
    const url = "http://localhost:3000/en/search";
    const page = {
      url: () => url,
      evaluate: async () => {
        events.push("inspect");
        return { url, unavailable: false, heading: "Search", searchReady: true };
      },
      close: async () => events.push("page.close"),
    };
    const browser = {
      newPage: async () => {
        events.push("newPage");
        return page;
      },
      disconnect: async () => events.push("disconnect"),
    };
    const deps = [
      {
        default: async (requested, flags, engineConfig, suppliedPage) => {
          events.push("engine");
          assert.equal(requested, url);
          assert.equal(suppliedPage, page);
          assert.equal(engineConfig, undefined);
          assert.deepEqual(flags, {
            ...config.ci.collect.settings,
            port: 9999,
            output: "html",
            logLevel: "info",
          });
          if (failure) throw new Error("engine fixture");
          return { lhr: makeReport(url), report: "<!doctype html>" };
        },
      },
      { Launcher: fakeChrome({ events, scenario: "success", capture }) },
      {
        default: {
          executablePath: async () => "/nonexistent-fixture-browser",
          connect: async (options) => {
            assert.deepEqual(options, {
              browserURL: "http://127.0.0.1:9999",
              defaultViewport: null,
            });
            return browser;
          },
        },
      },
    ];
    if (failure)
      await assert.rejects(
        auditWithChrome(url, config.ci.collect.settings, deps, { verifyContent: true }),
        /engine fixture/,
      );
    else
      assert.equal(
        (await auditWithChrome(url, config.ci.collect.settings, deps, { verifyContent: true }))
          .contentReadiness.passed,
        true,
      );
    assert.deepEqual(events, [
      "launch",
      "newPage",
      "engine",
      ...(failure ? [] : ["inspect"]),
      "page.close",
      "disconnect",
      "kill",
    ]);
  });
}

for (const scenario of ["success", "engine failure", "launch failure", "cleanup failure"]) {
  test(`owned Chrome lifecycle, projected diagnostics and settings: ${scenario}`, async () => {
    const dir = await mkdtemp(join(tmpdir(), "chrome-lifecycle-"));
    const events = [],
      capture = {};
    const url = "http://localhost/fixture";
    const result = {
      lhr: makeReport(url),
      report: "<!doctype html><title>fixture</title>",
    };
    const engineError = new Error("engine fixture");
    const diagnosticsPath = join(dir, "diagnostic.json");
    const context = {
      diagnosticsPath,
      urlIndex: 1,
      run: 1,
      source: {
        checkout_sha: "1".repeat(40),
        checkout_tree: "2".repeat(40),
        candidate_sha: "3".repeat(40),
        run_id: "123",
        run_attempt: "1",
        config_sha256: "4".repeat(64),
        Secret: "PRIVATE_IDENTITY_SENTINEL",
        env: "PRIVATE_ENV_SENTINEL",
      },
    };
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
        Launcher: fakeChrome({
          events,
          scenario,
          capture,
          stderr: "PRIVATE_STDERR_SENTINEL No usable sandbox! arbitrary private contents",
        }),
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
    try {
      if (scenario === "success")
        assert.equal(await auditWithChrome(url, config.ci.collect.settings, deps, context), result);
      else
        await assert.rejects(
          auditWithChrome(url, config.ci.collect.settings, deps, context),
          scenario === "engine failure" ? engineError : /Chrome (launch|cleanup) failed/,
        );
      assert.deepEqual(
        events,
        scenario === "launch failure"
          ? ["path resolved", "launch", "kill"]
          : ["path resolved", "launch", "engine", "kill"],
      );
      assert.deepEqual(capture.options.chromeFlags, [...safeDefaults, "--headless=new"]);
      assert.equal(capture.options.ignoreDefaultFlags, true);
      await assert.rejects(stat(capture.options.userDataDir), {
        code: "ENOENT",
      });
      const bytes = await readFile(diagnosticsPath, "utf8"),
        diagnostic = JSON.parse(bytes);
      assert.ok(!bytes.includes("PRIVATE_"));
      assert.deepEqual(diagnostic.stderr_reasons, ["sandbox_unavailable"]);
      assert.equal(diagnostic.checkout_sha, context.source.checkout_sha);
      assert.equal(diagnostic.checkout_tree, context.source.checkout_tree);
      assert.equal(diagnostic.candidate_sha, context.source.candidate_sha);
      assert.equal(diagnostic.run_id, "123");
      assert.equal(diagnostic.run_attempt, "1");
      assert.equal(diagnostic.config_sha256, "4".repeat(64));
      assert.equal(diagnostic.exit_code, scenario === "launch failure" ? 17 : null);
      assert.equal(diagnostic.cleanup_failed, scenario === "cleanup failure");
      assert.equal(diagnostic.collection_completed, scenario === "success");
      assert.equal(diagnostic.security_flags_rejected, false);
      assert.equal((await stat(diagnosticsPath)).mode & 0o777, 0o600);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
}

test("effective pinned Linux launcher flags preserve sandbox mechanisms", async () => {
  const { Launcher } = await import("chrome-launcher");
  const options = {
    chromePath: "/fixture/chrome",
    chromeFlags: [...Launcher.defaultFlags(), "--headless=new"],
    ignoreDefaultFlags: true,
    userDataDir: "/fixture/profile",
  };
  const launcher = new Launcher(options);
  launcher.port = 0; // spawnProcess sets the dynamic port immediately before spawn.
  const flags = launcher.flags;
  assert.ok(flags.includes("--headless=new"));
  assert.ok(flags.includes("--remote-debugging-port=0"));
  assert.ok(
    !flags.some((flag) =>
      /^--(?:no-sandbox|disable-(?:setuid|namespace|seccomp-filter|gpu)-sandbox|disable-web-security|ignore-certificate-errors|allow-insecure-localhost)/.test(
        flag,
      ),
    ),
  );
  assert.deepEqual(
    flags.filter(
      (flag) =>
        !flag.startsWith("--remote-debugging-port=") &&
        !flag.startsWith("--user-data-dir=") &&
        flag !== "about:blank",
    ),
    options.chromeFlags,
  );
});

for (const forbidden of [
  "--no-sandbox",
  "--disable-setuid-sandbox",
  "--disable-namespace-sandbox",
  "--disable-web-security",
  "--ignore-certificate-errors",
  "--allow-insecure-localhost",
]) {
  test(`security bypass is rejected before browser launch: ${forbidden}`, async () => {
    const events = [],
      capture = {};
    class Unsafe extends fakeChrome({ events, scenario: "success", capture }) {
      static defaultFlags() {
        return [forbidden];
      }
    }
    const deps = [
      {
        default: async () => {
          throw new Error("engine must not execute");
        },
      },
      { Launcher: Unsafe },
      { default: { executablePath: () => "/fixture/chrome" } },
    ];
    await assert.rejects(
      auditWithChrome("http://localhost/fixture", {}, deps),
      /Chrome validate_flags failed/,
    );
    assert.deepEqual(events, []);
  });
}

test("launch failure produces no LHR, no retries, safe source-bound diagnostics and exit1", async () => {
  const dir = await mkdtemp(join(tmpdir(), "chrome-no-collection-"));
  const events = [],
    capture = {};
  const deps = [
    {
      default: async () => {
        throw new Error("engine must not execute");
      },
    },
    {
      Launcher: fakeChrome({
        events,
        scenario: "launch failure",
        capture,
        stderr: "missing private data",
      }),
    },
    { default: { executablePath: () => "/fixture/chrome" } },
  ];
  try {
    const result = await runPerformance(fixtureConfig(dir), {
      audit: (url, settings, _deps, context) => auditWithChrome(url, settings, deps, context),
      configSha256: "5".repeat(64),
    });
    assert.equal(result.exitCode, 1);
    assert.deepEqual(result.manifest, []);
    assert.deepEqual(result.assertions, []);
    assert.deepEqual(events, ["launch", "kill"]);
    const diagnostic = JSON.parse(
      await readFile(join(dir, ".lighthouseci", "chrome-startup-1-1.json")),
    );
    const identity = await sourceIdentity(process.cwd());
    for (const [key, value] of Object.entries(identity)) assert.equal(diagnostic[key], value);
    assert.deepEqual(diagnostic.stderr_reasons, ["unknown"]);
    assert.equal(diagnostic.stage, "launch");
    assert.equal(diagnostic.config_sha256, "5".repeat(64));
    assert.ok(!JSON.stringify(result).includes("PRIVATE_"));
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("stderr projection emits only known categories and never raw contents", () => {
  assert.deepEqual(classifyChromeStderr("PRIVATE_SECRET unknown"), ["unknown"]);
  assert.deepEqual(
    classifyChromeStderr("PRIVATE_SECRET error while loading shared libraries libprivate.so"),
    ["missing_shared_library"],
  );
  assert.deepEqual(classifyChromeStderr("AppArmor user namespace denied PRIVATE_SECRET"), [
    "user_namespace_policy",
  ]);
});

test("hosted identity projects only checkout/head/run fields and fails closed on mismatch", async () => {
  const dir = await mkdtemp(join(tmpdir(), "identity-control-"));
  const eventPath = join(dir, "event.json");
  try {
    const local = await sourceIdentity(process.cwd(), {});
    await writeFile(
      eventPath,
      JSON.stringify({
        pull_request: {
          head: { sha: "1".repeat(40) },
          body: "PRIVATE_EVENT_SENTINEL",
        },
      }),
    );
    const env = {
      GITHUB_ACTIONS: "true",
      GITHUB_EVENT_NAME: "pull_request",
      GITHUB_EVENT_PATH: eventPath,
      GITHUB_SHA: local.checkout_sha,
      GITHUB_RUN_ID: "123",
      GITHUB_RUN_ATTEMPT: "1",
      SECRET: "PRIVATE_ENV_SENTINEL",
    };
    const hosted = await sourceIdentity(process.cwd(), env);
    assert.deepEqual(hosted, {
      checkout_sha: local.checkout_sha,
      checkout_tree: local.checkout_tree,
      candidate_sha: "1".repeat(40),
      run_id: "123",
      run_attempt: "1",
    });
    await writeFile(eventPath, JSON.stringify({ after: local.checkout_sha }));
    const push = await sourceIdentity(process.cwd(), {
      ...env,
      GITHUB_EVENT_NAME: "push",
    });
    assert.equal(push.candidate_sha, local.checkout_sha);
    await assert.rejects(sourceIdentity(process.cwd(), env), /identity/);
    await writeFile(
      eventPath,
      JSON.stringify({ pull_request: { head: { sha: "private-invalid" } } }),
    );
    await assert.rejects(sourceIdentity(process.cwd(), env), /identity/);
    await writeFile(eventPath, JSON.stringify({ pull_request: { head: { sha: "1".repeat(40) } } }));
    await assert.rejects(
      sourceIdentity(process.cwd(), { ...env, GITHUB_SHA: "9".repeat(40) }),
      /identity/,
    );
    await assert.rejects(
      sourceIdentity(process.cwd(), { ...env, GITHUB_RUN_ID: "private" }),
      /identity/,
    );
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("CLI invalid input exits nonzero before browser collection", () => {
  const result = spawnSync(
    process.execPath,
    [new URL("./lighthouse-runner.mjs", import.meta.url).pathname, "--unsupported"],
    { encoding: "utf8" },
  );
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Usage/);
});
