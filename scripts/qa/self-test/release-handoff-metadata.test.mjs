import assert from "node:assert/strict";
import crypto from "node:crypto";
import test from "node:test";

import adapter from "../../ci/github_handoff_metadata.cjs";

const SHA = "a".repeat(40);
const ARCHIVE = Buffer.from("bounded-proof-archive");

function fixture() {
  const run = {
    id: 10,
    run_attempt: 2,
    head_sha: SHA,
    head_branch: "staging",
    head_repository: { id: 1290591718 },
    repository: { id: 1290591718, full_name: "KaluMuso/Convergeo" },
    path: ".github/workflows/staging-operation.yml",
  };
  const smoke = {
    name: "deploy / Staging smoke + evidence",
    status: "completed",
    started_at: "2026-09-14T12:00:00Z",
    completed_at: "2026-09-14T12:02:00Z",
  };
  const artifact = {
    id: 20,
    name: "staging-sha-proof-10-attempt-2",
    expired: false,
    size_in_bytes: ARCHIVE.length,
    created_at: "2026-09-14T12:01:00Z",
    digest: `sha256:${crypto.createHash("sha256").update(ARCHIVE).digest("hex")}`,
  };
  const github = {
    request: async () => ({ data: run }),
    paginate: async (_route, params) => (params.attempt_number === 2 ? [smoke] : []),
    rest: {
      actions: {
        listWorkflowRunArtifacts: async () => ({
          data: { total_count: 1, artifacts: [artifact] },
        }),
        downloadArtifact: async () => ({ data: ARCHIVE }),
      },
      git: { getRef: async () => ({ data: { object: { sha: SHA } } }) },
    },
  };
  return {
    run,
    artifact,
    github,
    context: { repo: { owner: "KaluMuso", repo: "Convergeo" } },
  };
}

test("authenticated current-attempt artifact is selected exactly", async () => {
  const value = fixture();
  const result = await adapter.collectHandoffMetadata({
    github: value.github,
    context: value.context,
    runId: 10,
    attempt: 2,
  });
  assert.equal(result.artifact.id, 20);
  assert.equal(result.artifact.workflow_run.path, ".github/workflows/staging-operation.yml");
  assert.equal(result.currentStagingSha, SHA);
});

test("stale-attempt artifact name cannot satisfy the current handoff", async () => {
  const value = fixture();
  value.artifact.name = "staging-sha-proof-10-attempt-1";
  await assert.rejects(
    adapter.collectHandoffMetadata({
      github: value.github,
      context: value.context,
      runId: 10,
      attempt: 2,
    }),
    /INVALID_CURRENT_PROOF_ARTIFACT/,
  );
});

test("download tampering is fatal even when provider metadata looks valid", async () => {
  const value = fixture();
  value.github.rest.actions.downloadArtifact = async () => ({ data: Buffer.from("tampered") });
  await assert.rejects(
    adapter.collectHandoffMetadata({
      github: value.github,
      context: value.context,
      runId: 10,
      attempt: 2,
    }),
    /PROOF_ARTIFACT_DIGEST_MISMATCH/,
  );
});

test("fork/source workflow metadata fails before artifact use", async () => {
  const value = fixture();
  value.run.head_repository.id = 999;
  await assert.rejects(
    adapter.collectHandoffMetadata({
      github: value.github,
      context: value.context,
      runId: 10,
      attempt: 2,
    }),
    /UNTRUSTED_SOURCE_RUN/,
  );
});

test("user-supplied attempt and artifact enumeration stay bounded", async () => {
  const value = fixture();
  await assert.rejects(
    adapter.collectHandoffMetadata({
      github: value.github,
      context: value.context,
      runId: 10,
      attempt: adapter.MAX_RUN_ATTEMPTS + 1,
    }),
    /INVALID_SOURCE_RUN_IDENTITY/,
  );
  value.github.rest.actions.listWorkflowRunArtifacts = async () => ({
    data: { total_count: 101, artifacts: [value.artifact] },
  });
  await assert.rejects(
    adapter.collectHandoffMetadata({
      github: value.github,
      context: value.context,
      runId: 10,
      attempt: 2,
    }),
    /UNBOUNDED_PROOF_ARTIFACT_SET/,
  );
});
