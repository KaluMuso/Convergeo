import assert from "node:assert/strict";
import {
  chmodSync,
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const sha = spawnSync("git", ["-C", root, "rev-parse", "HEAD"], { encoding: "utf8" }).stdout.trim();

function runRecovery(mode, restoreRc, dryRunRc = 0) {
  const temp = mkdtempSync(join(tmpdir(), "cert-recovery-"));
  try {
    const bin = join(temp, "bin");
    mkdirSync(bin);
    const fakeBash = join(bin, "bash");
    writeFileSync(
      fakeBash,
      '#!/bin/sh\ncase "$2" in *infra/scripts/restore-drill.sh*) touch "$RESTORE_CALLED"; exit "$FAKE_RESTORE_RC";; *backup_drill.sh*--dry-run*) exit "$FAKE_DRY_RUN_RC";; esac\nexit 0\n',
    );
    chmodSync(fakeBash, 0o755);
    const restoreCalled = join(temp, "restore-called");
    const result = spawnSync(
      "/bin/bash",
      [
        join(root, "scripts/qa/release-certify.sh"),
        "--mode",
        mode,
        "--environment",
        "staging",
        "--layer",
        "recovery",
        "--run-id",
        "mechanism-only",
        "--evidence-root",
        temp,
      ],
      {
        cwd: root,
        encoding: "utf8",
        env: {
          ...process.env,
          PATH: `${bin}:${process.env.PATH}`,
          CERT_RUN_RESTORE_DRILL: "1",
          FAKE_RESTORE_RC: String(restoreRc),
          FAKE_DRY_RUN_RC: String(dryRunRc),
          RESTORE_CALLED: restoreCalled,
        },
      },
    );
    const gatePath = join(temp, sha, "staging", "mechanism-only", "gate-restore-drill-proof.json");
    assert.ok(existsSync(gatePath), `restore gate missing: ${result.stdout}\n${result.stderr}`);
    return {
      gate: JSON.parse(readFileSync(gatePath, "utf8")),
      backupGate: JSON.parse(
        readFileSync(
          join(temp, sha, "staging", "mechanism-only", "gate-backup-script-dry-run.json"),
          "utf8",
        ),
      ),
      restoreCalled: existsSync(restoreCalled),
    };
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
}

test("a failed backup dry run still records strict recovery as blocked", () => {
  const { gate, backupGate, restoreCalled } = runRecovery("integrated-staging", 0, 9);
  assert.equal(backupGate.status, "FAIL");
  assert.equal(backupGate.return_code, 9);
  assert.equal(gate.status, "BLOCKED_EXTERNAL");
  assert.equal(restoreCalled, false);
});

for (const mode of ["integrated-staging", "production-readiness"]) {
  test(`${mode} cannot accept synthetic drill success as restore proof`, () => {
    const { gate, restoreCalled } = runRecovery(mode, 0);
    assert.equal(gate.status, "BLOCKED_EXTERNAL");
    assert.match(gate.detail, /trusted recovery evidence/i);
    assert.equal(restoreCalled, false);
  });
}

test("local mechanism success remains available without claiming real restore proof", () => {
  const { gate, restoreCalled } = runRecovery("local-development", 0);
  assert.equal(gate.status, "PASS");
  assert.match(gate.detail, /mechanism-only/i);
  assert.equal(restoreCalled, true);
});

test("local synthetic failure remains a failure", () => {
  const { gate, restoreCalled } = runRecovery("local-development", 7);
  assert.equal(gate.status, "FAIL");
  assert.equal(gate.return_code, 7);
  assert.equal(restoreCalled, true);
});
