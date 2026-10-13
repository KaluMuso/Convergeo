import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  checkpoints,
  ipv4Rules,
  ipv6Rules,
  qualify,
  qualifyPackage,
} from "./assert-cart-response-drill.mjs";

const sha = "a".repeat(40);
for (const fault of ["none", "source", "bytes", "receipt", "entries"]) {
  test(`runtime package custody rejects ${fault}`, () => {
    const bytes = Buffer.from(
      JSON.stringify({
        version: 1,
        source_sha: sha,
        source_tree: sha,
        entries: { "runtime-input": { type: "file" } },
      }),
    );
    const digest = createHash("sha256").update(bytes).digest("hex");
    const receipt = {
      verified: true,
      source_sha: sha,
      manifest_sha256: digest,
      entries: 1,
    };
    const guard = { runtime_manifest_sha256: digest };
    let payload = bytes;
    if (fault === "source") receipt.source_sha = "b".repeat(40);
    if (fault === "bytes") payload = Buffer.concat([bytes, Buffer.from(" ")]);
    if (fault === "receipt") receipt.verified = false;
    if (fault === "entries") receipt.entries = 2;
    if (fault === "none") qualifyPackage(payload, receipt, guard, sha);
    else assert.throws(() => qualifyPackage(payload, receipt, guard, sha));
  });
}
for (const health of [
  "",
  "broken JSON",
  JSON.stringify([
    { name: "api", ok: false, secret: "SENTINEL_PRIVATE_VALUE" },
    { name: "customer", ok: true },
  ]),
])
  test("startup diagnostics survive incomplete health and omit unapproved fields", () => {
    const shell = readFileSync(
      new URL("../qa/run-cart-response-drill.sh", import.meta.url),
      "utf8",
    );
    const code = shell
      .split('python3 - "$drill_output" "$drill_phase"')[1]
      .split("<<'PY'\n")[1]
      .split("\nPY")[0];
    const directory = mkdtempSync(join(tmpdir(), "cart-drill-diagnostic-"));
    try {
      writeFileSync(join(directory, "private-health-probe.json"), health);
      writeFileSync(
        join(directory, "private-api.log"),
        "libpython Permission denied SENTINEL_PRIVATE_VALUE",
      );
      const result = spawnSync(
        "python3",
        ["-c", code, directory, "server_startup", "1", "1", "running"],
        { encoding: "utf8" },
      );
      assert.equal(result.status, 0, result.stderr);
      const output = readFileSync(join(directory, "diagnostics.json"), "utf8");
      assert.ok(!output.includes("SENTINEL_PRIVATE_VALUE"));
      const receipt = JSON.parse(output);
      assert.deepEqual(receipt.api_log_categories, ["Permission denied", "libpython"]);
      if (health.startsWith("["))
        assert.deepEqual(receipt.latest_health, [
          { name: "api", ok: false },
          { name: "customer", ok: true },
        ]);
      else assert.equal(receipt.health_evidence, "unavailable_or_malformed");
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });
function fixture() {
  return {
    outcome: {
      version: 1,
      qualified: true,
      blockedImages: 3,
      checkpoints: Object.fromEntries(checkpoints.map((p) => [p, true])),
      stages: [
        {
          name: "committed_before_discard",
          qty: 1,
          claims: 1,
          events: 1,
          price: 1000,
        },
        { name: "replayed", qty: 1, claims: 1, events: 1, price: 1000 },
        { name: "fresh", qty: 2, claims: 2, events: 2, price: 1100 },
        {
          name: "stock_revalidated",
          qty: 2,
          claims: 2,
          events: 2,
          price: 1100,
        },
      ],
    },
    guard: {
      version: 1,
      source_sha: sha,
      customer_execution_mode: "development; production loopback guard preserved",
      uid: 998,
      ipv4_owner_hook_verified: true,
      ipv6_owner_hook_verified: true,
      all_other_ipv4_and_ipv6_rejected: true,
      api_and_customer_listener_uid_verified: true,
      process_and_firewall_cleanup: true,
      runtime_package_verified: true,
      runtime_package_no_private_links: true,
      runtime_manifest_sha256: "a".repeat(64),
      allowed_loopback_tcp_ports: [3000, 8000, 54321, 54322],
      dnat_original_tcp_ports: [54321, 54322],
      dnat_original_destination: "127.0.0.1",
      loopback_server_reply_original_tcp_ports: [3000, 8000],
      ipv4_rules: [...ipv4Rules],
      ipv6_rules: [...ipv6Rules],
      rejected_packets: 0,
    },
  };
}
test("complete evidence qualifies", () => {
  const { outcome, guard } = fixture();
  assert.equal(qualify(outcome, guard, sha).qualified, true);
});
for (const [name, change] of [
  [
    "missing commit checkpoint",
    ({ outcome }) => delete outcome.checkpoints.committed_before_discard,
  ],
  [
    "unchecked browser UID",
    ({ outcome }) => (outcome.checkpoints.browser_subprocess_uid_covered = false),
  ],
  ["skipped scenario", ({ outcome }) => (outcome.qualified = false)],
  ["raw rule missing", ({ guard }) => guard.ipv4_rules.splice(1, 1)],
  [
    "raw rule broadens destination",
    ({ guard }) => (guard.ipv4_rules[1] = guard.ipv4_rules[1].replace("127.0.0.1/32", "0.0.0.0/0")),
  ],
  ["extra checkpoint", ({ outcome }) => (outcome.checkpoints.other = true)],
  ["missing replay", ({ outcome }) => outcome.stages.splice(1, 1)],
  ["duplicate increment", ({ outcome }) => (outcome.stages[1].qty = 2)],
  ["duplicate claim", ({ outcome }) => (outcome.stages[1].claims = 2)],
  ["missing initial event", ({ outcome }) => (outcome.stages[0].events = 0)],
  ["replay event", ({ outcome }) => (outcome.stages[1].events = 2)],
  ["fresh increment missing", ({ outcome }) => (outcome.stages[2].qty = 1)],
  ["fresh price stale", ({ outcome }) => (outcome.stages[2].price = 1000)],
  ["wrong source", ({ guard }) => (guard.source_sha = "b".repeat(40))],
  ["root UID", ({ guard }) => (guard.uid = 0)],
  ["unverified runtime inputs", ({ guard }) => (guard.runtime_package_verified = false)],
  ["private runtime links", ({ guard }) => (guard.runtime_package_no_private_links = false)],
  ["missing runtime manifest", ({ guard }) => delete guard.runtime_manifest_sha256],
  ["missing IPv6 guard", ({ guard }) => (guard.ipv6_owner_hook_verified = false)],
  ["broad DNS permission", ({ guard }) => guard.allowed_loopback_tcp_ports.push(53)],
  ["broad DNAT", ({ guard }) => guard.dnat_original_tcp_ports.push(443)],
  ["wrong database host", ({ guard }) => (guard.dnat_original_destination = "10.0.0.1")],
  ["stale unguarded server", ({ guard }) => (guard.api_and_customer_listener_uid_verified = false)],
  ["cleanup failure", ({ guard }) => (guard.process_and_firewall_cleanup = false)],
])
  test(`rejects ${name}`, () => {
    const f = fixture();
    change(f);
    assert.throws(() => qualify(f.outcome, f.guard, sha));
  });
test("workflow owns one bounded fail-closed drill with existing dependencies", () => {
  const workflow = readFileSync(
    new URL("../../.github/workflows/perf.yml", import.meta.url),
    "utf8",
  );
  assert.equal(
    (workflow.match(/name: Cart interrupted-response synthetic drill/g) || []).length,
    1,
  );
  assert.match(workflow, /timeout-minutes: 5\n\s+env:\n\s+CART_DRILL_LOCAL: "1"/);
  const gate =
    "if: ${{ !cancelled() && steps.cart_local_stack.outcome == 'success' && steps.cart_head_build.outcome == 'success' }}";
  assert.equal(workflow.split(gate).length - 1, 2);
  assert.match(workflow, /name: Start local Supabase stack\n\s+id: cart_local_stack/);
  assert.match(workflow, /name: Build customer app \(head\)\n\s+id: cart_head_build/);
  assert.match(workflow, /node scripts\/ci\/assert-cart-response-drill\.mjs/);
  assert.match(workflow, /if-no-files-found: error/);
  const shell = readFileSync(new URL("../qa/run-cart-response-drill.sh", import.meta.url), "utf8");
  assert.match(shell, /--dports 3000,8000,54321,54322/);
  assert.match(shell, /--ctorigdst 127\.0\.0\.1 --ctorigdstport/);
  assert.match(shell, /ip6tables -w -A CARTDRILL6 -j REJECT/);
  assert.doesNotMatch(shell, /npm install|pnpm i|supabase db|docker run/);
  assert.match(shell, /LD_LIBRARY_PATH="\$drill_python_library"/);
  assert.match(shell, /drill_python_library="\$\{pythonLocation:\?\}\/lib"/);
  const setup = shell.indexOf("sudo useradd --system");
  assert.match(shell, /registry\.findExecutable\("chromium-headless-shell"\)\.executablePath\(\)/);
  for (const preflight of [
    ".next/BUILD_ID",
    '[ ! -x "$drill_node" ]',
    '[ ! -x "$drill_python_real" ]',
    '[ ! -r "$drill_next" ]',
    '[ ! -x "$drill_browser_executable" ]',
  ]) {
    assert.ok(shell.indexOf(preflight) >= 0 && shell.indexOf(preflight) < setup);
  }
});
