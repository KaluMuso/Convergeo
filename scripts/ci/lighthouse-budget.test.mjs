import assert from "node:assert/strict";
import fs from "node:fs";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  assertReports,
  collectReports,
  sanitizeDiagnostic,
} from "./lighthouse-budget.mjs";

const config = JSON.parse(
  fs.readFileSync(new URL("../../lighthouserc.json", import.meta.url)),
);
function fixture() {
  return config.ci.collect.url.flatMap((url) =>
    Array.from({ length: 3 }, () => ({
      requestedUrl: url,
      categories: {
        performance: { score: 0.9 },
        accessibility: { score: 1 },
        seo: { score: 1 },
        "best-practices": { score: 1 },
      },
      audits: { "largest-contentful-paint": { numericValue: 2000 } },
    })),
  );
}
test("complete clean five URL three run report passes", () =>
  assert.equal(assertReports(config, fixture()).passed, true));
test("missing run fails closed", () =>
  assert.throws(() => assertReports(config, fixture().slice(1)), /Incomplete/));
test("missing URL cannot be replaced by duplicate runs", () => {
  const reports = fixture();
  reports[0].requestedUrl = reports[3].requestedUrl;
  assert.throws(() => assertReports(config, reports), /Incomplete/);
});
test("runtime failure cannot pass on other good runs", () => {
  const reports = fixture();
  reports[0].runtimeError = { code: "FAILED_DOCUMENT_REQUEST" };
  assert.throws(() => assertReports(config, reports), /failed collection/);
});
test("metric absence cannot pass on other good runs", () => {
  const reports = fixture();
  delete reports[0].categories.performance;
  assert.throws(() => assertReports(config, reports), /Missing metric/);
});
test("median performance and LCP preserve budgets", () => {
  const reports = fixture();
  reports[0].categories.performance.score = 0.49;
  assert.equal(assertReports(config, reports).passed, true);
  reports[1].categories.performance.score = 0.49;
  assert.equal(assertReports(config, reports).passed, false);
  reports[0].categories.performance.score = 0.9;
  reports[0].audits["largest-contentful-paint"].numericValue = 6501;
  reports[1].audits["largest-contentful-paint"].numericValue = 6501;
  assert.equal(assertReports(config, reports).passed, false);
});
test("default optimistic score and checkout SEO warning retain LHCI semantics", () => {
  const reports = fixture();
  reports[0].categories.accessibility.score = 0.1;
  assert.equal(assertReports(config, reports).passed, true);
  for (const run of reports.filter((r) => r.requestedUrl.endsWith("/checkout")))
    run.categories.seo.score = 0;
  assert.equal(assertReports(config, reports).passed, true);
  for (const run of reports.slice(0, 3))
    run.categories.accessibility.score = 0.89;
  assert.equal(assertReports(config, reports).passed, false);
});

async function withMockCollection(makeReport, check) {
  const directory = await mkdtemp(join(tmpdir(), "lighthouse-budget-"));
  const calls = new Map();
  const launchedPorts = [];
  const killedPorts = [];
  const launch = async () => {
    const port = 9000 + launchedPorts.length;
    launchedPorts.push(port);
    return { port, kill: async () => killedPorts.push(port) };
  };
  const lighthouse = async (url, { port }) => {
    const call = (calls.get(url) ?? 0) + 1;
    calls.set(url, call);
    const lhr = {
      ...fixture().find((report) => report.requestedUrl === url),
      ...makeReport(url, call),
      lighthouseVersion: "test",
      userAgent: "mock Chrome",
    };
    return {
      lhr,
      report: [JSON.stringify(lhr), "<html></html>"],
      artifacts: {
        TraceError: {
          traceEvents: [
            {
              name: "navigationStart",
              ts: 123,
              args: {
                data: {
                  url: "http://localhost:3000/en?token=secret-local-token",
                  authorization: "Bearer secret-local-token",
                  hostedUrl: "https://private.example.com/account",
                },
              },
            },
          ],
        },
        DevtoolsLogError: [
          {
            method: "Network.requestWillBeSent",
            params: {
              request: {
                url: "http://localhost:3000/en?token=secret-local-token",
              },
            },
          },
        ],
      },
    };
  };
  try {
    const reports = await collectReports(
      config,
      { lighthouse, launch },
      directory,
    );
    const manifest = JSON.parse(
      await readFile(join(directory, "manifest.json"), "utf8"),
    );
    await check({
      reports,
      manifest,
      directory,
      calls,
      launchedPorts,
      killedPorts,
    });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

test("each required sample gets a fresh browser; all runtime errors remain blocking", async () => {
  await withMockCollection(
    (url, call) =>
      (url.endsWith("/p/smartphone-x1") && call === 3) ||
      (url.endsWith("/checkout") && call === 1)
        ? { runtimeError: { code: "NO_NAVSTART" } }
        : {},
    async ({ reports, manifest, directory, launchedPorts, killedPorts }) => {
      assert.equal(reports.length, 15);
      assert.equal(manifest.length, 15);
      assert.deepEqual(
        manifest.map(({ url, run }) => [url, run]),
        config.ci.collect.url.flatMap((url) =>
          [0, 1, 2].map((run) => [url, run]),
        ),
      );
      assert.equal(
        manifest.filter((entry) => entry.runtimeError === "NO_NAVSTART").length,
        2,
      );
      assert.equal(launchedPorts.length, 15);
      assert.deepEqual(killedPorts, launchedPorts);
      const filenames = await readdir(directory);
      assert(filenames.includes("2-2-trace.json"));
      assert(filenames.includes("4-0-devtools-log.json"));
      const diagnostic = await readFile(
        join(directory, "2-2-trace.json"),
        "utf8",
      );
      assert.match(diagnostic, /navigationStart/);
      assert.match(diagnostic, /http:\/\/localhost:3000\/en/);
      assert.doesNotMatch(
        diagnostic,
        /secret-local-token|private\.example\.com/,
      );
      assert.throws(
        () => assertReports(config, reports),
        (error) =>
          /\/p\/smartphone-x1/.test(error.message) &&
          /\/checkout/.test(error.message) &&
          /NO_NAVSTART/.test(error.message),
      );
    },
  );
});

test("Chrome is killed when Lighthouse throws before a report is produced", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lighthouse-budget-"));
  let killed = false;
  try {
    await assert.rejects(
      collectReports(
        config,
        {
          launch: async () => ({
            port: 9000,
            kill: async () => (killed = true),
          }),
          lighthouse: async () => {
            throw new Error("trace capture failed");
          },
        },
        directory,
      ),
      /trace capture failed/,
    );
    assert.equal(killed, true);
    assert.deepEqual(
      JSON.parse(await readFile(join(directory, "manifest.json"), "utf8")),
      [
        {
          url: config.ci.collect.url[0],
          run: 0,
          error: "LIGHTHOUSE_EXCEPTION",
        },
      ],
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("low performance scores never trigger a retry", async () => {
  await withMockCollection(
    (url, call) =>
      url.endsWith("/en") && call <= 2
        ? {
            categories: {
              ...fixture()[0].categories,
              performance: { score: 0.49 },
            },
          }
        : {},
    async ({ reports, manifest, launchedPorts, killedPorts }) => {
      assert.equal(reports.length, 15);
      assert.equal(manifest.length, 15);
      assert.equal(launchedPorts.length, 15);
      assert.deepEqual(killedPorts, launchedPorts);
      assert.equal(assertReports(config, reports).passed, false);
    },
  );
});

test("diagnostic sanitizer removes payloads and hosted URLs", () => {
  const result = sanitizeDiagnostic({
    name: "navigationStart",
    url: "https://private.example.com/a?key=secret",
    headers: { authorization: "Bearer secret" },
    postData: "secret body",
    method: "Network.requestWillBeSent",
  });
  assert.equal(result.name, "navigationStart");
  assert.equal(result.url, "[redacted URL]");
  assert.equal(result.headers.authorization, "[redacted]");
  assert.equal(result.postData, "[redacted]");
  assert.equal(result.method, "Network.requestWillBeSent");
});
