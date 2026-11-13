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
 * The final sweep added the eleventh and last such route,
 * `intake/[sessionId]`: its page body calls `isIntakeRouteAccessible()`, which
 * reads `cookies()`, the feature flag, `supabase.auth.getUser()` and the vendor
 * allowlist on every render. Its flag being off does not make prerendering it
 * safe — a static route risks that runtime failure instead of the clean
 * fail-closed 404 it is supposed to return.
 *
 * SCOPE: segments with a non-locale dynamic param only. This is deliberately
 * NOT an app-wide ban on `generateStaticParams()` — the locale-only export is
 * correct for every single-param segment, and the Vendor app as a whole must
 * not become dynamic.
 */

const APP_DIR = path.dirname(fileURLToPath(import.meta.url));

type ProtectedRoute = {
  label: string;
  segments: readonly string[];
  /** The segment's non-locale dynamic param name. */
  param: string;
  /** Surfaces that must survive the fix. */
  keeps: readonly string[];
};

/**
 * Every server-rendered page with a non-locale dynamic segment that serves
 * authenticated, per-record data. All ten must be `force-dynamic`.
 */
const PROTECTED_DYNAMIC_ROUTES: readonly ProtectedRoute[] = [
  {
    label: "ƒ /[locale]/orders/[id]",
    segments: ["[locale]", "orders", "[id]"],
    param: "id",
    keeps: ["generateMetadata", "setRequestLocale", "OrderDetailView"],
  },
  {
    label: "ƒ /[locale]/events/[id]/scan",
    segments: ["[locale]", "events", "[id]", "scan"],
    param: "id",
    keeps: ["generateMetadata", "setRequestLocale", "ScannerView"],
  },
  {
    label: "ƒ /[locale]/disputes/[id]",
    segments: ["[locale]", "disputes", "[id]"],
    param: "id",
    keeps: ["generateMetadata", "setRequestLocale", "VendorDisputeDetailView"],
  },
  {
    label: "ƒ /[locale]/events/[id]/dashboard",
    segments: ["[locale]", "events", "[id]", "dashboard"],
    param: "id",
    keeps: ["generateMetadata", "setRequestLocale", "EventDashboard"],
  },
  {
    label: "ƒ /[locale]/events/[id]/edit",
    segments: ["[locale]", "events", "[id]", "edit"],
    param: "id",
    keeps: ["generateMetadata", "setRequestLocale", "EventEditView"],
  },
  {
    label: "ƒ /[locale]/events/[id]/roster",
    segments: ["[locale]", "events", "[id]", "roster"],
    param: "id",
    keeps: ["generateMetadata", "setRequestLocale", "RosterView"],
  },
  {
    label: "ƒ /[locale]/events/[id]/tickets",
    segments: ["[locale]", "events", "[id]", "tickets"],
    param: "id",
    keeps: ["generateMetadata", "setRequestLocale", "TicketTypeConfig"],
  },
  {
    label: "ƒ /[locale]/listings/[id]/edit",
    segments: ["[locale]", "listings", "[id]", "edit"],
    param: "id",
    keeps: ["generateMetadata", "setRequestLocale", "ListingEditForm"],
  },
  {
    label: "ƒ /[locale]/services/[id]/edit",
    segments: ["[locale]", "services", "[id]", "edit"],
    param: "id",
    keeps: ["generateMetadata", "setRequestLocale", "ServiceEditView"],
  },
  {
    // Flag-gated (waha_vendor_intake, default off) and still request-specific:
    // isIntakeRouteAccessible() reads cookies(), the flag, auth.getUser() and
    // the vendor allowlist. A disabled route must 404 cleanly, not risk a
    // static-to-dynamic runtime failure.
    label: "ƒ /[locale]/intake/[sessionId]",
    segments: ["[locale]", "intake", "[sessionId]"],
    param: "sessionId",
    keeps: [
      "generateMetadata",
      "setRequestLocale",
      "isIntakeRouteAccessible",
      "notFound",
      "IntakeReview",
    ],
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
const CLIENT_DYNAMIC_ROUTES = [
  {
    label: "/[locale]/jobs/[id]",
    segments: ["[locale]", "jobs", "[id]"],
    param: "id",
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

/** True when a path contains a dynamic segment other than `[locale]`. */
function hasNonLocaleDynamicSegment(file: string): boolean {
  return path
    .relative(APP_DIR, file)
    .split(path.sep)
    .some((segment) => /^\[.+\]$/.test(segment) && segment !== "[locale]");
}

/**
 * Every `page.tsx` under a non-locale dynamic segment, discovered from disk.
 *
 * Deliberately not `[id]`-specific: `intake/[sessionId]` is the route that
 * escaped the previous sweep precisely because its param is not named `id`.
 */
function discoverDynamicPages(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      discoverDynamicPages(full, found);
    } else if (entry.name === "page.tsx" && hasNonLocaleDynamicSegment(full)) {
      found.push(full);
    }
  }
  return found;
}

describe("vendor protected dynamic routes cannot regress to static generation", () => {
  for (const route of PROTECTED_DYNAMIC_ROUTES) {
    describe(route.label, () => {
      it('exports dynamic = "force-dynamic"', () => {
        expect(readCode(routeFile(route.segments))).toMatch(
          /export\s+const\s+dynamic\s*=\s*["']force-dynamic["']\s*;/,
        );
      });

      it("declares no page-level generateStaticParams for the arbitrary param", () => {
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

      it(`still receives both route params (locale + ${route.param})`, () => {
        expect(readCode(routeFile(route.segments))).toMatch(
          new RegExp(
            `params:\\s*Promise<\\{\\s*locale:\\s*string;\\s*${route.param}:\\s*string\\s*\\}>`,
          ),
        );
      });
    });
  }

  for (const route of CLIENT_DYNAMIC_ROUTES) {
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

      it(`still receives both route params (locale + ${route.param})`, () => {
        expect(readCode(routeFile(route.segments))).toMatch(
          new RegExp(
            `params:\\s*Promise<\\{\\s*locale:\\s*string;\\s*${route.param}:\\s*string\\s*\\}>`,
          ),
        );
      });
    });
  }

  it("the inventory is exhaustive — every non-locale dynamic page on disk is covered", () => {
    // The real guard against this defect returning: a NEW dynamic route added
    // later is caught here instead of in a staging 500. Discovery is from the
    // filesystem, so the table cannot silently fall behind the app.
    //
    // Matching ANY non-locale dynamic segment, not just `[id]`, is the lesson
    // from intake/[sessionId]: it survived the previous sweep only because its
    // param happens to be named something else.
    const discovered = discoverDynamicPages(APP_DIR).sort();
    const covered = [...PROTECTED_DYNAMIC_ROUTES, ...CLIENT_DYNAMIC_ROUTES]
      .map((route) => routeFile(route.segments))
      .sort();

    expect(discovered).toEqual(covered);
    expect(discovered).toHaveLength(11);
  });

  it("no ancestor segment forces these routes back to static", () => {
    // A `force-static` (or `dynamicParams = false`) on an ancestor layout
    // would override the page-level intent. Walk the REAL chain from each
    // route file up to app/, so a layout added later is covered automatically.
    const ancestors = new Set<string>();
    for (const route of [...PROTECTED_DYNAMIC_ROUTES, ...CLIENT_DYNAMIC_ROUTES]) {
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
      ["[locale]", "intake", "page.tsx"],
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
