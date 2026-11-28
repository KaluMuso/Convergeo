// @vitest-environment node
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { resolveAdminActiveItem } from "./[locale]/_components/admin-nav-config";

/**
 * Route contract for every admin page.
 *
 * 1. Every page that renders inside the permission shell must resolve to an admin
 *    nav item. The shell denies a route with no nav item to any restricted role
 *    (fail closed), so a new page that nobody wired into the nav silently becomes
 *    superadmin-only: this test makes that a reviewed decision instead.
 * 2. Every server page exports a document title (`generateMetadata`), so browser
 *    tabs and history entries are not all just "Convergeo Admin".
 */
const LOCALE_ROOT = join(fileURLToPath(new URL(".", import.meta.url)), "[locale]");

// Auth/recovery screens render bare (no shell); the notifications page is the one
// personal surface the shell lets every admin open (see `isPersonalRoute`).
const NO_NAV_ITEM = new Set(["/permission-denied", "/login", "/reset-password", "/notifications"]);
// Client component page: titles come from its own AdminPageClient header.
const NO_METADATA = new Set(["/notifications"]);

function pageRoutes(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "_components" || entry.name === "node_modules") continue;
      pageRoutes(path, out);
    } else if (entry.name === "page.tsx" && existsSync(path)) {
      out.push(path);
    }
  }
  return out;
}

const pages = pageRoutes(LOCALE_ROOT).map((file) => {
  const rest = relative(LOCALE_ROOT, join(file, ".."))
    .split(sep)
    .filter((segment) => !/^\(.*\)$/.test(segment))
    .join("/");
  return { file, route: rest ? `/${rest}` : "/", source: readFileSync(file, "utf8") };
});

describe("admin page contract", () => {
  it("finds the admin pages", () => {
    expect(pages.length).toBeGreaterThan(50);
  });

  it("maps every shell page to a nav item (restricted roles fail closed otherwise)", () => {
    const unmapped = pages
      .map((page) => page.route.replace(/\/\[[^\]]+\]/g, "/x"))
      .filter(
        (route) =>
          !NO_NAV_ITEM.has(route) &&
          !route.startsWith("/reset-password") &&
          resolveAdminActiveItem(route) === undefined,
      );
    expect(unmapped).toEqual([]);
  });

  it("exports generateMetadata from every server page", () => {
    const missing = pages
      .filter(
        (page) =>
          !NO_METADATA.has(page.route) &&
          !page.route.startsWith("/login") &&
          !page.route.startsWith("/reset-password") &&
          !page.route.startsWith("/permission-denied") &&
          !/export (async )?function generateMetadata/.test(page.source),
      )
      .map((page) => page.route);
    expect(missing).toEqual([]);
  });
});
