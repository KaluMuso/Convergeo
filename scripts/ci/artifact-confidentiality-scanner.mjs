#!/usr/bin/env node

import { createHash } from "node:crypto";
import { existsSync, lstatSync, readFileSync, readdirSync } from "node:fs";
import { extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gunzipSync, inflateRawSync } from "node:zlib";

const ZIP_LOCAL = 0x04034b50;
const ZIP_CENTRAL = 0x02014b50;
const ZIP_EOCD = 0x06054b50;
const ZIP_DATA_DESCRIPTOR = 0x08074b50;

const DEFAULT_LIMITS = Object.freeze({
  maxDepth: 8,
  maxEntries: 10_000,
  maxNodeBytes: 64 * 1024 * 1024,
  maxTotalDecodedBytes: 256 * 1024 * 1024,
  maxBase64CandidatesPerNode: 2_000,
  maxCompressionRatio: 1_000,
});

const TEXT_EXTENSIONS = new Set([
  ".css", ".csv", ".htm", ".html", ".js", ".json", ".log", ".md",
  ".mjs", ".svg", ".txt", ".xml", ".yaml", ".yml",
]);

const BASE64_PATTERNS = [
  /base64\s*,\s*([A-Za-z0-9+/_=\r\n\t ]{8,})/g,
  /<script\b[^>]*>\s*([A-Za-z0-9+/_=\r\n\t ]{8,})\s*<\/script>/gi,
  /(?:^|[^A-Za-z0-9+/_-])([A-Za-z0-9+/_-]{32,}={0,2})(?=$|[^A-Za-z0-9+/_=-])/g,
];

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

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

function hasZipMagic(buffer) {
  if (buffer.length < 4) return false;
  const signature = buffer.readUInt32LE(0);
  return [ZIP_LOCAL, ZIP_EOCD, ZIP_DATA_DESCRIPTOR, ZIP_CENTRAL].includes(signature);
}

function looksTextual(buffer, location) {
  if (TEXT_EXTENSIONS.has(extname(location).toLowerCase())) return true;
  const sample = buffer.subarray(0, Math.min(buffer.length, 8_192));
  if (sample.length === 0) return true;
  let suspicious = 0;
  for (const byte of sample) {
    if (byte === 0 || byte < 9 || (byte > 13 && byte < 32)) suspicious++;
  }
  return suspicious / sample.length < 0.02;
}

function normalizeBase64(raw) {
  const compact = raw.replace(/\s+/g, "").replace(/-/g, "+").replace(/_/g, "/");
  if (compact.length < 8 || compact.length % 4 === 1) return null;
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(compact)) return null;
  const unpadded = compact.replace(/=+$/, "");
  const padded = compact.padEnd(Math.ceil(compact.length / 4) * 4, "=");
  let decoded;
  try {
    decoded = Buffer.from(padded, "base64");
  } catch {
    return null;
  }
  if (decoded.length < 8) return null;
  if (decoded.toString("base64").replace(/=+$/, "") !== unpadded) return null;
  return decoded;
}

function readUInt16(buffer, offset, context) {
  if (offset < 0 || offset + 2 > buffer.length) throw new Error(`${context}: truncated uint16`);
  return buffer.readUInt16LE(offset);
}

function readUInt32(buffer, offset, context) {
  if (offset < 0 || offset + 4 > buffer.length) throw new Error(`${context}: truncated uint32`);
  return buffer.readUInt32LE(offset);
}

function parseZip(buffer, limits) {
  let eocd = -1;
  const lowerBound = Math.max(0, buffer.length - 65_557);
  for (let offset = buffer.length - 22; offset >= lowerBound; offset--) {
    if (readUInt32(buffer, offset, "ZIP EOCD search") === ZIP_EOCD) {
      eocd = offset;
      break;
    }
  }
  if (eocd < 0) throw new Error("ZIP end-of-central-directory record missing");

  const disk = readUInt16(buffer, eocd + 4, "ZIP EOCD");
  const centralDisk = readUInt16(buffer, eocd + 6, "ZIP EOCD");
  const diskEntries = readUInt16(buffer, eocd + 8, "ZIP EOCD");
  const totalEntries = readUInt16(buffer, eocd + 10, "ZIP EOCD");
  const centralSize = readUInt32(buffer, eocd + 12, "ZIP EOCD");
  const centralOffset = readUInt32(buffer, eocd + 16, "ZIP EOCD");
  const commentLength = readUInt16(buffer, eocd + 20, "ZIP EOCD");
  if (disk !== 0 || centralDisk !== 0 || diskEntries !== totalEntries) {
    throw new Error("multi-disk ZIP archives are unsupported");
  }
  if (totalEntries > limits.maxEntries) {
    throw new Error(`ZIP entry limit exceeded (${totalEntries} > ${limits.maxEntries})`);
  }
  if (centralOffset === 0xffffffff || centralSize === 0xffffffff || totalEntries === 0xffff) {
    throw new Error("ZIP64 archive requires an unsupported parser path");
  }
  if (eocd + 22 + commentLength > buffer.length) throw new Error("truncated ZIP comment");
  if (centralOffset + centralSize > eocd) throw new Error("ZIP central directory is out of bounds");

  const entries = [];
  const names = new Map();
  let cursor = centralOffset;
  for (let index = 0; index < totalEntries; index++) {
    const context = `ZIP central entry ${index}`;
    if (readUInt32(buffer, cursor, context) !== ZIP_CENTRAL) {
      throw new Error(`${context}: invalid central-directory signature`);
    }
    const flags = readUInt16(buffer, cursor + 8, context);
    const method = readUInt16(buffer, cursor + 10, context);
    const expectedCrc = readUInt32(buffer, cursor + 16, context);
    const compressedSize = readUInt32(buffer, cursor + 20, context);
    const uncompressedSize = readUInt32(buffer, cursor + 24, context);
    const fileNameLength = readUInt16(buffer, cursor + 28, context);
    const extraLength = readUInt16(buffer, cursor + 30, context);
    const entryCommentLength = readUInt16(buffer, cursor + 32, context);
    const localOffset = readUInt32(buffer, cursor + 42, context);
    const centralEnd = cursor + 46 + fileNameLength + extraLength + entryCommentLength;
    if (centralEnd > eocd) throw new Error(`${context}: entry extends beyond central directory`);
    if (flags & 0x1) throw new Error(`${context}: encrypted entries cannot be inspected`);
    if (![0, 8].includes(method)) throw new Error(`${context}: unsupported compression method ${method}`);
    if ([compressedSize, uncompressedSize, localOffset].includes(0xffffffff)) {
      throw new Error(`${context}: ZIP64 entry requires an unsupported parser path`);
    }
    if (uncompressedSize > limits.maxNodeBytes) {
      throw new Error(`${context}: uncompressed size exceeds scan limit`);
    }
    if (compressedSize > 0 && uncompressedSize / compressedSize > limits.maxCompressionRatio) {
      throw new Error(`${context}: compression ratio exceeds scan limit`);
    }

    const rawName = buffer.subarray(cursor + 46, cursor + 46 + fileNameLength).toString("utf8");
    const name = rawName || `<unnamed-${index}>`;
    if (readUInt32(buffer, localOffset, `${context} local header`) !== ZIP_LOCAL) {
      throw new Error(`${context}: invalid local-header signature for ${name}`);
    }
    const localFlags = readUInt16(buffer, localOffset + 6, `${context} local header`);
    const localMethod = readUInt16(buffer, localOffset + 8, `${context} local header`);
    if (localFlags & 0x1) throw new Error(`${context}: encrypted local entry ${name}`);
    if (localMethod !== method) throw new Error(`${context}: compression method mismatch for ${name}`);
    const localNameLength = readUInt16(buffer, localOffset + 26, `${context} local header`);
    const localExtraLength = readUInt16(buffer, localOffset + 28, `${context} local header`);
    const dataStart = localOffset + 30 + localNameLength + localExtraLength;
    const dataEnd = dataStart + compressedSize;
    if (dataStart < 0 || dataEnd > buffer.length) {
      throw new Error(`${context}: compressed data is out of bounds for ${name}`);
    }
    const compressed = buffer.subarray(dataStart, dataEnd);
    let data;
    try {
      data = method === 0 ? Buffer.from(compressed) : inflateRawSync(compressed, {
        maxOutputLength: limits.maxNodeBytes,
      });
    } catch (error) {
      throw new Error(`${context}: decompression failed for ${name}: ${error.message}`);
    }
    if (data.length !== uncompressedSize) throw new Error(`${context}: uncompressed size mismatch for ${name}`);
    if (crc32(data) !== expectedCrc) throw new Error(`${context}: CRC mismatch for ${name}`);

    const occurrence = (names.get(name) ?? 0) + 1;
    names.set(name, occurrence);
    entries.push({
      name: occurrence === 1 ? name : `${name}#${occurrence}`,
      data,
      duplicate: occurrence > 1,
    });
    cursor = centralEnd;
  }
  if (cursor !== centralOffset + centralSize) {
    throw new Error("ZIP central-directory size does not match parsed entries");
  }
  return entries;
}

function filesUnder(root) {
  const absoluteRoot = resolve(root);
  if (!existsSync(absoluteRoot)) throw new Error(`artifact root does not exist: ${absoluteRoot}`);
  const pending = [absoluteRoot];
  const files = [];
  while (pending.length > 0) {
    const current = pending.pop();
    const stat = lstatSync(current);
    if (stat.isSymbolicLink()) throw new Error(`symbolic link is not scan-safe: ${current}`);
    if (stat.isFile()) {
      files.push({ absolute: current, display: relative(process.cwd(), current) || current });
      continue;
    }
    if (!stat.isDirectory()) throw new Error(`unsupported artifact node: ${current}`);
    const children = readdirSync(current).sort().reverse();
    for (const child of children) pending.push(join(current, child));
  }
  return files.sort((a, b) => a.absolute.localeCompare(b.absolute));
}

function scanInputs(inputs, sentinels, suppliedLimits = {}) {
  const limits = { ...DEFAULT_LIMITS, ...suppliedLimits };
  const sentinelBuffers = sentinels
    .map((value) => String(value))
    .filter((value) => value.length > 0)
    .map((value, index) => {
      const utf8 = Buffer.from(value);
      const base64 = utf8.toString("base64");
      return {
        index,
        utf8,
        utf16le: Buffer.from(value, "utf16le"),
        encoded: [...new Set([base64, base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")])]
          .map((candidate) => Buffer.from(candidate)),
      };
    });
  if (sentinelBuffers.length === 0) throw new Error("at least one non-empty sentinel is required");

  const result = {
    files: inputs.length,
    representations: 0,
    archives: 0,
    base64Payloads: 0,
    duplicatePayloads: 0,
    duplicateArchiveEntries: 0,
    decodedBytes: 0,
    findings: [],
    errors: [],
  };
  const findingKeys = new Set();

  function addFinding(location, representation, sentinelIndex) {
    const key = `${location}\u0000${representation}\u0000${sentinelIndex}`;
    if (findingKeys.has(key)) return;
    findingKeys.add(key);
    result.findings.push({ location, representation, sentinelIndex });
  }

  function addError(location, error) {
    result.errors.push({ location, error: error instanceof Error ? error.message : String(error) });
  }

  function inspect(buffer, location, depth, representation) {
    result.representations++;
    result.decodedBytes += buffer.length;
    if (buffer.length > limits.maxNodeBytes) {
      addError(location, `payload exceeds scan limit (${buffer.length} > ${limits.maxNodeBytes})`);
      return;
    }
    if (result.decodedBytes > limits.maxTotalDecodedBytes) {
      addError(location, "total decoded-byte scan limit exceeded");
      return;
    }

    for (const sentinel of sentinelBuffers) {
      if (buffer.indexOf(sentinel.utf8) >= 0) addFinding(location, representation, sentinel.index);
      if (buffer.indexOf(sentinel.utf16le) >= 0) {
        addFinding(location, `${representation}:utf16le`, sentinel.index);
      }
      if (sentinel.encoded.some((candidate) => buffer.indexOf(candidate) >= 0)) {
        addFinding(location, `${representation}:base64`, sentinel.index);
      }
    }

    const extension = extname(location.split("::").at(-1) ?? location).toLowerCase();
    const zipLike = hasZipMagic(buffer) || extension === ".zip";
    const gzipLike =
      (buffer.length >= 2 && buffer[0] === 0x1f && buffer[1] === 0x8b) ||
      extension === ".gz" || extension === ".gzip";

    if ((zipLike || gzipLike) && depth >= limits.maxDepth) {
      addError(location, `nested archive depth limit reached at ${depth}`);
      return;
    }

    if (zipLike) {
      result.archives++;
      let entries;
      try {
        entries = parseZip(buffer, limits);
      } catch (error) {
        addError(location, error);
        return;
      }
      for (const entry of entries) {
        if (entry.duplicate) result.duplicateArchiveEntries++;
        inspect(entry.data, `${location}::zip:${entry.name}`, depth + 1, "zip-entry");
      }
      return;
    }

    if (gzipLike) {
      result.archives++;
      let decoded;
      try {
        decoded = gunzipSync(buffer, { maxOutputLength: limits.maxNodeBytes });
      } catch (error) {
        addError(location, `gzip decompression failed: ${error.message}`);
        return;
      }
      inspect(decoded, `${location}::gzip`, depth + 1, "gzip-member");
      return;
    }

    if (!looksTextual(buffer, location)) return;
    if (depth >= limits.maxDepth) {
      const textAtLimit = buffer.toString("utf8");
      if (BASE64_PATTERNS.some((pattern) => new RegExp(pattern.source, pattern.flags).test(textAtLimit))) {
        addError(location, `nested encoded-payload depth limit reached at ${depth}`);
      }
      return;
    }

    const text = buffer.toString("utf8");
    const seenCandidates = new Set();
    let candidateCount = 0;
    for (const sourcePattern of BASE64_PATTERNS) {
      const pattern = new RegExp(sourcePattern.source, sourcePattern.flags);
      for (const match of text.matchAll(pattern)) {
        candidateCount++;
        if (candidateCount > limits.maxBase64CandidatesPerNode) {
          addError(location, "base64 candidate limit exceeded");
          return;
        }
        const decoded = normalizeBase64(match[1]);
        if (!decoded) continue;
        const fingerprint = sha256(decoded);
        if (seenCandidates.has(fingerprint)) {
          result.duplicatePayloads++;
          continue;
        }
        seenCandidates.add(fingerprint);
        result.base64Payloads++;
        inspect(
          decoded,
          `${location}::base64:${result.base64Payloads}:${fingerprint.slice(0, 12)}`,
          depth + 1,
          "base64-decoded",
        );
      }
    }
  }

  for (const input of inputs) inspect(input.buffer, input.location, 0, input.representation ?? "raw");
  return result;
}

export function scanArtifactInputs({ inputs, sentinels, limits = {} }) {
  return scanInputs(inputs, sentinels, limits);
}

export function scanArtifactPaths({ roots, sentinels, limits = {} }) {
  const files = roots.flatMap(filesUnder);
  return scanInputs(
    files.map(({ absolute, display }) => ({
      location: display.replace(/\\/g, "/"),
      buffer: readFileSync(absolute),
      representation: "raw-file",
    })),
    sentinels,
    limits,
  );
}

export function formatScanSummary(result) {
  return {
    verdict: result.findings.length === 0 && result.errors.length === 0 ? "PASS" : "FAIL",
    files: result.files,
    representations: result.representations,
    archives: result.archives,
    base64Payloads: result.base64Payloads,
    duplicatePayloads: result.duplicatePayloads,
    duplicateArchiveEntries: result.duplicateArchiveEntries,
    decodedBytes: result.decodedBytes,
    findings: result.findings,
    errors: result.errors,
  };
}

function parseCli(argv) {
  const roots = [];
  const sentinelEnvNames = [];
  let json = false;
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--root") roots.push(argv[++index]);
    else if (arg === "--sentinel-env") sentinelEnvNames.push(argv[++index]);
    else if (arg === "--json") json = true;
    else throw new Error(`unknown or incomplete argument: ${arg}`);
  }
  if (roots.length === 0) throw new Error("at least one --root is required");
  const names = sentinelEnvNames.length > 0
    ? sentinelEnvNames
    : ["ARTIFACT_SCAN_SENTINELS", "SCANNER_ARTIFACT_SENTINEL"];
  const sentinels = names.flatMap((name) => (process.env[name] ?? "").split(/\r?\n/)).filter(Boolean);
  if (sentinels.length === 0) throw new Error(`no sentinels configured in: ${names.join(", ")}`);
  return { roots, sentinels, json };
}

function main() {
  try {
    const { roots, sentinels, json } = parseCli(process.argv.slice(2));
    const summary = formatScanSummary(scanArtifactPaths({ roots, sentinels }));
    console.log(json ? JSON.stringify(summary, null, 2) : JSON.stringify(summary));
    process.exit(summary.verdict === "PASS" ? 0 : 1);
  } catch (error) {
    console.error(JSON.stringify({ verdict: "FAIL", error: error.message }));
    process.exit(2);
  }
}

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) main();
