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
  for (const url of collect.url) {
    const runs = reports.filter((report) => report.requestedUrl === url);
    if (runs.length !== collect.numberOfRuns || runs.some((r) => r.runtimeError)) {
      throw new Error(`Incomplete or failed collection: ${url}`);
    }
    const matches = assertions.assertMatrix.filter((entry) =>
      new RegExp(entry.matchingUrlPattern).test(url),
    );
    if (matches.length !== 1) throw new Error(`Expected one assertion matrix entry: ${url}`);
    for (const [metric, [level, options]] of Object.entries(matches[0].assertions)) {
      if (!["error", "warn"].includes(level))
        throw new Error(`Unsupported assertion level: ${level}`);
      const keys = Object.keys(options).filter((key) => key !== "aggregationMethod");
      if (keys.length !== 1 || !["minScore", "maxNumericValue"].includes(keys[0])) {
        throw new Error(`Unsupported budget: ${metric}`);
      }
      const kind = keys[0];
      const values = runs.map((run) =>
        metric.startsWith("categories:")
          ? run.categories?.[metric.slice(11)]?.score
          : run.audits?.[metric]?.[kind === "minScore" ? "score" : "numericValue"],
      );
      if (values.some((value) => typeof value !== "number" || !Number.isFinite(value))) {
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
      if (!Number.isFinite(expected)) throw new Error(`Invalid threshold: ${metric}`);
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
  return { passed: results.every((result) => result.passed || result.level === "warn"), results };
}

export async function collect(config) {
  const { default: lighthouse } = await import("lighthouse");
  const { launch } = await import("chrome-launcher");
  const root = config.ci.upload.outputDir;
  if (config.ci.upload.target !== "filesystem")
    throw new Error("Only filesystem report retention is supported");
  const directory = path.join(root, new Date().toISOString().replaceAll(":", "-"));
  await fs.mkdir(directory, { recursive: true });
  const browser = await launch({
    chromePath: process.env.CHROME_PATH,
    chromeFlags: ["--headless", "--disable-gpu", ...(process.env.CI ? ["--no-sandbox"] : [])],
  });
  const reports = [];
  const manifest = [];
  try {
    for (const [index, url] of config.ci.collect.url.entries()) {
      for (let run = 0; run < config.ci.collect.numberOfRuns; run++) {
        const result = await lighthouse(url, {
          ...config.ci.collect.settings,
          port: browser.port,
          output: ["json", "html"],
          logLevel: "error",
        });
        if (!result) throw new Error(`No Lighthouse result: ${url}`);
        const jsonPath = path.join(directory, `${index}-${run}.json`);
        const htmlPath = path.join(directory, `${index}-${run}.html`);
        await fs.writeFile(jsonPath, JSON.stringify(result.lhr, null, 2));
        await fs.writeFile(htmlPath, result.report[1]);
        manifest.push({
          url,
          run,
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
    const assertions = assertReports(config, reports);
    await fs.writeFile(
      path.join(directory, "assertion-results.json"),
      JSON.stringify(assertions, null, 2),
    );
    console.log(JSON.stringify({ directory, ...assertions }, null, 2));
    return assertions.passed;
  } finally {
    await browser.kill();
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const config = JSON.parse(await fs.readFile("lighthouserc.json", "utf8"));
    process.exitCode = (await collect(config)) ? 0 : 1;
  } catch (error) {
    console.error(error);
    process.exitCode = 2;
  }
}
