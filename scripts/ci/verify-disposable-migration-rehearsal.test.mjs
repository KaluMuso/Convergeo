import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import {
  committedInventoryDigest,
  committedMigrationInventory,
  digest,
  main,
  verify,
} from "./verify-disposable-migration-rehearsal.mjs";

const root = resolve(fileURLToPath(new URL(".", import.meta.url)), "..", "..");

const target = "ci_migration_123456abcdef_baseline";
const marker = `CONVERGEO_DISPOSABLE_MIGRATION_REHEARSAL:${target}`;
const row = (version, statements = null, statements_shape = null) => ({
  version,
  statements,
  statements_shape,
  name: `fixture_${version}`,
  created_by: "fixture",
  idempotency_key: `fixture-${version}`,
  rollback: [],
  rollback_shape: null,
});
function snapshot(database, history) {
  return {
    snapshot_schema: 1,
    database,
    database_marker: database === target ? marker : null,
    server_address: "127.0.0.1",
    server_port: 54322,
    ledger_columns: [
      ["version", "text"],
      ["statements", "text[]"],
      ["name", "text"],
      ["created_by", "text"],
      ["idempotency_key", "text"],
      ["rollback", "text[]"],
    ].map(([name, type]) => ({ name, type, not_null: name === "version" })),
    version_primary_key: true,
    idempotency_key_unique: true,
    history,
    catalog: {
      database: { owner: "postgres", acl: null },
      schemas: [{ name: "public", owner: "postgres", acl: "{postgres=UC/postgres}" }],
      relations: [
        {
          schema: "public",
          name: "t",
          kind: "r",
          owner: "postgres",
          acl: null,
        },
      ],
      column_privileges: [],
      functions: [],
      types: [],
      default_privileges: [],
    },
  };
}
const clone = (x) => structuredClone(x);
function fixture() {
  const source = snapshot("source_baseline", [
    row("0001"),
    row("0003", []),
    row(
      "0005",
      [
        ["A", null],
        ["B", "C"],
      ],
      "[2:3][0:1]",
    ),
  ]);
  const restored = snapshot(target, clone(source.history));
  const entries = ["0001", "0002", "0003", "0004", "0005"].map((version) => ({
    version,
    filename: `${version}_fixture.sql`,
    sha256: version.slice(-1).repeat(64),
  }));
  const binding = {
    purpose: "DISPOSABLE_MIGRATION_REHEARSAL_ONLY",
    source_commit: "a".repeat(40),
    source_tree: "b".repeat(40),
    source_database: source.database,
    target_database: target,
    migration_inventory_sha256: "e".repeat(64),
    source_snapshot_sha256: "c".repeat(64),
    dump_sha256: "d".repeat(64),
    ordered_pending_inputs: clone(
      entries.filter((entry) => ["0002", "0004"].includes(entry.version)),
    ),
  };
  const identity = {
    commit: binding.source_commit,
    tree: binding.source_tree,
    inventory: binding.migration_inventory_sha256,
    entries,
  };
  return { source, restored, binding, identity };
}
const check = (f, checkpoints = []) =>
  verify(f.binding, f.source, f.restored, "c".repeat(64), "d".repeat(64), checkpoints, f.identity);

test("accepts exact baseline and ordered committed checkpoints even with interleaved versions", () => {
  const f = fixture(),
    first = clone(f.restored),
    second = clone(f.restored);
  first.history.splice(1, 0, row("0002", ["SQL"], "[1:1]"));
  second.history.splice(1, 0, row("0002", ["SQL"], "[1:1]"));
  second.history.splice(3, 0, row("0004"));
  assert.deepEqual(check(f, [first, second]), {
    baseline_rows: 3,
    restored_exact: true,
    applied_versions: ["0002", "0004"],
    next_expected_version: null,
  });
});

test("accepts exact committed prefix and identifies next input", () => {
  const f = fixture(),
    first = clone(f.restored);
  first.history.splice(1, 0, row("0002"));
  assert.deepEqual(check(f, [first]), {
    baseline_rows: 3,
    restored_exact: true,
    applied_versions: ["0002"],
    next_expected_version: "0004",
  });
});

test("rejects null, empty, dimension, bound, content and metadata loss", () => {
  const changes = [
    (x) => {
      x.history[0].statements = [];
    },
    (x) => {
      x.history[1].statements = null;
    },
    (x) => {
      x.history[2].statements_shape = "[1:2][1:2]";
    },
    (x) => {
      x.history[2].statements[0][1] = "changed";
    },
    (x) => {
      x.history[0].rollback = null;
    },
    (x) => {
      x.history[1].created_by = "other";
    },
    (x) => {
      x.history[1].idempotency_key = "other";
    },
  ];
  for (const change of changes) {
    const f = fixture();
    change(f.restored);
    assert.throws(() => check(f), /restored history differs/);
  }
});

test("rejects missing unique constraint, changed owner or ACL, and wrong target", () => {
  const f = fixture();
  f.restored.idempotency_key_unique = false;
  assert.throws(() => check(f), /key constraints/);
  const g = fixture();
  g.restored.catalog.relations[0].owner = "other";
  assert.throws(() => check(g), /catalog differs/);
  const h = fixture();
  h.restored.catalog.schemas[0].acl = null;
  assert.throws(() => check(h), /catalog differs/);
  const i = fixture();
  i.restored.server_address = "10.0.0.3";
  assert.throws(() => check(i), /loopback fixture/);
  const j = fixture();
  j.restored.catalog.database.owner = "other";
  assert.throws(() => check(j), /catalog differs/);
});

test("rejects fabricated baseline, skipped version and wrong dump hash", () => {
  const f = fixture(),
    first = clone(f.restored),
    second = clone(f.restored);
  first.history.splice(1, 0, row("0002"));
  second.history.splice(1, 0, row("0002"));
  second.history.push(row("0006"));
  assert.throws(() => check(f, [first, second]), /exact committed prefix/);
  first.history[0].name = "fabricated";
  assert.throws(() => check(f, [first, second]), /rewrote existing history/);
  assert.throws(
    () => verify(f.binding, f.source, f.restored, "c".repeat(64), "e".repeat(64), [], f.identity),
    /dump_sha256/,
  );
});

test("rejects unknown file, swapped SQL hash and already recorded migration", () => {
  const f = fixture();
  f.binding.ordered_pending_inputs[0].sha256 = "f".repeat(64);
  assert.throws(() => check(f), /migration file\/version\/SHA-256/);
  const g = fixture();
  g.binding.ordered_pending_inputs[0].version = "9999";
  assert.throws(() => check(g), /migration file\/version\/SHA-256/);
  const h = fixture();
  h.binding.ordered_pending_inputs[0].version = "0001";
  h.binding.ordered_pending_inputs[0].filename = "0001_fixture.sql";
  h.binding.ordered_pending_inputs[0].sha256 = "1".repeat(64);
  assert.throws(() => check(h), /already present in baseline/);
});

test("rejects a partial pending plan and an unbound installed-history version", () => {
  const omitted = fixture();
  omitted.binding.ordered_pending_inputs.pop();
  assert.throws(() => check(omitted), /omits or adds a committed migration/);

  const foreign = fixture();
  foreign.source.history.push(row("0006"));
  foreign.restored.history.push(row("0006"));
  assert.throws(() => check(foreign), /outside the bound committed inventory/);
});

test("accepts reviewed tuple independent of JSON property order", () => {
  const f = fixture();
  f.binding.ordered_pending_inputs[0] = {
    sha256: "2".repeat(64),
    filename: "0002_fixture.sql",
    version: "0002",
  };
  assert.equal(check(f).next_expected_version, "0002");
});

test("CLI binds physical source snapshot and dump bytes", () => {
  const f = fixture(),
    dir = mkdtempSync(join(tmpdir(), "migration-rehearsal-"));
  const paths = Object.fromEntries(
    ["source", "restored", "dump", "binding"].map((x) => [
      x,
      join(dir, x + (x === "dump" ? ".dump" : ".json")),
    ]),
  );
  writeFileSync(paths.dump, "synthetic dump bytes");
  f.binding.source_commit = execFileSync("git", ["-C", root, "rev-parse", "HEAD"], {
    encoding: "utf8",
  }).trim();
  f.binding.source_tree = execFileSync("git", ["-C", root, "rev-parse", "HEAD^{tree}"], {
    encoding: "utf8",
  }).trim();
  f.binding.migration_inventory_sha256 = committedInventoryDigest(root, f.binding.source_commit);
  const realInputs = committedMigrationInventory(root, f.binding.source_commit);
  assert.equal(realInputs.length, 138);
  f.source.history = realInputs.slice(0, 114).map((input) => row(input.version));
  f.source.history[0].rollback = null;
  f.source.history[1].statements = [];
  f.source.history[2].statements = ["synthetic SQL"];
  f.source.history[2].statements_shape = "[0:0]";
  f.source.history[2].rollback = ["synthetic rollback"];
  f.source.history[2].rollback_shape = "[-2:-2]";
  f.source.history[2].created_by = null;
  f.source.history[2].idempotency_key = null;
  f.restored.history = clone(f.source.history);
  f.binding.ordered_pending_inputs = realInputs.slice(114);
  writeFileSync(paths.source, JSON.stringify(f.source));
  writeFileSync(paths.restored, JSON.stringify(f.restored));
  f.binding.source_snapshot_sha256 = digest(Buffer.from(JSON.stringify(f.source)));
  f.binding.dump_sha256 = digest(Buffer.from("synthetic dump bytes"));
  writeFileSync(paths.binding, JSON.stringify(f.binding));
  const args = [
    "--repo-root",
    root,
    "--binding",
    paths.binding,
    "--source",
    paths.source,
    "--dump",
    paths.dump,
    "--restored",
    paths.restored,
  ];
  assert.deepEqual(main(args), {
    baseline_rows: 114,
    restored_exact: true,
    applied_versions: [],
    next_expected_version: realInputs[114].version,
  });
  const checkpoint = clone(f.restored);
  checkpoint.history.push(row(realInputs[114].version));
  checkpoint.history.sort((a, b) => a.version.localeCompare(b.version));
  const checkpointPath = join(dir, "checkpoint.json");
  writeFileSync(checkpointPath, JSON.stringify(checkpoint));
  assert.deepEqual(main([...args, "--checkpoint", checkpointPath]), {
    baseline_rows: 114,
    restored_exact: true,
    applied_versions: [realInputs[114].version],
    next_expected_version: realInputs[115].version,
  });
  writeFileSync(paths.dump, "tampered");
  assert.throws(() => main(args), /dump_sha256/);
});

test("rejects modified and untracked SQL under an unchanged bound commit", () => {
  const repo = mkdtempSync(join(tmpdir(), "migration-source-binding-"));
  const migrations = join(repo, "supabase", "migrations");
  mkdirSync(migrations, { recursive: true });
  const file = join(migrations, "0001_fixture.sql");
  writeFileSync(file, "select 1;\n");
  execFileSync("git", ["init", "-q", repo]);
  execFileSync("git", ["-C", repo, "add", "--", "supabase/migrations/0001_fixture.sql"]);
  execFileSync("git", [
    "-C",
    repo,
    "-c",
    "user.name=Fixture",
    "-c",
    "user.email=fixture@example.invalid",
    "commit",
    "-qm",
    "Synthetic migration fixture",
  ]);
  const commit = execFileSync("git", ["-C", repo, "rev-parse", "HEAD"], {
    encoding: "utf8",
  }).trim();
  assert.equal(committedMigrationInventory(repo, commit).length, 1);

  writeFileSync(file, "select 2;\n");
  assert.throws(() => committedMigrationInventory(repo, commit), /migration bytes differ/);
  writeFileSync(file, "select 1;\n");
  writeFileSync(join(migrations, "0002_untracked.sql"), "select 2;\n");
  assert.throws(() => committedMigrationInventory(repo, commit), /migration inventory differs/);
});
