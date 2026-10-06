import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import process from "node:process";
import { afterEach, test } from "node:test";
import { fileURLToPath, URL } from "node:url";

import { checkRunbooks } from "./check-ops-runbook-preflight.mjs";

const realRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const temporary = [];
afterEach(() => {
  for (const dir of temporary.splice(0)) rmSync(dir, { recursive: true, force: true });
});

function fixture(deploy = "") {
  const root = mkdtempSync(join(tmpdir(), "ops-runbook-preflight-"));
  temporary.push(root);
  mkdirSync(join(root, "docs/ops"), { recursive: true });
  writeFileSync(join(root, "docs/ops/production-release-control.md"), "## Exact source\n");
  writeFileSync(
    join(root, "docs/ops/deploy-verify-runbook.md"),
    `# Deploy\n[release](production-release-control.md#exact-source)\n${deploy}\n`,
  );
  writeFileSync(
    join(root, "docs/ops/n8n-activation-runbook.md"),
    "# n8n\n[deploy](deploy-verify-runbook.md#deploy)\n",
  );
  return root;
}

test("current exact-source runbooks pass the offline preflight", () => {
  assert.deepEqual(checkRunbooks(realRoot), []);
});

test("warnings in prose and shell comments are not executable commands", () => {
  const root = fixture(
    "Do not run `supabase db push` or `db-restore.sh --force`.\n```bash\n# docker compose stop n8n\n```",
  );
  assert.deepEqual(checkRunbooks(root), []);
});

test("explicit historical marker exempts only its adjacent shell example", () => {
  const root = fixture(
    "<!-- ops-preflight: historical-do-not-run -->\n```bash\nsupabase db push\n```\n```bash\nvercel deploy --prod\n```",
  );
  assert.equal(checkRunbooks(root).length, 1);
  assert.match(checkRunbooks(root)[0], /unbound production deploy/);
});

test("parenthesized and encoded paths, reference links, inline code and duplicate anchors", () => {
  const root = fixture(
    "[plain](guide(with-parens).md#repeated-1)\n[encoded](guide%28with-parens%29.md#repeated%2D1)\n[space](guide%20with%20space.md#title)\n[reference][evidence]\n[evidence]: guide(with-parens).md#repeated-1\n`[illustration](missing.md)`\n``[another](also-missing.md) with ` inside``",
  );
  writeFileSync(
    join(root, "docs/ops/guide(with-parens).md"),
    "# Repeated\n```bash\n# Repeated\n```\n# Repeated\n",
  );
  writeFileSync(join(root, "docs/ops/guide with space.md"), "# Title\n");
  assert.deepEqual(checkRunbooks(root), []);
});

test("broken reference-style definition fails", () => {
  const root = fixture("[reference][evidence]\n[evidence]: missing-evidence.md");
  assert.match(checkRunbooks(root).join("\n"), /missing-evidence\.md/);
});

for (const command of [
  "supabase db push",
  "infra/scripts/db-restore.sh --force",
  "ssh opc@old-oci-vm",
  "docker compose -f infra/docker-compose.yml ps",
  "docker compose stop n8n",
  "docker compose up -d api caddy",
  "vercel deploy --prod",
]) {
  test(`rejects runnable historical command: ${command}`, () => {
    const root = fixture(`\`\`\`bash\n${command}\n\`\`\``);
    assert.match(checkRunbooks(root).join("\n"), /docs\/ops\/deploy-verify-runbook\.md:\d+:/);
  });
}

test("rejects missing release-evidence target and broken anchor", () => {
  const root = fixture(
    "[missing](absent.md)\n[wrong section](production-release-control.md#missing-heading)",
  );
  assert.equal(checkRunbooks(root).length, 2);
  const run = spawnSync(
    process.execPath,
    [fileURLToPath(new URL("./check-ops-runbook-preflight.mjs", import.meta.url)), "--root", root],
    { encoding: "utf8" },
  );
  assert.equal(run.status, 1);
  assert.match(run.stderr, /missing heading/);
});
