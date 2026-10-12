import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

export const checkpoints = [
  "dedicated_uid_and_local_stack",
  "guest_cookie_established",
  "committed_before_discard",
  "one_response_discarded",
  "actual_ui_uncertain_error",
  "retry_same_key_and_body",
  "replay_quantity_price_ui",
  "authoritative_price_notice_ui",
  "fresh_key_same_intent_body",
  "fresh_quantity_price_ui",
  "authoritative_stock_notice_browser_api",
  "exactly_three_real_adds",
  "no_external_browser_requests",
  "browser_subprocess_uid_covered",
  "synthetic_fixture_cleanup",
];

export const ipv4Rules = [
  "-N CARTDRILL4",
  "-A CARTDRILL4 -d 127.0.0.1/32 -p tcp -m multiport --dports 3000,8000,54321,54322 -j RETURN",
  ...[54321, 54322].map(
    (p) =>
      `-A CARTDRILL4 -p tcp -m conntrack --ctorigdst 127.0.0.1 --ctorigdstport ${p} -j RETURN`,
  ),
  ...[3000, 8000].map(
    (p) =>
      `-A CARTDRILL4 -p tcp -m conntrack --ctdir REPLY --ctorigdst 127.0.0.1 --ctorigdstport ${p} -j RETURN`,
  ),
  "-A CARTDRILL4 -j REJECT --reject-with icmp-port-unreachable",
];
export const ipv6Rules = [
  "-N CARTDRILL6",
  "-A CARTDRILL6 -j REJECT --reject-with icmp6-port-unreachable",
];

function ruleTokens(rules) {
  return rules.map((rule) => rule.trim().split(/\s+/).sort());
}

export function qualify(outcome, guard, sha) {
  assert.match(sha, /^[a-f0-9]{40}$/);
  assert.equal(outcome.version, 1);
  assert.equal(outcome.qualified, true);
  assert.equal(outcome.failedPhase, undefined);
  assert.deepEqual(
    Object.keys(outcome.checkpoints).sort(),
    [...checkpoints].sort(),
  );
  for (const point of checkpoints)
    assert.equal(outcome.checkpoints[point], true, point);
  assert.ok(
    Number.isInteger(outcome.blockedImages) && outcome.blockedImages >= 0,
  );
  assert.equal(outcome.stages.length, 4);
  const price = outcome.stages[0].price;
  assert.ok(Number.isSafeInteger(price) && price > 0);
  assert.deepEqual(outcome.stages, [
    { name: "committed_before_discard", qty: 1, claims: 1, events: 1, price },
    { name: "replayed", qty: 1, claims: 1, events: 1, price },
    { name: "fresh", qty: 2, claims: 2, events: 2, price: price + 100 },
    {
      name: "stock_revalidated",
      qty: 2,
      claims: 2,
      events: 2,
      price: price + 100,
    },
  ]);
  assert.equal(guard.version, 1);
  assert.equal(guard.source_sha, sha);
  assert.equal(
    guard.customer_execution_mode,
    "development; production loopback guard preserved",
  );
  assert.ok(Number.isInteger(guard.uid) && guard.uid > 0);
  for (const key of [
    "ipv4_owner_hook_verified",
    "ipv6_owner_hook_verified",
    "all_other_ipv4_and_ipv6_rejected",
    "api_and_customer_listener_uid_verified",
    "process_and_firewall_cleanup",
  ])
    assert.equal(guard[key], true, key);
  assert.deepEqual(
    guard.allowed_loopback_tcp_ports,
    [3000, 8000, 54321, 54322],
  );
  assert.deepEqual(guard.dnat_original_tcp_ports, [54321, 54322]);
  assert.deepEqual(
    guard.loopback_server_reply_original_tcp_ports,
    [3000, 8000],
  );
  assert.equal(guard.dnat_original_destination, "127.0.0.1");
  assert.deepEqual(ruleTokens(guard.ipv4_rules), ruleTokens(ipv4Rules));
  assert.deepEqual(ruleTokens(guard.ipv6_rules), ruleTokens(ipv6Rules));
  assert.ok(
    Number.isInteger(guard.rejected_packets) && guard.rejected_packets >= 0,
  );
  return {
    qualified: true,
    source_sha: sha,
    customer_execution_mode: guard.customer_execution_mode,
    required_checkpoints: checkpoints,
    stages: outcome.stages,
    blocked_images: outcome.blockedImages,
    rejected_packets: guard.rejected_packets,
    coverage:
      "dedicated UID application/browser/native SQL traffic; Supabase container daemons excluded",
    analytics_limit:
      "Controlled funnel counts only; analytics remains best effort",
    scope_limit:
      "Same established guest cart; no cross-cart exactly-once claim",
  };
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const [outcomePath, guardPath, outputPath, sha] = process.argv.slice(2);
  let proof;
  try {
    proof = qualify(
      JSON.parse(readFileSync(outcomePath)),
      JSON.parse(readFileSync(guardPath)),
      sha,
    );
  } catch {
    proof = {
      qualified: false,
      problem: "missing_or_incomplete_drill_evidence",
    };
    process.exitCode = 1;
  }
  // Missing execution must still retain a failure receipt; never invent success.
  const { mkdirSync } = await import("node:fs");
  const { dirname } = await import("node:path");
  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, JSON.stringify(proof, null, 2) + "\n");
  console.log(
    proof.qualified
      ? "PASS: complete cart response drill"
      : "FAIL: incomplete cart response drill",
  );
}
