import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import test from "node:test";
import { URL } from "node:url";

const root = new URL("../../package.json", import.meta.url);
const manifest = JSON.parse(readFileSync(root, "utf8"));
const rootRequire = createRequire(root);
const lock = readFileSync(new URL("../../pnpm-lock.yaml", import.meta.url), "utf8");
function packageFrom(requireFrom, name) {
  const entry = requireFrom.resolve(name);
  let directory = dirname(entry);
  while (directory !== dirname(directory)) {
    try {
      const value = JSON.parse(readFileSync(join(directory, "package.json"), "utf8"));
      if (value.name === name) return { manifest: value, require: createRequire(entry) };
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
    directory = dirname(directory);
  }
  throw new Error(`No package manifest for ${name}`);
}

test("the direct tooling closure has no LHCI, FTP, proxy-agent or extract-zip package nodes", () => {
  assert.equal(manifest.packageManager, "pnpm@9.15.4");
  assert.equal(manifest.devDependencies.lighthouse, "13.5.0");
  assert.equal(manifest.devDependencies["chrome-launcher"], "1.2.2");
  assert.equal(manifest.devDependencies["@lhci/cli"], undefined);
  assert.equal(manifest.devDependencies.puppeteer, undefined);
  assert.equal(
    manifest.devDependencies.yauzl,
    undefined,
    "unused browser-download peer must not become a new root dependency",
  );
  assert.equal(manifest.pnpm.patchedDependencies?.["basic-ftp@5.3.1"], undefined);
  assert.doesNotMatch(
    lock,
    /^ {2}['"]?(?:@lhci\/(?:cli|utils)|basic-ftp|get-uri|extract-zip|proxy-agent|puppeteer)@/m,
  );
});
test("the installed Lighthouse uses its supported Core25/Browsers3 closure without install scripts", async () => {
  const lighthouse = packageFrom(rootRequire, "lighthouse");
  assert.equal(lighthouse.manifest.version, "13.5.0");
  assert.equal(lighthouse.manifest.engines.node, ">=22.19");
  assert.equal(lighthouse.manifest.dependencies["puppeteer-core"], "^25.9.0");
  const core = packageFrom(lighthouse.require, "puppeteer-core");
  const browsers = packageFrom(core.require, "@puppeteer/browsers");
  assert.match(core.manifest.version, /^25\./);
  assert.match(browsers.manifest.version, /^3\./);
  for (const value of [lighthouse.manifest, core.manifest, browsers.manifest]) {
    for (const event of ["preinstall", "install", "postinstall"])
      assert.equal(value.scripts?.[event], undefined);
  }
  assert.equal(typeof (await import("lighthouse")).default, "function");
});
test("performance workflow invokes the guarded adapter with an explicit existing Chrome path", () => {
  const workflow = readFileSync(
    new URL("../../.github/workflows/perf.yml", import.meta.url),
    "utf8",
  );
  const step = workflow.match(
    / {6}- name: Lighthouse performance assertions[^\n]*\n[\s\S]*?(?= {6}- name:|$)/,
  )?.[0];
  assert.ok(step);
  assert.match(step, /CHROME_PATH: \/usr\/bin\/google-chrome/);
  assert.match(step, /run: pnpm perf:lighthouse --config=lighthouserc\.json/);
  assert.doesNotMatch(
    step.replace(/^\s*#.*$/gm, ""),
    /continue-on-error|--no-sandbox|--disable-.*sandbox|--ignore-certificate|install|download|\|\| true/,
  );
  assert.match(workflow, /test -x "\$CHROME_PATH"/);
  assert.match(workflow, /pnpm perf:lighthouse:test/);
  const runner = readFileSync(new URL("./lighthouse-budget.mjs", import.meta.url), "utf8");
  assert.doesNotMatch(runner, /import\(["'](?:puppeteer|@puppeteer\/browsers)["']\)/);
});
