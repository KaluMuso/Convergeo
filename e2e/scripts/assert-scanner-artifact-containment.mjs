import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { join, relative } from "node:path";
import { inflateRawSync } from "node:zlib";

const sentinel = "S3_SCANNER_SECRET_SENTINEL_DO_NOT_UPLOAD";
const outputRoot = join(process.cwd(), ".scanner-artifact-regression");
const config = "playwright.scanner-artifact.config.ts";

function filesUnder(root) {
  if (!existsSync(root)) return [];
  return readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const path = join(root, entry.name);
    return entry.isDirectory() ? filesUnder(path) : [path];
  });
}

function zipEntries(buffer) {
  let eocd = -1;
  for (let offset = buffer.length - 22; offset >= Math.max(0, buffer.length - 65_557); offset--) {
    if (buffer.readUInt32LE(offset) === 0x06054b50) {
      eocd = offset;
      break;
    }
  }
  if (eocd < 0) throw new Error("ZIP end-of-central-directory record missing");

  const entries = [];
  const count = buffer.readUInt16LE(eocd + 10);
  let cursor = buffer.readUInt32LE(eocd + 16);
  for (let index = 0; index < count; index++) {
    if (buffer.readUInt32LE(cursor) !== 0x02014b50) {
      throw new Error(`invalid ZIP central directory entry ${index}`);
    }
    const method = buffer.readUInt16LE(cursor + 10);
    const compressedSize = buffer.readUInt32LE(cursor + 20);
    const fileNameLength = buffer.readUInt16LE(cursor + 28);
    const extraLength = buffer.readUInt16LE(cursor + 30);
    const commentLength = buffer.readUInt16LE(cursor + 32);
    const localOffset = buffer.readUInt32LE(cursor + 42);
    const name = buffer.subarray(cursor + 46, cursor + 46 + fileNameLength).toString("utf8");
    if (buffer.readUInt32LE(localOffset) !== 0x04034b50) {
      throw new Error(`invalid ZIP local header for ${name}`);
    }
    const localNameLength = buffer.readUInt16LE(localOffset + 26);
    const localExtraLength = buffer.readUInt16LE(localOffset + 28);
    const dataStart = localOffset + 30 + localNameLength + localExtraLength;
    const compressed = buffer.subarray(dataStart, dataStart + compressedSize);
    const data = method === 0 ? compressed : method === 8 ? inflateRawSync(compressed) : null;
    if (data) entries.push({ name, data });
    cursor += 46 + fileNameLength + extraLength + commentLength;
  }
  return entries;
}

rmSync(outputRoot, { recursive: true, force: true });
try {
  const run = spawnSync(
    process.execPath,
    ["./node_modules/@playwright/test/cli.js", "test", "--config", config],
    {
      cwd: process.cwd(),
      encoding: "utf8",
      env: { ...process.env, SCANNER_ARTIFACT_SENTINEL: sentinel },
    },
  );
  const transcript = `${run.stdout ?? ""}\n${run.stderr ?? ""}`;
  if (run.status === 0) throw new Error("deliberate scanner assertion unexpectedly passed");
  if (!transcript.includes("deliberate-scanner-artifact-failure")) {
    throw new Error(`scanner regression failed for an unexpected reason:\n${transcript}`);
  }
  if (transcript.includes(sentinel)) {
    throw new Error("scanner sentinel leaked into the Playwright process transcript");
  }

  const files = filesUnder(outputRoot);
  const forbiddenArtifacts = files.filter((path) =>
    /(?:\.zip|\.webm|\.png|error-context\.md)$/i.test(path),
  );
  const leaks = [];
  for (const path of files) {
    const body = readFileSync(path);
    if (body.includes(sentinel)) leaks.push(relative(process.cwd(), path));
    if (path.toLowerCase().endsWith(".zip")) {
      for (const entry of zipEntries(body)) {
        if (entry.data.includes(sentinel)) {
          leaks.push(`${relative(process.cwd(), path)}::${entry.name}`);
        }
      }
    }
  }

  if (forbiddenArtifacts.length > 0) {
    throw new Error(
      `scanner run retained forbidden diagnostics:\n${forbiddenArtifacts
        .map((path) => relative(process.cwd(), path))
        .join("\n")}`,
    );
  }
  if (leaks.length > 0) throw new Error(`scanner sentinel leaked:\n${leaks.join("\n")}`);

  console.log(
    `PASS scanner artifact containment: deliberate failure=${run.status}, files=${files.length}, sentinel matches=0`,
  );
} finally {
  if (process.env.KEEP_SCANNER_ARTIFACT_EVIDENCE !== "1") {
    rmSync(outputRoot, { recursive: true, force: true });
  }
}
