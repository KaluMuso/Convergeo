import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import test from "node:test";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const python = process.env.PYTHON_BIN || "python3";
const bash = process.env.BASH_BIN || "bash";
const producer = ".github/workflows/deploy-staging.yml";
const outer = ".github/workflows/staging-operation.yml";
const sha = "a".repeat(40);
const runId = 700;
const repository = { id: 1290591718, full_name: "KaluMuso/Convergeo" };
const workflow = readFileSync(path.join(root, producer), "utf8");
const lookup = workflow
  .split("- name: Read authenticated prior-attempt checkpoint")[1]
  .split("- name: Resolve create versus reuse")[0]
  .split("script: |")[1]
  .split("\n")
  .map((line) => line.replace(/^ {12}/, ""))
  .join("\n");
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
function command(executable, args, options = {}) {
  const result = spawnSync(executable, args, {
    cwd: root,
    encoding: "utf8",
    timeout: 30000,
    ...options,
  });
  assert.equal(result.error, undefined);
  return result;
}
const py = (args) => command(python, args);
const ok = (result) => assert.equal(result.status, 0, result.stderr || result.stdout);
const json = (file) => JSON.parse(readFileSync(file, "utf8"));
const write = (file, value) => writeFileSync(file, JSON.stringify(value));
function fixture(portal, workflowPath = outer) {
  const directory = mkdtempSync(path.join(os.tmpdir(), "checkpoint-seam-"));
  const common = [
    "--portal",
    portal,
    "--project-id",
    "prj_" + portal,
    "--candidate-sha",
    sha,
    "--configuration-revision",
    "fixture-v1",
    "--run-id",
    String(runId),
  ];
  const cli = path.join(root, "scripts/ci/vercel_deployment_checkpoint.py");
  const first = path.join(directory, "first.json");
  const checkpoint = path.join(directory, "deployment-checkpoint.json");
  ok(py([cli, "select", ...common, "--run-attempt", "1", "--output", first]));
  assert.equal(json(first).decision, "create");
  ok(
    py([
      cli,
      "write",
      ...common,
      "--run-attempt",
      "1",
      "--selection",
      first,
      "--deployment-id",
      "dpl_" + portal,
      "--generated-at",
      "2026-09-14T12:00:10Z",
      "--output",
      checkpoint,
    ]),
  );
  assert.equal(json(checkpoint).producer.workflow, producer);
  const zip = path.join(directory, "source.zip");
  ok(
    py([
      "-c",
      "import sys,zipfile\nwith zipfile.ZipFile(sys.argv[2],'w') as z: z.write(sys.argv[1],'deployment-checkpoint.json')",
      checkpoint,
      zip,
    ]),
  );
  const archive = readFileSync(zip);
  const run = {
    id: runId,
    run_attempt: 1,
    head_sha: sha,
    head_branch: "staging",
    path: workflowPath,
    repository: { ...repository },
  };
  const job = {
    id: 901,
    name:
      (workflowPath === outer ? "Deploy and prove candidate / " : "") +
      "Vercel Preview proof (" +
      portal +
      ")",
    run_attempt: 1,
    status: "completed",
    conclusion: "failure",
    started_at: "2026-09-14T12:00:00Z",
    completed_at: "2026-09-14T12:01:00Z",
  };
  const artifact = {
    id: 900,
    name: "staging-preview-checkpoint-" + portal + "-700-attempt-1",
    expired: false,
    size_in_bytes: archive.length,
    digest: "sha256:" + createHash("sha256").update(archive).digest("hex"),
    created_at: "2026-09-14T12:00:12Z",
  };
  const live = {
    id: "dpl_" + portal,
    projectId: "prj_" + portal,
    target: null,
    readyState: "READY",
    url: "convergeo-" + portal + "-fixture.vercel.app",
    meta: {
      githubCommitSha: sha,
      convergeoBuildConfigRevision: "fixture-v1",
      convergeoRepositoryId: "1290591718",
      convergeoSourceRunId: "700",
      convergeoCreationAttempt: "1",
    },
  };
  const context = {
    runId,
    sha,
    ref: "refs/heads/staging",
    repo: { owner: "KaluMuso", repo: "Convergeo" },
  };
  return {
    directory,
    portal,
    common,
    cli,
    checkpoint,
    archive,
    run,
    job,
    artifact,
    live,
    context,
  };
}
async function metadata(f) {
  const outputs = {},
    failures = [];
  const actions = {
    listWorkflowRunArtifacts: Symbol("list"),
    downloadArtifact: async (args) => {
      assert.deepEqual(args, {
        owner: "KaluMuso",
        repo: "Convergeo",
        artifact_id: 900,
        archive_format: "zip",
      });
      return { data: f.archive };
    },
  };
  const github = {
    rest: { actions },
    paginate: async (route, args) => {
      assert.equal(args.run_id, runId);
      if (route === actions.listWorkflowRunArtifacts) return [f.artifact];
      assert.equal(
        route,
        "GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt_number}/jobs",
      );
      assert.equal(args.attempt_number, 1);
      return [f.job];
    },
    request: async (route, args) => {
      assert.equal(
        route,
        "GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt_number}",
      );
      assert.equal(args.attempt_number, 1);
      return { data: f.run };
    },
  };
  const core = {
    setOutput: (key, value) => {
      outputs[key] = value;
    },
    setFailed: (message) => {
      failures.push(message);
    },
    info: () => {},
  };
  // Execute the checked-in workflow script verbatim; only the authenticated API transport is synthetic.
  await new AsyncFunction("require", "process", "context", "github", "core", lookup)(
    require,
    {
      env: { PORTAL: f.portal, CURRENT_ATTEMPT: "2", RUNNER_TEMP: f.directory },
    },
    f.context,
    github,
    core,
  );
  return { outputs, failures };
}
function select(f) {
  const location = path.join(f.directory, "checkpoint-" + f.portal);
  const live = path.join(f.directory, "live.json");
  write(live, f.live);
  return py([
    f.cli,
    "select",
    ...f.common,
    "--run-attempt",
    "2",
    "--source-attempt",
    "1",
    "--archive",
    path.join(location, "prior.zip"),
    "--artifact-metadata",
    path.join(location, "artifact.json"),
    "--live-metadata",
    live,
    "--output",
    path.join(f.directory, "reuse.json"),
  ]);
}
function freshProof(f) {
  const interpreter = py(["-c", "import sys; print(sys.executable)"]);
  ok(interpreter);
  const bin = path.join(f.directory, "bin");
  mkdirSync(bin);
  const transport = path.join(bin, "transport.py");
  // No network implementation; unknown requests are fatal.
  writeFileSync(
    transport,
    String.raw`import json,os,sys
from pathlib import Path
args=sys.argv[1:]
url=args[-1]
def option(*names):
    return next((args[args.index(n)+1] for n in names if n in args), None)
live=json.loads(Path(os.environ["TEST_LIVE"]).read_text())
if "/v13/deployments/" in url:
    result=live
elif "/aliases?" in url:
    result={"alias":"customer.staging.vergeo5.com"}
elif "/env?" in url:
    result={"envs":[]}
elif url in ("https://"+live["url"]+"/en/health", "https://customer.staging.vergeo5.com/en/health"):
    result={"status":"ok","app":os.environ["TEST_PORTAL"],"env":"staging",
            "apiHost":"api.staging.vergeo5.com","buildId":live["meta"]["githubCommitSha"]}
else:
    raise SystemExit("unexpected offline request: "+url)
with open(os.environ["TEST_CALLS"],"a") as log: log.write(url+"\n")
Path(option("-o","--output")).write_text(json.dumps(result))
headers=option("-D","--dump-header")
if headers: Path(headers).write_text("HTTP/2 200\nContent-Type: application/json\n")
print("200",end="")
`,
  );
  for (const [name, body] of [
    ["python3", 'exec "$TEST_PYTHON" "$@"'],
    ["curl", 'exec "$TEST_PYTHON" "$TEST_TRANSPORT" "$@"'],
  ]) {
    writeFileSync(path.join(bin, name), "#!/usr/bin/env bash\n" + body + "\n", {
      mode: 0o755,
    });
  }
  const output = path.join(f.directory, "attempt-2");
  const env = {
    ...process.env,
    PATH: bin + path.delimiter + process.env.PATH,
    TEST_PYTHON: interpreter.stdout.trim(),
    TEST_TRANSPORT: transport,
    TEST_BIN: bin,
    HTTPS_PROXY: "http://127.0.0.1:9",
    HTTP_PROXY: "http://127.0.0.1:9",
    ALL_PROXY: "http://127.0.0.1:9",
    NO_PROXY: "",
    TEST_LIVE: path.join(f.directory, "live.json"),
    TEST_PORTAL: f.portal,
    TEST_CALLS: path.join(f.directory, "calls.txt"),
    GITHUB_REPOSITORY: repository.full_name,
    GITHUB_REPOSITORY_ID: String(repository.id),
    GITHUB_RUN_ID: "700",
    GITHUB_RUN_ATTEMPT: "2",
    GITHUB_SHA: sha,
    GITHUB_REF_NAME: "staging",
    VERCEL_TOKEN: "synthetic-token",
    VERCEL_ORG_ID: "team_fixture",
    ["VERCEL_PROJECT_ID_" + f.portal.toUpperCase()]: "prj_" + f.portal,
    STAGING_BUILD_CONFIG_REVISION: "fixture-v1",
    STAGING_API_BASE_URL: "https://api.staging.vergeo5.com",
    CUSTOMER_STAGING_STABLE_HOSTNAME: f.portal === "customer" ? "customer.staging.vergeo5.com" : "",
    VERCEL_PORTAL_BYPASS_SECRET: "",
    VERCEL_AUTOMATION_BYPASS_SECRET: "",
    GITHUB_OUTPUT: "",
    GITHUB_STEP_SUMMARY: "",
  };
  const args = [
    path.join(root, "scripts/ci/vercel-staging-preview-prove.sh"),
    "--portal",
    f.portal,
    "--output-dir",
    output,
    "--selection-file",
    path.join(f.directory, "reuse.json"),
  ].map((arg) => arg.replaceAll("\\", "/"));
  const isolatedShell = [
    "-c",
    'if command -v cygpath >/dev/null; then TEST_BIN="$(cygpath -u "$TEST_BIN")"; fi; ' +
      'export PATH="$TEST_BIN:$PATH"; ' +
      '[[ "$(command -v curl)" == "$TEST_BIN/curl" ]] || exit 97; ' +
      '[[ "$(command -v python3)" == "$TEST_BIN/python3" ]] || exit 98; ' +
      'exec bash "$@"',
    "checkpoint-offline",
  ];
  ok(command(bash, [...isolatedShell, ...args, "--phase", "prepare"], { env }));
  assert.equal(json(path.join(output, "deployment-checkpoint.json")).action, "reused");
  assert.throws(() => readFileSync(path.join(output, "evidence.json")));
  ok(command(bash, [...isolatedShell, ...args, "--phase", "prove"], { env }));
  const proof = json(path.join(output, "evidence.json"));
  assert.equal(proof.health_build_id, sha);
  assert.equal(proof.deployment_action, "reused");
  assert.equal(proof.deployment_create_calls, 0);
  assert.equal(proof.reused_deployments, 1);
  assert.equal(proof.deployment_origin_attempt, 1);
  assert.ok(readFileSync(env.TEST_CALLS, "utf8").includes("/en/health"));
  if (f.portal === "customer") {
    assert.equal(proof.stable_hostname_status, "verified");
    assert.ok(
      readFileSync(env.TEST_CALLS, "utf8").includes(
        "https://customer.staging.vergeo5.com/en/health",
      ),
    );
  }
}
for (const workflowPath of [outer, producer]) {
  for (const portal of ["customer", "vendor", "admin"]) {
    test(
      workflowPath + ": attempt 1 checkpoint -> attempt 2 reuse -> fresh " + portal + " proof",
      async () => {
        const f = fixture(portal, workflowPath);
        try {
          const result = await metadata(f);
          assert.deepEqual(result.failures, []);
          assert.equal(result.outputs.found, "true");
          assert.equal(
            json(path.join(f.directory, "checkpoint-" + portal, "artifact.json")).workflow_run.path,
            workflowPath,
          );
          ok(select(f));
          assert.equal(json(path.join(f.directory, "reuse.json")).decision, "reuse");
          freshProof(f);
        } finally {
          rmSync(f.directory, { recursive: true, force: true });
        }
      },
    );
  }
}
for (const [label, mutate] of [
  [
    "workflow",
    (f) => {
      f.run.path = ".github/workflows/arbitrary.yml";
    },
  ],
  [
    "repository",
    (f) => {
      f.run.repository.full_name = "attacker/Convergeo";
    },
  ],
  [
    "repository ID",
    (f) => {
      f.run.repository.id = 1;
    },
  ],
  [
    "ref",
    (f) => {
      f.run.head_branch = "master";
    },
  ],
  [
    "SHA",
    (f) => {
      f.run.head_sha = "b".repeat(40);
    },
  ],
  [
    "short SHA",
    (f) => {
      f.run.head_sha = f.context.sha = sha.slice(0, 12);
    },
  ],
  [
    "run",
    (f) => {
      f.run.id = 701;
    },
  ],
  [
    "attempt",
    (f) => {
      f.run.run_attempt = 2;
    },
  ],
  [
    "source job",
    (f) => {
      f.job.name = "unrelated";
    },
  ],
  [
    "source job attempt",
    (f) => {
      f.job.run_attempt = 2;
    },
  ],
  [
    "digest",
    (f) => {
      f.artifact.digest = "sha256:" + "0".repeat(64);
    },
  ],
  [
    "time",
    (f) => {
      f.artifact.created_at = "2026-09-14T12:02:00Z";
    },
  ],
]) {
  test("workflow rejects " + label + " without a create fallback", async () => {
    const f = fixture("customer");
    try {
      mutate(f);
      const result = await metadata(f);
      assert.ok(result.failures.length > 0);
      assert.equal(result.outputs.found, undefined);
      assert.throws(() =>
        readFileSync(path.join(f.directory, "checkpoint-customer", "artifact.json")),
      );
    } finally {
      rmSync(f.directory, { recursive: true, force: true });
    }
  });
}
for (const [label, mutate] of [
  [
    "workflow",
    (m) => {
      m.workflow_run.path = ".github/workflows/arbitrary.yml";
    },
  ],
  [
    "repository",
    (m) => {
      m.workflow_run.repository = "attacker/Convergeo";
    },
  ],
  [
    "repository ID",
    (m) => {
      m.workflow_run.repository_id = 1;
    },
  ],
  [
    "ref",
    (m) => {
      m.workflow_run.head_branch = "master";
    },
  ],
  [
    "SHA",
    (m) => {
      m.workflow_run.head_sha = "b".repeat(40);
    },
  ],
  [
    "attempt",
    (m) => {
      m.workflow_run.run_attempt = 2;
    },
  ],
  [
    "source job attempt",
    (m) => {
      m.source_job.run_attempt = 2;
    },
  ],
  [
    "source job",
    (m) => {
      m.source_job.name = "unrelated";
    },
  ],
  [
    "digest",
    (m) => {
      m.digest = "sha256:" + "0".repeat(64);
    },
  ],
  [
    "time",
    (m) => {
      m.created_at = "2026-09-14T12:02:00Z";
    },
  ],
]) {
  test("Python rejects transported " + label + " without a create fallback", async () => {
    const f = fixture("customer", producer);
    try {
      assert.deepEqual((await metadata(f)).failures, []);
      const file = path.join(f.directory, "checkpoint-customer", "artifact.json");
      const value = json(file);
      mutate(value);
      write(file, value);
      const result = select(f);
      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /checkpoint rejected/);
      assert.throws(() => readFileSync(path.join(f.directory, "reuse.json")));
    } finally {
      rmSync(f.directory, { recursive: true, force: true });
    }
  });
}
