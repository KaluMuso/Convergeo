import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { assertReports } from "./lighthouse-budget.mjs";

const config = JSON.parse(fs.readFileSync(new URL("../../lighthouserc.json", import.meta.url)));
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
  for (const run of reports.slice(0, 3)) run.categories.accessibility.score = 0.89;
  assert.equal(assertReports(config, reports).passed, false);
});
