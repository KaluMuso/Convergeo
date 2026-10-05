#!/usr/bin/env node
/** Offline evidence gate for a separately authorized disposable DB rehearsal.
 * Never connects to a database. Exact source bytes and target identity are bound
 * by hashes, then restored history and owner/ACL catalogs are compared.
 */
import { readFileSync, readdirSync } from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { join } from "node:path";

const columns = ["version", "statements", "name", "created_by", "idempotency_key", "rollback"];
const rowFields = [...columns, "statements_shape", "rollback_shape"];
const catalogFields = [
  "database",
  "schemas",
  "relations",
  "column_privileges",
  "functions",
  "types",
  "default_privileges",
];
const sha1 = /^[0-9a-f]{40}$/;
const sha256 = /^[0-9a-f]{64}$/;
const targetName = /^ci_migration_[0-9a-f]{12}_[a-z0-9_]{1,32}$/;

export class RehearsalError extends Error {}
function fail(message) {
  throw new RehearsalError(message);
}
function exact(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}
function sameFields(value, expected) {
  return (
    value &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    exact(Object.keys(value).sort(), [...expected].sort())
  );
}
function sha(value, pattern, label) {
  if (typeof value !== "string" || !pattern.test(value))
    fail(`${label} must be a full lowercase SHA`);
}
export function digest(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}
export function migrationInventory(directory) {
  const files = readdirSync(directory)
    .filter((name) => name.endsWith(".sql"))
    .sort();
  if (!files.length || files.some((name) => !/^[0-9]+_.+\.sql$/.test(name))) {
    fail("migration inventory is empty or malformed");
  }
  const versions = files.map((name) => name.split("_", 1)[0]);
  if (new Set(versions).size !== versions.length) fail("duplicate migration version");
  return files.map((name) => ({
    version: name.split("_", 1)[0],
    filename: name,
    sha256: digest(readFileSync(join(directory, name))),
  }));
}
function inventoryHash(entries) {
  return digest(JSON.stringify(entries.map(({ filename, sha256 }) => ({ filename, sha256 }))));
}
export function inventoryDigest(directory) {
  return inventoryHash(migrationInventory(directory));
}
export function committedMigrationInventory(root, commit) {
  sha(commit, sha1, "source_commit");
  const directory = join(root, "supabase", "migrations");
  const workingEntries = migrationInventory(directory);
  const prefix = "supabase/migrations/";
  const files = execFileSync(
    "git",
    ["-C", root, "ls-tree", "-r", "-z", commit, "--", "supabase/migrations"],
    { encoding: "utf8" },
  )
    .split("\0")
    .filter(Boolean)
    .map((record) => {
      const tab = record.indexOf("\t");
      const name = record.slice(tab + 1);
      if (!name.endsWith(".sql")) return null;
      const match = /^(100644|100755) blob ([0-9a-f]{40})$/.exec(record.slice(0, tab));
      if (!match || !name.startsWith(prefix)) fail("bound Git migration is not a regular SQL file");
      return { name: name.slice(prefix.length), oid: match[2] };
    })
    .filter(Boolean)
    .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
  const committedNames = files.map((file) => file.name);
  if (
    !exact(
      workingEntries.map((entry) => entry.filename),
      committedNames,
    )
  ) {
    fail("working migration inventory differs from bound Git commit");
  }
  const blobs = execFileSync("git", ["-C", root, "cat-file", "--batch"], {
    input: `${files.map((file) => file.oid).join("\n")}\n`,
    maxBuffer: 64 * 1024 * 1024,
  });
  let offset = 0;
  return workingEntries.map((entry, index) => {
    const endHeader = blobs.indexOf(10, offset);
    const header = blobs.subarray(offset, endHeader).toString("ascii");
    const match = /^([0-9a-f]{40}) blob (\d+)$/.exec(header);
    if (!match || match[1] !== files[index].oid) fail("bound Git migration blob lookup failed");
    const start = endHeader + 1;
    const end = start + Number(match[2]);
    if (end >= blobs.length || blobs[end] !== 10) fail("bound Git migration blob is truncated");
    const bytes = blobs.subarray(start, end);
    offset = end + 1;
    const working = readFileSync(join(directory, entry.filename));
    // Git may check out LF blobs with CRLF on Windows. No other byte change is accepted.
    const normalized = Buffer.from(working.toString("latin1").replace(/\r\n/g, "\n"), "latin1");
    if (!working.equals(bytes) && !normalized.equals(bytes)) {
      fail(`working migration bytes differ from bound Git commit: ${entry.filename}`);
    }
    return { ...entry, sha256: digest(bytes) };
  });
}
export function committedInventoryDigest(root, commit) {
  return inventoryHash(committedMigrationInventory(root, commit));
}
export function readJson(path) {
  const value = JSON.parse(readFileSync(path, "utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value))
    fail(`${path}: expected JSON object`);
  return value;
}

export function validateSnapshot(snapshot, label) {
  if (snapshot?.snapshot_schema !== 1) fail(`${label}: unknown snapshot schema`);
  if (typeof snapshot.database !== "string" || !snapshot.database)
    fail(`${label}: database identity missing`);
  if (
    !Array.isArray(snapshot.ledger_columns) ||
    snapshot.ledger_columns.length !== 6 ||
    !exact(snapshot.ledger_columns.map((x) => x?.name).sort(), [...columns].sort()) ||
    snapshot.ledger_columns.some(
      (x) =>
        !sameFields(x, ["name", "type", "not_null"]) ||
        typeof x.type !== "string" ||
        !x.type ||
        typeof x.not_null !== "boolean",
    )
  ) {
    fail(`${label}: all six ledger columns and types are required`);
  }
  if (snapshot.version_primary_key !== true || snapshot.idempotency_key_unique !== true) {
    fail(`${label}: ledger key constraints missing`);
  }
  if (!Array.isArray(snapshot.history)) fail(`${label}: history missing`);
  const versions = [],
    keys = [];
  for (const [index, row] of snapshot.history.entries()) {
    if (!sameFields(row, rowFields)) fail(`${label}: incomplete history row ${index}`);
    if (typeof row.version !== "string" || !/^[0-9]+$/.test(row.version)) {
      fail(`${label}: invalid version in row ${index}`);
    }
    versions.push(row.version);
    if (row.idempotency_key !== null) {
      if (typeof row.idempotency_key !== "string") fail(`${label}: invalid idempotency key`);
      keys.push(row.idempotency_key);
    }
    for (const field of ["statements", "rollback"]) {
      const value = row[field],
        shape = row[`${field}_shape`];
      if (value !== null && !Array.isArray(value)) fail(`${label}: invalid ${field} array`);
      if (shape !== null && (typeof shape !== "string" || !/^(\[-?\d+:-?\d+\])+$/.test(shape))) {
        fail(`${label}: invalid ${field} array dimensions`);
      }
      if (value === null && shape !== null) fail(`${label}: null ${field} has dimensions`);
    }
  }
  if (!exact(versions, [...versions].sort()) || new Set(versions).size !== versions.length) {
    fail(`${label}: history versions unordered or duplicate`);
  }
  if (new Set(keys).size !== keys.length) fail(`${label}: duplicate non-null idempotency key`);
  if (
    !sameFields(snapshot.catalog, catalogFields) ||
    !sameFields(snapshot.catalog.database, ["owner", "acl"]) ||
    catalogFields
      .filter((key) => key !== "database")
      .some((key) => !Array.isArray(snapshot.catalog[key]))
  ) {
    fail(`${label}: owner/ACL catalog evidence incomplete`);
  }
}

export function verify(
  binding,
  source,
  restored,
  sourceHash,
  dumpHash,
  checkpoints = [],
  identity = null,
) {
  if (binding?.purpose !== "DISPOSABLE_MIGRATION_REHEARSAL_ONLY") fail("unbound rehearsal purpose");
  sha(binding.source_commit, sha1, "source_commit");
  sha(binding.source_tree, sha1, "source_tree");
  sha(binding.migration_inventory_sha256, sha256, "migration_inventory_sha256");
  if (
    !identity ||
    !Array.isArray(identity.entries) ||
    binding.source_commit !== identity.commit ||
    binding.source_tree !== identity.tree ||
    binding.migration_inventory_sha256 !== identity.inventory
  ) {
    fail("checkout commit/tree or migration inventory differs from bound source");
  }
  for (const [field, actual] of [
    ["source_snapshot_sha256", sourceHash],
    ["dump_sha256", dumpHash],
  ]) {
    sha(binding[field], sha256, field);
    if (binding[field] !== actual) fail(`${field} differs from supplied evidence`);
  }
  validateSnapshot(source, "source");
  validateSnapshot(restored, "restored");
  if (source.database !== binding.source_database) fail("source database identity mismatch");
  const target = binding.target_database;
  if (typeof target !== "string" || !targetName.test(target))
    fail("target is not an owned disposable DB name");
  const marker = `CONVERGEO_DISPOSABLE_MIGRATION_REHEARSAL:${target}`;
  for (const [label, snapshot] of [
    ["restored", restored],
    ...checkpoints.map((snapshot, index) => [`checkpoint ${index + 1}`, snapshot]),
  ]) {
    if (
      snapshot.database !== target ||
      snapshot.database_marker !== marker ||
      snapshot.server_address !== "127.0.0.1" ||
      snapshot.server_port !== 54322
    ) {
      fail(`${label}: target identity, marker, or loopback fixture differs`);
    }
    if (!exact(source.ledger_columns, snapshot.ledger_columns))
      fail(`${label}: ledger column definitions differ`);
  }
  for (const field of ["version_primary_key", "idempotency_key_unique", "history", "catalog"]) {
    if (!exact(source[field], restored[field]))
      fail(`restored ${field} differs from source baseline`);
  }
  const inputs = binding.ordered_pending_inputs;
  if (
    !Array.isArray(inputs) ||
    !inputs.length ||
    inputs.some(
      (input) =>
        !sameFields(input, ["version", "filename", "sha256"]) ||
        typeof input.version !== "string" ||
        !/^[0-9]+$/.test(input.version) ||
        typeof input.filename !== "string" ||
        !input.filename.startsWith(`${input.version}_`) ||
        !input.filename.endsWith(".sql") ||
        typeof input.sha256 !== "string" ||
        !sha256.test(input.sha256) ||
        !identity.entries.some(
          (entry) =>
            entry.version === input.version &&
            entry.filename === input.filename &&
            entry.sha256 === input.sha256,
        ),
    )
  ) {
    fail("bound ordered migration file/version/SHA-256 tuples missing or divergent");
  }
  const expected = inputs.map((input) => input.version);
  if (
    new Set(expected).size !== expected.length ||
    expected.some((version) => source.history.some((row) => row.version === version))
  ) {
    fail("bound pending versions duplicate or already present in baseline");
  }
  if (checkpoints.length > expected.length) fail("more checkpoints than bound migrations");
  const result = {
    baseline_rows: source.history.length,
    restored_exact: true,
    applied_versions: [],
    next_expected_version: expected[0],
  };
  if (checkpoints.length) {
    let previous = restored.history;
    for (const [index, checkpoint] of checkpoints.entries()) {
      validateSnapshot(checkpoint, `checkpoint ${index + 1}`);
      const old = new Map(previous.map((row) => [row.version, row]));
      for (const row of checkpoint.history) {
        if (old.has(row.version) && !exact(row, old.get(row.version))) {
          fail(`checkpoint ${index + 1} rewrote existing history row ${row.version}`);
        }
      }
      const added = checkpoint.history.filter((row) => !old.has(row.version));
      if (
        checkpoint.history.length !== previous.length + 1 ||
        added.length !== 1 ||
        added[0].version !== expected[index]
      ) {
        fail(`checkpoint ${index + 1} is not the exact committed prefix`);
      }
      previous = checkpoint.history;
    }
    result.applied_versions = expected.slice(0, checkpoints.length);
    result.next_expected_version = expected[checkpoints.length] ?? null;
  }
  return result;
}

export function main(argv) {
  const values = { checkpoint: [] };
  for (let i = 0; i < argv.length; i += 2) {
    if (
      !["--binding", "--source", "--dump", "--restored", "--checkpoint", "--repo-root"].includes(
        argv[i],
      ) ||
      !argv[i + 1]
    ) {
      fail(
        "usage: --repo-root DIR --binding FILE --source FILE --dump FILE --restored FILE [--checkpoint FILE ...]",
      );
    }
    if (argv[i] === "--checkpoint") values.checkpoint.push(argv[i + 1]);
    else values[argv[i].slice(2)] = argv[i + 1];
  }
  for (const key of ["repo-root", "binding", "source", "dump", "restored"])
    if (!values[key]) fail(`missing --${key}`);
  const root = values["repo-root"];
  const git = (ref) =>
    execFileSync("git", ["-C", root, "rev-parse", ref], { encoding: "utf8" }).trim();
  const binding = readJson(values.binding);
  const entries = committedMigrationInventory(root, binding.source_commit);
  const identity = {
    commit: git("HEAD"),
    tree: git("HEAD^{tree}"),
    inventory: inventoryHash(entries),
    entries,
  };
  return verify(
    binding,
    readJson(values.source),
    readJson(values.restored),
    digest(readFileSync(values.source)),
    digest(readFileSync(values.dump)),
    values.checkpoint.map(readJson),
    identity,
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    console.log(JSON.stringify(main(process.argv.slice(2))));
  } catch (error) {
    console.error(`REHEARSAL BLOCKED: ${error.message}`);
    process.exitCode = 1;
  }
}
