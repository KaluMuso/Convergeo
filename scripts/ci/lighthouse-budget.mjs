import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

// This deliberately implements only our checked-in assertion contract. Unknown
// assertions fail closed instead of silently weakening a future budget change.
export function assertReports(config, reports) {
  const { collect, assert: assertions } = config.ci;
  const results = [];
  if (reports.length !== collect.url.length * collect.numberOfRuns) {
    throw new Error("Incomplete collection: unexpected report count");
  }
  const failedCollections = [];
  for (const url of collect.url) {
    const runs = reports.filter((report) => report.requestedUrl === url);
    if (
      runs.length !== collect.numberOfRuns ||
      runs.some((r) => r.runtimeError)
    ) {
      const errors = runs.flatMap((report, run) =>
        report.runtimeError
          ? [`run ${run + 1}: ${report.runtimeError.code ?? "runtime error"}`]
          : [],
      );
      failedCollections.push(
        `${url} (${runs.length}/${collect.numberOfRuns} runs${errors.length ? `; ${errors.join(", ")}` : ""})`,
      );
    }
  }
  if (failedCollections.length) {
    throw new Error(
      `Incomplete or failed collection: ${failedCollections.join("; ")}`,
    );
  }
  for (const url of collect.url) {
    const runs = reports.filter((report) => report.requestedUrl === url);
    const matches = assertions.assertMatrix.filter((entry) =>
      new RegExp(entry.matchingUrlPattern).test(url),
    );
    if (matches.length !== 1)
      throw new Error(`Expected one assertion matrix entry: ${url}`);
    for (const [metric, [level, options]] of Object.entries(
      matches[0].assertions,
    )) {
      if (!["error", "warn"].includes(level))
        throw new Error(`Unsupported assertion level: ${level}`);
      const keys = Object.keys(options).filter(
        (key) => key !== "aggregationMethod",
      );
      if (
        keys.length !== 1 ||
        !["minScore", "maxNumericValue"].includes(keys[0])
      ) {
        throw new Error(`Unsupported budget: ${metric}`);
      }
      const kind = keys[0];
      const values = runs.map((run) =>
        metric.startsWith("categories:")
          ? run.categories?.[metric.slice(11)]?.score
          : run.audits?.[metric]?.[
              kind === "minScore" ? "score" : "numericValue"
            ],
      );
      if (
        values.some(
          (value) => typeof value !== "number" || !Number.isFinite(value),
        )
      ) {
        throw new Error(`Missing metric: ${url} ${metric}`);
      }
      const method = options.aggregationMethod ?? "optimistic";
      if (!["median", "optimistic", "pessimistic"].includes(method))
        throw new Error(`Unsupported aggregation: ${method}`);
      const sorted = [...values].sort((a, b) => a - b);
      const mid = Math.floor(sorted.length / 2);
      const actual =
        method === "median"
          ? sorted.length % 2
            ? sorted[mid]
            : (sorted[mid - 1] + sorted[mid]) / 2
          : (method === "optimistic") === (kind === "minScore")
            ? Math.max(...values)
            : Math.min(...values);
      const expected = options[kind];
      if (!Number.isFinite(expected))
        throw new Error(`Invalid threshold: ${metric}`);
      results.push({
        url,
        metric,
        level,
        method,
        values,
        actual,
        expected,
        passed: kind === "minScore" ? actual >= expected : actual <= expected,
      });
    }
  }
  return {
    passed: results.every((result) => result.passed || result.level === "warn"),
    results,
  };
}

// Keep trace structure and timing while removing payloads, headers and hosted
// URLs before diagnostic artifacts are uploaded from CI.
const DIAGNOSTIC_TRACE_NAMES = new Set([
  "TracingStartedInBrowser",
  "TracingStartedInPage",
  "navigationStart",
  "ResourceSendRequest",
  "FrameCommittedInBrowser",
  "ProcessReadyInBrowser",
  "thread_name",
  "process_name",
]);

export function sanitizeDiagnostic(value, key = "") {
  if (Array.isArray(value))
    return value.map((item) => sanitizeDiagnostic(item));
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([childKey, childValue]) => [
        childKey,
        sanitizeDiagnostic(childValue, childKey),
      ]),
    );
  }
  if (typeof value !== "string") return value;
  if (/url$/i.test(key)) {
    try {
      const url = new URL(value);
      return ["localhost", "127.0.0.1"].includes(url.hostname)
        ? `${url.origin}${url.pathname}`
        : "[redacted URL]";
    } catch {
      return "[redacted URL]";
    }
  }
  if (key === "name" && DIAGNOSTIC_TRACE_NAMES.has(value)) return value;
  if (
    key === "method" &&
    /^(Network|Page|Runtime|Tracing|Target)\.[A-Za-z0-9]+$/.test(value)
  )
    return value;
  if (key === "ph" && /^[A-Z]$/.test(value)) return value;
  return "[redacted]";
}

// A failed navigation can still have trace and DevTools data. Emit only counts
// and fixed labels so CI logs remain useful when artifact downloads are blocked.
export function summarizeNavigationDiagnostic(trace, devtoolsLog) {
  const events = Array.isArray(trace?.traceEvents) ? trace.traceEvents : [];
  const messages = Array.isArray(devtoolsLog) ? devtoolsLog : [];
  const isKeyEvent = (event) =>
    typeof event?.cat === "string" &&
    (event.cat.includes("blink.user_timing") ||
      event.cat.includes("loading") ||
      event.cat.includes("devtools.timeline") ||
      event.cat === "__metadata");
  const frameId = (event) =>
    event.args?.data?.frame ?? event.args?.data?.frameID ?? event.args?.frame;
  const keyEvents = events.filter(isKeyEvent);
  const browserStart = keyEvents.find(
    (event) => event.name === "TracingStartedInBrowser",
  );
  const browserMainFrame = browserStart?.args?.data?.frames?.find(
    (frame) => !frame.parent,
  );
  const pageStart = keyEvents.find(
    (event) => event.name === "TracingStartedInPage",
  );
  const mainFrame =
    browserMainFrame?.processId && browserMainFrame?.frame
      ? browserMainFrame.frame
      : pageStart?.args?.data?.page;
  const mainFrameSource =
    browserMainFrame?.processId && browserMainFrame?.frame
      ? "browser"
      : mainFrame
        ? "page"
        : "unresolved";
  const navStarts = keyEvents.filter(
    (event) => event.name === "navigationStart",
  );
  const mainFrameNavStarts = mainFrame
    ? navStarts.filter((event) => frameId(event) === mainFrame)
    : [];
  const acceptableMainFrameNavStarts = mainFrameNavStarts.filter((event) => {
    const url = event.args?.data?.documentLoaderURL;
    return url === undefined || /^https?:|^chrome:/.test(url);
  });
  const documentStatuses = messages
    .filter(
      (message) =>
        message.method === "Network.responseReceived" &&
        message.params?.type === "Document",
    )
    .map((message) => message.params?.response?.status)
    .filter((status) => Number.isInteger(status));
  return {
    traceEventCount: events.length,
    keyEventCount: keyEvents.length,
    mainFrameSource,
    navigationStartCount: navStarts.length,
    mainFrameNavigationStartCount: mainFrameNavStarts.length,
    acceptableMainFrameNavigationStartCount:
      acceptableMainFrameNavStarts.length,
    documentResponseStatuses: documentStatuses,
    devtoolsMessageCount: messages.length,
    diagnosis: !events.length
      ? "trace-unavailable"
      : !mainFrame
        ? "main-frame-unresolved"
        : !navStarts.length
          ? "navigation-start-absent"
          : !mainFrameNavStarts.length
            ? "navigation-start-other-frame"
            : !acceptableMainFrameNavStarts.length
              ? "navigation-start-url-rejected"
              : "navigation-start-present-check-trace-processing",
  };
}

// Every required measurement gets a fresh Chrome process. Failed runs stay in
// the report set, so the budget check cannot pass on a replacement sample.
export async function collectReports(
  config,
  { lighthouse, launch, logDiagnostic = console.error },
  directory,
) {
  const reports = [];
  const manifest = [];
  for (const [index, url] of config.ci.collect.url.entries()) {
    for (let run = 0; run < config.ci.collect.numberOfRuns; run++) {
      const browser = await launch({
        chromePath: process.env.CHROME_PATH,
        chromeFlags: [
          "--headless",
          "--disable-gpu",
          ...(process.env.CI ? ["--no-sandbox"] : []),
        ],
      });
      let result;
      let collectionError;
      try {
        result = await lighthouse(url, {
          ...config.ci.collect.settings,
          port: browser.port,
          output: ["json", "html"],
          logLevel: "error",
        });
      } catch (error) {
        collectionError = error;
      } finally {
        await browser.kill();
      }
      if (collectionError) {
        manifest.push({ url, run, error: "LIGHTHOUSE_EXCEPTION" });
        await fs.writeFile(
          path.join(directory, "manifest.json"),
          JSON.stringify(manifest, null, 2),
        );
        throw collectionError;
      }
      if (!result) {
        manifest.push({ url, run, error: "NO_LIGHTHOUSE_RESULT" });
        await fs.writeFile(
          path.join(directory, "manifest.json"),
          JSON.stringify(manifest, null, 2),
        );
        throw new Error(`No Lighthouse result: ${url}`);
      }
      const runtimeError = result.lhr.runtimeError;
      const jsonPath = path.join(directory, `${index}-${run}.json`);
      const htmlPath = path.join(directory, `${index}-${run}.html`);
      await fs.writeFile(jsonPath, JSON.stringify(result.lhr, null, 2));
      await fs.writeFile(htmlPath, result.report[1]);
      if (runtimeError) {
        if (runtimeError.code === "NO_NAVSTART") {
          logDiagnostic(
            "Lighthouse NO_NAVSTART diagnostic:",
            JSON.stringify(
              summarizeNavigationDiagnostic(
                result.artifacts?.TraceError ?? result.artifacts?.Trace,
                result.artifacts?.DevtoolsLogError ??
                  result.artifacts?.DevtoolsLog,
              ),
            ),
          );
        }
        for (const [name, artifact] of [
          ["trace", result.artifacts?.TraceError ?? result.artifacts?.Trace],
          [
            "devtools-log",
            result.artifacts?.DevtoolsLogError ?? result.artifacts?.DevtoolsLog,
          ],
        ]) {
          if (artifact) {
            await fs.writeFile(
              path.join(directory, `${index}-${run}-${name}.json`),
              JSON.stringify(sanitizeDiagnostic(artifact)),
            );
          }
        }
      }
      manifest.push({
        url,
        run,
        runtimeError: runtimeError?.code,
        jsonPath,
        htmlPath,
        lighthouseVersion: result.lhr.lighthouseVersion,
        userAgent: result.lhr.userAgent,
      });
      await fs.writeFile(
        path.join(directory, "manifest.json"),
        JSON.stringify(manifest, null, 2),
      );
      reports.push(result.lhr);
    }
  }
  return reports;
}

export async function collect(config) {
  const { default: lighthouse } = await import("lighthouse");
  const { launch } = await import("chrome-launcher");
  const root = config.ci.upload.outputDir;
  if (config.ci.upload.target !== "filesystem")
    throw new Error("Only filesystem report retention is supported");
  const directory = path.join(
    root,
    new Date().toISOString().replaceAll(":", "-"),
  );
  await fs.mkdir(directory, { recursive: true });
  const reports = await collectReports(
    config,
    { lighthouse, launch },
    directory,
  );
  const assertions = assertReports(config, reports);
  await fs.writeFile(
    path.join(directory, "assertion-results.json"),
    JSON.stringify(assertions, null, 2),
  );
  console.log(JSON.stringify({ directory, ...assertions }, null, 2));
  return assertions.passed;
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  try {
    const config = JSON.parse(await fs.readFile("lighthouserc.json", "utf8"));
    process.exitCode = (await collect(config)) ? 0 : 1;
  } catch (error) {
    console.error(error);
    process.exitCode = 2;
  }
}
