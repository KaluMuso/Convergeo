import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workflow = readFileSync(new URL("../../.github/workflows/perf.yml", import.meta.url), "utf8");
const config = JSON.parse(readFileSync(new URL("../../lighthouserc.json", import.meta.url), "utf8"));

function checkReportUpload(source) {
  const step = source.match(/      - name: Upload Lighthouse reports\r?\n[\s\S]*?(?=\r?\n      - name:|$)/)?.[0];
  assert.ok(step, "report upload step must exist");
  assert.match(step, /^        if: always\(\)\s*$/m, "assertion failure must retain reports");
  assert.match(step, /^        uses: actions\/upload-artifact@/m);
  assert.match(step, /^          include-hidden-files: true\s*$/m, "dot-directory reports must be included");
  assert.match(step, /^          path: \.lighthouseci\s*$/m, "upload must remain confined to report directory");
  assert.equal(config.ci.upload.target, "filesystem");
  assert.equal(config.ci.upload.outputDir, ".lighthouseci");
}

test("failed Lighthouse assertions still retain the configured hidden report directory", () => {
  checkReportUpload(workflow);
});

test("negative control: default hidden-file exclusion is rejected", () => {
  assert.throws(() => checkReportUpload(workflow.replace("include-hidden-files: true", "include-hidden-files: false")), /dot-directory reports/);
});

test("negative control: omitted hidden-file option is rejected", () => {
  assert.throws(() => checkReportUpload(workflow.replace("include-hidden-files: true", "")), /dot-directory reports/);
});

test("negative control: broad upload scope is rejected", () => {
  assert.throws(() => checkReportUpload(workflow.replace("path: .lighthouseci", "path: .")), /confined/);
});

test("negative control: success-only report retention is rejected", () => {
  const marker = workflow.indexOf("      - name: Upload Lighthouse reports");
  const changed = workflow.slice(0, marker) + workflow.slice(marker).replace("if: always()", "if: success()");
  assert.throws(() => checkReportUpload(changed), /assertion failure/);
});
