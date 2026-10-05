#!/usr/bin/env node
/** Format index blobs, then preserve unstaged edits with a three-way merge.
 * Git's index.lock excludes cooperative index writers. All worktree writes are
 * prepared first and checked against snapshots; rollback never overwrites an
 * observed concurrent edit. No filenames are interpreted as shell or glob input.
 */
import { spawn } from "node:child_process";
import { constants } from "node:fs";
import * as fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";

const MAX_OUTPUT = 256 * 1024 * 1024;

async function command(args, { cwd, env = process.env, input, allowed = [0] }) {
  return new Promise((resolve, reject) => {
    const child = spawn("git", args, { cwd, env, stdio: ["pipe", "pipe", "pipe"] });
    const stdout = [];
    const stderr = [];
    let size = 0;
    child.stdout.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_OUTPUT) child.kill();
      else stdout.push(chunk);
    });
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.on("error", reject);
    child.stdin.on("error", (error) => {
      if (error.code !== "EPIPE") reject(error);
    });
    child.on("close", (code) => {
      if (!allowed.includes(code) || size > MAX_OUTPUT) {
        reject(
          new Error(`git ${args[0]} failed (${code}): ${Buffer.concat(stderr).toString().trim()}`),
        );
      } else resolve({ output: Buffer.concat(stdout), code });
    });
    child.stdin.end(input);
  });
}

function text(buffer) {
  const value = buffer.toString("utf8");
  if (!Buffer.from(value).equals(buffer))
    throw new Error("Non-UTF-8 path or formatted text; refusing lossy conversion");
  return value;
}

function records(buffer) {
  if (!buffer.length) return [];
  if (buffer.at(-1) !== 0) throw new Error("Invalid NUL-delimited Git output");
  return text(buffer.subarray(0, -1)).split("\0");
}

async function readOptional(file) {
  try {
    return await fs.readFile(file);
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

function equal(a, b) {
  return a === null ? b === null : b !== null && a.equals(b);
}

async function snapshot(root, name) {
  const absolute = path.resolve(root, name);
  if (!absolute.startsWith(`${root}${path.sep}`))
    throw new Error(`Unsafe Git path: ${JSON.stringify(name)}`);
  let directory = root;
  for (const part of name.split("/").slice(0, -1)) {
    directory = path.join(directory, part);
    let stat;
    try {
      stat = await fs.lstat(directory);
    } catch (error) {
      if (error.code === "ENOENT") return { bytes: null };
      throw error;
    }
    if (!stat.isDirectory() || stat.isSymbolicLink())
      throw new Error(`Unsafe parent for ${JSON.stringify(name)}`);
  }
  let handle;
  try {
    handle = await fs.open(absolute, constants.O_RDONLY | constants.O_NOFOLLOW);
    const stat = await handle.stat();
    if (!stat.isFile()) throw new Error(`Not a regular worktree file: ${JSON.stringify(name)}`);
    return { bytes: await handle.readFile(), mode: stat.mode, ino: stat.ino, dev: stat.dev };
  } catch (error) {
    if (error.code === "ENOENT") return { bytes: null };
    throw error;
  } finally {
    await handle?.close();
  }
}

function sameSnapshot(a, b) {
  return (
    equal(a.bytes, b.bytes) &&
    (a.bytes === null || (a.mode === b.mode && a.ino === b.ino && a.dev === b.dev))
  );
}

// Cleanup only files we created, even if an existing untracked file collides or
// another process replaces a temporary path. O_EXCL and O_NOFOLLOW protect writes.
async function removeOwned(file, owned) {
  let stat;
  try {
    stat = await fs.lstat(file);
  } catch (error) {
    if (error.code === "ENOENT") return;
    throw error;
  }
  if (stat.ino === owned.ino && stat.dev === owned.dev) await fs.unlink(file);
}

async function writeTemporary(file, bytes, mode) {
  const handle = await fs.open(file, "wx", mode);
  const owned = await handle.stat();
  try {
    await handle.writeFile(bytes);
    await handle.chmod(mode);
    await handle.sync();
    const stat = await handle.stat();
    return { bytes, mode: stat.mode, ino: stat.ino, dev: stat.dev };
  } catch (error) {
    await removeOwned(file, owned);
    throw error;
  } finally {
    await handle.close();
  }
}

async function cleanupFailure(error, { committed, primaryError, location }) {
  if (primaryError) primaryError.message += `\nCleanup needs review: ${location}: ${error.message}`;
  else if (!committed) throw error;
  else
    console.warn(
      `Staged formatter committed successfully; cleanup needs review: ${location}: ${error.message}`,
    );
}

export async function formatStaged({ cwd = process.cwd(), env = process.env, onPhase } = {}) {
  const git = (args, options = {}) => command(args, { cwd, env, ...options });
  const root = path.resolve(
    text((await git(["rev-parse", "--show-toplevel"])).output).replace(/\n$/, ""),
  );
  cwd = root;
  // --path-format preserves linked-worktree and GIT_INDEX_FILE semantics.
  const index = text(
    (await git(["rev-parse", "--path-format=absolute", "--git-path", "index"])).output,
  ).replace(/\n$/, "");
  // A path-limited Git commit has already prepared a separate real index.
  // Updating only its next-index commit view would leave reverse formatting
  // staged afterwards, so require normal staging/commit instead.
  if (/^next-index-.*\.lock$/.test(path.basename(index))) {
    throw new Error(
      "Path-limited Git commits cannot safely format both Git indexes; use git add for the intended files, then git commit without path arguments",
    );
  }
  const lockPath = `${index}.lock`;
  let lock;
  let transaction;
  let committed = false;
  let retainRecovery = false;
  let primaryError;
  let cancelled = false;
  const changes = [];
  const applied = [];
  const onSignal = () => {
    cancelled = true;
  };
  const checkSignal = () => {
    if (cancelled) throw new Error("Staged formatting interrupted");
  };
  const assertLock = async () => {
    const actual = await fs.lstat(lockPath);
    const held = await lock.stat();
    if (actual.ino !== held.ino || actual.dev !== held.dev)
      throw new Error("Git index lock was replaced concurrently");
  };
  try {
    lock = await fs.open(lockPath, "wx", 0o600);
    process.on("SIGINT", onSignal);
    process.on("SIGTERM", onSignal);
    let indexMode = 0o600;
    let originalIndex = null;
    let originalIndexStat;
    let indexHandle;
    try {
      indexHandle = await fs.open(index, constants.O_RDONLY | constants.O_NOFOLLOW);
      const stat = await indexHandle.stat();
      if (!stat.isFile()) throw new Error("Git index is not a regular file");
      originalIndexStat = stat;
      indexMode = stat.mode;
      originalIndex = await indexHandle.readFile();
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    } finally {
      await indexHandle?.close();
    }
    transaction = await fs.mkdtemp(path.join(path.dirname(index), "format-staged-"));
    const temporaryIndex = path.join(transaction, "index");
    const temporaryEnv = { ...env, GIT_INDEX_FILE: temporaryIndex };
    if (originalIndex !== null) {
      await fs.writeFile(temporaryIndex, originalIndex);
      await fs.writeFile(path.join(transaction, "original-index"), originalIndex);
    } else await git(["read-tree", "--empty"], { env: temporaryEnv });
    if ((await git(["ls-files", "--unmerged", "-z"])).output.length)
      throw new Error("Unmerged index; resolve conflicts before formatting");
    const names = records(
      (
        await git([
          "diff",
          "--cached",
          "--name-only",
          "--no-renames",
          "--diff-filter=ACMRT",
          "-z",
          "--",
        ])
      ).output,
    );
    if (!names.length) return { formatted: 0 };
    const entries = new Map(
      records((await git(["ls-files", "--stage", "-z"])).output).map((record) => {
        const tab = record.indexOf("\t");
        const [mode, oid, stage] = record.slice(0, tab).split(" ");
        if (tab < 0 || stage !== "0") throw new Error("Invalid index entry");
        return [record.slice(tab + 1), { mode, oid }];
      }),
    );
    const gitConfiguration = (await git(["config", "--null", "--list"])).output;
    const behaviorPaths = new Set([
      path.join(root, ".gitignore"),
      path.join(root, ".prettierignore"),
      path.join(root, "packages/config/prettier.config.mjs"),
    ]);
    for (const name of names) {
      let directory = path.dirname(path.join(root, name));
      while (true) {
        behaviorPaths.add(path.join(directory, ".editorconfig"));
        if (directory === path.dirname(directory)) break;
        directory = path.dirname(directory);
      }
    }
    const behaviorFiles = new Map();
    for (const file of behaviorPaths) behaviorFiles.set(file, await readOptional(file));
    const attributeNames = ["filter", "working-tree-encoding", "text", "eol", "ident", "crlf"];
    const attributesFor = async (name) =>
      (
        await git(["check-attr", "-z", "--stdin", ...attributeNames], {
          input: Buffer.from(
            (Array.isArray(name) ? name : [name]).map((item) => `${item}\0`).join(""),
          ),
        })
      ).output;
    const attributeSnapshots = new Map();
    const assertBehavior = async () => {
      if (!(await git(["config", "--null", "--list"])).output.equals(gitConfiguration))
        throw new Error("Git configuration changed concurrently");
      if (
        attributeSnapshots.size &&
        !(await attributesFor([...attributeSnapshots.keys()])).equals(
          Buffer.concat([...attributeSnapshots.values()]),
        )
      ) {
        throw new Error("Git attributes changed concurrently");
      }
      for (const [file, original] of behaviorFiles) {
        const change = applied.find((item) => path.join(root, item.name) === file);
        if (!equal(change?.replacement ?? original, await readOptional(file)))
          throw new Error(`Formatter configuration changed concurrently: ${JSON.stringify(file)}`);
      }
    };
    const require = createRequire(path.join(root, "package.json"));
    const prettier = require("prettier");
    prettier.clearConfigCache();
    const configFile = path.join(root, "packages/config/prettier.config.mjs");
    for (const name of names) {
      checkSignal();
      const entry = entries.get(name);
      // Symlinks and submodules are Git objects, never formatter input.
      if (!entry || !["100644", "100755"].includes(entry.mode)) continue;
      const absolute = path.join(root, name);
      const config = await prettier.resolveConfig(absolute, {
        config: configFile,
        editorconfig: true,
      });
      const info = await prettier.getFileInfo(absolute, {
        ignorePath: [path.join(root, ".gitignore"), path.join(root, ".prettierignore")],
        resolveConfig: false,
      });
      if (info.ignored || (!info.inferredParser && !config?.parser)) continue;
      const rawAttributes = await attributesFor(name);
      attributeSnapshots.set(name, rawAttributes);
      const attributes = records(rawAttributes);
      for (let i = 0; i < attributes.length; i += 3) {
        if (
          ["filter", "working-tree-encoding"].includes(attributes[i + 1]) &&
          !["unspecified", "unset"].includes(attributes[i + 2])
        )
          throw new Error(`Unsupported Git ${attributes[i + 1]} for ${JSON.stringify(name)}`);
      }
      const staged = (await git(["cat-file", "blob", entry.oid])).output;
      const formatted = Buffer.from(
        await prettier.format(text(staged), { ...config, filepath: absolute }),
      );
      if (formatted.equals(staged)) continue;
      const original = await snapshot(root, name);
      const oid = text(
        (await git(["hash-object", "-w", `--path=${name}`, "--stdin"], { input: formatted }))
          .output,
      ).trim();
      if (oid === entry.oid) continue;
      const stagedWorktree = (await git(["cat-file", "--filters", `--path=${name}`, entry.oid]))
        .output;
      const formattedWorktree = (await git(["cat-file", "--filters", `--path=${name}`, oid]))
        .output;
      let replacement = null;
      if (original.bytes !== null) {
        if (original.bytes.equals(stagedWorktree)) replacement = formattedWorktree;
        else {
          const mergePaths = ["formatted", "staged", "working"].map((part) =>
            path.join(transaction, part),
          );
          await fs.writeFile(mergePaths[0], formattedWorktree);
          await fs.writeFile(mergePaths[1], stagedWorktree);
          await fs.writeFile(mergePaths[2], original.bytes);
          const merged = await git(["merge-file", "-p", "--", ...mergePaths], { allowed: [0, 1] });
          if (merged.code !== 0)
            throw new Error(
              `Formatting conflicts with unstaged edits in ${JSON.stringify(name)}; stage or separate those edits first`,
            );
          replacement = merged.output;
        }
      }
      changes.push({ name, entry, oid, original, replacement });
    }
    checkSignal();
    if (!changes.length) return { formatted: 0 };
    await git(["update-index", "-z", "--index-info"], {
      env: temporaryEnv,
      input: Buffer.from(
        changes.map(({ name, entry, oid }) => `${entry.mode} ${oid}\t${name}\0`).join(""),
      ),
    });
    const assertIndex = async () => {
      await assertLock();
      let current;
      try {
        current = await fs.open(index, constants.O_RDONLY | constants.O_NOFOLLOW);
        const stat = await current.stat();
        if (
          !originalIndexStat ||
          !stat.isFile() ||
          stat.mode !== originalIndexStat.mode ||
          stat.ino !== originalIndexStat.ino ||
          stat.dev !== originalIndexStat.dev ||
          !equal(originalIndex, await current.readFile())
        ) {
          throw new Error("Git index changed concurrently; formatting aborted");
        }
      } catch (error) {
        if (error.code !== "ENOENT" || originalIndex !== null) throw error;
      } finally {
        await current?.close();
      }
    };
    // Durable originals precede the first worktree promotion. A failed rollback
    // retains these files and the manifest instead of attempting a late backup.
    await fs.writeFile(
      path.join(transaction, "manifest.json"),
      JSON.stringify(
        changes.map(({ name, original }, i) => ({
          name,
          original: original.bytes === null ? null : `original-${i}`,
          mode: original.mode,
        })),
        null,
        2,
      ),
    );
    for (const [i, change] of changes.entries()) {
      if (change.original.bytes !== null) {
        const backup = await fs.open(path.join(transaction, `original-${i}`), "wx", 0o600);
        try {
          await backup.writeFile(change.original.bytes);
          await backup.sync();
        } finally {
          await backup.close();
        }
      }
    }
    await onPhase?.("prepared");
    checkSignal();
    await assertIndex();
    await assertBehavior();
    for (const change of changes) {
      if (!sameSnapshot(change.original, await snapshot(root, change.name)))
        throw new Error(`Worktree changed concurrently: ${JSON.stringify(change.name)}`);
    }
    for (const change of changes) {
      await onPhase?.("before-write", change.name);
      checkSignal();
      await assertBehavior();
      if (change.replacement === null || change.replacement.equals(change.original.bytes)) continue;
      if (!sameSnapshot(change.original, await snapshot(root, change.name)))
        throw new Error(`Worktree changed concurrently: ${JSON.stringify(change.name)}`);
      const absolute = path.join(root, change.name);
      const temp = path.join(
        path.dirname(absolute),
        `.format-staged-${path.basename(transaction)}-${applied.length}`,
      );
      let temporary;
      try {
        temporary = await writeTemporary(temp, change.replacement, change.original.mode);
        if (!sameSnapshot(change.original, await snapshot(root, change.name)))
          throw new Error(`Worktree changed concurrently: ${JSON.stringify(change.name)}`);
        if (!sameSnapshot(temporary, await snapshot(root, path.relative(root, temp))))
          throw new Error("Temporary formatter file changed concurrently");
        change.written = temporary;
        await fs.rename(temp, absolute);
        applied.push(change);
        await onPhase?.("written", change.name);
      } finally {
        if (temporary) await removeOwned(temp, temporary);
      }
    }
    checkSignal();
    await assertIndex();
    for (const change of changes) {
      const expected = change.written ?? change.original;
      if (!sameSnapshot(expected, await snapshot(root, change.name)))
        throw new Error(`Worktree changed concurrently: ${JSON.stringify(change.name)}`);
    }
    await onPhase?.("before-commit");
    checkSignal();
    await assertBehavior();
    await lock.chmod(indexMode);
    await lock.writeFile(await fs.readFile(temporaryIndex));
    await lock.sync();
    checkSignal();
    await assertIndex();
    await assertBehavior();
    for (const change of changes) {
      if (!sameSnapshot(change.written ?? change.original, await snapshot(root, change.name)))
        throw new Error(`Worktree changed concurrently: ${JSON.stringify(change.name)}`);
    }
    await fs.rename(lockPath, index);
    committed = true;
    return { formatted: changes.length };
  } catch (error) {
    primaryError = error;
    const rollbackErrors = [];
    for (const change of applied.reverse()) {
      try {
        if (!sameSnapshot(change.written, await snapshot(root, change.name)))
          throw new Error("Concurrent edit retained; automatic rollback refused");
        const backup = path.join(
          path.dirname(path.join(root, change.name)),
          `.format-staged-${path.basename(transaction)}-rollback-${applied.indexOf(change)}`,
        );
        const temporary = await writeTemporary(backup, change.original.bytes, change.original.mode);
        try {
          if (!sameSnapshot(change.written, await snapshot(root, change.name)))
            throw new Error("Concurrent edit retained; automatic rollback refused");
          if (!sameSnapshot(temporary, await snapshot(root, path.relative(root, backup))))
            throw new Error("Temporary rollback file changed concurrently");
          await fs.rename(backup, path.join(root, change.name));
        } finally {
          await removeOwned(backup, temporary);
        }
      } catch (rollbackError) {
        retainRecovery = true;
        rollbackErrors.push(`${JSON.stringify(change.name)}: ${rollbackError.message}`);
      }
    }
    if (rollbackErrors.length) {
      error.message += `\nRollback needs review: ${rollbackErrors.join("; ")}. Original bytes retained in ${transaction}`;
      retainRecovery = true;
    }
    throw error;
  } finally {
    process.off("SIGINT", onSignal);
    process.off("SIGTERM", onSignal);
    if (lock) {
      try {
        if (!committed) {
          await assertLock();
          await fs.unlink(lockPath);
        }
      } catch (error) {
        retainRecovery = true;
        await cleanupFailure(error, { committed, primaryError, location: lockPath });
      } finally {
        try {
          await lock.close();
        } catch (error) {
          await cleanupFailure(error, { committed, primaryError, location: index });
        }
      }
    }
    if (transaction && !retainRecovery) {
      try {
        await fs.rm(transaction, { recursive: true, force: true });
      } catch (error) {
        await cleanupFailure(error, { committed, primaryError, location: transaction });
      }
    }
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  formatStaged()
    .then(({ formatted }) => {
      console.log(`Staged formatter: ${formatted} file(s) formatted`);
    })
    .catch((error) => {
      console.error(`Staged formatter: ${error.message}`);
      process.exitCode = 1;
    });
}
