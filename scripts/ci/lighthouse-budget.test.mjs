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
  summarizeNavigationDiagnostic,
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
  const diagnostics = [];
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
      {
        lighthouse,
        launch,
        logDiagnostic: (...parts) => diagnostics.push(parts.join(" ")),
      },
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
      diagnostics,
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
    async ({
      reports,
      manifest,
      directory,
      launchedPorts,
      killedPorts,
      diagnostics,
    }) => {
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
      assert.equal(diagnostics.length, 2);
      assert(diagnostics.every((line) => line.includes("NO_NAVSTART")));
      assert(diagnostics.every((line) => !line.includes("secret-local-token")));
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

test("navigation diagnostic distinguishes absent, other-frame, and rejected URL", () => {
  const browserStart = {
    name: "TracingStartedInBrowser",
    cat: "devtools.timeline",
    args: { data: { frames: [{ frame: "main-secret", processId: 1 }] } },
  };
  const navStart = (frame, documentLoaderURL) => ({
    name: "navigationStart",
    cat: "loading",
    args: { data: { frame, documentLoaderURL } },
  });
  const messages = [
    {
      method: "Network.responseReceived",
      params: {
        type: "Document",
        response: { status: 200, url: "https://secret.example.com" },
      },
    },
  ];
  const summarize = (...events) =>
    summarizeNavigationDiagnostic(
      { traceEvents: [browserStart, ...events] },
      messages,
    );
  assert.equal(summarize().diagnosis, "navigation-start-absent");
  assert.equal(
    summarize(navStart("other-secret", "http://localhost:3000/en")).diagnosis,
    "navigation-start-other-frame",
  );
  assert.equal(
    summarize(navStart("main-secret", "about:blank")).diagnosis,
    "navigation-start-url-rejected",
  );
  const accepted = summarize(
    navStart("main-secret", "http://localhost:3000/en?token=secret"),
  );
  assert.equal(
    accepted.diagnosis,
    "navigation-start-present-check-trace-processing",
  );
  assert.deepEqual(accepted.documentResponseStatuses, [200]);
  assert.doesNotMatch(
    JSON.stringify(accepted),
    /main-secret|other-secret|secret\.example|token=secret/,
  );
  assert.equal(
    summarizeNavigationDiagnostic(undefined, undefined).diagnosis,
    "trace-unavailable",
  );
});

test("navigation aliases preserve frame equality without exposing identifiers", () => {
  const trace = {
    traceEvents: [
      {
        name: "TracingStartedInBrowser",
        cat: "devtools.timeline",
        args: {
          data: {
            frames: [
              { frame: "private-root-id", processId: 41 },
              {
                frame: "private-child-id",
                parent: "private-root-id",
                processId: 42,
              },
            ],
          },
        },
      },
      {
        name: "FrameCommittedInBrowser",
        cat: "devtools.timeline",
        pid: 41,
        ts: 180,
        args: {
          data: {
            frame: "private-child-id",
            processId: 42,
            url: "https://private.example.com/secret",
            headers: { authorization: "Bearer private-token" },
          },
        },
      },
      {
        name: "navigationStart",
        cat: "loading",
        pid: 42,
        tid: 7,
        ts: 200,
        args: {
          data: {
            frame: "private-child-id",
            documentLoaderURL:
              "http://localhost:3000/en/search?token=private-token",
            isLoadingMainFrame: true,
          },
        },
      },
    ],
  };
  const result = summarizeNavigationDiagnostic(trace, []);
  assert.equal(result.selectedMainFrameAlias, "frame-1");
  assert.equal(result.selectedMainFramePid, 41);
  assert.deepEqual(result.browserFrameMarkers, [
    { alias: "frame-1", processId: 41, isRoot: true },
    { alias: "frame-2", processId: 42, isRoot: false },
  ]);
  assert.deepEqual(result.navigationMarkers, [
    {
      alias: "frame-2",
      pid: 42,
      tid: 7,
      ts: 200,
      isLoadingMainFrame: true,
    },
  ]);
  assert.equal(result.frameProcessMarkers[0].alias, "frame-2");
  assert.equal(result.frameProcessMarkers[0].processId, 42);
  assert.equal(result.diagnosis, "navigation-start-other-frame");
  assert.equal(
    summarizeNavigationDiagnostic(trace, []).selectedMainFrameAlias,
    "frame-1",
  );
  assert.equal(
    summarizeNavigationDiagnostic(
      {
        traceEvents: [
          {
            name: "TracingStartedInBrowser",
            cat: "devtools.timeline",
            args: {
              data: { frames: [{ frame: "another-private-id", processId: 9 }] },
            },
          },
        ],
      },
      [],
    ).selectedMainFrameAlias,
    "frame-1",
  );
  assert.doesNotMatch(
    JSON.stringify(result),
    /private-root-id|private-child-id|private-token|private\.example\.com/,
  );
});

test("navigation diagnostic bounds marker output and tolerates malformed frames", () => {
  const trace = {
    traceEvents: [
      {
        name: "TracingStartedInBrowser",
        cat: "devtools.timeline",
        args: { data: { frames: "invalid" } },
      },
      ...Array.from({ length: 10 }, (_, index) => ({
        name: "navigationStart",
        cat: "loading",
        pid: index,
        ts: index,
        args: { data: { frame: `private-${index}` } },
      })),
    ],
  };
  const result = summarizeNavigationDiagnostic(trace, []);
  assert.equal(result.mainFrameSource, "unresolved");
  assert.equal(result.navigationStartCount, 10);
  assert.equal(result.navigationMarkers.length, 8);
  assert.equal(result.navigationMarkersTruncated, true);
  assert.equal(result.navigationMarkers[0].pid, 2);
  assert.doesNotMatch(JSON.stringify(result), /private-/);
});

test("document response statuses stay bounded without losing their total", () => {
  const messages = Array.from({ length: 12 }, (_, index) => ({
    method: "Network.responseReceived",
    params: { type: "Document", response: { status: 200 + index } },
  }));
  const result = summarizeNavigationDiagnostic(undefined, messages);
  assert.equal(result.documentResponseStatusCount, 12);
  assert.deepEqual(
    result.documentResponseStatuses,
    [204, 205, 206, 207, 208, 209, 210, 211],
  );
  assert.equal(result.documentResponseStatusesTruncated, true);
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
