import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { URL } from "node:url";

// The LHCI collector chain (proxy-agent -> get-uri -> basic-ftp) and the
// extract-zip archive path were removed instead of patched. Fail closed if a
// future dependency change resolves any of them again.
const lock = readFileSync(new URL("../../pnpm-lock.yaml", import.meta.url), "utf8");
const [, graph = ""] = lock.split(/^packages:$/m);
const resolved = new Set(
  [...graph.matchAll(/^ {2}'?(@?[^@\s'][^@\s']*)@\d/gm)].map((match) => match[1]),
);

test("lockfile resolves a package graph", () => {
  assert.ok(resolved.size > 100, "unexpectedly small or unparsed lockfile");
  assert.ok(resolved.has("next"), "parser no longer sees resolved packages");
});

for (const name of ["@lhci/cli", "basic-ftp", "extract-zip", "get-uri", "proxy-agent"]) {
  test(`${name} is absent from the resolved dependency graph`, () => {
    assert.equal(resolved.has(name), false, `${name} is resolved again`);
  });
}

test("Puppeteer browser downloads extract through the patched yauzl only", () => {
  const browsers = [...graph.matchAll(/^ {2}'@puppeteer\/browsers@([\d.]+)/gm)].map((m) => m[1]);
  assert.ok(browsers.length > 0);
  const yauzl = [...graph.matchAll(/^ {2}yauzl@([\d.]+)/gm)].map((m) => m[1]);
  assert.deepEqual([...new Set(yauzl)], ["3.4.0"]);
});
