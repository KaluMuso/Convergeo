import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { runInNewContext } from "node:vm";

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

const browserSource = readFileSync(
  new URL("../../e2e/scripts/cart-response-drill.mjs", import.meta.url),
  "utf8",
);
const diagnosticSource = browserSource.slice(
  browserSource.indexOf("function cartFailureDiagnostic("),
  browserSource.indexOf("\nconst browserDiagnostic ="),
);
const diagnostic = runInNewContext(`(${diagnosticSource})`);
const scalarState = {
  posts: 1,
  firstResponseStatus: 200,
  firstClickCompleted: true,
  errorVisibilityPassed: true,
  routeFailureObserved: true,
  routeFailureStage: "cart_response_dispose",
  routeFailurePost: 1,
  firstResponseDisposed: false,
};
const committed = { committed_before_discard: true, one_response_discarded: true };
const plain = (value) => JSON.parse(JSON.stringify(value));

test("browser failure projection has fixed bounded scalar fields only", () => {
  const projected = plain(diagnostic("discard_route_integrity", scalarState, committed));
  assert.deepEqual(projected, {
    format: "cart_browser_failure_v1",
    failure_stage: "discard_route_integrity",
    intercepted_posts: 1,
    first_response_status: 200,
    first_click_completed: true,
    error_visibility_assertion_passed: true,
    route_failure_observed: true,
    route_failure_stage: "cart_response_dispose",
    route_failure_post: 1,
    first_response_disposed: false,
    db_commit_recorded: true,
    response_discard_recorded: true,
    fixture_cleanup_recorded: false,
  });
  assert.ok(Buffer.byteLength(JSON.stringify(projected)) < 1024);
});
for (const value of [-1, 1001, 1.5, Infinity, NaN, 3n, Symbol("PRIVATE"), "PRIVATE", {}]) {
  test("browser projection rejects invalid counters without coercion", () => {
    const result = diagnostic(
      "discard_click",
      { ...scalarState, posts: value, routeFailurePost: value },
      {},
    );
    assert.equal(result.intercepted_posts, null);
    assert.equal(result.route_failure_post, null);
  });
}
for (const status of [
  99,
  600,
  200.5,
  Infinity,
  "PRIVATE",
  {
    toJSON() {
      throw new Error("PRIVATE");
    },
  },
]) {
  test("browser projection rejects invalid status values", () => {
    assert.equal(
      diagnostic("discard_click", { firstResponseStatus: status }, {}).first_response_status,
      null,
    );
  });
}
test("browser projection ignores private fields, getters, prototypes and serializers", () => {
  const privateValue = "COOKIE_CREDENTIAL_BODY_CUSTOMER_PRIVATE";
  const state = {
    ...scalarState,
    cookie: privateValue,
    body: privateValue,
    credentials: privateValue,
    customer: privateValue,
    toJSON() {
      throw new Error(privateValue);
    },
  };
  const result = diagnostic(
    privateValue.repeat(1000),
    { ...state, routeFailureStage: privateValue },
    committed,
  );
  assert.equal(result.failure_stage, "unclassified");
  assert.equal(result.route_failure_stage, "unclassified");
  assert.ok(!JSON.stringify(result).includes(privateValue));
  Object.defineProperty(state, "posts", {
    get() {
      throw new Error(privateValue);
    },
  });
  const getterResult = diagnostic("discard_click", state, Object.create(committed));
  assert.equal(getterResult.intercepted_posts, null);
  assert.equal(getterResult.db_commit_recorded, false);
  const proxy = new Proxy(
    {},
    {
      getOwnPropertyDescriptor() {
        throw new Error(privateValue);
      },
    },
  );
  assert.equal(diagnostic("discard_click", proxy, proxy).intercepted_posts, null);
});
test("browser projection accepts boundaries and distinguishes unknown booleans", () => {
  for (const posts of [0, 1000])
    assert.equal(diagnostic("discard_click", { posts }, {}).intercepted_posts, posts);
  for (const firstResponseStatus of [100, 599])
    assert.equal(
      diagnostic("discard_click", { firstResponseStatus }, {}).first_response_status,
      firstResponseStatus,
    );
  const unknown = diagnostic({}, { firstClickCompleted: "PRIVATE", routeFailureObserved: 1 }, null);
  assert.equal(unknown.first_click_completed, null);
  assert.equal(unknown.route_failure_observed, null);
  assert.equal(unknown.route_failure_stage, "none");
});

const firstPhase = browserSource.slice(
  browserSource.indexOf('  phase = "discard_after_commit";'),
  browserSource.indexOf('  phase = "actual_browser_retry";'),
);
const catchStart = browserSource.indexOf("} catch {\n  report.failedPhase");
const catchBody = browserSource.slice(
  catchStart + "} catch {\n".length,
  browserSource.indexOf("} finally {", catchStart),
);
const logStart = browserSource.indexOf("  if (report.failureDiagnostic) {");
const logBlock = browserSource.slice(logStart, browserSource.indexOf("  if (browser)", logStart));
for (const [fault, code] of [
  ["click", "discard_click"],
  ["visibility", "discard_error_visibility"],
  ["route", "discard_route_integrity"],
  ["none", null],
]) {
  test(`actual first-discard assertions expose ${fault} without relaxing acceptance`, async () => {
    const logs = [];
    const state = {
      ...scalarState,
      firstClickCompleted: false,
      errorVisibilityPassed: false,
      routeFailureObserved: fault === "route",
      routeFailureStage: "cart_response_dispose",
    };
    const result = await runInNewContext(
      `(async () => {
      let phase; let failureStage = "outside_discard";
      const report = {checkpoints: {...committed}};
      const point = name => report.checkpoints[name] = true;
      const browserDiagnostic = state;
      const routeFailure = fault === "route" ? true : undefined;
      const process = {exitCode: 0};
      try { ${firstPhase} } catch { ${catchBody} }
      report.checkpoints.synthetic_fixture_cleanup = true;
      ${logBlock}
      return {exit: process.exitCode, summary: report.failureDiagnostic, checkpoints: report.checkpoints};
    })()`,
      {
        assert,
        state,
        committed,
        fault,
        cartFailureDiagnostic: diagnostic,
        add: {
          async click() {
            if (fault === "click") throw new Error("PRIVATE_COOKIE_BODY");
          },
        },
        page: {
          getByTestId(id) {
            assert.equal(id, "pdp-add-to-cart-error");
            return id;
          },
        },
        expect() {
          return {
            async toBeVisible() {
              if (fault === "visibility") throw new Error("PRIVATE_CUSTOMER");
            },
          };
        },
        console: {
          log(line) {
            logs.push(line);
          },
        },
      },
    );
    assert.equal(result.exit, code ? 1 : 0);
    assert.equal(result.checkpoints.actual_ui_uncertain_error, code ? undefined : true);
    assert.equal(logs.length, code ? 1 : 0);
    if (code) {
      assert.equal(result.summary.failure_stage, code);
      assert.equal(result.summary.first_click_completed, fault !== "click");
      assert.equal(result.summary.error_visibility_assertion_passed, fault === "route");
      assert.equal(result.summary.fixture_cleanup_recorded, true);
      assert.equal(
        logs[0],
        `cart-drill-browser-failure-summary: ${JSON.stringify(result.summary)}`,
      );
      assert.ok(!logs[0].includes("PRIVATE"));
      assert.ok(Buffer.byteLength(logs[0]) < 1024);
    }
  });
}
test("diagnostic scalar observations cannot substitute for any of the fifteen checkpoints", () => {
  const f = fixture();
  f.outcome.qualified = false;
  f.outcome.failureDiagnostic = diagnostic("discard_route_integrity", scalarState, committed);
  assert.throws(() => qualify(f.outcome, f.guard, sha));
  assert.equal(checkpoints.length, 15);
});

const routeSource = browserSource.slice(
  browserSource.indexOf('  await context.route("**/*", async (route) => {'),
  browserSource.indexOf('  phase = "establish_guest";'),
);
for (const [fault, code] of [
  ["status", "cart_response_status"],
  ["commit", "native_commit_check"],
  ["abort", "response_abort"],
  ["dispose", "cart_response_dispose"],
  ["none", "none"],
]) {
  test(`actual interception records bounded ${fault} stage without changing commit/discard gates`, async () => {
    let handler;
    const response = {
      status: () => (fault === "status" ? 503 : 200),
      async json() {
        return {
          cart_id: "synthetic-cart",
          items: [{ listing_id: "synthetic-listing", qty: 1, unit_price_ngwee: 10000 }],
          subtotal_ngwee: 10000,
        };
      },
      async dispose() {
        if (fault === "dispose") throw new Error("PRIVATE_RESPONSE");
      },
    };
    const route = {
      request: () => ({
        url: () => "http://127.0.0.1:8000/cart/items",
        resourceType: () => "fetch",
        method: () => "POST",
        async allHeaders() {
          return { "idempotency-key": "synthetic-key", cookie: "PRIVATE_COOKIE" };
        },
        postData: () =>
          JSON.stringify({ listing_id: "synthetic-listing", qty: 1, customer: "PRIVATE_BODY" }),
      }),
      fetch: async () => response,
      async abort(reason) {
        if (fault === "abort" && reason === "connectionreset") throw new Error("PRIVATE_ABORT");
      },
    };
    const result = await runInNewContext(
      `(async () => {
      let posts = 0, routeFailure, externalRequests = 0, firstKey, firstBody, listingId, price, bound = false;
      const cartId = "synthetic-cart", origin = "http://127.0.0.1:3000", api = "http://127.0.0.1:8000";
      const report = {blockedImages: 0, checkpoints: {}};
      const browserDiagnostic = {...scalarState, posts: 0, routeFailureObserved: false, firstResponseDisposed: false};
      const point = name => report.checkpoints[name] = true;
      ${routeSource}
      await invoke(route);
      if (fault === "dispose") await invoke(lateRoute);
      return {summary: cartFailureDiagnostic("discard_route_integrity", browserDiagnostic, report.checkpoints), routeFailure, bound};
    })()`,
      {
        assert,
        URL,
        scalarState,
        route,
        fault,
        cartFailureDiagnostic: diagnostic,
        lateRoute: {
          request: () => ({
            url: () => "http://127.0.0.1:3000/en/health",
            resourceType: () => "fetch",
            method: () => "GET",
          }),
          async fetch() {
            throw new Error("PRIVATE_LATE_REQUEST");
          },
          async abort() {},
        },
        context: {
          async route(pattern, callback) {
            assert.equal(pattern, "**/*");
            handler = callback;
          },
        },
        invoke: async (request) => handler(request),
        db(action) {
          assert.equal(action, "bind");
          return { price: 10000, guest: true, empty: true };
        },
        state(...args) {
          assert.deepEqual(args, ["committed_before_discard", 1, 1, 1, 10000, "synthetic-key"]);
          if (fault === "commit") throw new Error("PRIVATE_DATABASE");
        },
      },
    );
    assert.equal(result.summary.route_failure_stage, code);
    assert.equal(result.summary.route_failure_post, fault === "none" ? null : 1);
    assert.equal(result.routeFailure, fault === "none" ? undefined : true);
    assert.equal(result.summary.first_response_status, fault === "status" ? 503 : 200);
    assert.equal(result.summary.db_commit_recorded, !["status", "commit"].includes(fault));
    assert.equal(result.summary.response_discard_recorded, ["dispose", "none"].includes(fault));
    assert.equal(result.summary.first_response_disposed, fault === "none");
    assert.ok(!JSON.stringify(result.summary).includes("PRIVATE"));
  });
}
const finalStart = browserSource.indexOf("} finally {", catchStart) + "} finally {".length;
const finalBlock = browserSource.slice(
  finalStart,
  browserSource.indexOf("  if (browser)", finalStart),
);
for (const [name, primary, cleaned, raised] of [
  ["cleanup only", null, false, false],
  ["cleanup exception", null, false, true],
  ["primary retained on cleanup failure", "discard_click", false, false],
  ["cleanup succeeds after primary", "discard_error_visibility", true, false],
]) {
  test(`actual finalization emits bounded ${name} before browser close`, () => {
    const logs = [];
    const result = runInNewContext(
      `(() => {
      const report = {qualified: !primary, checkpoints: {...committed}};
      if (primary) report.failureDiagnostic = cartFailureDiagnostic(primary, scalarState, report.checkpoints);
      const process = {exitCode: primary ? 1 : 0}, bound = true, browserDiagnostic = scalarState;
      const point = name => report.checkpoints[name] = true;
      ${finalBlock}
      return {summary: report.failureDiagnostic, qualified: report.qualified, exit: process.exitCode};
    })()`,
      {
        assert,
        primary,
        scalarState,
        committed,
        cartFailureDiagnostic: diagnostic,
        db(action) {
          assert.equal(action, "cleanup");
          if (raised) throw new Error("PRIVATE_CLEANUP");
          return { cleaned };
        },
        console: {
          log(line) {
            logs.push(line);
          },
        },
      },
    );
    assert.equal(result.summary.failure_stage, primary ?? "fixture_cleanup");
    assert.equal(result.summary.fixture_cleanup_recorded, cleaned);
    assert.equal(result.qualified, false);
    assert.equal(result.exit, 1);
    assert.equal(logs.length, 1);
    assert.ok(!logs[0].includes("PRIVATE"));
  });
}
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
