import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import * as fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, URL } from "node:url";

import { formatStaged } from "./format-staged.mjs";

const dependencyRoot =
  process.env.STAGED_FORMATTER_TEST_NODE_MODULES ??
  fileURLToPath(new URL("../node_modules", import.meta.url));

async function repository(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "format-staged-test-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  // Strip inherited Git redirects so every operation stays in this disposable repo.
  const fixtureEnv = Object.fromEntries(
    Object.entries(process.env).filter(([key]) => !key.startsWith("GIT_")),
  );
  Object.assign(fixtureEnv, {
    GIT_CONFIG_NOSYSTEM: "1",
    GIT_CONFIG_GLOBAL: "/dev/null",
    GIT_AUTHOR_NAME: "Fixture",
    GIT_AUTHOR_EMAIL: "fixture@example.invalid",
    GIT_COMMITTER_NAME: "Fixture",
    GIT_COMMITTER_EMAIL: "fixture@example.invalid",
  });
  const git = (...args) =>
    execFileSync("git", ["--literal-pathspecs", ...args], {
      cwd: root,
      env: fixtureEnv,
      stdio: ["pipe", "pipe", "pipe"],
    });
  git("init", "-q");
  git("config", "core.autocrlf", "false");
  await fs.mkdir(path.join(root, "packages/config"), { recursive: true });
  await fs.writeFile(
    path.join(root, "packages/config/prettier.config.mjs"),
    'export default { semi: true, singleQuote: false, endOfLine: "lf" };\n',
  );
  await fs.writeFile(path.join(root, "package.json"), '{"private":true}\n');
  await fs.writeFile(path.join(root, ".gitignore"), "node_modules\n");
  await fs.writeFile(path.join(root, ".prettierignore"), "ignored.js\n");
  await fs.symlink(
    dependencyRoot,
    path.join(root, "node_modules"),
    process.platform === "win32" ? "junction" : "dir",
  );
  git("add", ".");
  git("commit", "-qm", "fixture");
  const write = async (name, content) => {
    await fs.mkdir(path.dirname(path.join(root, name)), { recursive: true });
    await fs.writeFile(path.join(root, name), content);
  };
  const stage = async (name, content) => {
    await write(name, content);
    git("add", "--", name);
  };
  const indexBytes = () => fs.readFile(path.join(root, ".git/index"));
  const blob = (name) => git("show", `:0:${name}`);
  const run = (options = {}) => formatStaged({ cwd: root, env: fixtureEnv, ...options });
  const clean = async () => {
    await assert.rejects(fs.lstat(path.join(root, ".git/index.lock")), { code: "ENOENT" });
    assert.deepEqual(
      (await fs.readdir(path.join(root, ".git"))).filter((name) =>
        name.startsWith("format-staged-"),
      ),
      [],
    );
  };
  return { root, git, write, stage, blob, indexBytes, run, clean, fixtureEnv };
}

async function preservesOnFailure(repo, action, pattern) {
  const index = await repo.indexBytes();
  await assert.rejects(action, pattern);
  assert.deepEqual(await repo.indexBytes(), index);
  await repo.clean();
}

test("empty staged set is a no-op, including index bytes", async (t) => {
  const repo = await repository(t);
  const before = await repo.indexBytes();
  assert.deepEqual(await repo.run(), { formatted: 0 });
  assert.deepEqual(await repo.indexBytes(), before);
  await repo.clean();
});

test("formats all literal filenames; preserves executable modes and unrelated bytes", async (t) => {
  const repo = await repository(t);
  const names = [
    "with space.js",
    "line\nbreak.js",
    "-leading.js",
    "雪.js",
    "[literal].js",
    "colon:name.js",
    "tab\tname.js",
    ":(glob)*.js",
    "quotes\"'$().js",
    "$()literal.js",
    "`literal-command`.js",
    "nested/file.js",
    "app/[locale]/(auth)/email-form.test.tsx",
  ].filter(
    (name) =>
      process.platform !== "win32" ||
      !Array.from(name).some((char) => char.charCodeAt(0) < 32 || /[<>:"\\|?*]/.test(char)),
  );
  for (const name of names) await repo.stage(name, "const value=1\n");
  await fs.chmod(path.join(repo.root, "-leading.js"), 0o755);
  repo.git("add", "--", "-leading.js");
  const untracked = Buffer.from([0, 255, 10, 13, 1]);
  await repo.write("untracked.bin", untracked);
  assert.equal((await repo.run()).formatted, names.length);
  for (const name of names) {
    assert.equal(repo.blob(name).toString(), "const value = 1;\n");
    assert.equal(await fs.readFile(path.join(repo.root, name), "utf8"), "const value = 1;\n");
  }
  if (process.platform !== "win32") {
    assert.equal((await fs.stat(path.join(repo.root, "-leading.js"))).mode & 0o777, 0o755);
    assert.match(repo.git("ls-files", "--stage", "--", "-leading.js").toString(), /^100755 /);
  }
  assert.deepEqual(await fs.readFile(path.join(repo.root, "untracked.bin")), untracked);
  await repo.clean();
});

test("unknown binary and ignored files retain index and worktree bytes", async (t) => {
  const repo = await repository(t);
  const binary = Buffer.from([0, 255, 254, 10]);
  await repo.stage("unknown.custom", binary);
  await repo.stage("ignored.js", "invalid javascript {\n");
  await repo.write("ignored.js", "unstaged ignored contents\n");
  const before = await repo.indexBytes();
  assert.equal((await repo.run()).formatted, 0);
  assert.deepEqual(await repo.indexBytes(), before);
  assert.deepEqual(repo.blob("unknown.custom"), binary);
  assert.equal(
    await fs.readFile(path.join(repo.root, "ignored.js"), "utf8"),
    "unstaged ignored contents\n",
  );
  await repo.clean();
});

test("partial staging formats only staged blob and merges distant unstaged changes", async (t) => {
  const repo = await repository(t);
  const staged =
    "const first=1\n\n// separator one\n// separator two\n// separator three\n\nconst last = 2;\n";
  await repo.stage("partial.js", staged);
  await repo.write(
    "partial.js",
    staged.replace("const last = 2;", "const last = 3;\n// unstaged literal bytes  "),
  );
  assert.equal((await repo.run()).formatted, 1);
  assert.equal(
    repo.blob("partial.js").toString(),
    staged.replace("const first=1", "const first = 1;"),
  );
  assert.equal(
    await fs.readFile(path.join(repo.root, "partial.js"), "utf8"),
    staged
      .replace("const first=1", "const first = 1;")
      .replace("const last = 2;", "const last = 3;\n// unstaged literal bytes  "),
  );
  await repo.clean();
});

test("overlapping unstaged edit fails before mutation of any candidate", async (t) => {
  const repo = await repository(t);
  await repo.stage("a.js", "const first=1\n");
  await repo.stage("z.js", "const value=1\n");
  await repo.write("z.js", "const value=2\n");
  await preservesOnFailure(repo, repo.run(), /conflicts with unstaged edits/);
  assert.equal(await fs.readFile(path.join(repo.root, "a.js"), "utf8"), "const first=1\n");
  assert.equal(await fs.readFile(path.join(repo.root, "z.js"), "utf8"), "const value=2\n");
});

test("a parser error after a valid candidate leaves everything unchanged", async (t) => {
  const repo = await repository(t);
  await repo.stage("a.js", "const value=1\n");
  await repo.stage("z.js", "const =\n");
  await preservesOnFailure(repo, repo.run(), /Unexpected token/);
  assert.equal(await fs.readFile(path.join(repo.root, "a.js"), "utf8"), "const value=1\n");
});

test("staged rename formats destination and staged deletion preserves same-name untracked file", async (t) => {
  const repo = await repository(t);
  await repo.stage("old.js", "const old = 1;\n");
  await repo.stage("deleted.js", "const removed = 1;\n");
  repo.git("commit", "-qm", "files");
  repo.git("mv", "--", "old.js", "new name.js");
  await repo.stage("new name.js", "const old=1\n");
  repo.git("rm", "--", "deleted.js");
  await repo.write("deleted.js", "untracked replacement  \n");
  assert.equal((await repo.run()).formatted, 1);
  assert.equal(repo.blob("new name.js").toString(), "const old = 1;\n");
  assert.equal(
    await fs.readFile(path.join(repo.root, "deleted.js"), "utf8"),
    "untracked replacement  \n",
  );
  await repo.clean();
});

test("staged file deleted from worktree stays absent", async (t) => {
  const repo = await repository(t);
  await repo.stage("missing.js", "const value=1\n");
  await fs.unlink(path.join(repo.root, "missing.js"));
  assert.equal((await repo.run()).formatted, 1);
  assert.equal(repo.blob("missing.js").toString(), "const value = 1;\n");
  await assert.rejects(fs.lstat(path.join(repo.root, "missing.js")), { code: "ENOENT" });
  await repo.clean();
});

test("intent-to-add is not promoted into the commit", async (t) => {
  const repo = await repository(t);
  await repo.write("intent.js", "const value=1\n");
  repo.git("add", "-N", "--", "intent.js");
  const index = await repo.indexBytes();
  assert.equal((await repo.run()).formatted, 0);
  assert.deepEqual(await repo.indexBytes(), index);
  assert.equal(await fs.readFile(path.join(repo.root, "intent.js"), "utf8"), "const value=1\n");
  await repo.clean();
});

test("index symlink is skipped; worktree symlink replacing regular index file fails safely", async (t) => {
  const repo = await repository(t);
  await repo.write("target.js", "const value=1\n");
  await fs.symlink("target.js", path.join(repo.root, "link.js"));
  repo.git("add", "--", "link.js");
  assert.equal((await repo.run()).formatted, 0);
  assert.equal(await fs.readlink(path.join(repo.root, "link.js")), "target.js");
  await repo.stage("regular.js", "const value=1\n");
  await fs.unlink(path.join(repo.root, "regular.js"));
  await fs.symlink("target.js", path.join(repo.root, "regular.js"));
  await preservesOnFailure(repo, repo.run(), /ELOOP/);
  assert.equal(await fs.readFile(path.join(repo.root, "target.js"), "utf8"), "const value=1\n");
});

test("custom Git clean/smudge and working-tree encoding fail closed", async (t) => {
  const repo = await repository(t);
  await repo.stage("file.js", "const value=1\n");
  await repo.write(".gitattributes", "file.js filter=custom\n");
  await preservesOnFailure(repo, repo.run(), /Unsupported Git filter/);
  await repo.write(".gitattributes", "file.js working-tree-encoding=UTF-8\n");
  await preservesOnFailure(repo, repo.run(), /Unsupported Git working-tree-encoding/);
});

test("Git CRLF conversion keeps LF in index and CRLF in worktree", async (t) => {
  const repo = await repository(t);
  await repo.write(".gitattributes", "*.js text eol=crlf\n");
  await repo.stage("crlf.js", "const value=1\r\n");
  assert.equal((await repo.run()).formatted, 1);
  assert.equal(repo.blob("crlf.js").toString(), "const value = 1;\n");
  assert.equal(await fs.readFile(path.join(repo.root, "crlf.js"), "utf8"), "const value = 1;\r\n");
  await repo.clean();
});

test("another index lock blocks without removing its lock", async (t) => {
  const repo = await repository(t);
  await repo.stage("file.js", "const value=1\n");
  await fs.writeFile(path.join(repo.root, ".git/index.lock"), "another writer");
  const before = await repo.indexBytes();
  await assert.rejects(repo.run(), /EEXIST/);
  assert.deepEqual(await repo.indexBytes(), before);
  assert.equal(
    await fs.readFile(path.join(repo.root, ".git/index.lock"), "utf8"),
    "another writer",
  );
});

test("concurrent worktree edit before writes is preserved and blocks commit", async (t) => {
  const repo = await repository(t);
  await repo.stage("file.js", "const value=1\n");
  await preservesOnFailure(
    repo,
    repo.run({
      onPhase: async (phase) => {
        if (phase === "prepared") await repo.write("file.js", "concurrent editor bytes\n");
      },
    }),
    /Worktree changed concurrently/,
  );
  assert.equal(
    await fs.readFile(path.join(repo.root, "file.js"), "utf8"),
    "concurrent editor bytes\n",
  );
});

test("concurrent index change is retained and blocks worktree mutations", async (t) => {
  const repo = await repository(t);
  await repo.stage("file.js", "const value=1\n");
  const concurrent = Buffer.from("concurrent index bytes");
  await assert.rejects(
    repo.run({
      onPhase: async (phase) => {
        if (phase === "prepared")
          await fs.writeFile(path.join(repo.root, ".git/index"), concurrent);
      },
    }),
    /index changed concurrently/,
  );
  assert.deepEqual(await repo.indexBytes(), concurrent);
  assert.equal(await fs.readFile(path.join(repo.root, "file.js"), "utf8"), "const value=1\n");
  await repo.clean();
});

test("failure after first promotion rolls worktree bytes and modes back", async (t) => {
  const repo = await repository(t);
  await repo.stage("a.js", "const a=1\n");
  await repo.stage("b.js", "const b=1\n");
  await fs.chmod(path.join(repo.root, "a.js"), 0o755);
  await preservesOnFailure(
    repo,
    repo.run({
      onPhase: (phase) => {
        if (phase === "written") throw new Error("injected promotion failure");
      },
    }),
    /injected promotion failure/,
  );
  assert.equal(await fs.readFile(path.join(repo.root, "a.js"), "utf8"), "const a=1\n");
  assert.equal(await fs.readFile(path.join(repo.root, "b.js"), "utf8"), "const b=1\n");
  assert.equal((await fs.stat(path.join(repo.root, "a.js"))).mode & 0o777, 0o755);
});

test("rollback retains a concurrent edit after promotion and preserves recovery bytes", async (t) => {
  const repo = await repository(t);
  await repo.stage("file.js", "const value=1\n");
  const before = await repo.indexBytes();
  await assert.rejects(
    repo.run({
      onPhase: async (phase) => {
        if (phase === "written") {
          await repo.write("file.js", "concurrent after write\n");
          throw new Error("injected failure");
        }
      },
    }),
    /Rollback needs review.*Original bytes retained/s,
  );
  assert.deepEqual(await repo.indexBytes(), before);
  assert.equal(
    await fs.readFile(path.join(repo.root, "file.js"), "utf8"),
    "concurrent after write\n",
  );
  const recovery = (await fs.readdir(path.join(repo.root, ".git"))).find((name) =>
    name.startsWith("format-staged-"),
  );
  assert.ok(recovery);
  assert.equal(
    await fs.readFile(path.join(repo.root, ".git", recovery, "original-0"), "utf8"),
    "const value=1\n",
  );
  await assert.rejects(fs.lstat(path.join(repo.root, ".git/index.lock")), { code: "ENOENT" });
});

test("ancestor swapped to a symlink is rejected without modifying external target", async (t) => {
  const repo = await repository(t);
  await repo.stage("directory/file.js", "const value=1\n");
  await fs.mkdir(path.join(repo.root, "external"));
  await repo.write("external/file.js", "external untouched\n");
  await preservesOnFailure(
    repo,
    repo.run({
      onPhase: async (phase) => {
        if (phase === "prepared") {
          await fs.rename(
            path.join(repo.root, "directory"),
            path.join(repo.root, "original-directory"),
          );
          await fs.symlink("external", path.join(repo.root, "directory"));
        }
      },
    }),
    /Unsafe parent/,
  );
  assert.equal(
    await fs.readFile(path.join(repo.root, "external/file.js"), "utf8"),
    "external untouched\n",
  );
});

test("unmerged index is refused unchanged", async (t) => {
  const repo = await repository(t);
  await repo.stage("file.js", "const value=1\n");
  const oid = repo.git("rev-parse", ":0:file.js").toString().trim();
  execFileSync("git", ["update-index", "--index-info"], {
    cwd: repo.root,
    env: repo.fixtureEnv,
    input: `0 ${"0".repeat(40)}\tfile.js\n100644 ${oid} 1\tfile.js\n100644 ${oid} 2\tfile.js\n100644 ${oid} 3\tfile.js\n`,
  });
  await preservesOnFailure(repo, repo.run(), /Unmerged index/);
});

test("split index is supported without changing unrelated entries", async (t) => {
  const repo = await repository(t);
  await repo.stage("file.js", "const value=1\n");
  repo.git("update-index", "--split-index");
  assert.equal((await repo.run()).formatted, 1);
  assert.equal(repo.blob("file.js").toString(), "const value = 1;\n");
  assert.equal(repo.git("ls-files").toString().split("\n").filter(Boolean).length, 5);
  await repo.clean();
});

test("a removed parent directory stays absent while staged content is formatted", async (t) => {
  const repo = await repository(t);
  await repo.stage("removed/file.js", "const value=1\n");
  await fs.rm(path.join(repo.root, "removed"), { recursive: true });
  assert.equal((await repo.run()).formatted, 1);
  assert.equal(repo.blob("removed/file.js").toString(), "const value = 1;\n");
  await assert.rejects(fs.lstat(path.join(repo.root, "removed")), { code: "ENOENT" });
  await repo.clean();
});

test("unborn repository formats staged addition", async (t) => {
  const repo = await repository(t);
  repo.git("update-ref", "-d", "HEAD");
  await repo.stage("file.js", "const value=1\n");
  assert.equal((await repo.run()).formatted, 2); // package.json is also staged in unborn index.
  assert.equal(repo.blob("file.js").toString(), "const value = 1;\n");
  await repo.clean();
});

test("invalid UTF-8 known text refuses lossy formatting", async (t) => {
  const repo = await repository(t);
  await repo.stage("file.js", Buffer.from([0xff, 10]));
  await preservesOnFailure(repo, repo.run(), /Non-UTF-8/);
  assert.deepEqual(repo.blob("file.js"), Buffer.from([0xff, 10]));
});

test("configuration and attribute changes during preparation block writes", async (t) => {
  for (const kind of ["prettier", "ignore", "editorconfig", "gitconfig", "attributes"]) {
    const repo = await repository(t);
    await repo.stage("file.js", "const value=1\n");
    await preservesOnFailure(
      repo,
      repo.run({
        onPhase: async (phase) => {
          if (phase !== "prepared") return;
          if (kind === "prettier")
            await repo.write(
              "packages/config/prettier.config.mjs",
              "export default { semi: false };\n",
            );
          if (kind === "ignore") await repo.write(".prettierignore", "*.js\n");
          if (kind === "editorconfig")
            await repo.write(".editorconfig", "root = true\n[*]\nindent_size = 4\n");
          if (kind === "gitconfig") repo.git("config", "core.autocrlf", "true");
          if (kind === "attributes") await repo.write(".gitattributes", "file.js text eol=crlf\n");
        },
      }),
      /configuration changed concurrently|attributes changed concurrently/,
    );
    assert.equal(await fs.readFile(path.join(repo.root, "file.js"), "utf8"), "const value=1\n");
  }
});

test("failure immediately before index promotion restores all worktree changes", async (t) => {
  const repo = await repository(t);
  await repo.stage("a.js", "const a=1\n");
  await repo.stage("b.js", "const b=1\n");
  await preservesOnFailure(
    repo,
    repo.run({
      onPhase: (phase) => {
        if (phase === "before-commit") throw new Error("injected final failure");
      },
    }),
    /injected final failure/,
  );
  assert.equal(await fs.readFile(path.join(repo.root, "a.js"), "utf8"), "const a=1\n");
  assert.equal(await fs.readFile(path.join(repo.root, "b.js"), "utf8"), "const b=1\n");
});

test("SIGTERM during transaction rolls worktree back and blocks promotion", async (t) => {
  const repo = await repository(t);
  await repo.stage("file.js", "const value=1\n");
  await preservesOnFailure(
    repo,
    repo.run({
      onPhase: (phase) => {
        if (phase === "written") process.emit("SIGTERM");
      },
    }),
    /interrupted/,
  );
  assert.equal(await fs.readFile(path.join(repo.root, "file.js"), "utf8"), "const value=1\n");
});

test("temporary filename collision retains an existing untracked file", async (t) => {
  const repo = await repository(t);
  await repo.stage("file.js", "const value=1\n");
  let collision;
  await preservesOnFailure(
    repo,
    repo.run({
      onPhase: async (phase) => {
        if (phase !== "prepared") return;
        const transaction = (await fs.readdir(path.join(repo.root, ".git"))).find((name) =>
          name.startsWith("format-staged-"),
        );
        collision = `.format-staged-${transaction}-0`;
        await repo.write(collision, "untracked collision bytes\n");
      },
    }),
    /EEXIST/,
  );
  assert.equal(
    await fs.readFile(path.join(repo.root, collision), "utf8"),
    "untracked collision bytes\n",
  );
  assert.equal(await fs.readFile(path.join(repo.root, "file.js"), "utf8"), "const value=1\n");
});

test("success preserves original index permissions", async (t) => {
  const repo = await repository(t);
  await repo.stage("file.js", "const value=1\n");
  await fs.chmod(path.join(repo.root, ".git/index"), 0o664);
  assert.equal((await repo.run()).formatted, 1);
  assert.equal((await fs.stat(path.join(repo.root, ".git/index"))).mode & 0o777, 0o664);
  await repo.clean();
});

async function installRealHooks(repo) {
  const sourceRoot = fileURLToPath(new URL("..", import.meta.url));
  await repo.write(
    "scripts/format-staged.mjs",
    await fs.readFile(path.join(sourceRoot, "scripts/format-staged.mjs")),
  );
  await repo.write("lefthook.yml", await fs.readFile(path.join(sourceRoot, "lefthook.yml")));
  await repo.write(
    "commitlint.config.cjs",
    await fs.readFile(path.join(sourceRoot, "commitlint.config.cjs")),
  );
  await repo.write(
    "package.json",
    JSON.stringify({
      private: true,
      packageManager: "pnpm@9.15.4",
      scripts: { "format:staged": "node scripts/format-staged.mjs" },
    }),
  );
  execFileSync(process.execPath, [path.join(dependencyRoot, "lefthook/bin/index.js"), "install"], {
    cwd: repo.root,
    env: repo.fixtureEnv,
    stdio: "pipe",
  });
}

test("real lefthook pre-commit formats and commitlint validates normal disposable commits", async (t) => {
  const repo = await repository(t);
  await installRealHooks(repo);
  await repo.stage("file.js", "const value=1\n");
  repo.git("commit", "-qm", "fix: format fixture");
  assert.equal(repo.git("show", "HEAD:file.js").toString(), "const value = 1;\n");
  assert.equal(repo.blob("file.js").toString(), "const value = 1;\n");
  assert.equal(await fs.readFile(path.join(repo.root, "file.js"), "utf8"), "const value = 1;\n");
  const previousHead = repo.git("rev-parse", "HEAD");
  await repo.stage("file.js", "const value = 2;\n");
  const index = repo.git("ls-files", "--stage", "-v", "-z");
  assert.throws(() => repo.git("commit", "-qm", "bad message"), /Command failed/);
  assert.deepEqual(repo.git("rev-parse", "HEAD"), previousHead);
  assert.deepEqual(repo.git("ls-files", "--stage", "-v", "-z"), index);
  repo.git("commit", "-qm", "fix: valid conventional message");
  assert.equal(repo.git("show", "HEAD:file.js").toString(), "const value = 2;\n");
  await repo.clean();
});

test("real hook parser failure blocks Git commit and preserves index/worktree", async (t) => {
  const repo = await repository(t);
  await installRealHooks(repo);
  await repo.stage("file.js", "const =\n");
  const previousHead = repo.git("rev-parse", "HEAD");
  const index = repo.git("ls-files", "--stage", "-v", "-z");
  assert.throws(() => repo.git("commit", "-qm", "fix: invalid fixture"), /Command failed/);
  assert.deepEqual(repo.git("rev-parse", "HEAD"), previousHead);
  assert.deepEqual(repo.git("ls-files", "--stage", "-v", "-z"), index);
  assert.equal(await fs.readFile(path.join(repo.root, "file.js"), "utf8"), "const =\n");
  await repo.clean();
});

test("real hook preserves unstaged edits through normal Git commit", async (t) => {
  const repo = await repository(t);
  await installRealHooks(repo);
  const staged =
    "const first=1\n\n// separator one\n// separator two\n// separator three\n\nconst last = 2;\n";
  await repo.stage("file.js", staged);
  await repo.write(
    "file.js",
    staged.replace("const last = 2;", "const last = 3;\n// unstaged bytes  "),
  );
  repo.git("commit", "-qm", "fix: partially staged fixture");
  assert.equal(
    repo.git("show", "HEAD:file.js").toString(),
    staged.replace("const first=1", "const first = 1;"),
  );
  assert.equal(
    repo.blob("file.js").toString(),
    staged.replace("const first=1", "const first = 1;"),
  );
  assert.equal(
    await fs.readFile(path.join(repo.root, "file.js"), "utf8"),
    staged
      .replace("const first=1", "const first = 1;")
      .replace("const last = 2;", "const last = 3;\n// unstaged bytes  "),
  );
  await repo.clean();
});

test("real hook rejects path-limited Git commit without changing either index or worktree", async (t) => {
  const repo = await repository(t);
  await repo.stage("take.js", "const take = 1;\n");
  await repo.stage("later.js", "const later = 1;\n");
  repo.git("commit", "-qm", "fixture files");
  await installRealHooks(repo);
  await repo.stage("take.js", "const take=2\n");
  await repo.stage("later.js", "const later=2\n");
  const previousHead = repo.git("rev-parse", "HEAD");
  const index = repo.git("ls-files", "--stage", "-v", "-z");
  let failure;
  try {
    repo.git("commit", "-qm", "fix: path-limited fixture", "--", "take.js");
  } catch (error) {
    failure = error;
  }
  assert.ok(failure);
  assert.match(
    Buffer.concat([failure.stdout, failure.stderr]).toString(),
    /Path-limited Git commits/,
  );
  assert.deepEqual(repo.git("rev-parse", "HEAD"), previousHead);
  assert.deepEqual(repo.git("ls-files", "--stage", "-v", "-z"), index);
  assert.equal(await fs.readFile(path.join(repo.root, "take.js"), "utf8"), "const take=2\n");
  assert.equal(await fs.readFile(path.join(repo.root, "later.js"), "utf8"), "const later=2\n");
  await repo.clean();
});

test("real hook supports git commit -a with Git's index.lock commit view", async (t) => {
  const repo = await repository(t);
  await repo.stage("file.js", "const value = 1;\n");
  repo.git("commit", "-qm", "fixture file");
  await installRealHooks(repo);
  await repo.write("file.js", "const value=2\n");
  repo.git("commit", "-qam", "fix: commit all fixture");
  assert.equal(repo.git("show", "HEAD:file.js").toString(), "const value = 2;\n");
  assert.equal(repo.blob("file.js").toString(), "const value = 2;\n");
  assert.equal(await fs.readFile(path.join(repo.root, "file.js"), "utf8"), "const value = 2;\n");
  await repo.clean();
});

test("invalid UTF-8 Git filename is rejected without changing index or file bytes", async (t) => {
  const repo = await repository(t);
  const filename = Buffer.concat([
    Buffer.from(`${repo.root}/`),
    Buffer.from([0xff]),
    Buffer.from(".js"),
  ]);
  await fs.writeFile(filename, "const value=1\n");
  repo.git("add", ".");
  await preservesOnFailure(repo, repo.run(), /Non-UTF-8/);
  assert.equal(await fs.readFile(filename, "utf8"), "const value=1\n");
});
