// Signed-in WebP screenshots of the three portals against the loopback
// fixture backend. See README.md for how to run the dev servers.
//
//   node docs/ops/screenshots/harness/capture.mjs <customer|vendor|admin> [route-name ...]
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import puppeteer from "puppeteer";

import { startMockBackend } from "./mock-backend.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const MAX_BYTES = 80 * 1024;

const VIEWPORTS = [
  { name: "360", width: 360, height: 780, isMobile: true, hasTouch: true },
  { name: "1280", width: 1280, height: 800 },
];
const THEMES = ["light", "dark"];
const QUICK = process.env.QUICK === "1";

// Report-only CSP notice from the existing middleware policy; failed loads are
// reported per URL by the response listener (and per path as unfixtured calls).
const IGNORED_CONSOLE = [/upgrade-insecure-requests/, /^Failed to load resource/];
// Not served by `next dev` (Serwist is disabled in development).
const DEV_ONLY_PATHS = new Set(["/sw.js", "/favicon.ico"]);

const APPS = {
  customer: {
    task: "t32",
    base: process.env.CUSTOMER_URL ?? "http://127.0.0.1:3000",
    mockPort: 54331,
    roles: ["customer"],
    routes: [
      { name: "home", path: "/en", signedIn: false, height: { 360: 1400, 1280: 1000 } },
      {
        name: "home-empty",
        path: "/en",
        signedIn: false,
        emptyApi: true,
        height: { 360: 1400, 1280: 1300 },
      },
      { name: "account", path: "/en/account" },
      { name: "orders", path: "/en/account/orders" },
      { name: "cart", path: "/en/cart" },
      { name: "vendors", path: "/en/vendors", signedIn: false },
      { name: "search", path: "/en/search?q=laptop", signedIn: false },
      { name: "categories", path: "/en/categories", signedIn: false },
      { name: "help", path: "/en/help", signedIn: false },
    ],
  },
  vendor: {
    task: "t33",
    base: process.env.VENDOR_URL ?? "http://127.0.0.1:3001",
    mockPort: 54332,
    roles: ["customer", "vendor"],
    routes: [
      { name: "home", path: "/en" },
      { name: "products", path: "/en/listings" },
      { name: "orders", path: "/en/orders" },
      { name: "profile", path: "/en/profile" },
      { name: "payouts", path: "/en/payouts" },
      { name: "analytics", path: "/en/analytics" },
      { name: "login", path: "/en/login", signedIn: false },
    ],
  },
  admin: {
    task: "t34",
    base: process.env.ADMIN_URL ?? "http://127.0.0.1:3002",
    mockPort: 54333,
    roles: ["customer", "superadmin"],
    routes: [
      { name: "overview", path: "/en" },
      { name: "kyc", path: "/en/kyc" },
      { name: "vendors", path: "/en/trials" },
      { name: "orders", path: "/en/orders?status=placed" },
      { name: "login", path: "/en/login", signedIn: false },
    ],
  },
};

async function encodeWithinBudget(page) {
  for (const quality of [72, 62, 52, 44, 36, 30]) {
    const data = await page.screenshot({ type: "webp", quality, captureBeyondViewport: false });
    if (data.length <= MAX_BYTES) return { data, quality };
  }
  throw new Error(`screenshot over ${MAX_BYTES} bytes at the lowest quality`);
}

/** Count the Next.js dev-overlay "Issues" badge, or 0 when it is absent. */
async function devIssueCount(page) {
  return page.evaluate(() => {
    const root = document.querySelector("nextjs-portal")?.shadowRoot;
    const count = root?.querySelector("[data-issues-count]")?.textContent ?? "0";
    return Number(count) || 0;
  });
}

/** Opens the dev overlay and returns the first issue's text (after the screenshot). */
async function devIssueText(page) {
  return page.evaluate(async () => {
    const root = document.querySelector("nextjs-portal")?.shadowRoot;
    const open = root?.querySelector("[data-issues-open]");
    if (!root || !open) return "";
    open.click();
    await new Promise((resolve) => setTimeout(resolve, 800));
    const dialog = root.querySelector("[role=dialog]") ?? root;
    return (dialog.textContent ?? "").replace(/\s+/g, " ").slice(0, 400);
  });
}

async function main() {
  const [appName, ...only] = process.argv.slice(2);
  const app = APPS[appName];
  if (!app) throw new Error(`usage: capture.mjs <${Object.keys(APPS).join("|")}> [route ...]`);
  const outDir = join(HERE, "..", app.task);
  await mkdir(outDir, { recursive: true });

  const backend = await startMockBackend({ port: app.mockPort });
  backend.setRoles(app.roles);
  const browser = await puppeteer.launch({ headless: true, args: ["--no-sandbox"] });
  const problems = [];

  try {
    for (const route of app.routes) {
      if (only.length > 0 && !only.includes(route.name)) continue;
      for (const viewport of QUICK ? VIEWPORTS.slice(1) : VIEWPORTS) {
        for (const theme of QUICK ? THEMES.slice(0, 1) : THEMES) {
          backend.setEmptyApi(route.emptyApi === true);
          const context = await browser.createBrowserContext();
          const page = await context.newPage();
          if (route.emptyApi) {
            // A hard-reload header makes `next dev` skip its server fetch cache.
            await page.setExtraHTTPHeaders({ "cache-control": "no-cache" });
          }
          await page.setViewport({ ...viewport, height: route.height?.[viewport.name] ?? viewport.height });
          await page.emulateMediaFeatures([
            { name: "prefers-color-scheme", value: theme },
            { name: "prefers-reduced-motion", value: "reduce" },
          ]);
          const consoleErrors = [];
          page.on("console", (message) => {
            const text = message.text();
            if (message.type() !== "error" || IGNORED_CONSOLE.some((pattern) => pattern.test(text))) {
              return;
            }
            consoleErrors.push(text);
          });
          page.on("response", (response) => {
            const url = new URL(response.url());
            if (response.status() >= 400 && url.origin === app.base && !DEV_ONLY_PATHS.has(url.pathname)) {
              consoleErrors.push(`HTTP ${response.status()} ${url.pathname}`);
            }
          });
          if (route.signedIn !== false) {
            const cookie = backend.sessionCookie();
            await context.setCookie({ ...cookie, url: app.base, sameSite: "Lax" });
          }
          await page.goto(`${app.base}${route.path}`, { waitUntil: "networkidle0", timeout: 120_000 });
          await new Promise((resolve) => setTimeout(resolve, 1500));
          const finalUrl = new URL(page.url());
          const finalPath = `${finalUrl.pathname}${finalUrl.search}`;
          if (finalPath !== route.path) {
            problems.push(`${route.name}: redirected to ${finalPath}`);
          }
          for (const error of consoleErrors) problems.push(`${route.name}: console error: ${error.slice(0, 240)}`);
          const issues = await devIssueCount(page);
          if (issues === 0) {
            // Only the idle dev-tools "N" button is left; it is dev-only chrome.
            await page.evaluate(() => document.querySelector("nextjs-portal")?.remove());
          }
          const { data, quality } = await encodeWithinBudget(page);
          const file = `${route.name}-${viewport.name}-${theme}.webp`;
          await writeFile(join(outDir, file), data);
          console.log(`${file} ${(data.length / 1024).toFixed(1)} KB q${quality}`);
          if (issues > 0) {
            problems.push(
              `${route.name} ${viewport.name} ${theme}: ${issues} dev issue(s): ${await devIssueText(page)}`,
            );
          }
          await context.close();
        }
      }
    }
  } finally {
    await browser.close();
    await backend.close();
  }

  if (backend.unhandled.size > 0) {
    console.log("\nUnfixtured API calls:");
    for (const [key, count] of backend.unhandled) console.log(`  ${key} ×${count}`);
  }
  if (problems.length > 0) {
    console.log("\nProblems:");
    for (const problem of [...new Set(problems)]) console.log(`  ${problem}`);
    process.exitCode = 1;
  }
}

await main();
