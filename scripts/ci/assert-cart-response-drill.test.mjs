import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { runInNewContext } from "node:vm";

import "./cart-response-drill-lifecycle.test.mjs";

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
const navigationSource = browserSource.slice(
  browserSource.indexOf("let navigationAttempt = null;"),
  browserSource.indexOf("\nfunction observeBrowserDiagnostic("),
);
const discardWaitSource = browserSource.slice(
  browserSource.indexOf("async function waitForFirstDiscard("),
  browserSource.indexOf("\nfunction db("),
);
const waitForFirstDiscard = runInNewContext(`(${discardWaitSource})`, {
  assert,
  setTimeout,
  clearTimeout,
});
for (const value of [true, false, undefined, "true"]) {
  test(`discard completion accepts only true and clears its bound for ${String(value)}`, async () => {
    const timer = Symbol("discard-deadline");
    let cleared = 0;
    const wait = runInNewContext(`(${discardWaitSource})`, {
      assert,
      setTimeout(_callback, milliseconds) {
        assert.equal(milliseconds, 15_000);
        return timer;
      },
      clearTimeout(handle) {
        assert.equal(handle, timer);
        cleared += 1;
      },
    });
    if (value === true) await wait(Promise.resolve(value));
    else
      await assert.rejects(wait(Promise.resolve(value)), {
        name: "AssertionError",
      });
    assert.equal(cleared, 1);
  });
}
test("missing first interception fails at the existing action bound without retries", async () => {
  let deadline;
  let cleared = 0;
  let scheduled = 0;
  const wait = runInNewContext(`(${discardWaitSource})`, {
    assert,
    setTimeout(callback, milliseconds) {
      assert.equal(milliseconds, 15_000);
      scheduled += 1;
      deadline = callback;
      return 1;
    },
    clearTimeout(handle) {
      assert.equal(handle, 1);
      cleared += 1;
    },
  });
  const rejected = assert.rejects(wait(new Promise(() => {})), {
    name: "AssertionError",
  });
  deadline();
  await rejected;
  assert.equal(scheduled, 1);
  assert.equal(cleared, 1);
});
test("discard completion promise rejection stays failed and clears its bound", async () => {
  const privateError = new Error("SYNTHETIC_PRIVATE_VALUE");
  let cleared = 0;
  const wait = runInNewContext(`(${discardWaitSource})`, {
    assert,
    setTimeout: () => 1,
    clearTimeout(handle) {
      assert.equal(handle, 1);
      cleared += 1;
    },
  });
  await assert.rejects(wait(Promise.reject(privateError)), (error) => error === privateError);
  assert.equal(cleared, 1);
});
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
const committed = {
  committed_before_discard: true,
  one_response_discarded: true,
};
const plain = (value) => JSON.parse(JSON.stringify(value));

test("browser failure projection has fixed bounded scalar fields only", () => {
  const projected = plain(diagnostic("discard_route_integrity", scalarState, committed));
  assert.deepEqual(projected, {
    format: "cart_browser_failure_v3",
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
    navigation_response_status: null,
    guest_response_status: null,
    stock_response_status: null,
    latest_add_response_status: null,
    latest_add_response_post: null,
    external_requests_observed: null,
    blocked_images_observed: null,
    native_check_reached: "unclassified",
    nav_error: "unclassified",
    nav_ms: null,
    nav_status_seen: null,
    nav_attempt: null,
    nav_done: null,
    nav_request: null,
    nav_response: null,
    nav_main_frame_event: null,
    nav_page_dom_event: null,
    nav_page_load_event: null,
    nav_closed: null,
    nav_context_closed: null,
    nav_crash: null,
    nav_detached: null,
    nav_disconnected: null,
    nav_fetch: "unclassified",
    nav_request_error: "unclassified",
    nav_route_error: "unclassified",
    nav_observers: null,
  });
  assert.ok(
    Buffer.byteLength(JSON.stringify(Object.fromEntries(Object.entries(projected).slice(0, 21)))) <
      1024,
  );
  assert.ok(Buffer.byteLength(JSON.stringify(projected)) < 2048);
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
        firstDiscardPromise: Promise.resolve(true),
        waitForFirstDiscard,
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
      assert.ok(
        Buffer.byteLength(
          `cart-drill-browser-failure-summary: ${JSON.stringify(Object.fromEntries(Object.entries(result.summary).slice(0, 21)))}`,
        ) < 1024,
      );
      assert.ok(Buffer.byteLength(logs[0]) < 2048);
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

test("failed discard completion stops before UI and retains a bounded failure stage", async () => {
  let visibilityChecks = 0;
  const result = await runInNewContext(
    `(async () => {
    let phase, failureStage;
    const report = {checkpoints: {...committed}}, process = {exitCode: 0};
    const browserDiagnostic = {...scalarState, firstClickCompleted: false, errorVisibilityPassed: false};
    const routeFailure = true;
    const point = name => report.checkpoints[name] = true;
    try { ${firstPhase} } catch { ${catchBody} }
    return {exit: process.exitCode, report};
  })()`,
    {
      assert,
      committed,
      scalarState,
      cartFailureDiagnostic: diagnostic,
      firstDiscardPromise: Promise.resolve(false),
      waitForFirstDiscard,
      add: { async click() {} },
      page: { getByTestId: () => "pdp-add-to-cart-error" },
      expect: () => ({
        async toBeVisible() {
          visibilityChecks += 1;
        },
      }),
    },
  );
  assert.equal(visibilityChecks, 0);
  assert.equal(result.exit, 1);
  assert.equal(result.report.failedPhase, "discard_after_commit");
  assert.equal(result.report.failureDiagnostic.failure_stage, "discard_completion");
  assert.equal(result.report.failureDiagnostic.error_visibility_assertion_passed, false);
  assert.equal(result.report.checkpoints.actual_ui_uncertain_error, undefined);
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
    const completionOutcomes = [];
    const response = {
      status: () => (fault === "status" ? 503 : 200),
      async json() {
        return {
          cart_id: "synthetic-cart",
          items: [
            {
              listing_id: "synthetic-listing",
              qty: 1,
              unit_price_ngwee: 10000,
            },
          ],
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
          return {
            "idempotency-key": "synthetic-key",
            cookie: "PRIVATE_COOKIE",
          };
        },
        postData: () =>
          JSON.stringify({
            listing_id: "synthetic-listing",
            qty: 1,
            customer: "PRIVATE_BODY",
          }),
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
      ${navigationSource}
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
        finishFirstDiscard(value) {
          completionOutcomes.push(value);
        },
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
    assert.deepEqual(completionOutcomes, [fault === "none"]);
    assert.ok(!JSON.stringify(result.summary).includes("PRIVATE"));
  });
}
test("first visibility assertion waits for actual commit, abort and response disposal", async () => {
  let handler, releaseResponse, routeRun;
  let visibilityChecks = 0;
  let aborted = false,
    disposed = false;
  const fetchResponse = new Promise((resolve) => {
    releaseResponse = resolve;
  });
  let finishFirstDiscard;
  const completion = new Promise((resolve) => {
    finishFirstDiscard = resolve;
  });
  const response = {
    status: () => 200,
    async json() {
      return {
        cart_id: "synthetic-cart",
        items: [{ listing_id: "synthetic-listing", qty: 1, unit_price_ngwee: 10000 }],
        subtotal_ngwee: 10000,
      };
    },
    async dispose() {
      disposed = true;
    },
  };
  const route = {
    request: () => ({
      url: () => "http://127.0.0.1:8000/cart/items",
      resourceType: () => "fetch",
      method: () => "POST",
      async allHeaders() {
        return {
          "idempotency-key": "synthetic-key",
          cookie: "synthetic-cookie",
        };
      },
      postData: () => JSON.stringify({ listing_id: "synthetic-listing", qty: 1 }),
    }),
    fetch: () => fetchResponse,
    async abort(reason) {
      assert.equal(reason, "connectionreset");
      aborted = true;
    },
  };
  const execution = runInNewContext(
    `(async () => {
    let phase, failureStage, posts = 0, routeFailure, externalRequests = 0;
    let firstKey, firstBody, listingId, price, bound = false;
    const cartId = "synthetic-cart", origin = "http://127.0.0.1:3000", api = "http://127.0.0.1:8000";
    const report = {blockedImages: 0, checkpoints: {}};
    const browserDiagnostic = {...scalarState, posts: 0, routeFailureObserved: false, firstResponseDisposed: false};
    const point = name => report.checkpoints[name] = true;
    ${navigationSource}
    ${routeSource}
    ${firstPhase}
    return report;
  })()`,
    {
      assert,
      URL,
      scalarState,
      firstDiscardPromise: completion,
      finishFirstDiscard,
      waitForFirstDiscard,
      context: {
        async route(_pattern, callback) {
          handler = callback;
        },
      },
      add: {
        async click() {
          routeRun = handler(route);
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
          async toBeVisible(...options) {
            visibilityChecks += 1;
            assert.deepEqual(options, []);
            assert.equal(
              aborted && disposed,
              true,
              "UI wait began before real response loss completed",
            );
          },
        };
      },
      db(action) {
        assert.equal(action, "bind");
        return { price: 10000, guest: true, empty: true };
      },
      state(...args) {
        assert.deepEqual(args, ["committed_before_discard", 1, 1, 1, 10000, "synthetic-key"]);
      },
    },
  );
  const settled = execution.then(
    (value) => ({ value }),
    (error) => ({ error }),
  );
  try {
    for (let i = 0; i < 12; i += 1) await Promise.resolve();
    assert.equal(
      visibilityChecks,
      0,
      "pending interception must not consume the visible-error wait",
    );
    assert.equal(aborted, false);
    assert.equal(disposed, false);
    releaseResponse(response);
    const result = await settled;
    assert.equal(result.error, undefined);
    assert.equal(visibilityChecks, 1);
    assert.deepEqual(
      { ...result.value.checkpoints },
      {
        committed_before_discard: true,
        one_response_discarded: true,
        actual_ui_uncertain_error: true,
      },
    );
  } finally {
    releaseResponse(response);
    await routeRun;
    await settled;
  }
});

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
const journeySetup = browserSource.slice(
  browserSource.indexOf("const browserDiagnostic ="),
  browserSource.indexOf("\nasync function waitForFirstDiscard("),
);
const journeyBody = browserSource.slice(
  browserSource.indexOf('\ntry {\n  failureStage = "local_flag_guard";') + "\ntry {\n".length,
  catchStart,
);
const nativeStateSource = browserSource.slice(
  browserSource.indexOf("function state("),
  browserSource.indexOf("\nconst money ="),
);
const moneySource = browserSource.slice(
  browserSource.indexOf("const money ="),
  browserSource.indexOf('\n\ntry {\n  failureStage = "local_flag_guard";'),
);
const completeFinally = browserSource.slice(finalStart, browserSource.lastIndexOf("\n}"));

async function offlineJourney(fault = null, scenario = {}) {
  const control = {},
    logs = [],
    calls = [];
  const privateError = new Error("PRIVATE_COOKIE_TOKEN_BODY_URL");
  let routeHandler,
    consoleHandler,
    clicks = 0,
    injected = false;
  const ledger = {
    qty: 0,
    claims: 0,
    events: 0,
    stored_price: 10000,
    key_committed: true,
  };
  const trip = () => {
    let code = control.stage();
    if (code === "stock_native_state") code = `stock_${control.native()}`;
    calls.push(code);
    if (code === fault && !injected) {
      injected = true;
      throw privateError;
    }
  };
  const checkedAssert = new Proxy(assert, {
    get(target, key) {
      const value = target[key];
      return typeof value === "function"
        ? (...args) => {
            trip();
            // Host fixtures cross the VM realm; compare their JSON values as the driver does in one realm.
            return value(...(key === "deepEqual" ? args.map(plain) : args));
          }
        : value;
    },
  });
  const response = (payload = {}) => ({
    status: () => 200,
    headers: () => ({}),
    json: async () => payload,
    dispose: async () => {},
  });
  function requestRoute(url, method = "GET", type = "fetch", ordinal = 0) {
    return {
      request: () => ({
        url: () => url,
        method: () => method,
        resourceType: () => type,
        allHeaders: async () => ({
          "idempotency-key": ordinal === 3 ? "fresh-key" : "first-key",
          cookie: "PRIVATE_COOKIE",
        }),
        postData: () => JSON.stringify({ listing_id: "synthetic-listing", qty: 1 }),
      }),
      async fetch() {
        if (!ordinal) return response();
        Object.assign(ledger, {
          qty: ordinal === 3 ? 2 : 1,
          claims: ordinal === 3 ? 2 : 1,
          events: ordinal === 3 ? 2 : 1,
          stored_price: ordinal === 3 ? 10100 : 10000,
        });
        return response({
          cart_id: "synthetic-cart",
          items: [
            {
              listing_id: "synthetic-listing",
              qty: ledger.qty,
              unit_price_ngwee: ledger.stored_price,
            },
          ],
          subtotal_ngwee: ledger.qty * ledger.stored_price,
        });
      },
      abort: async () => {},
      fulfill: async () => {},
    };
  }
  const locator = (id) => ({
    id,
    async click() {
      trip();
      if (id === "pdp-add-to-cart") {
        clicks += 1;
        await routeHandler(
          requestRoute("http://127.0.0.1:8000/cart/items", "POST", "fetch", clicks),
        );
      }
    },
    async waitFor() {
      trip();
    },
    async selectOption() {
      trip();
    },
  });
  const page = {
    on(event, callback) {
      if (event === "console") {
        trip();
        consoleHandler = callback;
      }
    },
    off() {},
    setDefaultTimeout(value) {
      assert.equal(value, 15000);
    },
    async goto(url) {
      trip();
      await routeHandler(requestRoute(url, "GET", "document"));
    },
    async evaluate(fn, url) {
      trip();
      return fn(url);
    },
    getByTestId: locator,
  };
  const context = {
    async newPage() {
      trip();
      return page;
    },
    async routeWebSocket() {
      trip();
    },
    async route(_pattern, callback) {
      trip();
      routeHandler = callback;
    },
    async cookies() {
      trip();
      return [{ name: "vergeo_guest_cart", value: "PRIVATE_COOKIE" }];
    },
  };
  const browser = {
    async newContext() {
      trip();
      return context;
    },
    async close() {},
  };
  let written;
  const result = await runInNewContext(
    `(async () => {
    const origin = "http://127.0.0.1:3000", api = "http://127.0.0.1:8000";
    const report = {version: 1, qualified: false, checkpoints: {}, stages: [], blockedImages: 0};
    let browser, bound = false, phase = "guard", failureStage = "outside_discard";
    const deadline = undefined, output = "synthetic-outcome";
    const point = name => report.checkpoints[name] = true;
    ${journeySetup}
    control.stage = () => failureStage;
    control.native = () => browserDiagnostic.nativeCheck;
    ${nativeStateSource}
    ${moneySource}
    try { ${journeyBody} } catch { ${catchBody} } finally { ${completeFinally} }
    return {report, exit: process.exitCode || 0};
  })()`,
    {
      assert: checkedAssert,
      URL,
      control,
      cartFailureDiagnostic: diagnostic,
      waitForFirstDiscard: async (completion) => {
        trip();
        return waitForFirstDiscard(completion);
      },
      process: {
        env: {
          CART_DRILL_LOCAL: "1",
          CART_DRILL_UID: "123",
          SUPABASE_URL: "http://127.0.0.1:54321",
          SUPABASE_DB_URL: "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
        },
        getuid: () => 123,
        pid: 10,
        exitCode: 0,
      },
      chromium: {
        async launch() {
          trip();
          return browser;
        },
      },
      expect(value) {
        return {
          async toBeEnabled() {
            trip();
          },
          async toBeVisible() {
            trip();
          },
          async toHaveText(text) {
            trip();
            assert.ok(typeof text === "string");
          },
          async toContainText(text) {
            trip();
            assert.ok(typeof text === "string");
          },
        };
      },
      async fetch(url, options = {}) {
        trip();
        await routeHandler(requestRoute(url, options.method || "GET"));
        const active = !scenario.stockOnly || url.endsWith("/revalidate");
        return {
          status: active ? (scenario.httpStatus ?? 200) : 200,
          get ok() {
            trip();
            return active && scenario.httpStatus ? scenario.httpStatus < 400 : true;
          },
          async json() {
            trip();
            if (active && scenario.invalidJson) throw privateError;
            if (active && scenario.invalidShape) return null;
            return url.endsWith("/revalidate")
              ? {
                  notices: [
                    {
                      listing_id: "synthetic-listing",
                      kind: "qty_reduced",
                      requested_qty: 2,
                      available_qty: 1,
                    },
                  ],
                }
              : { cart_id: "synthetic-cart", items: [] };
          },
        };
      },
      db(action) {
        if (action === "observe") {
          trip();
          return { ...ledger };
        }
        if (action === "bind") return { price: 10000, guest: true, empty: true };
        if (action === "cleanup") {
          if (fault === "fixture_cleanup") throw privateError;
          return { cleaned: true };
        }
        trip();
        return {};
      },
      execFileSync(command) {
        trip();
        assert.equal(command, "ps");
        return "123 10 1 node\n123 11 10 chrome";
      },
      writeFileSync(_path, bytes) {
        written = JSON.parse(bytes);
      },
      clearTimeout,
      console: {
        debug(token) {
          if (scenario.consoleUnavailable) throw privateError;
          consoleHandler({ type: () => "debug", text: () => token });
        },
        log(line) {
          logs.push(line);
        },
      },
    },
  );
  assert.deepEqual(plain(result.report), written);
  assert.ok(!JSON.stringify(written).includes("PRIVATE"));
  return { ...result, report: plain(result.report), logs, calls, clicks };
}

test("actual entire offline journey still qualifies every original checkpoint", async () => {
  const result = await offlineJourney();
  assert.equal(result.exit, 0, JSON.stringify(result.report.failureDiagnostic));
  assert.equal(result.clicks, 3);
  const { guard } = fixture();
  assert.equal(qualify(result.report, guard, sha).qualified, true);
  assert.equal(result.report.failureDiagnostic, undefined);
  assert.equal(
    result.logs.filter((line) => line.startsWith("cart-drill-browser-failure-summary:")).length,
    0,
  );
});
const journeyFaults = [
  "local_flag_guard",
  "uid_guard",
  "api_origin_guard",
  "database_origin_guard",
  "browser_launch",
  "browser_context",
  "browser_page",
  "browser_console_setup",
  "websocket_route_setup",
  "http_route_setup",
  "guest_navigation",
  "guest_bootstrap_dispatch",
  "guest_bootstrap_fetch",
  "guest_bootstrap_http",
  "guest_bootstrap_json",
  "guest_cart_identity",
  "guest_empty_cart",
  "guest_cookie_presence",
  "guest_pickup_selection",
  "guest_add_enabled",
  "discard_click",
  "discard_completion",
  "discard_error_visibility",
  "discard_route_integrity",
  "retry_click",
  "retry_success_visibility",
  "retry_subtotal",
  "retry_quantity",
  "retry_drawer_close",
  "price_fixture",
  "price_navigation",
  "price_notice_visibility",
  "price_notice_previous",
  "price_notice_current",
  "price_subtotal",
  "price_quantity",
  "fresh_navigation",
  "fresh_pickup_selection",
  "fresh_add_enabled",
  "fresh_click",
  "fresh_success_visibility",
  "fresh_subtotal",
  "fresh_quantity",
  "stock_fixture",
  "stock_revalidation_dispatch",
  "stock_revalidation_fetch",
  "stock_revalidation_http",
  "stock_revalidation_json",
  "stock_notice_presence",
  "stock_requested_quantity",
  "stock_available_quantity",
  "stock_native_observe",
  "stock_native_quantity",
  "stock_native_claims",
  "stock_native_events",
  "stock_native_price",
  "stock_restore",
  "final_add_count",
  "final_external_count",
  "final_route_integrity",
  "process_snapshot",
  "browser_child_presence",
  "browser_child_uid",
  "fixture_cleanup",
];
for (const fault of journeyFaults) {
  test(`actual journey diagnoses ${fault} and stays failed with original cleanup`, async () => {
    const result = await offlineJourney(fault);
    assert.equal(result.exit, 1);
    assert.equal(result.report.failureDiagnostic.failure_stage, fault);
    assert.equal(
      result.logs.filter((line) => line.startsWith("cart-drill-browser-failure-summary:")).length,
      1,
    );
    assert.ok(Buffer.byteLength(JSON.stringify(result.report.failureDiagnostic)) < 2048);
    const { guard } = fixture();
    assert.throws(() => qualify(result.report, guard, sha));
    if (
      fault.startsWith("guest_") ||
      fault.endsWith("_guard") ||
      (fault.startsWith("browser_") && !fault.startsWith("browser_child"))
    )
      assert.equal(result.clicks, 0);
    if (result.report.checkpoints.committed_before_discard)
      assert.equal(
        result.report.checkpoints.synthetic_fixture_cleanup,
        fault === "fixture_cleanup" ? undefined : true,
      );
  });
}
for (const fault of ["guest_pickup_probe", "fresh_pickup_probe"]) {
  test(`original optional ${fault} rejection remains nonfatal`, async () => {
    const result = await offlineJourney(fault);
    assert.equal(result.exit, 0);
    assert.equal(result.report.qualified, true);
    assert.ok(result.calls.includes(fault));
  });
}

for (const [name, scenario, code] of [
  ["guest HTTP rejection", { httpStatus: 503 }, "guest_bootstrap_http"],
  ["guest invalid JSON", { invalidJson: true }, "guest_bootstrap_json"],
  ["guest null JSON", { invalidShape: true }, "guest_cart_identity"],
  ["stock HTTP rejection", { stockOnly: true, httpStatus: 503 }, "stock_revalidation_http"],
  ["stock invalid JSON", { stockOnly: true, invalidJson: true }, "stock_revalidation_json"],
  ["stock null JSON", { stockOnly: true, invalidShape: true }, "stock_notice_find"],
]) {
  test(`original ${name} fails with its fixed stage and no private error text`, async () => {
    const result = await offlineJourney(null, scenario);
    assert.equal(result.exit, 1);
    assert.equal(result.report.failureDiagnostic.failure_stage, code);
    assert.ok(!JSON.stringify(result).includes("PRIVATE"));
    if (scenario.httpStatus)
      assert.equal(
        result.report.failureDiagnostic[
          scenario.stockOnly ? "stock_response_status" : "guest_response_status"
        ],
        503,
      );
    if (scenario.stockOnly) assert.equal(result.report.checkpoints.synthetic_fixture_cleanup, true);
  });
}
test("unavailable console diagnostics leave the entire original success journey intact", async () => {
  const result = await offlineJourney(null, { consoleUnavailable: true });
  const { guard } = fixture();
  assert.equal(qualify(result.report, guard, sha).qualified, true);
  assert.equal(result.report.failureDiagnostic, undefined);
});
test("unavailable console diagnostics use the fixed dispatch fallback on browser JSON failure", async () => {
  const result = await offlineJourney(null, {
    consoleUnavailable: true,
    invalidJson: true,
  });
  assert.equal(result.report.failureDiagnostic.failure_stage, "guest_bootstrap_dispatch");
  assert.equal(result.exit, 1);
});

function observerFixture(stage) {
  return runInNewContext(
    `(() => {
    let failureStage = stage;
    ${journeySetup}
    return {emit: observeBrowserDiagnostic, result: () => ({stage: failureStage, state: browserDiagnostic})};
  })()`,
    { stage },
  );
}
for (const group of ["guest", "stock"]) {
  const prefix = group === "guest" ? "guest_bootstrap" : "stock_revalidation";
  test(`browser ${group} observer accepts only exact active fixed stages and HTTP bounds`, () => {
    const observed = observerFixture(`${prefix}_dispatch`);
    for (const step of ["fetch", "http", "json"]) {
      observed.emit({
        type: () => "debug",
        text: () => `cart-drill-step:${prefix}_${step}`,
      });
      assert.equal(observed.result().stage, `${prefix}_${step}`);
    }
    for (const status of [100, 200, 503, 599]) {
      observed.emit({
        type: () => "debug",
        text: () => `cart-drill-status:${group}:${status}`,
      });
      assert.equal(observed.result().state[`${group}Status`], status);
    }
  });
  test(`browser ${group} observer ignores malformed, late, private and cross-operation input`, () => {
    const observed = observerFixture(`${prefix}_dispatch`);
    const original = plain(observed.result());
    const otherPrefix = group === "guest" ? "stock_revalidation" : "guest_bootstrap";
    for (const text of [
      "PRIVATE_COOKIE_BODY_URL",
      "PRIVATE".repeat(1000),
      null,
      503,
      {},
      Symbol("PRIVATE"),
      `cart-drill-step:${prefix}_json PRIVATE`,
      `cart-drill-step:${otherPrefix}_json`,
      `cart-drill-status:${group}:99`,
      `cart-drill-status:${group}:600`,
      `cart-drill-status:${group}:200.5`,
      `cart-drill-status:${group}:0200`,
      `cart-drill-status:${group}:200 PRIVATE`,
      `cart-drill-status:${group === "guest" ? "stock" : "guest"}:503`,
    ])
      observed.emit({ type: () => "debug", text: () => text });
    observed.emit({
      type: () => "log",
      text: () => `cart-drill-step:${prefix}_json`,
    });
    observed.emit({
      type() {
        throw new Error("PRIVATE");
      },
    });
    observed.emit({
      type: () => "debug",
      text() {
        throw new Error("PRIVATE");
      },
    });
    observed.emit(null);
    assert.deepEqual(plain(observed.result()), original);
    for (const stage of [
      "guest_cart_identity",
      "retry_click",
      "stock_notice_find",
      "outside_discard",
    ]) {
      const late = observerFixture(stage),
        before = plain(late.result());
      late.emit({
        type: () => "debug",
        text: () => `cart-drill-step:${prefix}_json`,
      });
      late.emit({
        type: () => "debug",
        text: () => `cart-drill-status:${group}:503`,
      });
      assert.deepEqual(plain(late.result()), before);
    }
  });
}
for (const [source, field, low, high] of [
  ["navigationStatus", "navigation_response_status", 100, 599],
  ["guestStatus", "guest_response_status", 100, 599],
  ["stockStatus", "stock_response_status", 100, 599],
  ["latestAddStatus", "latest_add_response_status", 100, 599],
  ["latestAddPost", "latest_add_response_post", 0, 1000],
  ["externalRequests", "external_requests_observed", 0, 1000],
  ["blockedImages", "blocked_images_observed", 0, 1000],
]) {
  test(`expanded diagnostic ${field} is bounded, own-data-only and never coerces private input`, () => {
    for (const value of [low, high])
      assert.equal(diagnostic("guest_navigation", { [source]: value }, {})[field], value);
    for (const value of [
      low - 1,
      high + 1,
      1.5,
      Infinity,
      NaN,
      "PRIVATE",
      3n,
      Symbol("PRIVATE"),
      {
        toJSON() {
          throw new Error("PRIVATE");
        },
      },
    ])
      assert.equal(diagnostic("guest_navigation", { [source]: value }, {})[field], null);
    let accessed = false;
    const input = Object.defineProperty({}, source, {
      get() {
        accessed = true;
        throw new Error("PRIVATE");
      },
    });
    assert.equal(diagnostic("guest_navigation", input, {})[field], null);
    assert.equal(accessed, false);
    assert.equal(
      diagnostic("guest_navigation", Object.create({ [source]: high }), {})[field],
      null,
    );
  });
}
test("native diagnostic cannot echo unknown stages, IDs or arbitrary serializers", () => {
  for (const value of ["PRIVATE_COOKIE_BODY_URL", {}, Symbol("PRIVATE"), null]) {
    const result = diagnostic("stock_native_state", { nativeCheck: value, key: "PRIVATE" }, {});
    assert.equal(result.failure_stage, "stock_native_state");
    assert.equal(result.native_check_reached, "unclassified");
    assert.equal(Object.keys(result).length, 40);
    assert.ok(!JSON.stringify(result).includes("PRIVATE"));
  }
  for (const native of ["observe", "quantity", "claims", "events", "price", "key"]) {
    const result = diagnostic("stock_native_state", { nativeCheck: `native_${native}` }, {});
    assert.equal(result.failure_stage, `stock_native_${native}`);
  }
});

async function routeFailureCase(config) {
  let handler;
  const aborts = [],
    completions = [];
  const ordinal = config.ordinal || 1;
  const body = JSON.stringify({
    listing_id: "synthetic-listing",
    qty: config.qty ?? 1,
  });
  const resultBody = {
    cart_id: "synthetic-cart",
    items: [
      {
        listing_id: "synthetic-listing",
        qty: ordinal === 3 ? 2 : 1,
        unit_price_ngwee: ordinal === 3 ? 10100 : 10000,
      },
    ],
    subtotal_ngwee: ordinal === 3 ? 20200 : 10000,
  };
  if (config.cartId) resultBody.cart_id = "PRIVATE_WRONG_ID";
  if (config.itemsMalformed) resultBody.items = null;
  if (config.lineMissing) resultBody.items = [];
  if (config.lineQuantity) resultBody.items[0].qty = 99;
  if (config.linePrice) resultBody.items[0].unit_price_ngwee = 99;
  if (config.subtotal) resultBody.subtotal_ngwee = 99;
  const privateError = new Error("PRIVATE_COOKIE_BODY_URL_ERROR");
  const response = {
    status: () => config.status || 200,
    headers: () => ({
      location: config.redirect ? "https://private.invalid/PRIVATE" : undefined,
    }),
    async json() {
      if (config.json) throw privateError;
      return resultBody;
    },
    async dispose() {
      if (config.dispose) throw privateError;
    },
  };
  const route = {
    request: () => ({
      url: () => config.url || "http://127.0.0.1:8000/cart/items",
      resourceType: () => config.type || "fetch",
      method: () => config.method || "POST",
      async allHeaders() {
        if (config.headers) throw privateError;
        return {
          "idempotency-key":
            config.key === null
              ? undefined
              : config.key || (ordinal === 3 ? "fresh-key" : "first-key"),
          cookie: config.cookie === false ? undefined : "PRIVATE_COOKIE",
        };
      },
      postData() {
        if (config.body) throw privateError;
        return config.invalidJson
          ? "PRIVATE_INVALID_JSON"
          : config.changedBody
            ? body.replace("synthetic-listing", "synthetic-other")
            : body;
      },
    }),
    async fetch() {
      if (config.fetch) throw privateError;
      return response;
    },
    async abort(reason) {
      aborts.push(reason);
      if (config.abort && reason === "connectionreset") throw privateError;
    },
    async fulfill() {
      if (config.fulfill) throw privateError;
    },
  };
  const result = await runInNewContext(
    `(async () => {
    let posts = ordinal - 1, routeFailure, externalRequests = 0, bound = false;
    let firstKey = "first-key", firstBody = originalBody, listingId = "synthetic-listing", price = 10000;
    const cartId = "synthetic-cart", origin = "http://127.0.0.1:3000", api = "http://127.0.0.1:8000";
    const report = {blockedImages: 0, checkpoints: {}, stages: []};
    const browserDiagnostic = {posts: 0, routeFailureObserved: false, firstResponseDisposed: false, nativeCheck: "none"};
    const point = name => report.checkpoints[name] = true;
    ${nativeStateSource}
    ${navigationSource}
    ${routeSource}
    await invoke(route);
    return {summary: cartFailureDiagnostic("discard_route_integrity", browserDiagnostic, report.checkpoints), bound, routeFailure};
  })()`,
    {
      ordinal,
      originalBody: JSON.stringify({ listing_id: "synthetic-listing", qty: 1 }),
      assert,
      URL,
      route,
      cartFailureDiagnostic: diagnostic,
      context: {
        async route(_pattern, callback) {
          handler = callback;
        },
      },
      invoke: (request) => handler(request),
      finishFirstDiscard: (value) => completions.push(value),
      db(action) {
        if (action === "bind") {
          if (config.bind) throw privateError;
          return {
            price: 10000,
            guest: config.guest !== false,
            empty: config.empty !== false,
          };
        }
        assert.equal(action, "observe");
        if (config.native === "observe") throw privateError;
        return {
          qty: config.native === "quantity" ? 99 : ordinal === 3 ? 2 : 1,
          claims: config.native === "claims" ? 99 : ordinal === 3 ? 2 : 1,
          events: config.native === "events" ? 99 : ordinal === 3 ? 2 : 1,
          stored_price: config.native === "price" ? 99 : ordinal === 3 ? 10100 : 10000,
          key_committed: config.native !== "key",
        };
      },
    },
  );
  assert.equal(result.routeFailure, true);
  assert.ok(!JSON.stringify(result.summary).includes("PRIVATE"));
  assert.ok(Buffer.byteLength(JSON.stringify(result.summary)) < 2048);
  return { summary: plain(result.summary), aborts, completions };
}
for (const [code, config] of [
  ["request_origin", { url: "https://private.invalid/PRIVATE" }],
  ["request_auth_path", { url: "http://127.0.0.1:8000/auth/PRIVATE" }],
  ["image_fulfil", { type: "image", fulfill: true }],
  ["cart_request_headers", { headers: true }],
  ["cart_key_presence", { key: null }],
  ["cart_cookie_presence", { cookie: false }],
  ["cart_request_body", { body: true }],
  ["cart_request_json", { invalidJson: true }],
  ["cart_request_quantity", { qty: 99 }],
  ["fixture_bind", { bind: true }],
  ["fixture_guest", { guest: false }],
  ["fixture_empty", { empty: false }],
  ["retry_key", { ordinal: 2, key: "wrong-key" }],
  ["retry_body", { ordinal: 2, changedBody: true }],
  ["fresh_add_count", { ordinal: 4 }],
  ["fresh_key", { ordinal: 3, key: "first-key" }],
  ["fresh_body", { ordinal: 3, changedBody: true }],
  ["cart_response_fetch", { fetch: true }],
  ["cart_response_status", { status: 503 }],
  ["cart_response_body", { json: true }],
  ["cart_identity", { cartId: true }],
  ["cart_line_find", { itemsMalformed: true }],
  ["cart_line_presence", { lineMissing: true }],
  ["cart_line_quantity", { lineQuantity: true }],
  ["cart_line_price", { linePrice: true }],
  ["cart_subtotal", { subtotal: true }],
  ...["observe", "quantity", "claims", "events", "price", "key"].map((native) => [
    `native_${native}`,
    { native },
  ]),
  ["response_abort", { abort: true }],
  ["cart_response_fulfil", { ordinal: 2, fulfill: true }],
  ["cart_response_dispose", { dispose: true }],
  ["other_response_fetch", { url: "http://127.0.0.1:3000/en", method: "GET", fetch: true }],
  ["other_redirect_origin", { url: "http://127.0.0.1:3000/en", method: "GET", redirect: true }],
  ["other_response_fulfil", { url: "http://127.0.0.1:3000/en", method: "GET", fulfill: true }],
  ["other_response_dispose", { url: "http://127.0.0.1:3000/en", method: "GET", dispose: true }],
]) {
  test(`actual route failure ${code} retains the original fail-closed boundary`, async () => {
    const result = await routeFailureCase(config);
    assert.equal(result.summary.route_failure_stage, code);
    assert.equal(result.summary.route_failure_observed, true);
    assert.equal(result.aborts.at(-1), "blockedbyclient");
    assert.equal(result.summary.external_requests_observed, code === "request_origin" ? 1 : 0);
    if (result.summary.route_failure_post === 1) assert.deepEqual(result.completions, [false]);
    if (config.status) assert.equal(result.summary.latest_add_response_status, 503);
  });
}

for (const [url, method] of [
  ["http://127.0.0.1:8000/cart", "GET"],
  ["http://127.0.0.1:8000/cart/revalidate", "POST"],
]) {
  test(`background route ${method} cannot overwrite explicit operation status`, async () => {
    const result = await routeFailureCase({
      url,
      method,
      status: 503,
      fulfill: true,
    });
    assert.equal(result.summary.route_failure_stage, "other_response_fulfil");
    assert.equal(result.summary.guest_response_status, null);
    assert.equal(result.summary.stock_response_status, null);
  });
}

function navigationFixture(options = {}) {
  let clock = options.start ?? 10,
    closed = false,
    connected = true;
  const pageEvents = new Map(),
    browserEvents = new Map(),
    contextEvents = new Map();
  const target =
    options.callSite === 1
      ? "http://127.0.0.1:3000/en/cart"
      : "http://127.0.0.1:3000/en/p/smartphone-x1";
  const frame = {};
  const subscribe = (map) => (event, handler) => {
    const list = map.get(event) ?? [];
    list.push(handler);
    map.set(event, list);
  };
  const remove = (map) => (event, handler) =>
    map.set(
      event,
      (map.get(event) ?? []).filter((item) => item !== handler),
    );
  const page = {
    on: options.onError
      ? () => {
          throw new Error("PRIVATE_OBSERVER_ERROR");
        }
      : subscribe(pageEvents),
    off: remove(pageEvents),
    context: () => ({ on: subscribe(contextEvents), off: remove(contextEvents) }),
    mainFrame: () => frame,
    isClosed: () => closed,
    async goto(...args) {
      assert.equal(args.length, 1);
      const [url] = args;
      assert.equal(url, target);
      if (options.goto) return options.goto(api);
    },
  };
  const browser = {
    on: subscribe(browserEvents),
    off: remove(browserEvents),
    isConnected: () => connected,
  };
  const snippets = [
    ...browserSource.matchAll(
      /^  beginNavigation\(page, browser, `[^`]+`\);\n  try \{\n    await page\.goto\(`[^`]+`\);\n    settleNavigation\(undefined, false\);\n  \} catch \(error\) \{\n    settleNavigation\(error, true\);\n    throw error;\n  \}/gm,
    ),
  ].map((match) => match[0]);
  assert.equal(snippets.length, 3);
  const code = snippets[options.callSite ?? 0];
  let api;
  const actual = runInNewContext(
    `(() => {
    let failureStage = "guest_navigation";
    const origin = "http://127.0.0.1:3000";
    ${journeySetup}
    return {
      begin: target => beginNavigation(page, browser, target),
      settle: (error, failed) => settleNavigation(error, failed),
      route: noteNavigationRoute,
      classify: navigationErrorClass,
      makeClosedTarget: reason => new (class TargetClosedError extends Error { constructor(cause) {super(cause || "Target page, context or browser has been closed");} })(reason),
      snapshot: () => cartFailureDiagnostic(failureStage, browserDiagnostic, {}),
      async originalGoto() {try { ${code} return {resolved: true}; } catch(error) {return {resolved: false, error};}},
    };
  })()`,
    {
      page,
      browser,
      performance: {
        now: () => {
          if (options.clockError) throw new Error("PRIVATE_CLOCK_ERROR");
          return clock;
        },
      },
      cartFailureDiagnostic: diagnostic,
    },
  );
  api = {
    ...actual,
    target,
    frame,
    clock: (value) => (clock = value),
    closed: (value) => (closed = value),
    connected: (value) => (connected = value),
    emit(event, ...args) {
      for (const fn of [...(pageEvents.get(event) ?? [])]) fn(...args);
    },
    closeContext() {
      for (const fn of [...(contextEvents.get("close") ?? [])]) fn();
    },
    disconnect() {
      connected = false;
      for (const fn of [...(browserEvents.get("disconnected") ?? [])]) fn();
    },
    handlers: (event) => [...(pageEvents.get(event) ?? [])],
    request(url = target, overrides = {}) {
      return {
        url: () => url,
        isNavigationRequest: () => true,
        frame: () => frame,
        redirectedFrom: () => null,
        failure: () => ({ errorText: "net::ERR_CONNECTION_REFUSED PRIVATE_URL_COOKIE" }),
        ...overrides,
      };
    },
  };
  return api;
}
for (const [input, expected] of [
  [{ name: "TimeoutError", message: "PRIVATE" }, "timeout"],
  ...[
    ["ERR_CONNECTION_REFUSED", "connection_refused"],
    ["ERR_CONNECTION_RESET", "connection_reset"],
    ["ERR_NAME_NOT_RESOLVED", "name_unresolved"],
    ["ERR_TIMED_OUT", "network_timeout"],
    ["ERR_ADDRESS_UNREACHABLE", "network_unreachable"],
    ["ERR_ABORTED", "aborted"],
    ["ERR_FAILED", "network_failed"],
  ].map(([code, expected]) => [
    { message: `page.goto: net::${code} at http://PRIVATE.invalid/PRIVATE?token=PRIVATE` },
    expected,
  ]),
  ...[
    ["ECONNREFUSED", "connection_refused"],
    ["ECONNRESET", "connection_reset"],
    ["ETIMEDOUT", "network_timeout"],
    ["ENOTFOUND", "name_unresolved"],
    ["EHOSTUNREACH", "network_unreachable"],
    ["ENETUNREACH", "network_unreachable"],
  ].map(([code, expected]) => [{ code, message: "PRIVATE" }, expected]),
  [{ message: "route.fetch: connect ECONNREFUSED PRIVATE_ADDRESS" }, "connection_refused"],
  [{ message: "apiRequestContext.fetch: getaddrinfo ENOTFOUND PRIVATE_HOST" }, "name_unresolved"],
  [{ name: "TargetClosedError", message: "PRIVATE_REASON" }, "target_closed"],
  [
    { message: "page.goto: Target page, context or browser has been closed\nPRIVATE_CALL_LOG" },
    "target_closed",
  ],
  [{ message: "page.goto: Page crashed\nPRIVATE" }, "page_crashed"],
  [{ message: "page.goto: Frame was detached\nPRIVATE" }, "frame_detached"],
  [{ message: "PRIVATE http://PRIVATE/?net::ERR_CONNECTION_REFUSED" }, "other_error"],
  [{ message: "page.goto: net::ERR_CONNECTION_REFUSED_EXTRA at PRIVATE" }, "network_other"],
  [{ message: "PRIVATE".repeat(2000) }, "unclassified"],
  [null, "unclassified"],
  [Symbol("PRIVATE"), "unclassified"],
]) {
  test(`navigation error classification supports ${expected} without echoing input`, () => {
    const f = navigationFixture();
    assert.equal(f.classify(input), expected);
    assert.ok(!f.classify(input).includes("PRIVATE"));
  });
}
test("pinned client closed-target with ordinary Error name and custom reason is distinguished by lifecycle", () => {
  const f = navigationFixture();
  const error = new Error("PRIVATE_CUSTOM_REASON");
  assert.equal(Object.getOwnPropertyDescriptor(error, "name"), undefined);
  assert.equal(f.classify(error, { closed: true }), "target_closed");
  assert.equal(f.classify(error, { disconnected: true }), "target_closed");
  assert.equal(f.classify(error, { crashed: true }), "page_crashed");
  assert.equal(f.classify(error, { detached: true }), "frame_detached");
  assert.equal(f.classify(error), "other_error");
});
test("original timeout class stays separate from network text and closed lifecycle", () => {
  const f = navigationFixture();
  assert.equal(
    f.classify(
      { name: "TimeoutError", message: "page.goto: net::ERR_CONNECTION_REFUSED at PRIVATE" },
      { closed: true },
    ),
    "timeout",
  );
});
test("navigation error projection never invokes getters, prototypes, serializers or coercion", () => {
  const f = navigationFixture();
  let calls = 0;
  const error = {
    toString() {
      calls++;
      throw new Error("PRIVATE");
    },
    toJSON() {
      calls++;
      throw new Error("PRIVATE");
    },
  };
  for (const key of ["name", "code", "message"])
    Object.defineProperty(error, key, {
      get() {
        calls++;
        throw new Error("PRIVATE");
      },
    });
  const flags = Object.defineProperty({}, "closed", {
    get() {
      calls++;
      throw new Error("PRIVATE");
    },
  });
  assert.equal(f.classify(error, flags), "unclassified");
  assert.equal(
    f.classify(Object.create({ name: "TimeoutError", code: "ECONNREFUSED", message: "PRIVATE" })),
    "unclassified",
  );
  assert.equal(
    f.classify(
      new Proxy(
        {},
        {
          getOwnPropertyDescriptor() {
            throw new Error("PRIVATE");
          },
        },
      ),
    ),
    "unclassified",
  );
  assert.equal(calls, 0);
});
for (const [name, error, flags] of [
  ["timeout", Object.assign(new Error("PRIVATE"), { name: "TimeoutError" }), {}],
  [
    "network refusal",
    new Error("page.goto: net::ERR_CONNECTION_REFUSED at http://PRIVATE/PRIVATE"),
    {},
  ],
  [
    "default closed target",
    new Error("page.goto: Target page, context or browser has been closed"),
    {},
  ],
  ["custom closed page", new Error("PRIVATE_REASON"), { closed: true }],
  ["custom closed browser", new Error("PRIVATE_REASON"), { disconnected: true }],
  ["page crash", new Error("PRIVATE_REASON"), { crashed: true }],
  ["frame detached", new Error("PRIVATE_REASON"), { detached: true }],
]) {
  test(`actual goto wrapper preserves the same ${name} error, time and snapshot before cleanup`, async () => {
    const f = navigationFixture({
      goto(api) {
        const request = api.request();
        api.emit("request", request);
        api.clock(15010);
        if (flags.closed) {
          api.closed(true);
          api.emit("close");
        }
        if (flags.disconnected) api.disconnect();
        if (flags.crashed) api.emit("crash");
        if (flags.detached) api.emit("framedetached", api.frame);
        throw error;
      },
    });
    const result = await f.originalGoto();
    assert.equal(result.resolved, false);
    assert.equal(result.error, error);
    const d = plain(f.snapshot());
    assert.equal(d.nav_ms, 15000);
    assert.equal(d.nav_done, false);
    assert.equal(d.nav_attempt, 1);
    assert.equal(d.nav_request, true);
    assert.equal(d.nav_observers, true);
    const expected = name.includes("closed")
      ? "target_closed"
      : name === "page crash"
        ? "page_crashed"
        : name === "frame detached"
          ? "frame_detached"
          : name === "network refusal"
            ? "connection_refused"
            : "timeout";
    assert.equal(d.nav_error, expected);
    assert.equal(d.nav_status_seen, false);
    f.emit("close");
    f.disconnect();
    f.emit("load");
    assert.deepEqual(plain(f.snapshot()), d);
    assert.equal(f.handlers("load").length, 0);
    assert.ok(!JSON.stringify(d).includes("PRIVATE"));
    assert.ok(Buffer.byteLength(JSON.stringify(d)) < 2048);
  });
}
test("navigation success keeps returned resolution and records request, route and main lifecycle", async () => {
  const f = navigationFixture({
    goto(api) {
      const request = api.request();
      api.emit("request", request);
      api.route(request, "started");
      api.route(request, "completed", { status: () => 200 });
      api.emit("response", { request: () => request });
      api.route(request, "fulfilled");
      api.emit("framenavigated", api.frame);
      api.emit("domcontentloaded");
      api.emit("load");
      api.clock(25.9);
    },
  });
  assert.equal((await f.originalGoto()).resolved, true);
  const d = plain(f.snapshot());
  assert.equal(d.nav_error, "none");
  assert.equal(d.nav_ms, 15);
  assert.equal(d.nav_done, true);
  for (const key of [
    "nav_status_seen",
    "nav_request",
    "nav_response",
    "nav_main_frame_event",
    "nav_page_dom_event",
    "nav_page_load_event",
  ])
    assert.equal(d[key], true);
  assert.equal(d.navigation_response_status, 200);
  assert.equal(d.nav_fetch, "fulfilled");
});
test("main timeout, request failure and underlying route refusal remain separate observations", () => {
  const f = navigationFixture();
  f.begin(f.target);
  const request = f.request();
  f.emit("request", request);
  f.route(request, "started");
  f.route(
    request,
    "error",
    undefined,
    new Error("route.fetch: connect ECONNREFUSED PRIVATE_ADDRESS"),
  );
  f.emit("requestfailed", { ...request });
  assert.equal(f.snapshot().nav_request_error, "none");
  request.failure = () => ({ errorText: "net::ERR_FAILED" });
  f.emit("requestfailed", request);
  f.clock(15010);
  f.settle({ name: "TimeoutError", message: "PRIVATE" }, true);
  const d = f.snapshot();
  assert.equal(d.nav_error, "timeout");
  assert.equal(d.nav_request_error, "network_failed");
  assert.equal(d.nav_route_error, "connection_refused");
  assert.equal(d.nav_fetch, "started");
});
test("same-URL first and third attempts reject old Request identities and stale listener closures", () => {
  const f = navigationFixture();
  f.begin(f.target);
  const old = f.request();
  f.emit("request", old);
  f.route(old, "completed", { status: () => 201 });
  const oldHandlers = f.handlers("load"),
    oldFrame = f.handlers("framenavigated");
  f.settle(undefined, false);
  f.begin("http://127.0.0.1:3000/en/cart");
  f.settle(undefined, false);
  f.begin(f.target);
  const before = plain(f.snapshot());
  f.emit("request", old);
  f.emit("response", { request: () => old });
  f.emit("requestfailed", old);
  f.route(old, "completed", { status: () => 503 });
  for (const fn of oldHandlers) fn();
  for (const fn of oldFrame) fn(f.frame);
  assert.deepEqual(plain(f.snapshot()), before);
  assert.equal(f.snapshot().navigation_response_status, null);
  assert.equal(f.snapshot().nav_attempt, 3);
  const fresh = f.request();
  f.emit("request", fresh);
  f.route(fresh, "completed", { status: () => 200 });
  assert.equal(f.snapshot().navigation_response_status, 200);
});
test("only current main-frame navigation and its redirect chain affect navigation observations", () => {
  const f = navigationFixture();
  f.begin(f.target);
  for (const request of [
    f.request(f.target, { isNavigationRequest: () => false }),
    f.request(f.target, { frame: () => ({}) }),
    f.request("http://PRIVATE.invalid/PRIVATE"),
    f.request(f.target, { redirectedFrom: () => ({}) }),
  ]) {
    f.emit("request", request);
    f.route(request, "completed", { status: () => 503 });
  }
  assert.equal(f.snapshot().nav_request, false);
  assert.equal(f.snapshot().navigation_response_status, null);
  const request = f.request();
  f.emit("request", request);
  const redirect = f.request("http://127.0.0.1:3000/en/redirected", {
    redirectedFrom: () => request,
  });
  f.emit("request", redirect);
  f.route(redirect, "completed", { status: () => 200 });
  f.emit("response", { request: () => redirect });
  assert.equal(f.snapshot().nav_response, true);
  assert.equal(f.snapshot().navigation_response_status, 200);
  f.emit("framenavigated", {});
  f.emit("framedetached", {});
  assert.equal(f.snapshot().nav_main_frame_event, false);
  assert.equal(f.snapshot().nav_detached, false);
});
for (const end of [NaN, Infinity, -1, "PRIVATE", Symbol("PRIVATE"), 200010]) {
  test("invalid or out-of-bound navigation clocks emit null without changing failure", () => {
    const f = navigationFixture();
    f.begin(f.target);
    f.clock(end);
    f.settle({ name: "TimeoutError" }, true);
    assert.equal(f.snapshot().nav_ms, null);
    assert.equal(f.snapshot().nav_error, "timeout");
  });
}
test("navigation classifier tolerates incomplete diagnostic SDK methods and oversized/private fields", () => {
  const f = navigationFixture();
  f.begin(f.target);
  const request = f.request();
  f.emit("request", request);
  request.failure = () => ({
    get errorText() {
      throw new Error("PRIVATE");
    },
  });
  f.emit("requestfailed", request);
  assert.equal(f.snapshot().nav_request_error, "unclassified");
  const d = diagnostic(
    "guest_navigation",
    {
      navError: "PRIVATE",
      navRequestError: "PRIVATE",
      navRouteError: "PRIVATE",
      navFetch: "PRIVATE",
      navAttempt: 4,
      navMs: 180001,
      navClosed: "PRIVATE",
    },
    {},
  );
  assert.equal(d.nav_error, "unclassified");
  assert.equal(d.nav_request_error, "unclassified");
  assert.equal(d.nav_route_error, "unclassified");
  assert.equal(d.nav_fetch, "unclassified");
  assert.equal(d.nav_attempt, null);
  assert.equal(d.nav_ms, null);
  assert.equal(d.nav_closed, null);
  assert.ok(!JSON.stringify(d).includes("PRIVATE"));
  for (const ms of [0, 180000])
    assert.equal(diagnostic("guest_navigation", { navMs: ms }, {}).nav_ms, ms);
});

test("new lifecycle listener records only an observed page event, never correlated response/readiness", () => {
  const f = navigationFixture();
  f.begin(f.target);
  f.settle(undefined, false);
  f.begin(f.target);
  // DOM/load events have no Request identity in the public SDK. Preserve that limitation.
  f.emit("domcontentloaded");
  f.emit("load");
  f.emit("framenavigated", f.frame);
  const d = f.snapshot();
  assert.equal(d.nav_page_dom_event, true);
  assert.equal(d.nav_page_load_event, true);
  assert.equal(d.nav_main_frame_event, true);
  assert.equal(d.nav_request, false);
  assert.equal(d.nav_response, false);
  assert.equal(d.nav_status_seen, false);
  assert.equal(d.nav_done, false);
});
for (const options of [{ onError: true }, { clockError: true }]) {
  test("observer or monotonic clock failure cannot replace the original goto error", async () => {
    const error = Object.assign(new Error("PRIVATE_ORIGINAL_TIMEOUT"), { name: "TimeoutError" });
    const f = navigationFixture({
      ...options,
      goto() {
        throw error;
      },
    });
    const result = await f.originalGoto();
    assert.equal(result.error, error);
    assert.equal(result.resolved, false);
    assert.equal(f.snapshot().nav_error, "timeout");
    if (options.onError) assert.equal(f.snapshot().nav_observers, false);
    if (options.clockError) assert.equal(f.snapshot().nav_ms, null);
  });
}
for (const key of [
  "navDone",
  "navRequest",
  "navResponse",
  "navCommit",
  "navDom",
  "navLoad",
  "navClosed",
  "navContextClosed",
  "navCrash",
  "navDetached",
  "navDisconnected",
  "navObservers",
]) {
  test(`navigation ${key} rejects arbitrary values and never invokes a getter`, () => {
    let reads = 0;
    const input = Object.defineProperty({}, key, {
      get() {
        reads++;
        throw new Error("PRIVATE");
      },
    });
    const d = diagnostic("guest_navigation", input, {});
    assert.equal(reads, 0);
    assert.ok(!JSON.stringify(d).includes("PRIVATE"));
    const field = {
      navDone: "nav_done",
      navRequest: "nav_request",
      navResponse: "nav_response",
      navCommit: "nav_main_frame_event",
      navDom: "nav_page_dom_event",
      navLoad: "nav_page_load_event",
      navClosed: "nav_closed",
      navContextClosed: "nav_context_closed",
      navCrash: "nav_crash",
      navDetached: "nav_detached",
      navDisconnected: "nav_disconnected",
      navObservers: "nav_observers",
    }[key];
    assert.equal(d[field], null);
    assert.equal(diagnostic("guest_navigation", { [key]: "PRIVATE" }, {})[field], null);
    for (const value of [true, false])
      assert.equal(diagnostic("guest_navigation", { [key]: value }, {})[field], value);
  });
}
test("status presence is bounded own numeric observation, not HTTP or page success", () => {
  for (const status of [100, 503, 599])
    assert.equal(
      diagnostic("guest_navigation", { navAttempt: 1, navigationStatus: status }, {})
        .nav_status_seen,
      true,
    );
  for (const status of [null, 99, 600, "PRIVATE", Symbol("PRIVATE")])
    assert.equal(
      diagnostic("guest_navigation", { navAttempt: 1, navigationStatus: status }, {})
        .nav_status_seen,
      false,
    );
  assert.equal(
    diagnostic("guest_navigation", { navAttempt: 0, navigationStatus: 200 }, {}).nav_status_seen,
    null,
  );
  assert.equal(
    diagnostic("guest_navigation", { navAttempt: 1, navigationStatus: 503, navDone: false }, {})
      .nav_done,
    false,
  );
});

test("pinned client TargetClosedError is classified even with private custom reason and no lifecycle event", () => {
  const f = navigationFixture();
  const error = f.makeClosedTarget("PRIVATE_OWNER_REASON");
  assert.equal(Object.getOwnPropertyDescriptor(error, "name"), undefined);
  assert.equal(f.classify(error), "target_closed");
  assert.equal(
    f.classify(f.makeClosedTarget("page.goto: net::ERR_CONNECTION_REFUSED at PRIVATE")),
    "target_closed",
  );
  let reads = 0;
  const errorLike = Object.create(
    Object.defineProperty({}, "constructor", {
      get() {
        reads++;
        throw new Error("PRIVATE");
      },
    }),
  );
  assert.equal(f.classify(errorLike), "unclassified");
  assert.equal(reads, 0);
});
test("context close is distinct from page close and browser disconnection in navigation snapshot", () => {
  const f = navigationFixture();
  f.begin(f.target);
  f.closeContext();
  f.settle(new Error("PRIVATE_REASON"), true);
  const d = f.snapshot();
  assert.equal(d.nav_error, "target_closed");
  assert.equal(d.nav_context_closed, true);
  assert.equal(d.nav_closed, false);
  assert.equal(d.nav_disconnected, false);
});
for (const [code, expected] of [
  ["ERR_BLOCKED_BY_CLIENT", "client_blocked"],
  ["ERR_EMPTY_RESPONSE", "empty_response"],
  ["ERR_UNKNOWN_PRIVATE", "network_other"],
]) {
  test(`bounded Chromium ${expected} observation never prints arbitrary code or URL`, () => {
    const f = navigationFixture();
    assert.equal(
      f.classify({ message: `page.goto: net::${code} at http://PRIVATE/PRIVATE` }),
      expected,
    );
  });
}

for (const callSite of [0, 1, 2]) {
  test(`original navigation site ${callSite + 1} retains one argument and the identical error`, async () => {
    const error = Object.assign(new Error("PRIVATE_TIMEOUT"), { name: "TimeoutError" });
    const f = navigationFixture({
      callSite,
      goto() {
        throw error;
      },
    });
    const result = await f.originalGoto();
    assert.equal(result.error, error);
    assert.equal(result.resolved, false);
    assert.equal(f.snapshot().nav_error, "timeout");
  });
}
test("closed-target type observation does not invoke an Error prototype constructor getter", () => {
  const f = navigationFixture();
  let reads = 0;
  class CustomError extends Error {}
  Object.defineProperty(CustomError.prototype, "constructor", {
    get() {
      reads++;
      throw new Error("PRIVATE");
    },
  });
  assert.equal(f.classify(new CustomError("PRIVATE")), "other_error");
  assert.equal(reads, 0);
});

test("full v3 projection is exactly forty bounded scalars with the original twenty-one-field budget", () => {
  const input = {
    ...scalarState,
    navAttempt: 3,
    navMs: 180000,
    navError: "connection_refused",
    navRequestError: "network_unreachable",
    navRouteError: "connection_refused",
    navFetch: "fulfilled",
    navigationStatus: 599,
  };
  for (const key of [
    "navDone",
    "navRequest",
    "navResponse",
    "navCommit",
    "navDom",
    "navLoad",
    "navClosed",
    "navContextClosed",
    "navCrash",
    "navDetached",
    "navDisconnected",
    "navObservers",
  ])
    input[key] = true;
  const d = diagnostic("guest_navigation", input, committed);
  assert.equal(Object.keys(d).length, 40);
  assert.ok(
    Object.values(d).every(
      (value) => value === null || ["boolean", "number", "string"].includes(typeof value),
    ),
  );
  assert.ok(Buffer.byteLength(JSON.stringify(d)) < 2048);
  assert.ok(
    Buffer.byteLength(JSON.stringify(Object.fromEntries(Object.entries(d).slice(0, 21)))) < 1024,
  );
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
