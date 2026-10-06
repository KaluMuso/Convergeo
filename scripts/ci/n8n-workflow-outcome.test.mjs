import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const root = new URL("../../infra/n8n/", import.meta.url);
const nudges = [
  ["kyc-nudge.json", "/internal/n8n/kyc-stalled/tick"],
  ["low-stock-alert.json", "/internal/n8n/low-stock/tick"],
  ["review-request.json", "/internal/n8n/review-requests/tick"],
  ["abandoned-cart.json", "/internal/n8n/abandoned-carts/tick"],
];

function load(name) {
  return JSON.parse(readFileSync(new URL(name, root), "utf8"));
}

function runCode(node, response) {
  const $input = { all: () => [{ json: response }] };
  return vm.runInNewContext(
    `(() => { ${node.parameters.jsCode} })()`,
    { $input },
    { timeout: 1000 },
  );
}

function downstream(workflow, name) {
  return workflow.connections[name]?.main?.[0]?.map((edge) => edge.node) ?? [];
}

for (const [name, endpoint] of nudges) {
  test(`${name}: isolated, inactive, and no transport replay`, () => {
    const workflow = load(name);
    const schedule = workflow.nodes.filter(
      (node) => node.type === "n8n-nodes-base.scheduleTrigger",
    );
    const requests = workflow.nodes.filter((node) => node.type === "n8n-nodes-base.httpRequest");
    assert.equal(workflow.active, false);
    assert.equal(schedule.length, 1);
    assert.equal(requests.length, 1);
    assert.ok(requests[0].parameters.url.endsWith(endpoint));
    assert.equal(requests[0].parameters.method, "POST");
    assert.equal(requests[0].retryOnFail, undefined);
    assert.equal(requests[0].continueOnFail, undefined);
    assert.deepEqual(downstream(workflow, schedule[0].name), [requests[0].name]);
    assert.deepEqual(downstream(workflow, requests[0].name), ["Assert Enqueue Outcome"]);
    assert.deepEqual(downstream(workflow, "Assert Enqueue Outcome"), []);
  });

  test(`${name}: checks full API envelope and emits only counters`, () => {
    const check = load(name).nodes.find((node) => node.name === "Assert Enqueue Outcome");
    const items = [{ phone_e164: "+260000000000" }, { phone_e164: "+260111111111" }];
    const result = runCode(check, { items, count: 2, enqueued: 1, skipped: 1 });
    assert.equal(
      JSON.stringify(result),
      JSON.stringify([{ json: { count: 2, enqueued: 1, skipped: 1 } }]),
    );
    assert.doesNotMatch(JSON.stringify(result), /phone_e164/);
    assert.equal(
      JSON.stringify(runCode(check, { items: [], count: 0, enqueued: 0, skipped: 0 })),
      JSON.stringify([{ json: { count: 0, enqueued: 0, skipped: 0 } }]),
    );
    for (const bad of [
      { error: { code: "failed" } },
      { items, count: 2, enqueued: 2, skipped: 1 },
      { items, count: 1, enqueued: 1, skipped: 0 },
      { items, count: 2, enqueued: "1", skipped: 1 },
      { items, count: 2, enqueued: -1, skipped: 3 },
    ]) {
      assert.throws(() => runCode(check, bad), /Operational tick returned invalid enqueue outcome/);
    }
  });
}

test("payment sweep checks numeric outcome while preserving transport retry and alert branch", () => {
  const workflow = load("payment-sweeper.json");
  const request = workflow.nodes.find((node) => node.name === "Sweep Stale Payments");
  const check = workflow.nodes.find((node) => node.name === "Assert Sweep Outcome");
  assert.equal(workflow.active, false);
  assert.equal(request.retryOnFail, true);
  assert.equal(request.maxTries, 3);
  assert.equal(request.waitBetweenTries, 5000);
  assert.deepEqual(downstream(workflow, request.name), [check.name]);
  assert.deepEqual(downstream(workflow, "On Workflow Error"), ["Sanitize Error Payload"]);
  assert.equal(
    JSON.stringify(
      runCode(check, {
        scanned: 2,
        expired: 1,
        reconciled_success: 1,
        released: 0,
      }),
    ),
    JSON.stringify([
      {
        json: { scanned: 2, expired: 1, reconciled_success: 1, released: 0 },
      },
    ]),
  );
  for (const bad of [
    { scanned: 1, expired: 0, reconciled_success: 0 },
    { scanned: 1, expired: -1, reconciled_success: 0, released: 0 },
    { scanned: "1", expired: 0, reconciled_success: 0, released: 0 },
  ]) {
    assert.throws(() => runCode(check, bad), /Payment sweeper returned invalid outcome counters/);
  }
});
