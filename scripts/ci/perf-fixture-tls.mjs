/** PR758-only hosted experiment. Importing this module performs no operations. */
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import * as fs from "node:fs";
import http from "node:http";
import https from "node:https";
import { createRequire } from "node:module";
import { homedir } from "node:os";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { pathToFileURL } from "node:url";

const WEB = "http://localhost:3000";
const CSP =
  "base-uri 'self'; object-src 'none'; frame-ancestors 'self'; form-action 'self'; upgrade-insecure-requests";
const checkout = path.resolve(import.meta.dirname, "../..");
const require = createRequire(import.meta.url);
const command = (bin, args, options = {}) =>
  execFileSync(bin, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
  }).trim();

export function requireHosted(env) {
  for (const [key, value] of Object.entries({
    GITHUB_ACTIONS: "true",
    RUNNER_ENVIRONMENT: "github-hosted",
    GITHUB_REPOSITORY: "KaluMuso/Convergeo",
    GITHUB_JOB: "perf",
    GITHUB_EVENT_NAME: "pull_request",
    GITHUB_BASE_REF: "master",
    GITHUB_HEAD_REF: "codex/phone-preservation-qualification-20261026",
    GITHUB_REF: "refs/pull/758/merge",
  }))
    assert.equal(env[key], value, "Unadmitted hosted input: " + key);
  assert.ok(env.RUNNER_TEMP && path.isAbsolute(env.RUNNER_TEMP));
  assert.match(env.GITHUB_RUN_ID ?? "", /^\d+$/);
  assert.match(env.GITHUB_RUN_ATTEMPT ?? "", /^\d+$/);
  for (const key of [
    "NODE_TLS_REJECT_UNAUTHORIZED",
    "PUPPETEER_DANGEROUS_NO_SANDBOX",
    "PW_CHROMIUM_PATH",
    "VERCEL_AUTOMATION_BYPASS_SECRET",
  ])
    assert.ok(!env[key], "Unadmitted browser/TLS override: " + key);
}

export function validateArguments(args) {
  for (const arg of args)
    assert.ok(
      !/^--(?:no-sandbox|disable-setuid-sandbox|ignore-certificate-errors|ignore-ssl-errors|allow-insecure-localhost|disable-web-security|allow-running-insecure-content|unsafely-treat-insecure-origin-as-secure|disable-site-isolation-trials)(?:=|$)/.test(
        arg,
      ) &&
        !arg.includes("ignore-certificate-errors-spki-list") &&
        !(
          /^--disable-features=/.test(arg) &&
          /LocalNetworkAccess|PrivateNetworkAccess|OutOfBlinkCors|IsolateOrigins/.test(arg)
        ),
      "Unsafe browser argument",
    );
}

function directory() {
  return path.join(
    process.env.RUNNER_TEMP,
    "convergeo-perf-" + process.env.GITHUB_RUN_ID + "-" + process.env.GITHUB_RUN_ATTEMPT,
  );
}
function receipt(name, value) {
  const dest = path.join(checkout, "perf-fixture-receipts");
  fs.mkdirSync(dest, { recursive: true, mode: 0o700 });
  fs.writeFileSync(
    path.join(dest, name + ".json"),
    JSON.stringify({ observed: new Date().toISOString(), ...value }, null, 2) + "\n",
    { mode: 0o600 },
  );
}
function save(state) {
  fs.writeFileSync(path.join(state.dir, "state.json"), JSON.stringify(state), { mode: 0o600 });
}
function optionalStat(file) {
  try {
    return fs.lstatSync(file);
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}
function ownedDirectory(file) {
  const stat = fs.lstatSync(file);
  assert.ok(stat.isDirectory() && !stat.isSymbolicLink(), "Refuse redirected directory");
  assert.equal(stat.uid, process.getuid(), "Directory not owned by this runner user");
  assert.equal(fs.realpathSync(file), file, "Refuse redirected directory ancestor");
}
function validateNssParents() {
  ownedDirectory(homedir());
  for (const relative of [".pki", ".local", ".local/share", ".local/share/pki"]) {
    const file = path.join(homedir(), relative);
    if (optionalStat(file)) ownedDirectory(file);
  }
}
function validateOwnedNss(state) {
  validateNssParents();
  ownedDirectory(state.nss);
  const marker = path.join(state.nss, ".convergeo-owner");
  const stat = fs.lstatSync(marker);
  assert.ok(stat.isFile() && !stat.isSymbolicLink());
  assert.equal(stat.uid, process.getuid());
  assert.equal(fs.readFileSync(marker, "utf8"), state.owner);
}
function load(checkNss = true) {
  const state = JSON.parse(fs.readFileSync(path.join(directory(), "state.json"), "utf8"));
  assert.equal(state.dir, directory());
  assert.equal(state.nss, path.join(homedir(), ".pki/nssdb"));
  assert.equal(fs.realpathSync(state.dir), state.dir);
  assert.equal(fs.lstatSync(state.dir).uid, process.getuid());
  assert.equal(state.owner, path.basename(directory()));
  if (state.createdNss && checkNss) validateOwnedNss(state);
  return state;
}
function dependencies() {
  const cliPackage = require.resolve("@lhci/cli/package.json");
  const cliRequire = createRequire(cliPackage);
  const lhRequire = createRequire(cliRequire.resolve("lighthouse/package.json"));
  const e2eRequire = createRequire(path.join(checkout, "e2e/package.json"));
  assert.equal(e2eRequire("@playwright/test/package.json").version, "1.56.1");
  assert.equal(lhRequire("puppeteer-core/package.json").version, "24.43.1");
  assert.equal(lhRequire("chrome-launcher/package.json").version, "1.2.1");
  return { cliRequire, lhRequire, e2eRequire };
}
function exportEnvironment(values) {
  assert.ok(process.env.GITHUB_ENV);
  for (const [key, value] of Object.entries(values)) {
    assert.ok(!String(value).includes("\n"));
    fs.appendFileSync(process.env.GITHUB_ENV, key + "=" + value + "\n");
  }
}
function certificate(state, name, ca, san) {
  const key = path.join(state.dir, name + ".key"),
    cert = path.join(state.dir, name + ".pem");
  if (!ca)
    command("openssl", [
      "req",
      "-x509",
      "-newkey",
      "rsa:2048",
      "-nodes",
      "-sha256",
      "-days",
      "1",
      "-subj",
      "/CN=" + state.owner + "-" + name,
      "-addext",
      "basicConstraints=critical,CA:TRUE,pathlen:0",
      "-addext",
      "keyUsage=critical,keyCertSign,cRLSign",
      "-keyout",
      key,
      "-out",
      cert,
    ]);
  else {
    const csr = path.join(state.dir, name + ".csr"),
      ext = path.join(state.dir, name + ".extensions");
    command("openssl", [
      "req",
      "-new",
      "-newkey",
      "rsa:2048",
      "-nodes",
      "-sha256",
      "-subj",
      "/CN=disposable-fixture",
      "-keyout",
      key,
      "-out",
      csr,
    ]);
    fs.writeFileSync(
      ext,
      "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=IP:" +
        san +
        "\n",
      { mode: 0o600 },
    );
    command("openssl", [
      "x509",
      "-req",
      "-in",
      csr,
      "-CA",
      path.join(state.dir, ca + ".pem"),
      "-CAkey",
      path.join(state.dir, ca + ".key"),
      "-CAcreateserial",
      "-days",
      "1",
      "-sha256",
      "-extfile",
      ext,
      "-out",
      cert,
    ]);
  }
  fs.chmodSync(key, 0o600);
  fs.chmodSync(cert, 0o600);
  return { key, cert };
}
async function inventory() {
  validateNssParents();
  for (const name of [".pki/nssdb", ".local/share/pki/nssdb"])
    assert.ok(!optionalStat(path.join(homedir(), name)), "Pre-existing NSS database: STOP");
  assert.equal(
    process.env.NEXT_PUBLIC_API_BASE_URL,
    "https://" + process.env.PERF_FIXTURE_API_HOST + ":8000",
  );
  const { cliRequire, e2eRequire } = dependencies();
  const selected = cliRequire("./src/utils.js").determineChromePath({});
  assert.ok(selected, "No existing Lighthouse Chrome installation");
  const chrome = fs.realpathSync(selected),
    chromeVersion = command(chrome, ["--version"]);
  assert.match(chromeVersion, /(?:Chrome|Chromium)\s+155\./);
  const pw = fs.realpathSync(e2eRequire("@playwright/test").chromium.executablePath());
  const pwVersion = command(pw, ["--version"]);
  assert.match(pwVersion, /Chromium\s+141\.0\.7390\.37/);
  const openssl = command("openssl", ["version"]);
  assert.match(openssl, /^OpenSSL 3\./);
  const nssTools = command("dpkg-query", ["-W", "-f=" + "$" + "{Version}", "libnss3-tools"]);
  const uvicorn = command(
    "uv",
    ["run", "--locked", "python", "-c", "import uvicorn; print(uvicorn.__version__)"],
    { cwd: path.join(checkout, "services/api") },
  );
  assert.equal(uvicorn, "0.50.2");
  const state = {
    dir: directory(),
    owner: "convergeo-perf-" + process.env.GITHUB_RUN_ID + "-" + process.env.GITHUB_RUN_ATTEMPT,
    nss: path.join(homedir(), ".pki/nssdb"),
    nssParentOwned: !fs.existsSync(path.join(homedir(), ".pki")),
    chrome,
    selectedChrome: chrome,
    chromeVersion,
    pw,
    pwVersion,
    api: process.env.NEXT_PUBLIC_API_BASE_URL,
    host: process.env.PERF_FIXTURE_API_HOST,
    processes: [],
    createdNss: false,
  };
  fs.mkdirSync(state.dir, { mode: 0o700 });
  process.umask(0o077);
  save(state);
  receipt("inventory", {
    result: "PASS",
    source: command("git", ["rev-parse", "HEAD"], { cwd: checkout }),
    chrome,
    chromeVersion,
    playwright: pw,
    playwrightVersion: pwVersion,
    proposedProfilesUnder: state.dir,
    nssPreconditions: "both absent; not created",
    uid: process.getuid(),
    node: process.versions.node,
    uvicorn,
    openssl,
    nssTools,
  });
}
async function sandbox(state) {
  for (const engine of ["playwright141", "lighthouse155"]) {
    await browserSession(state, engine, async ({ page }) => {
      await page.goto("about:blank");
    });
  }
  receipt("sandbox-admission", {
    result: "PASS",
    engines: ["playwright141", "lighthouse155"],
    legacyNssNowExists: Boolean(optionalStat(path.join(homedir(), ".pki/nssdb"))),
    modernNssNowExists: Boolean(optionalStat(path.join(homedir(), ".local/share/pki/nssdb"))),
  });
}
async function prepare(state) {
  assert.equal(
    JSON.parse(fs.readFileSync(path.join(checkout, "perf-fixture-receipts/sandbox-admission.json")))
      .result,
    "PASS",
  );
  validateNssParents();
  // Browser-created/default databases are not silently reclassified as ours.
  for (const name of [".pki/nssdb", ".local/share/pki/nssdb"])
    assert.ok(
      !optionalStat(path.join(homedir(), name)),
      "Pre-existing NSS database after sandbox admission: STOP",
    );
  const openssl = command("openssl", ["version"]);
  const nssTools = command("dpkg-query", ["-W", "-f=" + "$" + "{Version}", "libnss3-tools"]);
  try {
    certificate(state, "ca");
    certificate(state, "untrusted-ca");
    state.good = certificate(state, "server", "ca", state.host);
    state.wrong = certificate(state, "wrong-san", "ca", "192.0.2.1");
    state.untrusted = certificate(state, "untrusted-server", "untrusted-ca", state.host);
    state.ca = path.join(state.dir, "ca.pem");
    fs.rmSync(path.join(state.dir, "ca.key"));
    fs.rmSync(path.join(state.dir, "untrusted-ca.key"));
    fs.mkdirSync(path.dirname(state.nss), { recursive: true, mode: 0o700 });
    fs.mkdirSync(state.nss, { mode: 0o700 });
    state.createdNss = true;
    fs.writeFileSync(path.join(state.nss, ".convergeo-owner"), state.owner, { mode: 0o600 });
    save(state);
    command("certutil", ["-N", "--empty-password", "-d", "sql:" + state.nss]);
    command("certutil", [
      "-A",
      "-d",
      "sql:" + state.nss,
      "-n",
      state.owner,
      "-t",
      "C,,",
      "-i",
      state.ca,
    ]);
    command("certutil", ["-L", "-d", "sql:" + state.nss, "-n", state.owner]);
    save(state);
    exportEnvironment({
      NODE_EXTRA_CA_CERTS: state.ca,
      PERF_FIXTURE_TLS_KEY: state.good.key,
      PERF_FIXTURE_TLS_CERT: state.good.cert,
      CHROME_PATH: state.chrome,
    });
    receipt("preparation", {
      result: "PASS",
      source: command("git", ["rev-parse", "HEAD"], { cwd: checkout }),
      chrome: state.chrome,
      chromeVersion: state.chromeVersion,
      playwright: state.pw,
      playwrightVersion: state.pwVersion,
      nss: state.nss,
      nssPreconditions: "both absent; created legacy database only",
      uid: process.getuid(),
      openssl,
      nssTools,
      caIdentity: command("openssl", [
        "x509",
        "-in",
        state.ca,
        "-noout",
        "-fingerprint",
        "-sha256",
        "-dates",
      ]),
      serverIdentity: command("openssl", [
        "x509",
        "-in",
        state.good.cert,
        "-noout",
        "-ext",
        "subjectAltName",
        "-dates",
      ]),
    });
  } catch (error) {
    receipt("preparation-failure", { result: "FAIL", name: error.name, message: error.message });
    try {
      await cleanup(state);
    } catch {
      /* Independent cleanup receipt retains its failure. */
    }
    throw error;
  }
}
async function listen(server, port, host) {
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, host, resolve);
  });
  return server;
}
async function stop(server) {
  server.closeAllConnections?.();
  await new Promise((resolve) => server.close(resolve));
}
function tlsServer(pair) {
  return https.createServer(
    { key: fs.readFileSync(pair.key), cert: fs.readFileSync(pair.cert), minVersion: "TLSv1.2" },
    (req, res) => {
      if (req.headers.origin === WEB) res.setHeader("Access-Control-Allow-Origin", WEB);
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ fixture: "tls-control" }));
    },
  );
}
function procIdentity(pid) {
  const stat = fs.readFileSync("/proc/" + pid + "/stat", "utf8");
  const fields = stat.slice(stat.lastIndexOf(")") + 2).split(" ");
  return { pid, start: fields[19], group: Number(fields[2]) };
}
async function browserSession(state, engine, action) {
  const { lhRequire, e2eRequire } = dependencies();
  const profile = path.join(state.dir, engine + "-profile-" + Date.now());
  let browser, launched, context;
  try {
    let rootSession;
    if (engine === "playwright141") {
      context = await e2eRequire("@playwright/test").chromium.launchPersistentContext(profile, {
        executablePath: state.pw,
        chromiumSandbox: true,
        ignoreHTTPSErrors: false,
        bypassCSP: false,
      });
      browser = context.browser();
      rootSession = await browser.newBrowserCDPSession();
    } else {
      launched = await lhRequire("chrome-launcher").launch({
        chromePath: state.chrome,
        userDataDir: profile,
        chromeFlags: ["--headless=new", "--enable-automation"],
      });
      browser = await lhRequire("puppeteer-core").connect({
        browserURL: "http://127.0.0.1:" + launched.port,
        defaultViewport: null,
      });
      rootSession = await browser.target().createCDPSession();
      context = await browser.createBrowserContext();
    }
    const version = await rootSession.send("Browser.getVersion");
    assert.match(
      version.product,
      engine === "playwright141" ? /Chrome\/141\.0\.7390\.37/ : /Chrome\/155\./,
    );
    const { arguments: args } = await rootSession.send("Browser.getBrowserCommandLine");
    validateArguments(args);
    const actualExecutable = fs.realpathSync(args[0]);
    if (engine === "playwright141") assert.equal(actualExecutable, state.pw);
    else {
      // Distribution launchers may exec a sibling ELF binary. Bind subsequent
      // collection to the actual runtime executable, retaining the original selection.
      assert.equal(command(actualExecutable, ["--version"]), state.chromeVersion);
      state.chrome = actualExecutable;
      save(state);
    }
    const page = await context.newPage();
    const cdp =
      engine === "playwright141"
        ? await context.newCDPSession(page)
        : await page.createCDPSession();
    await cdp.send("Network.enable");
    const failures = [],
      requestUrls = new Map();
    cdp.on("Network.requestWillBeSent", (event) =>
      requestUrls.set(event.requestId, event.request.url),
    );
    cdp.on("Network.loadingFailed", (event) =>
      failures.push({
        requestId: event.requestId,
        url: requestUrls.get(event.requestId),
        errorText: event.errorText,
        corsErrorStatus: event.corsErrorStatus,
        blockedReason: event.blockedReason,
      }),
    );
    const processInfo = await rootSession.send("SystemInfo.getProcessInfo");
    const renderers = processInfo.processInfo
      .filter((item) => item.type === "renderer")
      .map((item) => {
        const status = fs.readFileSync("/proc/" + item.id + "/status", "utf8");
        const field = (key) => status.match(new RegExp("^" + key + ":\\s*(.+)$", "m"))?.[1];
        return {
          pid: item.id,
          uid: field("Uid"),
          seccomp: field("Seccomp"),
          noNewPrivs: field("NoNewPrivs"),
        };
      });
    assert.ok(
      renderers.length && renderers.every((row) => row.seccomp === "2" && row.noNewPrivs === "1"),
      "Renderer sandbox enforcement not demonstrated",
    );
    receipt(engine + "-" + process.argv[2].slice(2) + "-launch", {
      result: "PASS",
      version,
      actualExecutable,
      selectedChrome: state.selectedChrome,
      arguments: args,
      renderers,
      profile: args.find((arg) => arg.startsWith("--user-data-dir=")),
      nss: state.nss,
      uid: process.getuid(),
    });
    await action({ page, context, failures, cdp, engine });
  } catch (error) {
    receipt(engine + "-" + process.argv[2].slice(2) + "-failure", {
      result: "FAIL",
      name: error.name,
      message: String(error.message).replace(/eyJ[A-Za-z0-9_.-]+/g, "[REDACTED]"),
    });
    throw error;
  } finally {
    const errors = [];
    // Disposal needs a live CDP connection; then attempt each remaining cleanup
    // independently, even when a preceding operation failed.
    try {
      await context?.close();
    } catch (error) {
      errors.push({ reason: error });
    }
    if (engine !== "playwright141") {
      try {
        browser?.disconnect();
      } catch (error) {
        errors.push({ reason: error });
      }
      try {
        await launched?.kill();
      } catch (error) {
        errors.push({ reason: error });
      }
    }
    try {
      fs.rmSync(profile, { recursive: true, force: true });
    } catch (error) {
      errors.push({ reason: error });
    }
    receipt(engine + "-" + process.argv[2].slice(2) + "-profile-cleanup", {
      result: errors.length ? "FAIL" : "PASS",
      failures: errors.map((item) => item.reason?.name ?? "Error"),
      ownedProfile: profile,
    });
    assert.equal(errors.length, 0, "Owned browser/profile cleanup failed");
  }
}
async function pageFetch(page, url, options = {}) {
  return page.evaluate(
    async ({ url, options }) => {
      try {
        const response = await fetch(url, { ...options, signal: AbortSignal.timeout(15000) });
        return { status: response.status, url: response.url, body: await response.json() };
      } catch {
        return { error: "fetch-rejected" };
      }
    },
    { url, options },
  );
}
function requireTrust(state) {
  assert.equal(
    process.env.NODE_EXTRA_CA_CERTS,
    state.ca,
    "CA must be supplied at Node process launch",
  );
  assert.equal(process.env.CHROME_PATH, state.chrome);
}
async function supabasePage(page) {
  const result = await pageFetch(
    page,
    process.env.NEXT_PUBLIC_SUPABASE_URL +
      "/rest/v1/categories?select=slug,name&prohibited=eq.false",
    {
      headers: {
        apikey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
        Authorization: "Bearer " + process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
      },
    },
  );
  assert.equal(result.status, 200, "Actual page Supabase request failed");
  assert.ok(result.body.some((row) => row.slug === "electronics"));
  return { status: result.status, origin: new URL(result.url).origin, electronics: true };
}
async function admit(state) {
  requireTrust(state);
  const servers = [];
  try {
    for (const [pair, port] of [
      [state.good, 8000],
      [state.wrong, 8001],
      [state.untrusted, 8002],
    ])
      servers.push(await listen(tlsServer(pair), port, state.host));
    servers.push(
      await listen(
        http.createServer((req, res) => {
          res.setHeader("Content-Security-Policy", CSP);
          res.setHeader("Content-Type", "text/html");
          res.end(
            "<!doctype html><title>Disposable transport admission</title><p>Transport control, not application acceptance.</p>",
          );
        }),
        3000,
        "127.0.0.1",
      ),
    );
    const good = await fetch(state.api, { signal: AbortSignal.timeout(15000) });
    assert.equal(good.status, 200);
    assert.equal((await good.json()).fixture, "tls-control");
    let httpFailure;
    try {
      await fetch("http://" + state.host + ":8000", { signal: AbortSignal.timeout(5000) });
    } catch (error) {
      httpFailure = error.cause?.code;
    }
    assert.ok(
      ["UND_ERR_SOCKET", "ECONNRESET", "HPE_INVALID_CONSTANT"].includes(httpFailure),
      "TLS-only listener did not reject plaintext HTTP specifically",
    );
    const nodeResults = [];
    for (const port of [8001, 8002]) {
      let cause;
      try {
        await fetch("https://" + state.host + ":" + port, { signal: AbortSignal.timeout(15000) });
      } catch (error) {
        cause = error.cause?.code;
      }
      assert.ok(
        port === 8001
          ? cause === "ERR_TLS_CERT_ALTNAME_INVALID"
          : [
              "UNABLE_TO_VERIFY_LEAF_SIGNATURE",
              "SELF_SIGNED_CERT_IN_CHAIN",
              "UNABLE_TO_GET_ISSUER_CERT_LOCALLY",
            ].includes(cause),
        "Node certificate-specific rejection missing on " + port + ": " + cause,
      );
      nodeResults.push({ port, cause });
    }
    receipt("node-trust", {
      result: "PASS",
      positive: good.status,
      negatives: nodeResults,
      plaintextHttpFailure: httpFailure,
    });
    for (const engine of ["playwright141", "lighthouse155"])
      await browserSession(state, engine, async ({ page, failures }) => {
        await page.goto(WEB);
        const positive = await pageFetch(page, state.api);
        assert.equal(positive.status, 200);
        assert.equal(positive.body.fixture, "tls-control");
        assert.equal(new URL(positive.url).origin, state.api);
        const upgraded = await pageFetch(page, "http://" + state.host + ":8000");
        assert.equal(upgraded.status, 200);
        assert.equal(
          new URL(upgraded.url).origin,
          state.api,
          "CSP failed to upgrade the API request",
        );
        const negatives = [];
        for (const [port, code] of [
          [8001, "net::ERR_CERT_COMMON_NAME_INVALID"],
          [8002, "net::ERR_CERT_AUTHORITY_INVALID"],
        ]) {
          const start = failures.length;
          assert.equal(
            (await pageFetch(page, "https://" + state.host + ":" + port)).error,
            "fetch-rejected",
          );
          await delay(100);
          const expectedUrl = new URL("https://" + state.host + ":" + port).href;
          assert.ok(
            failures
              .slice(start)
              .some(
                (event) =>
                  event.url === expectedUrl && event.errorText === code && !event.corsErrorStatus,
              ),
            "Certificate-specific browser failure missing: " + code,
          );
          negatives.push({ port, errorText: code });
        }
        receipt(engine + "-trust", {
          result: "PASS",
          positive: { status: positive.status, origin: state.api },
          negatives,
          enforcedCspUpgrade: {
            status: upgraded.status,
            finalOrigin: new URL(upgraded.url).origin,
          },
          supabase: await supabasePage(page),
          syntheticDocumentOnly: true,
        });
      });
    receipt("transport-admission", { result: "PASS", engines: ["playwright141", "lighthouse155"] });
  } finally {
    const outcomes = await Promise.allSettled(servers.reverse().map(stop));
    const errors = outcomes.filter((result) => result.status === "rejected");
    receipt("control-listener-cleanup", {
      result: errors.length ? "FAIL" : "PASS",
      listeners: servers.length,
      failed: errors.length,
    });
    assert.equal(errors.length, 0, "Owned control-listener cleanup failed");
  }
}
function spawnOwned(state, kind, binary, args, cwd) {
  const fd = fs.openSync(path.join(state.dir, kind + ".log"), "a", 0o600);
  const child = spawn(binary, args, {
    cwd,
    detached: true,
    stdio: ["ignore", fd, fd],
    env: process.env,
  });
  fs.closeSync(fd);
  child.unref();
  assert.ok(child.pid);
  state.processes.push({ kind, ...procIdentity(child.pid) });
  save(state);
}
async function start(state, kind) {
  requireTrust(state);
  assert.equal(
    JSON.parse(
      fs.readFileSync(path.join(checkout, "perf-fixture-receipts/transport-admission.json")),
    ).result,
    "PASS",
  );
  if (kind === "api")
    spawnOwned(
      state,
      kind,
      "uv",
      [
        "run",
        "--locked",
        "uvicorn",
        "app.main:app",
        "--host",
        state.host,
        "--port",
        "8000",
        "--ssl-keyfile",
        state.good.key,
        "--ssl-certfile",
        state.good.cert,
      ],
      path.join(checkout, "services/api"),
    );
  else spawnOwned(state, kind, "pnpm", ["--filter", "customer", "start"], checkout);
  const url = kind === "api" ? state.api + "/healthz" : WEB + "/en/health";
  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1500) });
      if (response.ok) {
        receipt(kind + "-readiness", {
          result: "PASS",
          origin: new URL(url).origin,
          status: response.status,
        });
        return;
      }
    } catch {
      /* Bounded readiness, normal certificate verification throughout. */
    }
    await delay(2000);
  }
  throw new Error(kind + " readiness failed; no application qualification executed");
}
async function content(state) {
  requireTrust(state);
  await browserSession(state, "lighthouse155", async ({ page, context }) => {
    const document = await page.goto(WEB + "/en/c/electronics");
    assert.ok(document.headers()["content-security-policy"]?.includes("upgrade-insecure-requests"));
    const product = await pageFetch(page, state.api + "/products/smartphone-x1");
    assert.equal(product.status, 200);
    assert.equal(product.body.slug, "smartphone-x1");
    assert.equal(product.body.name, "Smartphone X1");
    assert.ok(product.body.listing_count > 0);
    const catalog = await pageFetch(
      page,
      state.api + "/catalog/listings?category_path=electronics",
    );
    assert.equal(catalog.status, 200);
    assert.ok(catalog.body.total > 0);
    assert.ok(catalog.body.items.some((row) => row.product_slug === "smartphone-x1"));
    const supabase = await supabasePage(page);
    const protectedResult = await pageFetch(page, state.api + "/account/wishlist");
    assert.ok(
      [401, 403].includes(protectedResult.status),
      "Anonymous protected request was not refused",
    );
    await page.waitForSelector('[data-testid="listing-grid"] a[href="/en/p/smartphone-x1"]', {
      visible: true,
    });
    assert.equal(await page.$('[data-testid="plp-unavailable"]'), null);
    await page.screenshot({
      path: path.join(checkout, "perf-fixture-receipts/category-chrome155.png"),
      fullPage: true,
    });
    await page.goto(WEB + "/en/p/smartphone-x1");
    assert.equal(await page.$('[data-testid="pdp-unavailable"]'), null);
    await page.waitForFunction(() =>
      [...document.querySelectorAll("h1")].some((el) => el.textContent?.trim() === "Smartphone X1"),
    );
    await page.waitForSelector('[data-testid="pdp-seller-count"]', { visible: true });
    const sellers = await page.$eval('[data-testid="pdp-seller-count"]', (el) => el.textContent);
    assert.ok(/\b[1-9]\d*\b/.test(sellers ?? ""));
    await page.screenshot({
      path: path.join(checkout, "perf-fixture-receipts/product-chrome155.png"),
      fullPage: true,
    });
    const badPage = await context.newPage();
    const badCdp = await badPage.createCDPSession();
    const target = state.api + "/catalog/listings?category_path=electronics";
    const requests = new Map(),
      origins = new Map(),
      statuses = new Map(),
      failures = new Map();
    await badCdp.send("Network.enable");
    badCdp.on("Network.requestWillBeSent", (event) => {
      requests.set(event.requestId, event.request.url);
      if (
        Object.entries(event.request.headers).some(
          ([key, value]) => key.toLowerCase() === "origin" && value === "http://127.0.0.1:3000",
        )
      )
        origins.set(event.requestId, true);
    });
    badCdp.on("Network.requestWillBeSentExtraInfo", (event) => {
      origins.set(
        event.requestId,
        origins.get(event.requestId) ||
          Object.entries(event.headers).some(
            ([key, value]) => key.toLowerCase() === "origin" && value === "http://127.0.0.1:3000",
          ),
      );
    });
    badCdp.on("Network.responseReceivedExtraInfo", (event) =>
      statuses.set(event.requestId, event.statusCode),
    );
    badCdp.on("Network.loadingFailed", (event) => failures.set(event.requestId, event));
    let corsProof;
    try {
      await badPage.goto("http://127.0.0.1:3000/en/p/smartphone-x1");
      assert.equal((await pageFetch(badPage, target)).error, "fetch-rejected");
      for (let attempt = 0; attempt < 50 && !corsProof; attempt++) {
        for (const [id, url] of requests) {
          const event = failures.get(id);
          if (
            url === target &&
            origins.get(id) &&
            statuses.get(id) === 200 &&
            ["MissingAllowOriginHeader", "AllowOriginMismatch"].includes(
              event?.corsErrorStatus?.corsError,
            ) &&
            !event.errorText.includes("ERR_CERT")
          )
            corsProof = {
              origin: "http://127.0.0.1:3000",
              apiStatus: 200,
              corsError: event.corsErrorStatus.corsError,
            };
        }
        if (!corsProof) await delay(100);
      }
      assert.ok(corsProof, "Request-bound actual browser CORS rejection not demonstrated");
    } finally {
      const closed = await Promise.allSettled([badCdp.detach(), badPage.close()]);
      assert.ok(
        closed.every((result) => result.status === "fulfilled"),
        "Negative page cleanup failed",
      );
    }
    receipt("lighthouse155-content", {
      result: "PASS",
      product: {
        slug: product.body.slug,
        name: product.body.name,
        listingCount: product.body.listing_count,
      },
      catalog: { total: catalog.body.total, expectedProduct: true },
      supabase,
      anonymousProtectedStatus: protectedResult.status,
      unapprovedOriginCors: corsProof,
      sellers,
    });
  });
}
async function cleanup(state) {
  const results = [],
    errors = [];
  const attempt = async (name, action) => {
    try {
      await action();
      results.push({ operation: name, result: "PASS" });
    } catch (error) {
      errors.push({ operation: name, name: error.name, message: error.message });
    }
  };
  for (const owned of [...state.processes].reverse())
    await attempt("process-" + owned.kind, async () => {
      try {
        const actual = procIdentity(owned.pid);
        assert.equal(actual.start, owned.start, "PID reused; refuse to signal");
        assert.equal(actual.group, owned.pid, "Unexpected process group");
        process.kill(-owned.pid, "SIGTERM");
        await delay(1000);
        try {
          const remaining = procIdentity(owned.pid);
          if (remaining.start === owned.start) {
            process.kill(-owned.pid, "SIGKILL");
            await delay(100);
          }
        } catch (error) {
          if (!["ENOENT", "ESRCH"].includes(error.code)) throw error;
        }
      } catch (error) {
        if (!["ENOENT", "ESRCH"].includes(error.code)) throw error;
      }
    });
  if (state.createdNss)
    await attempt("owned-nss", async () => {
      validateOwnedNss(state);
      fs.rmSync(state.nss, { recursive: true });
      if (state.nssParentOwned) fs.rmdirSync(path.dirname(state.nss));
    });
  // Key/profile cleanup is independent of process/NSS cleanup failures.
  await attempt("owned-key-profile-directory", async () => {
    ownedDirectory(state.dir);
    fs.rmSync(state.dir, { recursive: true });
  });
  receipt("cleanup", {
    result: errors.length ? "FAIL" : "PASS",
    operations: results,
    failures: errors,
  });
  assert.equal(errors.length, 0, "One or more owned cleanup operations failed; see receipt");
}
async function main() {
  requireHosted(process.env);
  process.umask(0o077);
  const mode = process.argv[2];
  if (mode === "--inventory") return inventory();
  if (mode === "--cleanup" && !fs.existsSync(directory())) {
    receipt("cleanup", {
      result: "NOT_NEEDED",
      reason: "Owned state absent; no pre-existing trust touched",
    });
    return;
  }
  const state = load(mode !== "--cleanup");
  if (mode === "--sandbox") return sandbox(state);
  if (mode === "--prepare") return prepare(state);
  if (mode === "--admit") return admit(state);
  if (mode === "--start-api") return start(state, "api");
  if (mode === "--start-app") return start(state, "app");
  if (mode === "--content") return content(state);
  if (mode === "--cleanup") return cleanup(state);
  throw new Error("Choose an explicit hosted fixture operation");
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  main().catch((error) => {
    receipt("failure", {
      result: "FAIL",
      operation: process.argv[2],
      name: error.name,
      message: String(error.message).replace(/eyJ[A-Za-z0-9_.-]+/g, "[REDACTED]"),
      code: error.code,
      causeCode: error.cause?.code,
    });
    console.error(
      "Hosted fixture operation failed; see redacted failure receipt (" + error.name + ")",
    );
    process.exitCode = 1;
  });
