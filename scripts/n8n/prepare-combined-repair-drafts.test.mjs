import assert from "node:assert/strict";
import { test } from "node:test";
import vm from "node:vm";
import { buildCombinedDrafts } from "./prepare-combined-repair-drafts.mjs";

const specs = [
  {
    id: "zkIe2zW72qp5fcli",
    versionId: "d2da699c-b1e7-44c7-8182-50ebb226a759",
    branches: [
      ["Every 6h", "KYC stalled tick", "/internal/n8n/kyc-stalled/tick", 60000],
      ["Daily 07:00", "Low stock tick", "/internal/n8n/low-stock/tick", 60000],
      ["Every 4h", "Review request tick", "/internal/n8n/review-requests/tick", 60000],
      ["Every 1h", "Payout failure tick", "/internal/n8n/payout-failures/tick", 60000],
    ],
  },
  {
    id: "C1MpTNjrfLACMG3f",
    versionId: "ff90171d-3a29-4bec-918d-99f2ccd7941f",
    branches: [
      ["Every 1 min", "Webhook drain tick", "/internal/reconciliation/webhook-drain-tick", 30000],
      ["Every 30 min", "Reconciliation poll tick", "/internal/reconciliation/poll-tick", 60000],
      ["Every 10 min", "Payment sweeper tick", "/internal/payment-sweeper/tick", 60000],
      [
        "Daily 02:00",
        "Daily reconciliation report",
        "/internal/reconciliation/daily-report",
        120000,
      ],
    ],
  },
];

function reference() {
  return {
    workflows: specs.map((spec) => {
      const nodes = [];
      const connections = {};
      for (const [triggerName, requestName, endpoint, timeout] of spec.branches) {
        nodes.push({
          id: `trigger-${triggerName}`,
          name: triggerName,
          type: "n8n-nodes-base.scheduleTrigger",
          typeVersion: 1.3,
          position: [0, nodes.length * 112],
          parameters: { rule: { interval: [{ field: "minutes", minutesInterval: 10 }] } },
        });
        nodes.push({
          id: `request-${requestName}`,
          name: requestName,
          type: "n8n-nodes-base.httpRequest",
          typeVersion: 4.4,
          position: [224, (nodes.length - 1) * 112],
          parameters: {
            method: "POST",
            url: `https://api.vergeo5.com${endpoint}`,
            authentication: "genericCredentialType",
            genericAuthType: "httpHeaderAuth",
            options: { timeout },
          },
        });
        connections[triggerName] = {
          main: [[{ node: requestName, type: "main", index: 0 }]],
        };
      }
      return {
        id: spec.id,
        name: `Installed ${spec.id}`,
        versionId: spec.versionId,
        activeVersionId: spec.versionId,
        activeVersionMatchesSaved: true,
        active: true,
        settings: { executionOrder: "v1", availableInMCP: true },
        nodes,
        connections,
      };
    }),
  };
}

test("builds inactive combined drafts while preserving unrelated money branches", () => {
  const input = reference();
  const before = structuredClone(input);
  const drafts = buildCombinedDrafts(input);
  assert.deepEqual(input, before);
  assert.deepEqual(
    drafts.map((draft) => draft.fileName),
    ["operational-nudges-combined.disabled.json", "payment-reconciliation-combined.disabled.json"],
  );
  const [nudges, payments] = drafts.map((draft) => draft.workflow);
  for (const workflow of [nudges, payments]) {
    assert.equal(workflow.active, false);
    assert.equal(workflow.id, undefined);
    assert.equal(workflow.settings.availableInMCP, undefined);
    assert.equal(
      workflow.nodes.some((node) => node.retryOnFail),
      false,
    );
  }
  assert.equal(nudges.nodes.filter((node) => node.type === "n8n-nodes-base.code").length, 4);
  assert.equal(payments.nodes.filter((node) => node.type === "n8n-nodes-base.code").length, 1);
  for (const name of [
    "Webhook drain tick",
    "Reconciliation poll tick",
    "Daily reconciliation report",
  ]) {
    const original = before.workflows[1].nodes.find((node) => node.name === name);
    const draft = payments.nodes.find((node) => node.name === name);
    assert.deepEqual(draft, original);
    assert.equal(payments.connections[name], undefined);
  }
  for (const name of [
    "KYC stalled tick",
    "Low stock tick",
    "Review request tick",
    "Payout failure tick",
  ]) {
    const request = nudges.nodes.find((node) => node.name === name);
    assert.equal(request.alwaysOutputData, true);
    const target = nudges.connections[name].main[0][0].node;
    const check = nudges.nodes.find((node) => node.name === target);
    assert.ok(check);
    const $input = { all: () => [{ json: { items: [{}], count: 1, enqueued: 1, skipped: 0 } }] };
    assert.equal(
      JSON.stringify(vm.runInNewContext(`(() => { ${check.parameters.jsCode} })()`, { $input })),
      JSON.stringify([{ json: { count: 1, enqueued: 1, skipped: 0 } }]),
    );
  }
  const paymentRequest = payments.nodes.find((node) => node.name === "Payment sweeper tick");
  assert.equal(paymentRequest.alwaysOutputData, true);
  assert.equal(
    payments.connections["Payment sweeper tick"].main[0][0].node,
    "Assert Payment sweeper tick outcome",
  );
});

test("refuses changed source identity, endpoint, replay policy, and extra nodes", () => {
  for (const mutate of [
    (input) => {
      input.workflows[0].versionId = "successor";
    },
    (input) => {
      input.workflows[0].nodes[1].parameters.url = "https://wrong.example/tick";
    },
    (input) => {
      input.workflows[1].nodes[5].retryOnFail = true;
    },
    (input) => {
      input.workflows[0].nodes.push({ name: "Unexpected" });
    },
    (input) => {
      input.workflows[0].nodes[2].id = input.workflows[0].nodes[0].id;
    },
    (input) => {
      input.workflows[0].nodes[0].id = `assert-${input.workflows[0].nodes[1].id}`;
    },
    (input) => {
      input.workflows[0].nodes[0].name = "Assert KYC stalled tick outcome";
    },
    (input) => {
      input.workflows[0].connections.Unexpected = { main: [[]] };
    },
  ]) {
    const input = reference();
    mutate(input);
    assert.throws(() => buildCombinedDrafts(input));
  }
});
