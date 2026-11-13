import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import process from "node:process";
import { test } from "node:test";
import { fileURLToPath, URL } from "node:url";

const source = fileURLToPath(new URL("./check-staged-symlinks.mjs", import.meta.url));

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), "staged-symlink-policy-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(join(root, "scripts", "ci"), { recursive: true });
  copyFileSync(source, join(root, "scripts", "ci", "check-staged-symlinks.mjs"));
  writeFileSync(join(root, ".empty-gitconfig"), "");
  writeFileSync(join(root, "ordinary.json"), '{ "value": 0 }\n');
  const env = {
    PATH: process.env.PATH,
    GIT_CONFIG_NOSYSTEM: "1",
    GIT_CONFIG_GLOBAL: join(root, ".empty-gitconfig"),
  };
  for (const key of ["NODE_OPTIONS", "OFFLINE_GUARD_LOG"]) {
    if (process.env[key]) env[key] = process.env[key];
  }
  function git(args, input) {
    const result = spawnSync("git", args, { cwd: root, env, input, encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr || result.error?.message);
    return result.stdout;
  }
  git(["init", "-q"]);
  git(["config", "user.name", "Offline Fixture"]);
  git(["config", "user.email", "fixture@example.invalid"]);
  git(["config", "commit.gpgsign", "false"]);
  function index(mode, path, content = "missing target") {
    const oid = git(["hash-object", "-w", "--stdin"], content).trim();
    git(["update-index", "--add", "--cacheinfo", `${mode},${oid},${path}`]);
  }
  function commit() {
    git(["commit", "-qm", "test: initialize fixture"]);
  }
  function state() {
    return [
      git(["ls-files", "--stage", "-z"]),
      git(["diff", "--cached", "--binary"]),
      readFileSync(join(root, "ordinary.json"), "utf8"),
    ];
  }
  function check(expected, extraEnv = {}) {
    const before = state();
    const result = spawnSync(
      process.execPath,
      [join(root, "scripts", "ci", "check-staged-symlinks.mjs")],
      { cwd: tmpdir(), env: { ...env, ...extraEnv }, encoding: "utf8" },
    );
    assert.equal(result.status, expected, result.stderr || result.error?.message);
    assert.deepEqual(state(), before, "the check must not mutate staged data or ordinary files");
    if (expected === 1) assert.match(result.stderr, /commit blocked|Commit blocked/);
    return result;
  }
  return { root, git, index, commit, check };
}

test("checks the initial index without needing HEAD", (t) => {
  const f = fixture(t);
  f.index("120000", "new link.json");
  f.check(1);
});

test("allows an empty index and ordinary files", (t) => {
  const f = fixture(t);
  f.check(0);
  f.index("100644", "ordinary.json", '{"value":1}\n');
  f.check(0);
});

for (const path of [
  "link.json",
  "space ü and comma, link.json",
  ".hidden/link",
  "nested/node_modules/link",
  ".svn/link",
  ".claude/skills/helper",
]) {
  test(`rejects staged symlink mode for ${path}`, (t) => {
    const f = fixture(t);
    f.index("120000", path);
    f.check(1);
  });
}

test("rejects a mixed batch before ordinary file mutation", (t) => {
  const f = fixture(t);
  f.index("100644", "ordinary.json", '{"value":1}\n');
  f.index("120000", ".svn/link");
  f.check(1);
});

test("rejects index symlinks even when the working tree is a regular file", (t) => {
  const f = fixture(t);
  f.index("120000", "ordinary.json", "../outside");
  f.check(1);
});

test("allows unchanged tracked symlinks", (t) => {
  const f = fixture(t);
  f.index("120000", "existing link");
  f.commit();
  f.index("100644", "ordinary.json", '{"value":1}\n');
  f.check(0);
});

test("allows deletion of a tracked symlink", (t) => {
  const f = fixture(t);
  f.index("120000", "old link");
  f.commit();
  f.git(["update-index", "--force-remove", "old link"]);
  f.check(0);
});

test("rejects symlink renames regardless of rename configuration", (t) => {
  const f = fixture(t);
  f.index("120000", "old link");
  f.commit();
  f.git(["config", "diff.renames", "copies"]);
  f.git(["update-index", "--force-remove", "old link"]);
  f.index("120000", "renamed space ü link");
  f.check(1);
});

test("rejects a copied symlink", (t) => {
  const f = fixture(t);
  f.index("120000", "old link");
  f.commit();
  f.index("120000", "copied link");
  f.check(1);
});

test("rejects regular-file to symlink type changes", (t) => {
  const f = fixture(t);
  f.git(["add", "ordinary.json"]);
  f.commit();
  f.index("120000", "ordinary.json");
  f.check(1);
});

test("allows symlink to regular-file type changes", (t) => {
  const f = fixture(t);
  f.index("120000", "ordinary.json");
  f.commit();
  f.index("100644", "ordinary.json", '{"value":1}\n');
  f.check(0);
});

test("does not treat gitlinks as symlinks", (t) => {
  const f = fixture(t);
  f.git(["add", "ordinary.json"]);
  f.commit();
  const oid = f.git(["rev-parse", "HEAD"]).trim();
  f.git(["update-index", "--add", "--cacheinfo", `160000,${oid},submodule`]);
  f.check(0);
});

test("reads all staged paths when diff.relative is configured", (t) => {
  const f = fixture(t);
  f.git(["config", "diff.relative", "true"]);
  f.index("120000", "elsewhere/link");
  f.check(1);
});

test("handles streamed Git output and bounds diagnostics without skipping entries", (t) => {
  const f = fixture(t);
  const oid = f.git(["hash-object", "-w", "--stdin"], "ordinary data").trim();
  const rows = Array.from(
    { length: 1200 },
    (_, i) => `100644 ${oid}\tfiles/${String(i).padStart(4, "0")}-${"x".repeat(100)}\0`,
  );
  f.git(["update-index", "-z", "--index-info"], rows.join(""));
  for (let i = 0; i < 22; i++) f.index("120000", `late/link ${i}`);
  assert.match(f.check(1).stderr, /and 2 more/);
});

test("fails closed when Git cannot be started", (t) => {
  const f = fixture(t);
  assert.match(f.check(1, { PATH: "" }).stderr, /Cannot inspect the staged index/);
});
