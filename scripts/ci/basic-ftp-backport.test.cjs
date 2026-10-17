// Listing fixtures adapted from basic-ftp's MIT-licensed parseListSpec.js at
// d0d9e07c56e519587bb50532ac6eadbb0cb0cfe9, Copyright (c) 2019 Patrick Juchli.
// See docs/ops/lhci-dependency-patches.md for the retained license and provenance.
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const { createRequire } = require("node:module");
const { resolve } = require("node:path");
const { test } = require("node:test");

const rootRequire = createRequire(resolve(__dirname, "../../package.json"));
const lhciRequire = createRequire(rootRequire.resolve("@lhci/cli/package.json"));
const lighthouseRequire = createRequire(lhciRequire.resolve("lighthouse"));
const puppeteerRequire = createRequire(lighthouseRequire.resolve("puppeteer-core"));
const browserRequire = createRequire(puppeteerRequire.resolve("@puppeteer/browsers"));
const utilsRequire = createRequire(lhciRequire.resolve("@lhci/utils/package.json"));
const utilsLighthouseRequire = createRequire(utilsRequire.resolve("lighthouse"));
const utilsPuppeteerRequire = createRequire(utilsLighthouseRequire.resolve("puppeteer-core"));
const utilsBrowserRequire = createRequire(utilsPuppeteerRequire.resolve("@puppeteer/browsers"));

function ftpConsumer(requireFrom) {
  const proxyRequire = createRequire(requireFrom.resolve("proxy-agent"));
  const pacRequire = createRequire(proxyRequire.resolve("pac-proxy-agent"));
  const getUriRequire = createRequire(pacRequire.resolve("get-uri"));
  const basicPath = getUriRequire.resolve("basic-ftp");
  return { getUriRequire, basicPath, basicRequire: createRequire(basicPath) };
}

const consumer = ftpConsumer(lhciRequire);
const basicFtp = consumer.getUriRequire("basic-ftp");
const { parseList, FileType } = basicFtp;
const unix = consumer.basicRequire("./parseListUnix.js");
const dos = consumer.basicRequire("./parseListDOS.js");
const normalUnix = "-rw-r--r-- 1 alice staff 42 Jan 1 2020 report.txt";

test("LHCI and browser get-uri consumers share patched basic-ftp 5.3.1", () => {
  assert.equal(consumer.basicRequire("../package.json").version, "5.3.1");
  assert.equal(ftpConsumer(browserRequire).basicPath, consumer.basicPath);
  assert.equal(ftpConsumer(utilsBrowserRequire).basicPath, consumer.basicPath);
  assert.equal(consumer.getUriRequire("basic-ftp").parseList, parseList);
});

const unixCases = [
  [
    "regular file",
    normalUnix,
    {
      name: "report.txt",
      size: 42,
      user: "alice",
      group: "staff",
      type: FileType.File,
      hardLinkCount: 1,
      rawModifiedAt: "Jan 1 2020",
      permissions: { user: 6, group: 4, world: 4 },
    },
  ],
  [
    "directory",
    "drwxr-xr-x 2 user group 4096 Feb 8 09:11 folder",
    {
      name: "folder",
      type: FileType.Directory,
      size: 4096,
      permissions: { user: 7, group: 5, world: 5 },
    },
  ],
  [
    "symbolic link",
    "lrwxrwxrwx 1 user group 23 Mar 2 18:06 macros -> /home/user/macros",
    { name: "macros", type: FileType.SymbolicLink, link: "/home/user/macros" },
  ],
  [
    "inode and block count",
    " 1234567 4 -rw-r--r-- 1 alice staff 42 Jan 1 2020 report.txt",
    { name: "report.txt", user: "alice", group: "staff", size: 42 },
  ],
  [
    "device size",
    "crw-rw----   1 root     sys    10, 0 Jan 12  2005 kmem",
    { name: "kmem", size: 10, type: FileType.File },
  ],
  [
    "numeric date",
    "-rw-r--r-- 1 user group 12345 2004-02-12 12:12 f.txt",
    { rawModifiedAt: "2004-02-12 12:12", size: 12345 },
  ],
  [
    "Japanese date",
    "-rw-r--r-- 1 user group 12345 1月 12日 2005年 f.txt",
    { rawModifiedAt: "1月 12日 2005年" },
  ],
  [
    "day-first date",
    "-rw-r--r-- 1 user group 12345 12 Feb 12:12 f.txt",
    { rawModifiedAt: "12 Feb 12:12" },
  ],
  [
    "tabs",
    "-rw-r--r--\t1\tuser\tgroup\t12345\tFeb 12\t12:12\tf.txt",
    { name: "f.txt", user: "user", group: "group" },
  ],
  [
    "Unicode and spaces in filename",
    "-rw-r--r-- 1 user group 42 Jan 1 2020 café report.txt",
    { name: "café report.txt", size: 42 },
  ],
  [
    "spaces in group",
    "-rw-r--r-- 1 patrick staff group 487 Feb 25 19:03 package.json",
    { user: "patrick", group: "staff group", size: 487 },
  ],
  [
    "no separator before link count",
    "drwxr-xr-x2 user group 4096 Feb 8 09:11 dir",
    { name: "dir", hardLinkCount: 2, type: FileType.Directory },
  ],
  [
    "negative user identifier",
    "drwxrwx--- 2 -1 60 4096 Sep 13 2006 shared",
    { user: "-1", group: "60" },
  ],
];

for (const [title, listing, expected] of unixCases) {
  test(`Unix: ${title}`, () => {
    const files = parseList(listing);
    assert.equal(files.length, 1);
    for (const [key, value] of Object.entries(expected))
      assert.deepEqual(files[0][key], value, key);
    assert.equal(
      files[0].modifiedAt,
      undefined,
      "LIST dates remain raw, without inventing a timezone",
    );
  });
}

test("DOS files, directories and names retain metadata", () => {
  const files = parseList("12-05-96 05:03PM <DIR> myDir\r\n11-14-97 04:21PM 953 MY FILE.INI");
  assert.deepEqual(
    files.map((f) => ({ name: f.name, size: f.size, type: f.type, date: f.rawModifiedAt })),
    [
      { name: "myDir", size: 0, type: FileType.Directory, date: "12-05-96 05:03PM" },
      { name: "MY FILE.INI", size: 953, type: FileType.File, date: "11-14-97 04:21PM" },
    ],
  );
});

test("MLSD remains unchanged and supplies a reliable date", () => {
  const [file] = parseList("type=file;size=42;modify=20260102030405; pac.js");
  assert.equal(file.name, "pac.js");
  assert.equal(file.size, 42);
  assert.equal(file.modifiedAt.toISOString(), "2026-01-02T03:04:05.000Z");
});

test("empty, blank and Unix total metadata lines do not invent entries", () => {
  assert.deepEqual(parseList("\r\n total 1\r\n".trimStart()), []);
  assert.deepEqual(
    parseList(`total 1\r\n\r\n${normalUnix}\r\n`).map((f) => f.name),
    ["report.txt"],
  );
});

test("Unix and DOS parent-directory entries remain filtered", () => {
  assert.deepEqual(
    parseList("drwxr-xr-x 1 user group 0 Jan 1 2020 .\r\ndrwxr-xr-x 1 user group 0 Jan 1 2020 .."),
    [],
  );
  assert.deepEqual(parseList("12-05-96 05:03PM <DIR> .\r\n12-05-96 05:03PM <DIR> .."), []);
});

const words = (prefix, count) =>
  Array.from({ length: count }, (_, i) => `${prefix}${i + 1}`).join(" ");
const listingWithNames = (owner, group) =>
  `-rw-r--r-- 1 ${owner} ${group} 12345 Feb 12 12:12 f.txt`;

test("eight-word owner and group boundaries are both accepted", () => {
  const owner = words("o", 8);
  const group = words("g", 8);
  const [file] = parseList(listingWithNames(owner, group));
  assert.equal(file.user, owner);
  assert.equal(file.group, group);
  assert.equal(file.size, 12345);
});

test("eight-word group remains accepted with a one-word owner", () => {
  const group = words("g", 8);
  const [file] = parseList(listingWithNames("owner", group));
  assert.equal(file.user, "owner");
  assert.equal(file.group, group);
});

for (const [ownerCount, groupCount] of [
  [9, 8],
  [8, 9],
]) {
  test(`over-budget name fields (${ownerCount}/${groupCount}) are discarded without losing the next file`, () => {
    const invalid = listingWithNames(words("o", ownerCount), words("g", groupCount));
    assert.equal(unix.testLine(invalid), false);
    assert.equal(unix.parseLine(invalid), undefined);
    assert.deepEqual(
      parseList(`${invalid}\r\n${normalUnix}`).map((f) => f.name),
      ["report.txt"],
    );
  });
}

test("junk-prefixed and malformed Unix lines are not accepted as partial matches", () => {
  for (const line of [
    `junk ${normalUnix}`,
    "-rw-r--r-- 1 owner group missing-size !",
    "not a listing",
  ]) {
    assert.equal(unix.testLine(line), false);
    assert.equal(unix.parseLine(line), undefined);
  }
  assert.equal(dos.parseLine("junk 12-05-96 05:03PM <DIR> myDir"), undefined);
});

for (const kind of ["unix", "dos"]) {
  test(`bounded ${kind} adversarial listing cannot monopolize the parser`, () => {
    const code = `
      const assert = require('node:assert/strict');
      const {parseList} = require(process.argv[1]);
      const kind = process.argv[2];
      const raw = kind === 'unix'
        ? '-rw-r--r-- 1 ' + 'a '.repeat(64 * 1024) + '!\\r\\n' + ${JSON.stringify(normalUnix)}
        : 'x'.repeat(256 * 1024) + '\\r\\n12-05-96 05:03PM <DIR> myDir';
      const names = parseList(raw).map(file => file.name);
      assert.deepEqual(names, kind === 'unix' ? ['report.txt'] : ['myDir']);
      process.stdout.write(JSON.stringify({bytes: Buffer.byteLength(raw), names}));
    `;
    const env = { PATH: process.env.PATH, LANG: "C.UTF-8" };
    for (const key of ["NODE_OPTIONS", "OFFLINE_GUARD_LOG"]) {
      if (process.env[key]) env[key] = process.env[key];
    }
    const result = spawnSync(process.execPath, ["-e", code, consumer.basicPath, kind], {
      env,
      encoding: "utf8",
      timeout: 2000,
      killSignal: "SIGKILL",
      maxBuffer: 16 * 1024,
    });
    assert.equal(result.error, undefined, result.error?.message);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.signal, null);
    assert.ok(JSON.parse(result.stdout).bytes <= 300 * 1024);
  });
}

// Replace only the imported Client constructor while loading the actual get-uri
// FTP consumer. Restore CommonJS state before exercising asynchronous behavior.
function mockedConsumer(scenario = {}) {
  const calls = [];
  const { getUriRequire, basicPath } = consumer;
  const modulePath = getUriRequire.resolve("./ftp.js");
  class OfflineClient {
    async access(options) {
      calls.push(["access", options]);
      if (scenario.accessError) throw scenario.accessError;
    }
    async lastMod(path) {
      calls.push(["lastMod", path]);
      if (scenario.lastModError) throw scenario.lastModError;
      return scenario.lastModified;
    }
    async list(path) {
      calls.push(["list", path]);
      if (scenario.listError) throw scenario.listError;
      return parseList(scenario.listing || "");
    }
    async downloadTo(stream, path) {
      calls.push(["downloadTo", path]);
      stream.end("offline PAC fixture");
      return { message: "offline transfer complete" };
    }
    close() {
      calls.push(["close"]);
    }
  }
  const originalExports = require.cache[basicPath].exports;
  const priorConsumer = require.cache[modulePath];
  let ftp;
  try {
    require.cache[basicPath].exports = { ...originalExports, Client: OfflineClient };
    delete require.cache[modulePath];
    ({ ftp } = getUriRequire(modulePath));
  } finally {
    require.cache[basicPath].exports = originalExports;
    if (priorConsumer) require.cache[modulePath] = priorConsumer;
    else delete require.cache[modulePath];
  }
  return { ftp, calls };
}

const ftpUrl = () => new URL("ftp://offline:fixture@ftp.example.invalid:2121/dir/pac%20file.js");
const reliableDate = new Date("2026-01-02T03:04:05.000Z");
const mlsdListing = "type=file;size=42;modify=20260102030405; pac file.js";
const methods = (calls) => calls.map(([name]) => name);
async function contents(stream) {
  const chunks = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks).toString("utf8");
}

test("get-uri preserves access options, decoded paths, MDTM and stream close behavior", async () => {
  const { ftp, calls } = mockedConsumer({ lastModified: reliableDate });
  const options = { secure: true, secureOptions: { minVersion: "TLSv1.2" } };
  const stream = await ftp(ftpUrl(), options);
  assert.equal(await contents(stream), "offline PAC fixture");
  assert.deepEqual(calls[0], [
    "access",
    { host: "ftp.example.invalid", port: 2121, user: "offline", password: "fixture", ...options },
  ]);
  assert.deepEqual(calls[1], ["lastMod", "/dir/pac file.js"]);
  assert.equal(stream.lastModified, reliableDate);
  assert.deepEqual(methods(calls), ["access", "lastMod", "downloadTo", "close"]);
  assert.deepEqual(calls[2], ["downloadTo", "/dir/pac file.js"]);
});

test("get-uri MDTM failure falls back to the actual MLSD parser", async () => {
  const { ftp, calls } = mockedConsumer({
    lastModError: new Error("offline MDTM unavailable"),
    listing: mlsdListing,
  });
  const stream = await ftp(ftpUrl());
  assert.equal(await contents(stream), "offline PAC fixture");
  assert.equal(stream.lastModified.toISOString(), reliableDate.toISOString());
  assert.deepEqual(
    calls.find(([name]) => name === "list"),
    ["list", "/dir"],
  );
  assert.deepEqual(methods(calls), ["access", "lastMod", "list", "downloadTo", "close"]);
});

test("get-uri Unix fallback retains raw-date/not-found behavior", async () => {
  const { ftp, calls } = mockedConsumer({
    listing: "-rw-r--r-- 1 owner group 42 Jan 1 2020 pac file.js",
  });
  await assert.rejects(ftp(ftpUrl()), { code: "ENOTFOUND" });
  assert.deepEqual(methods(calls), ["access", "lastMod", "list", "close"]);
});

test("get-uri missing listing entry remains not-found", async () => {
  const { ftp, calls } = mockedConsumer({ listing: "type=file;modify=20260102030405; another.js" });
  await assert.rejects(ftp(ftpUrl()), { code: "ENOTFOUND" });
  assert.deepEqual(methods(calls), ["access", "lastMod", "list", "close"]);
});

test("get-uri translates MDTM 550 without falling back or downloading", async () => {
  const { ftp, calls } = mockedConsumer({
    lastModError: Object.assign(new Error("offline missing"), { code: 550 }),
  });
  await assert.rejects(ftp(ftpUrl()), { code: "ENOTFOUND" });
  assert.deepEqual(methods(calls), ["access", "lastMod", "close"]);
});

for (const fallback of [false, true]) {
  test(`get-uri unchanged cache closes without downloading (LIST=${fallback})`, async () => {
    const { ftp, calls } = mockedConsumer(
      fallback ? { listing: mlsdListing } : { lastModified: reliableDate },
    );
    await assert.rejects(ftp(ftpUrl(), { cache: { lastModified: new Date(reliableDate) } }), {
      code: "ENOTMODIFIED",
    });
    assert.equal(methods(calls).includes("downloadTo"), false);
    assert.equal(methods(calls).at(-1), "close");
  });
}

test("get-uri stale cache still downloads", async () => {
  const { ftp, calls } = mockedConsumer({ lastModified: reliableDate });
  const stream = await ftp(ftpUrl(), { cache: { lastModified: new Date(0) } });
  assert.equal(await contents(stream), "offline PAC fixture");
  assert.equal(methods(calls).includes("downloadTo"), true);
  assert.equal(methods(calls).at(-1), "close");
});

for (const stage of ["access", "list"]) {
  test(`get-uri preserves ${stage} error identity and closes`, async () => {
    const error = new Error(`offline ${stage} failure`);
    const { ftp, calls } = mockedConsumer({ [`${stage}Error`]: error });
    await assert.rejects(ftp(ftpUrl()), (received) => received === error);
    assert.equal(methods(calls).includes("downloadTo"), false);
    assert.equal(methods(calls).at(-1), "close");
  });
}
