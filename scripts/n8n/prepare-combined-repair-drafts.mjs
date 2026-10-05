import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const n8nDirectory = new URL("../../infra/n8n/", import.meta.url);
const referenceBytes = 18173;
const referenceSha256 = "c47a4b0006a0b9f3bde53a76a24287cf335fd0c1174fb3d1087414d6cfae25ca";
const sources = [
  {
    id: "zkIe2zW72qp5fcli",
    versionId: "d2da699c-b1e7-44c7-8182-50ebb226a759",
    fileName: "operational-nudges-combined.disabled.json",
    branches: [
      ["/internal/n8n/kyc-stalled/tick", 60000],
      ["/internal/n8n/low-stock/tick", 60000],
      ["/internal/n8n/review-requests/tick", 60000],
      ["/internal/n8n/payout-failures/tick", 60000],
    ],
    checks: new Map([
      ["/internal/n8n/kyc-stalled/tick", "kyc-nudge.json"],
      ["/internal/n8n/low-stock/tick", "low-stock-alert.json"],
      ["/internal/n8n/review-requests/tick", "review-request.json"],
      ["/internal/n8n/payout-failures/tick", "low-stock-alert.json"],
    ]),
  },
  {
    id: "C1MpTNjrfLACMG3f",
    versionId: "ff90171d-3a29-4bec-918d-99f2ccd7941f",
    fileName: "payment-reconciliation-combined.disabled.json",
    branches: [
      ["/internal/reconciliation/webhook-drain-tick", 30000],
      ["/internal/reconciliation/poll-tick", 60000],
      ["/internal/payment-sweeper/tick", 60000],
      ["/internal/reconciliation/daily-report", 120000],
    ],
    checks: new Map([["/internal/payment-sweeper/tick", "payment-sweeper.json"]]),
  },
];

function outcomeCode(templateName) {
  const template = JSON.parse(readFileSync(new URL(templateName, n8nDirectory), "utf8"));
  const check = template.nodes.find((node) => node.name.startsWith("Assert "));
  if (!check || check.type !== "n8n-nodes-base.code") {
    throw new Error(`Missing outcome check in ${templateName}`);
  }
  return check.parameters.jsCode;
}

function edgeTo(name) {
  return { node: name, type: "main", index: 0 };
}

function buildOne(reference, spec) {
  if (
    reference.id !== spec.id ||
    reference.versionId !== spec.versionId ||
    reference.activeVersionId !== spec.versionId ||
    reference.activeVersionMatchesSaved !== true ||
    reference.active !== true
  ) {
    throw new Error(`Installed workflow identity or active version changed: ${spec.id}`);
  }
  if (!Array.isArray(reference.nodes) || reference.nodes.length !== spec.branches.length * 2) {
    throw new Error(`Unexpected node count: ${spec.id}`);
  }
  const nodes = structuredClone(reference.nodes);
  const connections = structuredClone(reference.connections);
  const originalConnectionKeys = Object.keys(connections);
  const names = new Set(nodes.map((node) => node.name));
  const ids = new Set(nodes.map((node) => node.id));
  if (
    names.size !== nodes.length ||
    ids.size !== nodes.length ||
    nodes.some((node) => typeof node.name !== "string" || typeof node.id !== "string") ||
    originalConnectionKeys.length !== spec.branches.length
  ) {
    throw new Error(`Installed workflow has duplicate nodes or unexpected edges: ${spec.id}`);
  }
  const visited = new Set();
  for (const [endpoint, timeout] of spec.branches) {
    const matchingRequests = nodes.filter(
      (node) => node.parameters?.url === `https://api.vergeo5.com${endpoint}`,
    );
    const request = matchingRequests.length === 1 ? matchingRequests[0] : undefined;
    const matchingTriggers = Object.entries(connections).filter(
      ([, value]) => JSON.stringify(value.main) === JSON.stringify([[edgeTo(request?.name)]]),
    );
    const triggerName = matchingTriggers.length === 1 ? matchingTriggers[0][0] : undefined;
    const trigger = nodes.find((node) => node.name === triggerName);
    if (
      trigger?.type !== "n8n-nodes-base.scheduleTrigger" ||
      trigger.typeVersion !== 1.3 ||
      request?.type !== "n8n-nodes-base.httpRequest" ||
      request.typeVersion !== 4.4 ||
      request.parameters?.method !== "POST" ||
      request.parameters?.authentication !== "genericCredentialType" ||
      request.parameters?.genericAuthType !== "httpHeaderAuth" ||
      request.parameters?.options?.timeout !== timeout ||
      request.retryOnFail !== undefined ||
      request.continueOnFail !== undefined ||
      request.alwaysOutputData !== undefined ||
      connections[request.name] !== undefined
    ) {
      throw new Error(`Installed branch drift: ${spec.id}: ${endpoint}`);
    }
    visited.add(triggerName);
    visited.add(request.name);
    const templateName = spec.checks.get(endpoint);
    if (!templateName) continue;
    const checkName = `Assert ${request.name} outcome`;
    const checkId = `assert-${request.id}`;
    if (names.has(checkName) || ids.has(checkId)) {
      throw new Error(`Outcome-check node collides with installed node: ${spec.id}`);
    }
    names.add(checkName);
    ids.add(checkId);
    request.alwaysOutputData = true;
    nodes.push({
      id: checkId,
      name: checkName,
      type: "n8n-nodes-base.code",
      typeVersion: 2,
      position: [request.position[0] + 240, request.position[1]],
      parameters: {
        mode: "runOnceForAllItems",
        language: "javaScript",
        jsCode: outcomeCode(templateName),
      },
    });
    connections[request.name] = { main: [[edgeTo(checkName)]] };
  }
  if (
    visited.size !== reference.nodes.length ||
    originalConnectionKeys.some((name) => !visited.has(name))
  ) {
    throw new Error(`Installed workflow contains an unexpected branch: ${spec.id}`);
  }
  const settings = structuredClone(reference.settings);
  delete settings.availableInMCP;
  return {
    name: `${reference.name} (disabled repair draft)`,
    nodes,
    connections,
    active: false,
    settings,
  };
}

export function buildCombinedDrafts(reference) {
  if (!reference || !Array.isArray(reference.workflows)) {
    throw new Error("Scrubbed installed-workflow reference is missing workflows");
  }
  return sources.map((spec) => {
    const source = reference.workflows.find((workflow) => workflow.id === spec.id);
    if (!source) throw new Error(`Missing installed workflow: ${spec.id}`);
    return { fileName: spec.fileName, workflow: buildOne(source, spec) };
  });
}

async function main() {
  const [, , inputPath, outputDirectory] = process.argv;
  if (!inputPath || !outputDirectory) {
    throw new Error(
      "Usage: node prepare-combined-repair-drafts.mjs <scrubbed-reference.json> <output-directory>",
    );
  }
  const bytes = await readFile(inputPath);
  const digest = createHash("sha256").update(bytes).digest("hex");
  if (bytes.length !== referenceBytes || digest !== referenceSha256) {
    throw new Error("Scrubbed installed-workflow reference bytes or SHA-256 changed");
  }
  const reference = JSON.parse(bytes.toString("utf8"));
  const drafts = buildCombinedDrafts(reference);
  await mkdir(outputDirectory, { recursive: true });
  for (const { fileName, workflow } of drafts) {
    await writeFile(path.join(outputDirectory, fileName), `${JSON.stringify(workflow, null, 2)}\n`);
  }
  process.stdout.write(`Created ${drafts.length} inactive drafts from SHA-256 ${digest}\n`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
