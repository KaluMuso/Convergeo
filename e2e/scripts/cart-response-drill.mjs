/** Actual customer UI retry against the existing disposable performance stack. */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";

import { chromium, expect } from "@playwright/test";

const root = resolve(import.meta.dirname, "../..");
const output = resolve(root, "e2e/results/cart-response-drill/outcome.json");
const python = resolve(root, "services/api/.venv/bin/python");
const helper = resolve(root, "scripts/qa/cart-response-drill-db.py");
const origin = "http://127.0.0.1:3000";
const api = "http://127.0.0.1:8000";
const report = {
  version: 1,
  qualified: false,
  checkpoints: {},
  stages: [],
  blockedImages: 0,
};
let browser;
let bound = false;
let phase = "guard";
let failureStage = "outside_discard";
const deadline = setTimeout(() => process.exit(124), 180_000);

function cartFailureDiagnostic(stage, state, checkpoints) {
  const read = (input, key) => {
    try {
      return Object.getOwnPropertyDescriptor(input, key)?.value;
    } catch {
      return undefined;
    }
  };
  const flag = (value) => (typeof value === "boolean" ? value : null);
  const integer = (value, min, max) =>
    Number.isSafeInteger(value) && value >= min && value <= max ? value : null;
  const label = (value, allowed) => (allowed.includes(value) ? value : "unclassified");
  const routeFailure = flag(read(state, "routeFailureObserved"));
  const nativeStages = [
    "native_observe",
    "native_quantity",
    "native_claims",
    "native_events",
    "native_price",
    "native_key",
  ];
  const nativeStage = read(state, "nativeCheck");
  const reportedStage =
    stage === "stock_native_state" && nativeStages.includes(nativeStage)
      ? `stock_${nativeStage}`
      : stage;
  return {
    format: "cart_browser_failure_v2",
    failure_stage: label(reportedStage, [
      "outside_discard",
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
      "guest_pickup_probe",
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
      "fresh_pickup_probe",
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
      "stock_notice_find",
      "stock_notice_presence",
      "stock_requested_quantity",
      "stock_available_quantity",
      "stock_native_state",
      "stock_native_observe",
      "stock_native_quantity",
      "stock_native_claims",
      "stock_native_events",
      "stock_native_price",
      "stock_native_key",
      "stock_restore",
      "final_add_count",
      "final_external_count",
      "final_route_integrity",
      "process_snapshot",
      "browser_child_presence",
      "browser_child_uid",
      "fixture_cleanup",
    ]),
    intercepted_posts: integer(read(state, "posts"), 0, 1000),
    first_response_status: integer(read(state, "firstResponseStatus"), 100, 599),
    first_click_completed: flag(read(state, "firstClickCompleted")),
    error_visibility_assertion_passed: flag(read(state, "errorVisibilityPassed")),
    route_failure_observed: routeFailure,
    route_failure_stage:
      routeFailure === true
        ? label(read(state, "routeFailureStage"), [
            "request_guard",
            "request_origin",
            "request_auth_path",
            "image_fulfil",
            "cart_request_guard",
            "cart_request_headers",
            "cart_key_presence",
            "cart_cookie_presence",
            "cart_request_body",
            "cart_request_json",
            "cart_request_quantity",
            "fixture_bind",
            "fixture_guest",
            "fixture_empty",
            "retry_key",
            "retry_body",
            "fresh_add_count",
            "fresh_key",
            "fresh_body",
            "cart_response_fetch",
            "cart_response_status",
            "cart_response_body",
            "cart_identity",
            "cart_line_find",
            "cart_line_presence",
            "cart_line_quantity",
            "cart_line_price",
            "cart_subtotal",
            "native_commit_check",
            "native_observe",
            "native_quantity",
            "native_claims",
            "native_events",
            "native_price",
            "native_key",
            "response_abort",
            "cart_response_fulfil",
            "cart_response_dispose",
            "other_response_fetch",
            "other_redirect_guard",
            "other_redirect_origin",
            "other_response_fulfil",
            "other_response_dispose",
          ])
        : "none",
    route_failure_post:
      routeFailure === true ? integer(read(state, "routeFailurePost"), 0, 1000) : null,
    first_response_disposed: flag(read(state, "firstResponseDisposed")),
    db_commit_recorded: read(checkpoints, "committed_before_discard") === true,
    response_discard_recorded: read(checkpoints, "one_response_discarded") === true,
    fixture_cleanup_recorded: read(checkpoints, "synthetic_fixture_cleanup") === true,
    navigation_response_status: integer(read(state, "navigationStatus"), 100, 599),
    guest_response_status: integer(read(state, "guestStatus"), 100, 599),
    stock_response_status: integer(read(state, "stockStatus"), 100, 599),
    latest_add_response_status: integer(read(state, "latestAddStatus"), 100, 599),
    latest_add_response_post: integer(read(state, "latestAddPost"), 0, 1000),
    external_requests_observed: integer(read(state, "externalRequests"), 0, 1000),
    blocked_images_observed: integer(read(state, "blockedImages"), 0, 1000),
    native_check_reached: label(read(state, "nativeCheck"), [
      "none",
      "native_observe",
      "native_quantity",
      "native_claims",
      "native_events",
      "native_price",
      "native_key",
    ]),
  };
}
const browserDiagnostic = {
  posts: 0,
  firstResponseStatus: null,
  firstClickCompleted: false,
  errorVisibilityPassed: false,
  routeFailureObserved: false,
  routeFailureStage: null,
  routeFailurePost: null,
  firstResponseDisposed: false,
  navigationStatus: null,
  guestStatus: null,
  stockStatus: null,
  latestAddStatus: null,
  latestAddPost: null,
  externalRequests: 0,
  blockedImages: 0,
  nativeCheck: "none",
};

function observeBrowserDiagnostic(message) {
  try {
    if (message.type() !== "debug") return;
    const token = message.text();
    if (typeof token !== "string" || token.length > 100) return;
    const guestActive = [
      "guest_bootstrap_dispatch",
      "guest_bootstrap_fetch",
      "guest_bootstrap_http",
      "guest_bootstrap_json",
    ].includes(failureStage);
    const stockActive = [
      "stock_revalidation_dispatch",
      "stock_revalidation_fetch",
      "stock_revalidation_http",
      "stock_revalidation_json",
    ].includes(failureStage);
    for (const code of [
      "guest_bootstrap_fetch",
      "guest_bootstrap_http",
      "guest_bootstrap_json",
      "stock_revalidation_fetch",
      "stock_revalidation_http",
      "stock_revalidation_json",
    ])
      if (
        token === `cart-drill-step:${code}` &&
        ((guestActive && code.startsWith("guest_")) || (stockActive && code.startsWith("stock_")))
      )
        failureStage = code;
    const status = /^cart-drill-status:(guest|stock):([1-5][0-9]{2})$/.exec(token);
    if (
      status &&
      ((status[1] === "guest" && guestActive) || (status[1] === "stock" && stockActive))
    )
      browserDiagnostic[status[1] === "guest" ? "guestStatus" : "stockStatus"] = Number(status[2]);
  } catch {
    // Diagnostic observation cannot replace an original failure or cleanup path.
  }
}

async function waitForFirstDiscard(completion) {
  let timer;
  try {
    assert.equal(
      await Promise.race([
        completion,
        new Promise((resolve) => {
          timer = setTimeout(() => resolve(false), 15_000);
        }),
      ]),
      true,
    );
  } finally {
    clearTimeout(timer);
  }
}

function db(action, payload = {}) {
  return JSON.parse(
    execFileSync(python, [helper, action], {
      input: JSON.stringify(payload),
      encoding: "utf8",
      timeout: 7000,
    }),
  );
}
function point(name) {
  report.checkpoints[name] = true;
}
function state(name, qty, claims, events, price, key) {
  browserDiagnostic.nativeCheck = "native_observe";
  const observed = db("observe", key ? { key } : {});
  report.lastNativeObservation = { name, ...observed };
  browserDiagnostic.nativeCheck = "native_quantity";
  assert.equal(observed.qty, qty);
  browserDiagnostic.nativeCheck = "native_claims";
  assert.equal(observed.claims, claims);
  browserDiagnostic.nativeCheck = "native_events";
  assert.equal(observed.events, events);
  browserDiagnostic.nativeCheck = "native_price";
  assert.equal(observed.stored_price, price);
  if (key) browserDiagnostic.nativeCheck = "native_key";
  if (key) assert.equal(observed.key_committed, true);
  report.stages.push({ name, qty, claims, events, price });
}
const money = (ngwee) =>
  `K${(ngwee / 100).toLocaleString("en-ZM", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

try {
  failureStage = "local_flag_guard";
  assert.equal(process.env.CART_DRILL_LOCAL, "1");
  failureStage = "uid_guard";
  assert.equal(process.env.CART_DRILL_UID, String(process.getuid()));
  failureStage = "api_origin_guard";
  assert.equal(process.env.SUPABASE_URL, "http://127.0.0.1:54321");
  failureStage = "database_origin_guard";
  assert.equal(
    process.env.SUPABASE_DB_URL,
    "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
  );
  point("dedicated_uid_and_local_stack");
  failureStage = "browser_launch";
  browser = await chromium.launch({
    args: [
      "--no-sandbox",
      "--disable-background-networking",
      "--disable-component-update",
      "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
    ],
  });
  failureStage = "browser_context";
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    serviceWorkers: "block",
  });
  failureStage = "browser_page";
  const page = await context.newPage();
  failureStage = "browser_console_setup";
  page.on("console", observeBrowserDiagnostic);
  page.setDefaultTimeout(15_000);
  let cartId, listingId, price, firstKey, firstBody;
  let posts = 0;
  let routeFailure;
  let finishFirstDiscard;
  const firstDiscardPromise = new Promise((resolve) => {
    finishFirstDiscard = resolve;
  });
  let externalRequests = 0;
  failureStage = "websocket_route_setup";
  await context.routeWebSocket("**/*", (socket) => {
    const url = new URL(socket.url());
    if (url.origin === "ws://127.0.0.1:3000" && url.pathname === "/_next/webpack-hmr") {
      socket.connectToServer();
      return;
    }
    externalRequests += 1;
    browserDiagnostic.externalRequests = externalRequests;
    socket.close();
  });
  failureStage = "http_route_setup";
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    let routeStage = "request_guard";
    let postOrdinal = 0;
    try {
      // Images are unrelated to the mutation contract. Fulfil before any local
      // image proxy or remote image host is contacted; this is counted explicitly.
      if (request.resourceType() === "image") {
        report.blockedImages += 1;
        browserDiagnostic.blockedImages = report.blockedImages;
        routeStage = "image_fulfil";
        await route.fulfill({
          status: 200,
          contentType: "image/svg+xml",
          body: "<svg xmlns='http://www.w3.org/2000/svg' width='1' height='1'/>",
        });
        return;
      }
      routeStage = "request_origin";
      assert.ok([origin, api].includes(url.origin));
      routeStage = "request_auth_path";
      assert.ok(!url.pathname.startsWith("/auth/"));
      if (url.origin === api && url.pathname === "/cart/items" && request.method() === "POST") {
        posts += 1;
        postOrdinal = posts;
        browserDiagnostic.posts = posts;
        routeStage = "cart_request_guard";
        routeStage = "cart_request_headers";
        const headers = await request.allHeaders();
        const key = headers["idempotency-key"];
        routeStage = "cart_key_presence";
        assert.ok(key && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(key));
        routeStage = "cart_cookie_presence";
        assert.ok(headers.cookie);
        routeStage = "cart_request_body";
        const body = request.postData();
        routeStage = "cart_request_json";
        const parsed = JSON.parse(body);
        routeStage = "cart_request_quantity";
        assert.equal(parsed.qty, 1);
        if (posts === 1) {
          firstKey = key;
          firstBody = body;
          listingId = parsed.listing_id;
          routeStage = "fixture_bind";
          const fixture = db("bind", { cart: cartId, listing: listingId });
          bound = true;
          price = fixture.price;
          routeStage = "fixture_guest";
          assert.equal(fixture.guest, true);
          routeStage = "fixture_empty";
          assert.equal(fixture.empty, true);
        } else if (posts === 2) {
          routeStage = "retry_key";
          assert.equal(key, firstKey);
          routeStage = "retry_body";
          assert.equal(body, firstBody);
          point("retry_same_key_and_body");
        } else {
          routeStage = "fresh_add_count";
          assert.equal(posts, 3);
          routeStage = "fresh_key";
          assert.notEqual(key, firstKey);
          routeStage = "fresh_body";
          assert.equal(body, firstBody);
          point("fresh_key_same_intent_body");
        }
        routeStage = "cart_response_fetch";
        const response = await route.fetch({
          maxRedirects: 0,
          maxRetries: 0,
          timeout: 15_000,
        });
        routeStage = "cart_response_status";
        try {
          browserDiagnostic.latestAddStatus = response.status();
          browserDiagnostic.latestAddPost = postOrdinal;
        } catch {}
        if (postOrdinal === 1) browserDiagnostic.firstResponseStatus = response.status();
        assert.equal(response.status(), 200);
        routeStage = "cart_response_body";
        const result = await response.json();
        routeStage = "cart_identity";
        assert.equal(result.cart_id, cartId);
        routeStage = "cart_line_find";
        const line = result.items.find((item) => item.listing_id === listingId);
        routeStage = "cart_line_presence";
        assert.ok(line);
        routeStage = "cart_line_quantity";
        assert.equal(line.qty, posts === 3 ? 2 : 1);
        routeStage = "cart_line_price";
        assert.equal(line.unit_price_ngwee, posts === 3 ? price + 100 : price);
        routeStage = "cart_subtotal";
        assert.equal(result.subtotal_ngwee, line.qty * line.unit_price_ngwee);
        if (posts === 1) {
          // Confirm native commit before withholding the response from the UI.
          routeStage = "native_commit_check";
          state("committed_before_discard", 1, 1, 1, price, key);
          point("committed_before_discard");
          routeStage = "response_abort";
          await route.abort("connectionreset");
          point("one_response_discarded");
        } else {
          routeStage = "native_commit_check";
          state(
            posts === 2 ? "replayed" : "fresh",
            posts === 2 ? 1 : 2,
            posts === 2 ? 1 : 2,
            posts === 2 ? 1 : 2,
            posts === 2 ? price : price + 100,
            key,
          );
          routeStage = "cart_response_fulfil";
          await route.fulfill({ response });
        }
        routeStage = "cart_response_dispose";
        await response.dispose();
        if (postOrdinal === 1) browserDiagnostic.firstResponseDisposed = true;
        return;
      }
      // Keep redirects inside this interception boundary; never auto-follow.
      routeStage = "other_response_fetch";
      const response = await route.fetch({
        maxRedirects: 0,
        maxRetries: 0,
        timeout: 15_000,
      });
      try {
        if (url.origin === origin && request.resourceType() === "document")
          browserDiagnostic.navigationStatus = response.status();
      } catch {}
      routeStage = "other_redirect_guard";
      const location = response.headers().location;
      if (location) routeStage = "other_redirect_origin";
      if (location) assert.ok([origin, api].includes(new URL(location, url).origin));
      routeStage = "other_response_fulfil";
      await route.fulfill({ response });
      routeStage = "other_response_dispose";
      await response.dispose();
    } catch {
      if (![origin, api].includes(url.origin)) externalRequests += 1;
      browserDiagnostic.externalRequests = externalRequests;
      routeFailure = true;
      if (!browserDiagnostic.routeFailureObserved) {
        if (
          routeStage === "native_commit_check" &&
          [
            "native_observe",
            "native_quantity",
            "native_claims",
            "native_events",
            "native_price",
            "native_key",
          ].includes(browserDiagnostic.nativeCheck)
        )
          routeStage = browserDiagnostic.nativeCheck;
        browserDiagnostic.routeFailureStage = routeStage;
        browserDiagnostic.routeFailurePost = postOrdinal;
      }
      browserDiagnostic.routeFailureObserved = true;
      await route.abort("blockedbyclient");
    } finally {
      if (postOrdinal === 1)
        finishFirstDiscard(
          browserDiagnostic.firstResponseDisposed &&
            report.checkpoints.committed_before_discard === true &&
            report.checkpoints.one_response_discarded === true &&
            !routeFailure,
        );
    }
  });
  phase = "establish_guest";
  failureStage = "guest_navigation";
  await page.goto(`${origin}/en/p/smartphone-x1`);
  failureStage = "guest_bootstrap_dispatch";
  const initial = await page.evaluate(async (url) => {
    const mark = (token) => {
      try {
        console.debug(token);
      } catch {}
    };
    mark("cart-drill-step:guest_bootstrap_fetch");
    const response = await fetch(`${url}/cart`, { credentials: "include" });
    try {
      const status = response.status;
      if (Number.isSafeInteger(status) && status >= 100 && status <= 599)
        mark(`cart-drill-status:guest:${status}`);
    } catch {}
    mark("cart-drill-step:guest_bootstrap_http");
    if (!response.ok) throw new Error("cart bootstrap failed");
    mark("cart-drill-step:guest_bootstrap_json");
    return response.json();
  }, api);
  failureStage = "guest_cart_identity";
  cartId = initial.cart_id;
  assert.ok(cartId);
  failureStage = "guest_empty_cart";
  assert.deepEqual(initial.items, []);
  failureStage = "guest_cookie_presence";
  assert.ok((await context.cookies(api)).some((cookie) => cookie.name === "vergeo_guest_cart"));
  point("guest_cookie_established");
  failureStage = "guest_add_enabled";
  const add = page.getByTestId("pdp-add-to-cart");
  async function choosePickup() {
    failureStage = phase === "fresh_intent" ? "fresh_pickup_probe" : "guest_pickup_probe";
    const select = page.getByTestId("pdp-pickup-location-select");
    if (
      await select
        .waitFor({ state: "visible", timeout: 3000 })
        .then(() => true)
        .catch(() => false)
    ) {
      failureStage = phase === "fresh_intent" ? "fresh_pickup_selection" : "guest_pickup_selection";
      await select.selectOption({ index: 1 });
    }
  }
  await choosePickup();
  failureStage = "guest_add_enabled";
  await expect(add).toBeEnabled();
  phase = "discard_after_commit";
  failureStage = "discard_click";
  await add.click();
  browserDiagnostic.firstClickCompleted = true;
  failureStage = "discard_completion";
  await waitForFirstDiscard(firstDiscardPromise);
  failureStage = "discard_error_visibility";
  await expect(page.getByTestId("pdp-add-to-cart-error")).toBeVisible();
  browserDiagnostic.errorVisibilityPassed = true;
  failureStage = "discard_route_integrity";
  assert.equal(routeFailure, undefined);
  point("actual_ui_uncertain_error");
  failureStage = "outside_discard";
  phase = "actual_browser_retry";
  failureStage = "retry_click";
  await add.click();
  failureStage = "retry_success_visibility";
  await expect(page.getByTestId("pdp-add-to-cart-success")).toBeVisible();
  failureStage = "retry_subtotal";
  await expect(page.getByTestId("mini-cart-subtotal")).toHaveText(money(price));
  failureStage = "retry_quantity";
  await expect(page.getByTestId("mini-cart-drawer")).toContainText("Quantity: 1");
  point("replay_quantity_price_ui");
  failureStage = "retry_drawer_close";
  await page.getByTestId("mini-cart-close").click();
  phase = "price_notice";
  failureStage = "price_fixture";
  db("price");
  failureStage = "price_navigation";
  await page.goto(`${origin}/en/cart`);
  const notice = page.getByTestId(`cart-notice-price_changed-${listingId}`);
  failureStage = "price_notice_visibility";
  await expect(notice).toBeVisible();
  failureStage = "price_notice_previous";
  await expect(notice).toContainText(money(price));
  failureStage = "price_notice_current";
  await expect(notice).toContainText(money(price + 100));
  failureStage = "price_subtotal";
  await expect(page.getByTestId("cart-subtotal")).toHaveText(money(price + 100));
  failureStage = "price_quantity";
  await expect(page.getByTestId(`cart-qty-${listingId}-value`)).toHaveText("1");
  point("authoritative_price_notice_ui");
  phase = "fresh_intent";
  failureStage = "fresh_navigation";
  await page.goto(`${origin}/en/p/smartphone-x1`);
  await choosePickup();
  failureStage = "fresh_add_enabled";
  await expect(page.getByTestId("pdp-add-to-cart")).toBeEnabled();
  failureStage = "fresh_click";
  await page.getByTestId("pdp-add-to-cart").click();
  failureStage = "fresh_success_visibility";
  await expect(page.getByTestId("pdp-add-to-cart-success")).toBeVisible();
  failureStage = "fresh_subtotal";
  await expect(page.getByTestId("mini-cart-subtotal")).toHaveText(money(2 * (price + 100)));
  failureStage = "fresh_quantity";
  await expect(page.getByTestId("mini-cart-drawer")).toContainText("Quantity: 2");
  point("fresh_quantity_price_ui");
  phase = "stock_notice";
  failureStage = "stock_fixture";
  db("stock");
  failureStage = "stock_revalidation_dispatch";
  const notices = await page.evaluate(async (url) => {
    const mark = (token) => {
      try {
        console.debug(token);
      } catch {}
    };
    mark("cart-drill-step:stock_revalidation_fetch");
    const response = await fetch(`${url}/cart/revalidate`, {
      method: "POST",
      credentials: "include",
    });
    try {
      const status = response.status;
      if (Number.isSafeInteger(status) && status >= 100 && status <= 599)
        mark(`cart-drill-status:stock:${status}`);
    } catch {}
    mark("cart-drill-step:stock_revalidation_http");
    if (!response.ok) throw new Error("stock revalidation failed");
    mark("cart-drill-step:stock_revalidation_json");
    return response.json();
  }, api);
  failureStage = "stock_notice_find";
  const stock = notices.notices.find((n) => n.listing_id === listingId && n.kind === "qty_reduced");
  failureStage = "stock_notice_presence";
  assert.ok(stock);
  failureStage = "stock_requested_quantity";
  assert.equal(stock.requested_qty, 2);
  failureStage = "stock_available_quantity";
  assert.equal(stock.available_qty, 1);
  failureStage = "stock_native_state";
  state("stock_revalidated", 2, 2, 2, price + 100);
  point("authoritative_stock_notice_browser_api");
  failureStage = "stock_restore";
  db("restore-stock");
  failureStage = "final_add_count";
  assert.equal(posts, 3);
  failureStage = "final_external_count";
  assert.equal(externalRequests, 0);
  failureStage = "final_route_integrity";
  assert.equal(routeFailure, undefined);
  point("exactly_three_real_adds");
  point("no_external_browser_requests");
  // --no-sandbox keeps Chromium subprocesses under the same firewall owner UID.
  failureStage = "process_snapshot";
  const processRows = execFileSync("ps", ["-eo", "uid=,pid=,ppid=,comm="], {
    encoding: "utf8",
  })
    .trim()
    .split("\n")
    .map((row) => row.trim().split(/\s+/));
  const descendants = new Set([process.pid]);
  for (let n = 0; n < processRows.length; n++)
    for (const [, pid, ppid] of processRows) {
      if (descendants.has(Number(ppid))) descendants.add(Number(pid));
    }
  const children = processRows.filter(([, pid]) => descendants.has(Number(pid)));
  failureStage = "browser_child_presence";
  assert.ok(children.some(([, , , command]) => /chrome|chromium|headless_shell/.test(command)));
  failureStage = "browser_child_uid";
  assert.ok(children.every(([uid]) => uid === process.env.CART_DRILL_UID));
  point("browser_subprocess_uid_covered");
  report.qualified = true;
  delete report.lastNativeObservation;
} catch {
  report.failedPhase = phase;
  report.failureDiagnostic = cartFailureDiagnostic(
    failureStage,
    browserDiagnostic,
    report.checkpoints,
  );
  process.exitCode = 1;
} finally {
  if (bound) {
    try {
      assert.equal(db("cleanup").cleaned, true);
      point("synthetic_fixture_cleanup");
    } catch {
      report.failureDiagnostic ??= cartFailureDiagnostic(
        "fixture_cleanup",
        browserDiagnostic,
        report.checkpoints,
      );
      report.qualified = false;
      report.failedPhase = "fixture_cleanup";
      process.exitCode = 1;
    }
  }
  if (report.failureDiagnostic) {
    report.failureDiagnostic.fixture_cleanup_recorded =
      report.checkpoints.synthetic_fixture_cleanup === true;
    console.log(`cart-drill-browser-failure-summary: ${JSON.stringify(report.failureDiagnostic)}`);
  }
  if (browser) await browser.close();
  clearTimeout(deadline);
  writeFileSync(output, JSON.stringify(report, null, 2) + "\n");
  console.log(
    report.qualified
      ? "Cart response drill assertions passed"
      : `Cart response drill failed: ${report.failedPhase}`,
  );
}
