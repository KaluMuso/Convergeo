import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { execFile, execFileSync } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, mkdir, readFile, rm, stat, symlink, writeFile } from "node:fs/promises";
import http from "node:http";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import test from "node:test";
import { pathToFileURL } from "node:url";
import { promisify } from "node:util";

const require = createRequire(import.meta.url);
const cli = createRequire(require.resolve("@lhci/cli/package.json"));
const utils = createRequire(cli.resolve("@lhci/utils/package.json"));
const lighthouse = createRequire(utils.resolve("lighthouse/package.json"));
const puppeteer = createRequire(lighthouse.resolve("puppeteer-core/package.json"));
const browsersMain = puppeteer.resolve("@puppeteer/browsers");
const browsersRequire = createRequire(browsersMain);
const browsers = puppeteer("@puppeteer/browsers");
const fileUtil = path.join(path.dirname(browsersMain), "fileUtil.js");
const execute = promisify(execFile);

// Only tiny synthetic archives are made here. Every escape target remains inside
// an owned outer directory; no producer/browser archive is downloaded or executed.
function archive(entries) {
  let offset = 0;
  const locals = [],
    central = [];
  for (const { name, body, mode = 0o100644 } of entries) {
    const filename = Buffer.from(name),
      data = Buffer.from(body);
    let crc = 0xffffffff;
    for (const byte of data) {
      crc ^= byte;
      for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
    crc = (crc ^ 0xffffffff) >>> 0;
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50);
    local.writeUInt16LE(20, 4);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(filename.length, 26);
    locals.push(local, filename, data);
    const record = Buffer.alloc(46);
    record.writeUInt32LE(0x02014b50);
    record.writeUInt16LE(0x0314, 4);
    record.writeUInt16LE(20, 6);
    record.writeUInt32LE(crc, 16);
    record.writeUInt32LE(data.length, 20);
    record.writeUInt32LE(data.length, 24);
    record.writeUInt16LE(filename.length, 28);
    record.writeUInt32LE((mode << 16) >>> 0, 38);
    record.writeUInt32LE(offset, 42);
    central.push(record, filename);
    offset += local.length + filename.length + data.length;
  }
  const directory = Buffer.concat(central),
    end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(directory.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, directory, end]);
}

async function owned(t) {
  const root = await mkdtemp(path.join(os.tmpdir(), "extract-zip-regression-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const destination = path.join(root, "destination"),
    outside = path.join(root, "outside");
  await mkdir(destination);
  await mkdir(outside);
  const marker = path.join(outside, "marker");
  await writeFile(marker, "UNCHANGED");
  return { root, destination, marker };
}

async function extract(engine, zip, destination) {
  const code = `import {${engine} as extract} from ${JSON.stringify(pathToFileURL(fileUtil).href)}; await extract(process.argv[1], process.argv[2]);`;
  try {
    await execute(process.execPath, ["--input-type=module", "-e", code, zip, destination], {
      timeout: 3000,
      maxBuffer: 8192,
    });
    return { rejected: false };
  } catch (error) {
    // A timeout/crash is a test failure, never evidence of traversal rejection.
    assert.equal(error.killed, false);
    assert.equal(error.signal, null);
    assert.equal(error.code, 1);
    assert.match(error.stderr, /Extraction failed/);
    return { rejected: true };
  }
}

test("the actual pinned Puppeteer CJS caller loads the supported ESM browsers package", async () => {
  assert.equal(
    JSON.parse(await readFile(path.join(path.dirname(browsersMain), "../package.json"))).version,
    "3.2.6",
  );
  const peer = browsersRequire("proxy-agent");
  assert.equal(typeof peer.ProxyAgent, "function");
  assert.match(browsersRequire.resolve("proxy-agent"), /proxy-agent@8\.0\.1/);
  assert.equal(typeof lighthouse("puppeteer-core").defaultArgs, "function");
  for (const key of [
    "createProfile",
    "computeSystemExecutablePath",
    "detectBrowserPlatform",
    "getInstalledBrowsers",
    "resolveBuildId",
    "uninstall",
    "launch",
    "computeExecutablePath",
    "TimeoutError",
  ])
    assert.equal(typeof browsers[key], "function", key);
  assert.ok(browsers.CDP_WEBSOCKET_ENDPOINT_REGEX instanceof RegExp);
  assert.ok(browsers.WEBDRIVER_BIDI_WEBSOCKET_ENDPOINT_REGEX instanceof RegExp);
  const esm = await import(pathToFileURL(browsersMain).href);
  assert.equal(esm.computeExecutablePath, browsers.computeExecutablePath);
});

test("Puppeteer path/default-argument and empty-cache APIs work without launching a browser", async (t) => {
  const { root } = await owned(t);
  const executable = browsers.computeExecutablePath({
    cacheDir: root,
    browser: browsers.Browser.CHROME,
    platform: browsers.BrowserPlatform.LINUX,
    buildId: "155.0.8059.39",
  });
  assert.equal(
    executable,
    path.join(root, "chrome", "linux-155.0.8059.39", "chrome-linux64", "chrome"),
  );
  assert.deepEqual(await browsers.getInstalledBrowsers({ cacheDir: root }), []);
  const args = lighthouse("puppeteer-core").defaultArgs({
    headless: true,
    userDataDir: path.join(root, "profile"),
  });
  assert.ok(args.includes(`--user-data-dir=${path.join(root, "profile")}`));
  assert.ok(!args.includes("--no-sandbox") && !args.includes("--ignore-certificate-errors"));
});

for (const engine of ["unpackArchive", "extractZipWithYauzl"]) {
  test(
    `${engine}: nested file, executable mode and safe relative symlink remain usable`,
    { timeout: 5000 },
    async (t) => {
      const { root, destination } = await owned(t);
      const zip = path.join(root, "fixture.zip");
      await writeFile(
        zip,
        archive([
          { name: "folder/file", body: "fixture", mode: 0o100755 },
          { name: "link", body: "folder/file", mode: 0o120777 },
        ]),
      );
      assert.equal((await extract(engine, zip, destination)).rejected, false);
      assert.equal(await readFile(path.join(destination, "link"), "utf8"), "fixture");
      // The Node fallback honors the process umask; native unzip restores the mode.
      const expectedMode = engine === "extractZipWithYauzl" ? 0o755 & ~process.umask() : 0o755;
      assert.equal((await stat(path.join(destination, "folder/file"))).mode & 0o777, expectedMode);
    },
  );
  for (const kind of [
    "duplicate-final-symlink",
    "symlink-directory",
    "preexisting-final-symlink",
    "dotdot",
    "absolute",
  ]) {
    test(
      `${engine}: ${kind} cannot overwrite the owned outside marker`,
      { timeout: 5000 },
      async (t) => {
        const { root, destination, marker } = await owned(t);
        const zip = path.join(root, "fixture.zip");
        let entries;
        if (kind === "duplicate-final-symlink")
          entries = [
            { name: "link", body: "../outside/marker", mode: 0o120777 },
            { name: "link", body: "MALICIOUS" },
          ];
        else if (kind === "symlink-directory")
          entries = [
            { name: "escape", body: "../outside", mode: 0o120777 },
            { name: "escape/marker", body: "MALICIOUS" },
          ];
        else if (kind === "preexisting-final-symlink") {
          await symlink(marker, path.join(destination, "link"));
          entries = [{ name: "link", body: "MALICIOUS" }];
        } else
          entries = [
            { name: kind === "absolute" ? marker : "../outside/marker", body: "MALICIOUS" },
          ];
        await writeFile(zip, archive(entries));
        const result = await extract(engine, zip, destination);
        if (engine === "extractZipWithYauzl") assert.equal(result.rejected, true);
        assert.equal(await readFile(marker, "utf8"), "UNCHANGED");
      },
    );
  }
}

test(
  "the actual LHCI fetch caller preserves direct, proxy and NO_PROXY routing",
  { timeout: 8000 },
  async (t) => {
    const listen = async (body) => {
      const server = http.createServer((request, response) => response.end(body));
      server.listen(0, "127.0.0.1");
      await once(server, "listening");
      t.after(() => new Promise((resolve) => server.close(resolve)));
      return `http://127.0.0.1:${server.address().port}`;
    };
    const target = await listen("DIRECT"),
      proxy = await listen("PROXY");
    const caller = cli.resolve("./src/fetch.js");
    const script = `const fetch=require(${JSON.stringify(caller)}); fetch(process.argv[1]).then(r=>r.text()).then(s=>console.log(s)).catch(e=>{console.error(e.message);process.exitCode=1});`;
    const env = { ...process.env };
    for (const key of [
      "HTTP_PROXY",
      "HTTPS_PROXY",
      "ALL_PROXY",
      "NO_PROXY",
      "http_proxy",
      "https_proxy",
      "all_proxy",
      "no_proxy",
    ])
      env[key] = "";
    for (const [overrides, expected] of [
      [{}, "DIRECT"],
      [{ HTTP_PROXY: proxy }, "PROXY"],
      [{ HTTP_PROXY: proxy, NO_PROXY: "127.0.0.1" }, "DIRECT"],
    ]) {
      const result = await execute(process.execPath, ["-e", script, target], {
        env: { ...env, ...overrides },
        timeout: 1500,
        maxBuffer: 8192,
      });
      assert.equal(result.stdout.trim(), expected);
    }
  },
);

test("the actual LHCI CLI still loads without browser execution", () => {
  const result = execFileSync(process.execPath, [cli.resolve("./src/cli.js"), "--help"], {
    encoding: "utf8",
    timeout: 3000,
    maxBuffer: 8192,
  });
  assert.match(result, /collect/);
});

test(
  "the actual LHCI caller evaluates loopback PAC DIRECT and PROXY selections",
  { timeout: 8000 },
  async (t) => {
    const requests = { target: 0, proxy: 0, pac: 0 };
    const listen = async (name, content) => {
      const server = http.createServer((request, response) => {
        requests[name]++;
        response.end(content());
      });
      server.listen(0, "127.0.0.1");
      await once(server, "listening");
      t.after(() => new Promise((resolve) => server.close(resolve)));
      return server.address().port;
    };
    const target = await listen("target", () => "DIRECT");
    const proxy = await listen("proxy", () => "PROXY");
    const pac = await listen(
      "pac",
      () =>
        `function FindProxyForURL(url, host) { return url.indexOf('/direct') !== -1 ? 'DIRECT' : 'PROXY 127.0.0.1:${proxy}'; }`,
    );
    const caller = cli.resolve("./src/fetch.js");
    const script = `const fetch=require(${JSON.stringify(caller)}); fetch(process.argv[1]).then(r=>r.text()).then(s=>console.log(s)).catch(e=>{console.error(e.message);process.exitCode=1});`;
    const env = { ...process.env };
    for (const key of [
      "HTTP_PROXY",
      "HTTPS_PROXY",
      "ALL_PROXY",
      "NO_PROXY",
      "http_proxy",
      "https_proxy",
      "all_proxy",
      "no_proxy",
    ])
      env[key] = "";
    env.HTTP_PROXY = `pac+http://127.0.0.1:${pac}/fixture.pac`;
    for (const [route, expected] of [
      ["direct", "DIRECT"],
      ["proxy", "PROXY"],
    ]) {
      const result = await execute(
        process.execPath,
        ["-e", script, `http://127.0.0.1:${target}/${route}`],
        { env, timeout: 2500, maxBuffer: 8192 },
      );
      assert.equal(result.stdout.trim(), expected);
    }
    assert.equal(requests.pac, 2);
    assert.equal(requests.target, 1);
    assert.equal(requests.proxy, 1);
  },
);
