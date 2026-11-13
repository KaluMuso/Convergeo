import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, it } from "node:test";

import {
  formatScanSummary,
  scanArtifactPaths,
} from "../../ci/artifact-confidentiality-scanner.mjs";

const SENTINEL = "PACKET_C_SECRET_SENTINEL_DO_NOT_RETAIN";
const temporaryRoots = [];

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < table.length; n++) {
    let value = n;
    for (let bit = 0; bit < 8; bit++) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    }
    table[n] = value >>> 0;
  }
  return table;
})();

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function storedZip(entries) {
  const locals = [];
  const centrals = [];
  let offset = 0;
  for (const [name, value] of entries) {
    const nameBytes = Buffer.from(name);
    const data = Buffer.isBuffer(value) ? value : Buffer.from(value);
    const crc = crc32(data);

    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(nameBytes.length, 26);
    locals.push(local, nameBytes, data);

    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(data.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(nameBytes.length, 28);
    central.writeUInt32LE(offset, 42);
    centrals.push(central, nameBytes);
    offset += local.length + nameBytes.length + data.length;
  }

  const centralBytes = Buffer.concat(centrals);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(entries.length, 8);
  eocd.writeUInt16LE(entries.length, 10);
  eocd.writeUInt32LE(centralBytes.length, 12);
  eocd.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, centralBytes, eocd]);
}

function artifactDir() {
  const root = mkdtempSync(join(tmpdir(), "vergeo-artifact-scan-"));
  temporaryRoots.push(root);
  return root;
}

function scan(root, limits) {
  return scanArtifactPaths({ roots: [root], sentinels: [SENTINEL], limits });
}

function encodeLayers(value, count, url = false) {
  let current = value;
  for (let layer = 0; layer < count; layer++) {
    const encoded = Buffer.from(current).toString("base64");
    current = url
      ? encoded.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
      : encoded;
  }
  return current;
}

function reportWithJsonValue(value) {
  const archive = storedZip([["report.json", JSON.stringify({ action: value })]]);
  return `<html><script id="playwrightReportBase64" type="application/zip">data:application/zip;base64,${archive.toString("base64")}</script></html>`;
}

afterEach(() => {
  while (temporaryRoots.length > 0) rmSync(temporaryRoots.pop(), { recursive: true, force: true });
});

describe("artifact confidentiality scanner", () => {
  it("detects raw sentinel retention", () => {
    const root = artifactDir();
    writeFileSync(join(root, "raw.txt"), `prefix ${SENTINEL} suffix`);
    const result = scan(root);
    assert.equal(formatScanSummary(result).verdict, "FAIL");
    assert.equal(result.findings.length, 1);
    assert.equal(result.findings[0].representation, "raw-file");
  });

  it("detects a directly base64-encoded sentinel, including short PIN-shaped values", () => {
    const root = artifactDir();
    const pin = "654321";
    writeFileSync(join(root, "encoded.json"), JSON.stringify({ pin: Buffer.from(pin).toString("base64") }));
    const result = scanArtifactPaths({ roots: [root], sentinels: [pin] });
    assert.equal(formatScanSummary(result).verdict, "FAIL");
    assert.ok(result.findings.some(({ representation }) => representation.endsWith(":base64")));
  });

  it("detects a raw leading-zero six-digit PIN", () => {
    const root = artifactDir();
    const pin = "000001";
    writeFileSync(join(root, "report.html"), reportWithJsonValue(pin));
    const result = scanArtifactPaths({ roots: [root], sentinels: [pin] });
    assert.equal(formatScanSummary(result).verdict, "FAIL");
    assert.ok(result.findings.some(({ location }) => location.endsWith("::zip:report.json")));
  });

  for (const pin of ["042817", "000001"]) {
    for (let layers = 1; layers <= 4; layers++) {
      it(`detects ${layers} base64 layers of leading-zero PIN ${pin.slice(0, 2)}… in HTML ZIP JSON`, () => {
        const root = artifactDir();
        for (const url of [false, true]) {
          writeFileSync(join(root, "report.html"), reportWithJsonValue(encodeLayers(pin, layers, url)));
          const result = scanArtifactPaths({ roots: [root], sentinels: [pin] });
          assert.equal(formatScanSummary(result).verdict, "FAIL");
          assert.ok(result.findings.some(({ location }) => location.endsWith("::zip:report.json")));
        }
      });
    }
  }

  it("detects mixed padding and alphabet across four layers", () => {
    const root = artifactDir();
    const pin = "042817";
    let nested = pin;
    for (const url of [false, true, false, true]) nested = encodeLayers(nested, 1, url);
    writeFileSync(join(root, "report.html"), reportWithJsonValue(nested));
    assert.equal(formatScanSummary(scanArtifactPaths({ roots: [root], sentinels: [pin] })).verdict, "FAIL");
  });

  it("detects padded and unpadded base64url forms of a long sentinel", () => {
    const root = artifactDir();
    const longSentinel = "scanner-" + "ÿ".repeat(24);
    for (const form of [
      Buffer.from(longSentinel).toString("base64").replace(/\+/g, "-").replace(/\//g, "_"),
      encodeLayers(longSentinel, 1, true),
    ]) {
      writeFileSync(join(root, "report.html"), reportWithJsonValue(form));
      assert.equal(
        formatScanSummary(scanArtifactPaths({ roots: [root], sentinels: [longSentinel] })).verdict,
        "FAIL",
      );
    }
  });

  it("fails when unsafe HTML reporter output embeds a base64 ZIP leak", () => {
    const root = artifactDir();
    const reportZip = storedZip([["trace/report.json", `{"action":"Fill ${SENTINEL}"}`]]);
    const html = `<html><script id="playwrightReportBase64" type="application/zip">${reportZip.toString("base64")}</script></html>`;
    writeFileSync(join(root, "report.html"), html);
    const result = scan(root);
    assert.equal(formatScanSummary(result).verdict, "FAIL");
    assert.equal(result.archives, 1);
    assert.ok(result.base64Payloads >= 1);
    assert.ok(result.findings.some(({ location }) => /base64:.*::zip:trace\/report\.json/.test(location)));
  });

  it("fails when trace capture is restored and retains a secret", () => {
    const root = artifactDir();
    writeFileSync(join(root, "trace.zip"), storedZip([["trace.trace", `action=${SENTINEL}`]]));
    const result = scan(root);
    assert.equal(formatScanSummary(result).verdict, "FAIL");
    assert.ok(result.findings.some(({ location }) => /trace\.zip::zip:trace\.trace$/.test(location)));
  });

  it("fails when prompt-copy snapshots are restored", () => {
    const root = artifactDir();
    writeFileSync(join(root, "error-context.md"), `input value: ${SENTINEL}`);
    assert.equal(formatScanSummary(scan(root)).verdict, "FAIL");
  });

  it("passes a clean raw and encoded artifact set", () => {
    const root = artifactDir();
    const reportZip = storedZip([["trace/report.txt", "public diagnostic content"]]);
    writeFileSync(join(root, "report.html"), `data:application/zip;base64,${reportZip.toString("base64")}`);
    writeFileSync(join(root, "summary.json"), JSON.stringify({ verdict: "PASS" }));
    const result = scan(root);
    assert.equal(formatScanSummary(result).verdict, "PASS");
    assert.deepEqual(result.errors, []);
    assert.deepEqual(result.findings, []);
  });

  it("fails closed on a malformed top-level archive", () => {
    const root = artifactDir();
    writeFileSync(join(root, "broken.zip"), Buffer.from("PK\u0003\u0004truncated"));
    const result = scan(root);
    assert.equal(formatScanSummary(result).verdict, "FAIL");
    assert.equal(result.findings.length, 0);
    assert.match(result.errors[0].error, /end-of-central-directory/i);
  });

  it("fails closed when a malformed encoded archive is restored", () => {
    const root = artifactDir();
    const malformed = Buffer.from("504b030400000000", "hex");
    writeFileSync(join(root, "report.html"), `<script>${malformed.toString("base64")}</script>`);
    const result = scan(root);
    assert.equal(formatScanSummary(result).verdict, "FAIL");
    assert.match(result.errors[0].location, /base64:/);
  });

  it("scans duplicate ZIP entry names instead of letting the later entry hide", () => {
    const root = artifactDir();
    writeFileSync(
      join(root, "duplicates.zip"),
      storedZip([
        ["same-name.txt", "clean first copy"],
        ["same-name.txt", `second copy ${SENTINEL}`],
      ]),
    );
    const result = scan(root);
    assert.equal(result.duplicateArchiveEntries, 1);
    assert.equal(formatScanSummary(result).verdict, "FAIL");
    assert.ok(result.findings.some(({ location }) => /same-name\.txt#2$/.test(location)));
  });

  it("fails closed when a report exceeds the decoded node budget", () => {
    const root = artifactDir();
    writeFileSync(join(root, "large.txt"), "clean but too large for the configured budget");
    const result = scan(root, { maxNodeBytes: 16 });
    assert.equal(formatScanSummary(result).verdict, "FAIL");
    assert.match(result.errors[0].error, /payload exceeds scan limit/);
  });

  it("fails closed when sentinel encoding exceeds its bounded budget", () => {
    const root = artifactDir();
    writeFileSync(join(root, "clean.txt"), "clean");
    assert.throws(
      () => scanArtifactPaths({ roots: [root], sentinels: ["S".repeat(4_097)] }),
      /sentinel exceeds 4096-byte encoding limit/,
    );
  });

  it("deduplicates overlapping base64 matches without skipping the payload", () => {
    const root = artifactDir();
    const encoded = Buffer.from("clean reusable payload").toString("base64");
    writeFileSync(join(root, "duplicate.html"), `<script>${encoded}</script><script>${encoded}</script>`);
    const result = scan(root);
    assert.equal(formatScanSummary(result).verdict, "PASS");
    assert.equal(result.base64Payloads, 1);
    assert.ok(result.duplicatePayloads >= 1);
  });

  it("recurses through ZIP to HTML to base64 ZIP", () => {
    const root = artifactDir();
    const inner = storedZip([["deep/secret.txt", SENTINEL]]);
    const html = `<script type="application/zip">${inner.toString("base64")}</script>`;
    const outer = storedZip([["playwright-report/index.html", html]]);
    writeFileSync(join(root, "outer.zip"), outer);
    const result = scan(root);
    assert.equal(formatScanSummary(result).verdict, "FAIL");
    assert.equal(result.archives, 2);
    assert.ok(result.findings.some(({ location }) => /outer\.zip::zip:.*::base64:.*::zip:deep\/secret\.txt/.test(location)));
  });

  it("never returns success for an unscanned nested payload", () => {
    const root = artifactDir();
    const encoded = Buffer.from(Buffer.from(SENTINEL).toString("base64")).toString("base64");
    writeFileSync(join(root, "nested.txt"), encoded);
    const result = scan(root, { maxDepth: 1 });
    assert.equal(formatScanSummary(result).verdict, "FAIL");
    assert.ok(result.errors.some(({ error }) => /depth limit/i.test(error)));
  });
});
