"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const REPOSITORY = "KaluMuso/Convergeo";
const REPOSITORY_ID = 1290591718;
const TRUSTED_WORKFLOWS = new Set([
  ".github/workflows/deploy-staging.yml",
  ".github/workflows/staging-operation.yml",
]);
const MAX_ARCHIVE_BYTES = 1024 * 1024;
const MAX_RUN_ATTEMPTS = 100;

function requireContract(condition, code) {
  if (!condition) throw new Error(code);
}

function exactLogicalJob(jobs, logicalName, attempt) {
  const matches = jobs.filter(
    (job) =>
      job.run_attempt === attempt &&
      (job.name === logicalName || job.name?.endsWith(` / ${logicalName}`)),
  );
  requireContract(matches.length === 1, "MISSING_OR_AMBIGUOUS_CURRENT_JOB");
  return matches[0];
}

async function collectHandoffMetadata({ github, context, runId, attempt }) {
  requireContract(
    Number.isSafeInteger(runId) &&
      runId > 0 &&
      Number.isSafeInteger(attempt) &&
      attempt > 0 &&
      attempt <= MAX_RUN_ATTEMPTS,
    "INVALID_SOURCE_RUN_IDENTITY",
  );
  requireContract(
    `${context.repo.owner}/${context.repo.repo}` === REPOSITORY,
    "UNTRUSTED_REPOSITORY",
  );

  const { owner, repo } = context.repo;
  const runResponse = await github.request(
    "GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt_number}",
    { owner, repo, run_id: runId, attempt_number: attempt },
  );
  const run = runResponse.data;
  requireContract(
    run.id === runId &&
      run.run_attempt === attempt &&
      run.repository?.id === REPOSITORY_ID &&
      run.repository?.full_name === REPOSITORY &&
      run.head_repository?.id === REPOSITORY_ID &&
      run.head_branch === "staging" &&
      /^[0-9a-f]{40}$/.test(run.head_sha || "") &&
      TRUSTED_WORKFLOWS.has(run.path),
    "UNTRUSTED_SOURCE_RUN",
  );

  const jobs = [];
  for (let runAttempt = 1; runAttempt <= attempt; runAttempt += 1) {
    const attemptJobs = await github.paginate(
      "GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt_number}/jobs",
      { owner, repo, run_id: runId, attempt_number: runAttempt, per_page: 100 },
    );
    for (const job of attemptJobs) {
      jobs.push({
        ...job,
        run_id: runId,
        run_attempt: runAttempt,
        head_sha: run.head_sha,
      });
    }
  }

  const smoke = exactLogicalJob(jobs, "Staging smoke + evidence", attempt);
  const smokeStarted = Date.parse(smoke.started_at);
  const smokeCompleted = Date.parse(smoke.completed_at);
  requireContract(
    smoke.status === "completed" &&
      Number.isFinite(smokeStarted) &&
      Number.isFinite(smokeCompleted) &&
      smokeStarted <= smokeCompleted,
    "INVALID_CURRENT_SMOKE_WINDOW",
  );

  const expectedName = `staging-sha-proof-${runId}-attempt-${attempt}`;
  const artifactResponse = await github.rest.actions.listWorkflowRunArtifacts({
    owner,
    repo,
    run_id: runId,
    name: expectedName,
    per_page: 100,
  });
  const artifactPage = artifactResponse.data;
  requireContract(
    Number.isSafeInteger(artifactPage.total_count) &&
      artifactPage.total_count <= 100 &&
      Array.isArray(artifactPage.artifacts) &&
      artifactPage.artifacts.length === artifactPage.total_count,
    "UNBOUNDED_PROOF_ARTIFACT_SET",
  );
  const artifacts = artifactPage.artifacts;
  const matching = artifacts.filter((artifact) => {
    const created = Date.parse(artifact.created_at);
    return (
      artifact.name === expectedName &&
      artifact.expired === false &&
      Number.isSafeInteger(artifact.size_in_bytes) &&
      artifact.size_in_bytes > 0 &&
      artifact.size_in_bytes <= MAX_ARCHIVE_BYTES &&
      /^sha256:[0-9a-f]{64}$/.test(artifact.digest || "") &&
      Number.isFinite(created) &&
      created >= smokeStarted &&
      created <= smokeCompleted
    );
  });
  requireContract(matching.length === 1, "INVALID_CURRENT_PROOF_ARTIFACT");
  const artifact = matching[0];
  const download = await github.rest.actions.downloadArtifact({
    owner,
    repo,
    artifact_id: artifact.id,
    archive_format: "zip",
  });
  const archive = Buffer.from(download.data);
  requireContract(
    archive.length > 0 && archive.length <= MAX_ARCHIVE_BYTES,
    "INVALID_PROOF_ARCHIVE_SIZE",
  );
  const digest = `sha256:${crypto.createHash("sha256").update(archive).digest("hex")}`;
  requireContract(digest === artifact.digest, "PROOF_ARTIFACT_DIGEST_MISMATCH");

  const refResponse = await github.rest.git.getRef({ owner, repo, ref: "heads/staging" });
  const currentStagingSha = refResponse.data.object.sha;
  requireContract(/^[0-9a-f]{40}$/.test(currentStagingSha || ""), "INVALID_STAGING_REF");

  return {
    run,
    jobs,
    artifact: {
      ...artifact,
      workflow_run: {
        id: run.id,
        head_sha: run.head_sha,
        head_branch: run.head_branch,
        repository_id: run.repository.id,
        path: run.path,
      },
    },
    archive,
    currentStagingSha,
  };
}

function writeHandoffMetadata(directory, result) {
  fs.mkdirSync(directory, { recursive: true });
  fs.writeFileSync(path.join(directory, "run.json"), JSON.stringify(result.run));
  fs.writeFileSync(path.join(directory, "artifact.json"), JSON.stringify(result.artifact));
  fs.writeFileSync(path.join(directory, "jobs.json"), JSON.stringify(result.jobs));
  fs.writeFileSync(path.join(directory, "proof.zip"), result.archive);
  fs.writeFileSync(path.join(directory, "expected-sha.txt"), `${result.run.head_sha}\n`);
  fs.writeFileSync(path.join(directory, "staging-sha.txt"), `${result.currentStagingSha}\n`);
}

module.exports = {
  MAX_ARCHIVE_BYTES,
  MAX_RUN_ATTEMPTS,
  collectHandoffMetadata,
  exactLogicalJob,
  writeHandoffMetadata,
};
