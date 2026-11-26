// T50 Batch C — browse grid / vendor directory evidence (360 + 1440, light).
import { mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import puppeteer from "puppeteer";

import { startMockBackend } from "../harness/mock-backend.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const BASE = process.env.CUSTOMER_URL ?? "http://127.0.0.1:3000";
const VIEWPORTS = [
  { name: "360", width: 360, height: 900 },
  { name: "1440", width: 1440, height: 900 },
];
const ROUTES = [
  { name: "vendors", path: "/en/vendors" },
  { name: "events", path: "/en/events" },
  { name: "search", path: "/en/search?q=laptop" },
  { name: "home", path: "/en" },
];

const mock = await startMockBackend({ port: 54331, role: "customer" });
const browser = await puppeteer.launch({ headless: true, args: ["--no-sandbox"] });

try {
  await mkdir(HERE, { recursive: true });
  for (const route of ROUTES) {
    for (const vp of VIEWPORTS) {
      const page = await browser.newPage();
      await page.setViewport(vp);
      await page.goto(`${BASE}${route.path}`, { waitUntil: "networkidle2", timeout: 120_000 });
      const file = join(HERE, `${route.name}-${vp.name}-light.webp`);
      await page.screenshot({ path: file, type: "webp", quality: 72, fullPage: true });
      await page.close();
      console.log("wrote", file);
    }
  }
} finally {
  await browser.close();
  await mock.close();
}