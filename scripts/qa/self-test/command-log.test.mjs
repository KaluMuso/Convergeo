import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync, rmSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, it, after } from "node:test";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

/**
 * Regression: run_timed must not lose failure logs via Bash command-substitution
 * subshells. Exercises the sanitize + file-based protocol from release-certify.sh.
 */
const root = mkdtempSync(join(tmpdir(), "cert-cmdlog-"));
after(() => rmSync(root, { recursive: true, force: true }));

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");

describe("command failure logging", () => {
  it("captures return code and sanitized stderr/stdout into a file (no secrets)", () => {
    const logOut = join(root, "out.txt");
    const script = join(root, "probe.sh");
    // Source only the helper functions by extracting a minimal replica that
    // matches release-certify.sh's file-based protocol (not $(run_timed)).
    writeFileSync(
      script,
      `#!/usr/bin/env bash
set -euo pipefail
LOG_OUT="${logOut}"
sanitize_log() {
  local raw="$1"
  python3 - "$raw" <<'PY'
import re, sys
text = sys.argv[1] if len(sys.argv) > 1 else ""
text = re.sub(r"(?i)(authorization:\\s*bearer\\s+)(\\S+)", r"\\1[REDACTED]", text)
text = re.sub(r"(?i)(api[_-]?key|token|secret|password)([\\"'=\\s:]+)(\\S+)", r"\\1\\2[REDACTED]", text)
print(text[-1500:])
PY
}
run_timed() {
  local log_out_file="$1"
  shift
  local log_file start end rc=0
  log_file="$(mktemp)"
  start=$(date +%s%3N 2>/dev/null || echo 0)
  set +e
  "$@" >"$log_file" 2>&1
  rc=$?
  set -e
  end=$(date +%s%3N 2>/dev/null || echo 1)
  local raw
  raw="$(tail -c 4000 "$log_file" 2>/dev/null || true)"
  sanitize_log "$raw" >"$log_out_file"
  rm -f "$log_file"
  _RUN_TIMED_MS=$((end - start))
  _RUN_TIMED_RC=$rc
  return 0
}
run_timed "$LOG_OUT" bash -c 'echo "Authorization: Bearer SUPERSECRETTOKEN"; echo boom; exit 7'
echo "RC=\${_RUN_TIMED_RC} MS=\${_RUN_TIMED_MS}"
test "\${_RUN_TIMED_RC}" = "7"
`,
    );
    chmodSync(script, 0o755);
    const res = spawnSync("bash", [script], { encoding: "utf8", cwd: REPO_ROOT });
    assert.equal(res.status, 0, `stdout=${res.stdout}\nstderr=${res.stderr}`);
    assert.match(res.stdout, /RC=7/);
    const logged = readFileSync(logOut, "utf8");
    assert.match(logged, /boom/);
    assert.match(logged, /\[REDACTED\]/);
    assert.doesNotMatch(logged, /SUPERSECRETTOKEN/);
  });
});
