// Reject changed index entries whose committed type is a symlink before any
// formatter runs. Read Git modes and NUL-delimited paths; never inspect targets.
import { Buffer } from "node:buffer";
import { spawn } from "node:child_process";
import console from "node:console";
import process from "node:process";
import { fileURLToPath, URL } from "node:url";

const git = spawn(
  "git",
  [
    "-c",
    "submodule.recurse=false",
    "-c",
    "diff.relative=false",
    "diff",
    "--cached",
    "--raw",
    "--no-abbrev",
    "--no-renames",
    "--no-ext-diff",
    "--no-textconv",
    "-z",
  ],
  {
    cwd: fileURLToPath(new URL("../../", import.meta.url)),
    stdio: ["ignore", "pipe", "inherit"],
  },
);

let pending = Buffer.alloc(0);
let destinationMode = null;
let inspectionFailed = false;
let spawnFailed = false;
let symlinkCount = 0;
const paths = [];

git.stdout.on("data", (chunk) => {
  if (inspectionFailed) return;
  pending = Buffer.concat([pending, chunk]);
  let end;
  while ((end = pending.indexOf(0)) !== -1) {
    const token = pending.subarray(0, end);
    pending = pending.subarray(end + 1);
    if (destinationMode === null) {
      // --no-renames represents renames/copies as single-path additions/deletions.
      const header = /^:([0-7]{6}) ([0-7]{6}) [0-9a-f]+ [0-9a-f]+ [A-Z][0-9]*$/.exec(
        token.toString("utf8"),
      );
      if (!header) {
        inspectionFailed = true;
        return;
      }
      destinationMode = header[2];
    } else {
      if (token.length === 0) {
        inspectionFailed = true;
        return;
      }
      if (destinationMode === "120000") {
        symlinkCount++;
        if (paths.length < 20) paths.push(JSON.stringify(token.toString("utf8")));
      }
      destinationMode = null;
    }
  }
});

git.on("error", () => {
  spawnFailed = true;
  console.error("Cannot inspect the staged index; commit blocked before formatting.");
  process.exitCode = 1;
});

git.on("close", (code) => {
  if (spawnFailed) return;
  if (code !== 0 || inspectionFailed || pending.length !== 0 || destinationMode !== null) {
    console.error("Cannot inspect the staged index; commit blocked before formatting.");
    process.exitCode = 1;
    return;
  }
  if (symlinkCount !== 0) {
    console.error("Commit blocked: staged symbolic links are not allowed.");
    for (const path of paths) console.error(`  ${path}`);
    if (symlinkCount > paths.length) {
      console.error(`  ... and ${symlinkCount - paths.length} more`);
    }
    process.exitCode = 1;
  }
});
