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
const deadline = setTimeout(() => process.exit(124), 180_000);

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
  const observed = db("observe", key ? { key } : {});
  report.lastNativeObservation = { name, ...observed };
  assert.equal(observed.qty, qty);
  assert.equal(observed.claims, claims);
  assert.equal(observed.events, events);
  assert.equal(observed.stored_price, price);
  if (key) assert.equal(observed.key_committed, true);
  report.stages.push({ name, qty, claims, events, price });
}
const money = (ngwee) =>
  `K${(ngwee / 100).toLocaleString("en-ZM", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

try {
  assert.equal(process.env.CART_DRILL_LOCAL, "1");
  assert.equal(process.env.CART_DRILL_UID, String(process.getuid()));
  assert.equal(process.env.SUPABASE_URL, "http://127.0.0.1:54321");
  assert.equal(
    process.env.SUPABASE_DB_URL,
    "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
  );
  point("dedicated_uid_and_local_stack");
  browser = await chromium.launch({
    args: [
      "--no-sandbox",
      "--disable-background-networking",
      "--disable-component-update",
      "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
    ],
  });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    serviceWorkers: "block",
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15_000);
  let cartId, listingId, price, firstKey, firstBody;
  let posts = 0;
  let routeFailure;
  let externalRequests = 0;
  await context.routeWebSocket("**/*", (socket) => {
    const url = new URL(socket.url());
    if (
      url.origin === "ws://127.0.0.1:3000" &&
      url.pathname === "/_next/webpack-hmr"
    ) {
      socket.connectToServer();
      return;
    }
    externalRequests += 1;
    socket.close();
  });
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    try {
      // Images are unrelated to the mutation contract. Fulfil before any local
      // image proxy or remote image host is contacted; this is counted explicitly.
      if (request.resourceType() === "image") {
        report.blockedImages += 1;
        await route.fulfill({
          status: 200,
          contentType: "image/svg+xml",
          body: "<svg xmlns='http://www.w3.org/2000/svg' width='1' height='1'/>",
        });
        return;
      }
      assert.ok([origin, api].includes(url.origin));
      assert.ok(!url.pathname.startsWith("/auth/"));
      if (
        url.origin === api &&
        url.pathname === "/cart/items" &&
        request.method() === "POST"
      ) {
        posts += 1;
        const headers = await request.allHeaders();
        const key = headers["idempotency-key"];
        assert.ok(key && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(key));
        assert.ok(headers.cookie);
        const body = request.postData();
        const parsed = JSON.parse(body);
        assert.equal(parsed.qty, 1);
        if (posts === 1) {
          firstKey = key;
          firstBody = body;
          listingId = parsed.listing_id;
          const fixture = db("bind", { cart: cartId, listing: listingId });
          bound = true;
          price = fixture.price;
          assert.equal(fixture.guest, true);
          assert.equal(fixture.empty, true);
        } else if (posts === 2) {
          assert.equal(key, firstKey);
          assert.equal(body, firstBody);
          point("retry_same_key_and_body");
        } else {
          assert.equal(posts, 3);
          assert.notEqual(key, firstKey);
          assert.equal(body, firstBody);
          point("fresh_key_same_intent_body");
        }
        const response = await route.fetch({
          maxRedirects: 0,
          maxRetries: 0,
          timeout: 15_000,
        });
        assert.equal(response.status(), 200);
        const result = await response.json();
        assert.equal(result.cart_id, cartId);
        const line = result.items.find((item) => item.listing_id === listingId);
        assert.ok(line);
        assert.equal(line.qty, posts === 3 ? 2 : 1);
        assert.equal(line.unit_price_ngwee, posts === 3 ? price + 100 : price);
        assert.equal(result.subtotal_ngwee, line.qty * line.unit_price_ngwee);
        if (posts === 1) {
          // Confirm native commit before withholding the response from the UI.
          state("committed_before_discard", 1, 1, 1, price, key);
          point("committed_before_discard");
          await route.abort("connectionreset");
          point("one_response_discarded");
        } else {
          state(
            posts === 2 ? "replayed" : "fresh",
            posts === 2 ? 1 : 2,
            posts === 2 ? 1 : 2,
            posts === 2 ? 1 : 2,
            posts === 2 ? price : price + 100,
            key,
          );
          await route.fulfill({ response });
        }
        await response.dispose();
        return;
      }
      // Keep redirects inside this interception boundary; never auto-follow.
      const response = await route.fetch({
        maxRedirects: 0,
        maxRetries: 0,
        timeout: 15_000,
      });
      const location = response.headers().location;
      if (location)
        assert.ok([origin, api].includes(new URL(location, url).origin));
      await route.fulfill({ response });
      await response.dispose();
    } catch {
      if (![origin, api].includes(url.origin)) externalRequests += 1;
      routeFailure = true;
      await route.abort("blockedbyclient");
    }
  });
  phase = "establish_guest";
  await page.goto(`${origin}/en/p/smartphone-x1`);
  const initial = await page.evaluate(async (url) => {
    const response = await fetch(`${url}/cart`, { credentials: "include" });
    if (!response.ok) throw new Error("cart bootstrap failed");
    return response.json();
  }, api);
  cartId = initial.cart_id;
  assert.ok(cartId);
  assert.deepEqual(initial.items, []);
  assert.ok(
    (await context.cookies(api)).some(
      (cookie) => cookie.name === "vergeo_guest_cart",
    ),
  );
  point("guest_cookie_established");
  const add = page.getByTestId("pdp-add-to-cart");
  async function choosePickup() {
    const select = page.getByTestId("pdp-pickup-location-select");
    if (
      await select
        .waitFor({ state: "visible", timeout: 3000 })
        .then(() => true)
        .catch(() => false)
    ) {
      await select.selectOption({ index: 1 });
    }
  }
  await choosePickup();
  await expect(add).toBeEnabled();
  phase = "discard_after_commit";
  await add.click();
  await expect(page.getByTestId("pdp-add-to-cart-error")).toBeVisible();
  assert.equal(routeFailure, undefined);
  point("actual_ui_uncertain_error");
  phase = "actual_browser_retry";
  await add.click();
  await expect(page.getByTestId("pdp-add-to-cart-success")).toBeVisible();
  await expect(page.getByTestId("mini-cart-subtotal")).toHaveText(money(price));
  await expect(page.getByTestId("mini-cart-drawer")).toContainText(
    "Quantity: 1",
  );
  point("replay_quantity_price_ui");
  await page.getByTestId("mini-cart-close").click();
  phase = "price_notice";
  db("price");
  await page.goto(`${origin}/en/cart`);
  const notice = page.getByTestId(`cart-notice-price_changed-${listingId}`);
  await expect(notice).toBeVisible();
  await expect(notice).toContainText(money(price));
  await expect(notice).toContainText(money(price + 100));
  await expect(page.getByTestId("cart-subtotal")).toHaveText(
    money(price + 100),
  );
  await expect(page.getByTestId(`cart-qty-${listingId}-value`)).toHaveText("1");
  point("authoritative_price_notice_ui");
  phase = "fresh_intent";
  await page.goto(`${origin}/en/p/smartphone-x1`);
  await choosePickup();
  await expect(page.getByTestId("pdp-add-to-cart")).toBeEnabled();
  await page.getByTestId("pdp-add-to-cart").click();
  await expect(page.getByTestId("pdp-add-to-cart-success")).toBeVisible();
  await expect(page.getByTestId("mini-cart-subtotal")).toHaveText(
    money(2 * (price + 100)),
  );
  await expect(page.getByTestId("mini-cart-drawer")).toContainText(
    "Quantity: 2",
  );
  point("fresh_quantity_price_ui");
  phase = "stock_notice";
  db("stock");
  const notices = await page.evaluate(async (url) => {
    const response = await fetch(`${url}/cart/revalidate`, {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) throw new Error("stock revalidation failed");
    return response.json();
  }, api);
  const stock = notices.notices.find(
    (n) => n.listing_id === listingId && n.kind === "qty_reduced",
  );
  assert.ok(stock);
  assert.equal(stock.requested_qty, 2);
  assert.equal(stock.available_qty, 1);
  state("stock_revalidated", 2, 2, 2, price + 100);
  point("authoritative_stock_notice_browser_api");
  db("restore-stock");
  assert.equal(posts, 3);
  assert.equal(externalRequests, 0);
  assert.equal(routeFailure, undefined);
  point("exactly_three_real_adds");
  point("no_external_browser_requests");
  // --no-sandbox keeps Chromium subprocesses under the same firewall owner UID.
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
  const children = processRows.filter(([, pid]) =>
    descendants.has(Number(pid)),
  );
  assert.ok(
    children.some(([, , , command]) =>
      /chrome|chromium|headless_shell/.test(command),
    ),
  );
  assert.ok(children.every(([uid]) => uid === process.env.CART_DRILL_UID));
  point("browser_subprocess_uid_covered");
  report.qualified = true;
  delete report.lastNativeObservation;
} catch {
  report.failedPhase = phase;
  process.exitCode = 1;
} finally {
  if (bound) {
    try {
      assert.equal(db("cleanup").cleaned, true);
      point("synthetic_fixture_cleanup");
    } catch {
      report.qualified = false;
      report.failedPhase = "fixture_cleanup";
      process.exitCode = 1;
    }
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
