import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * Protected arbitrary-ID route contract for the whole Vendor app.
 *
 * Origin (staging run 35456698878, attempt 1): the Vendor preview
 * dpl_CR6g8CaZas9LMVBFdEUUU5zhcGg4 returned HTTP 500 for
 *
 *   /en/orders/fc09ff52-3a68-4cae-af31-732808ccb27e
 *   /en/events/e1000000-0000-4000-8000-000000000001/scan
 *
 * with the runtime class "Page changed from static to dynamic at runtime": an
 * authenticated, `no-store` request was served by a route Next.js had
 * classified as static.
 *
 * Independent review of the first repair found the same defect class still
 * live on seven more segments — `disputes/[id]`, the four remaining
 * `events/[id]/*` pages, `listings/[id]/edit` and `services/[id]/edit`. The
 * root cause is uniform: each segment carries TWO dynamic params (`[locale]`
 * AND `[id]`) while its `generateStaticParams()` supplied only the locale
 * (`disputes/[id]` was worse still — it pinned one all-zero dummy UUID). `id`
 * is an arbitrary UUID, so no `generateStaticParams()` on these segments can
 * ever be correct.
 *
 * It is not only the page bodies that need a request: the shared vendor locale
 * layout resolves nav capabilities per request via `cookies()`, an
 * authenticated Supabase `auth.getUser()` and `cache: "no-store"` API probes,
 * so every one of these routes is request-specific by construction.
 *
 * These assertions read the real page sources, so they fail the moment a fix
 * is reverted — a build-output check alone would need a full `next build` and
 * could not run in `pnpm --filter vendor test`. The production route
 * classification (`ƒ` for all ten `[id]` routes) is verified separately by the
 * Vendor build.
 *
 * SCOPE: arbitrary-ID segments only. This is deliberately NOT an app-wide ban
 * on `generateStaticParams()` — the locale-only export is correct for every
 * single-param segment, and the Vendor app as a whole must not become dynamic.
 */

const APP_DIR = path.dirname(fileURLToPath(import.meta.url));

type ProtectedRoute = {
  label: string;
  segments: readonly string[];
  /** Surfaces that must survive the fix. */
  keeps: readonly string[];
};

/**
 * Every server-rendered `[id]` page that serves authenticated, per-record data.
 * All nine must be `force-dynamic`.
 */
const PROTECTED_ID_ROUTES: readonly ProtectedRoute[] = [
  {
    label: "ƒ /[locale]/orders/[id]",
    segments: ["[locale]", "orders", "[id]"],
    keeps: ["generateMetadata", "setRequestLocale", "OrderDetailView"],
  },
  {
    label: "ƒ /[locale]/events/[id]/scan",
    segments: ["[locale]", "events", "[id]", "scan"],
    keeps: ["generateMetadata", "setRequestLocale", "ScannerView"],
  },
  {
    label: "ƒ /[locale]/disputes/[id]",
    segments: ["[locale]", "disputes", "[id]"],
    keeps: ["generateMetadata", "setRequestLocale", "VendorDisputeDetailView"],
  },
  {
    label: "ƒ /[locale]/events/[id]/dashboard",
    segments: ["[locale]", "events", "[id]", "dashboard"],
    keeps: ["generateMetadata", "setRequestLocale", "EventDashboard"],
  },
  {
    label: "ƒ /[locale]/events/[id]/edit",
    segments: ["[locale]", "events", "[id]", "edit"],
    keeps: ["generateMetadata", "setRequestLocale", "EventEditView"],
  },
  {
    label: "ƒ /[locale]/events/[id]/roster",
    segments: ["[locale]", "events", "[id]", "roster"],
    keeps: ["generateMetadata", "setRequestLocale", "RosterView"],
  },
  {
    label: "ƒ /[locale]/events/[id]/tickets",
    segments: ["[locale]", "events", "[id]", "tickets"],
    keeps: ["generateMetadata", "setRequestLocale", "TicketTypeConfig"],
  },
  {
    label: "ƒ /[locale]/listings/[id]/edit",
    segments: ["[locale]", "listings", "[id]", "edit"],
    keeps: ["generateMetadata", "setRequestLocale", "ListingEditForm"],
  },
  {
    label: "ƒ /[locale]/services/[id]/edit",
    segments: ["[locale]", "services", "[id]", "edit"],
    keeps: ["generateMetadata", "setRequestLocale", "ServiceEditView"],
  },
] as const;

/**
 * `[id]` pages that are NOT server-rendered wrappers.
 *
 * `jobs/[id]` is a `"use client"` page: it never had a `generateStaticParams`,
 * reads its params through a `useEffect`, and Next already classifies it `ƒ`.
 * It is inventoried here rather than converted, so that it stays covered
 * against someone adding an incomplete `generateStaticParams` to it later —
 * which is exactly how the other nine acquired this defect.
 */
const CLIENT_ID_ROUTES = [
  {
    label: "/[locale]/jobs/[id]",
    segments: ["[locale]", "jobs", "[id]"],
  },
] as const;

function routeFile(segments: readonly string[]): string {
  return path.join(APP_DIR, ...segments, "page.tsx");
}

/** Strips comments so prose about a pattern never counts as live code. */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !line.trim().startsWith("//"))
    .join("\n");
}

function readCode(file: string): string {
  return stripComments(readFileSync(file, "utf8"));
}

/** Every `page.tsx` under a directory named `[id]`, discovered from disk. */
function discoverIdPages(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      discoverIdPages(full, found);
    } else if (entry.name === "page.tsx" && full.includes(`${path.sep}[id]${path.sep}`)) {
      found.push(full);
    }
  }
  return found;
}

describe("vendor protected [id] routes cannot regress to static generation", () => {
  for (const route of PROTECTED_ID_ROUTES) {
    describe(route.label, () => {
      it('exports dynamic = "force-dynamic"', () => {
        expect(readCode(routeFile(route.segments))).toMatch(
          /export\s+const\s+dynamic\s*=\s*["']force-dynamic["']\s*;/,
        );
      });

      it("declares no page-level generateStaticParams for the arbitrary [id]", () => {
        expect(readCode(routeFile(route.segments))).not.toMatch(/generateStaticParams/);
      });

      it("does not re-enable prerendering through a sibling export", () => {
        const code = readCode(routeFile(route.segments));
        // `force-static` / `dynamicParams = false` / `revalidate` would each
        // undo the fix while leaving the force-dynamic line in place.
        expect(code).not.toMatch(/["']force-static["']/);
        expect(code).not.toMatch(/export\s+const\s+dynamicParams\s*=/);
        expect(code).not.toMatch(/export\s+const\s+revalidate\s*=/);
      });

      it("keeps metadata, locale binding and the protected view intact", () => {
        const code = readCode(routeFile(route.segments));
        for (const kept of route.keeps) {
          expect(code).toContain(kept);
        }
      });

      it("still receives both route params", () => {
        expect(readCode(routeFile(route.segments))).toMatch(
          /params:\s*Promise<\{\s*locale:\s*string;\s*id:\s*string\s*\}>/,
        );
      });
    });
  }

  for (const route of CLIENT_ID_ROUTES) {
    describe(`${route.label} (client page — inventoried, not converted)`, () => {
      it("is a client component, so it is not a server prerender candidate", () => {
        expect(readFileSync(routeFile(route.segments), "utf8")).toMatch(/^\s*"use client";/m);
      });

      it("introduces no incomplete generateStaticParams contract", () => {
        // The defect the other nine had: a generateStaticParams that cannot
        // enumerate `id`. Adding one here would reintroduce it.
        expect(readCode(routeFile(route.segments))).not.toMatch(/generateStaticParams/);
      });

      it("does not opt into prerendering through a route-segment export", () => {
        const code = readCode(routeFile(route.segments));
        expect(code).not.toMatch(/["']force-static["']/);
        expect(code).not.toMatch(/export\s+const\s+dynamicParams\s*=/);
        expect(code).not.toMatch(/export\s+const\s+revalidate\s*=/);
      });

      it("still receives both route params", () => {
        expect(readCode(routeFile(route.segments))).toMatch(
          /params:\s*Promise<\{\s*locale:\s*string;\s*id:\s*string\s*\}>/,
        );
      });
    });
  }

  it("the inventory is exhaustive — every [id] page on disk is covered", () => {
    // The real guard against this defect returning: a NEW [id] route added
    // later is caught here instead of in a staging 500. Discovery is from the
    // filesystem, so the table cannot silently fall behind the app.
    const discovered = discoverIdPages(APP_DIR).sort();
    const covered = [...PROTECTED_ID_ROUTES, ...CLIENT_ID_ROUTES]
      .map((route) => routeFile(route.segments))
      .sort();

    expect(discovered).toEqual(covered);
    expect(discovered).toHaveLength(10);
  });

  it("no ancestor segment forces these routes back to static", () => {
    // A `force-static` (or `dynamicParams = false`) on an ancestor layout
    // would override the page-level intent. Walk the REAL chain from each
    // route file up to app/, so a layout added later is covered automatically.
    const ancestors = new Set<string>();
    for (const route of [...PROTECTED_ID_ROUTES, ...CLIENT_ID_ROUTES]) {
      let dir = path.dirname(routeFile(route.segments));
      while (dir.startsWith(APP_DIR)) {
        const layout = path.join(dir, "layout.tsx");
        if (existsSync(layout)) {
          ancestors.add(layout);
        }
        if (dir === APP_DIR) {
          break;
        }
        dir = path.dirname(dir);
      }
    }
    // The root locale layout is on every chain — a zero-length walk would
    // make this assertion vacuous.
    expect(ancestors.has(path.join(APP_DIR, "[locale]", "layout.tsx"))).toBe(true);

    for (const file of ancestors) {
      const code = readCode(file);
      expect(code, `${file} forces static rendering`).not.toMatch(/["']force-static["']/);
      expect(code, `${file} disables dynamicParams`).not.toMatch(
        /export\s+const\s+dynamicParams\s*=\s*false/,
      );
    }
  });

  it("the shared locale layout is unchanged and still resolves params per locale", () => {
    // The repair is page-level on purpose. Forcing the LAYOUT dynamic would
    // make the whole Vendor app request-rendered, which is out of scope.
    const code = readCode(path.join(APP_DIR, "[locale]", "layout.tsx"));
    expect(code).toMatch(/generateStaticParams/);
    expect(code).not.toMatch(/export\s+const\s+dynamic\s*=\s*["']force-dynamic["']/);
  });

  it("the fix is scoped — the Vendor app is not made dynamic wholesale", () => {
    // The single-param locale segments keep their (correct) static params, so
    // a blanket force-dynamic regression is caught here rather than in a build.
    const stillStatic = [
      ["[locale]", "page.tsx"],
      ["[locale]", "orders", "page.tsx"],
      ["[locale]", "events", "page.tsx"],
      ["[locale]", "disputes", "page.tsx"],
      ["[locale]", "listings", "page.tsx"],
      ["[locale]", "services", "page.tsx"],
    ];
    for (const segments of stillStatic) {
      const file = path.join(APP_DIR, ...segments);
      const code = readCode(file);
      expect(code, `${file} lost its locale generateStaticParams`).toMatch(/generateStaticParams/);
      expect(code, `${file} was made dynamic outside the repair scope`).not.toMatch(
        /export\s+const\s+dynamic\s*=\s*["']force-dynamic["']/,
      );
    }
  });
});
