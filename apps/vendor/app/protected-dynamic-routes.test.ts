import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * Protected dynamic-route contract (staging run 35456698878, attempt 1).
 *
 * The Vendor preview (dpl_CR6g8CaZas9LMVBFdEUUU5zhcGg4) returned HTTP 500 for
 *
 *   /en/orders/fc09ff52-3a68-4cae-af31-732808ccb27e
 *   /en/events/e1000000-0000-4000-8000-000000000001/scan
 *
 * with the runtime class "Page changed from static to dynamic at runtime": an
 * authenticated, `no-store` request was served by a route Next.js had
 * classified as static.
 *
 * Both segments carry TWO dynamic params — `[locale]` AND `[id]` — but each
 * page exported a `generateStaticParams()` returning locales only. `id` is an
 * arbitrary UUID: there is no enumerable set, so no `generateStaticParams()`
 * on these segments can ever be correct, and the routes must be dynamic.
 *
 * These assertions read the real page sources, so they fail if either fix is
 * reverted — a build-output check alone would need a full `next build` and
 * could not run in `pnpm --filter vendor test`. The build classification
 * (`ƒ /[locale]/orders/[id]`, `ƒ /[locale]/events/[id]/scan`) is verified
 * separately by the Vendor production build.
 *
 * SCOPE: exactly these two routes. This is deliberately NOT an app-wide ban on
 * `generateStaticParams()` — the locale-only export is correct for every
 * single-param segment, and the Vendor app as a whole must not become dynamic.
 */

const APP_DIR = path.dirname(fileURLToPath(import.meta.url));

/** Route segments that serve authenticated, per-record data under an `[id]`. */
const PROTECTED_ID_ROUTES = [
  {
    label: "ƒ /[locale]/orders/[id]",
    file: path.join(APP_DIR, "[locale]", "orders", "[id]", "page.tsx"),
    /** Surfaces that must survive the fix. */
    keeps: ["generateMetadata", "setRequestLocale", "OrderDetailView"],
  },
  {
    label: "ƒ /[locale]/events/[id]/scan",
    file: path.join(APP_DIR, "[locale]", "events", "[id]", "scan", "page.tsx"),
    keeps: ["generateMetadata", "setRequestLocale", "ScannerView"],
  },
] as const;

/** Strips comments so prose about a pattern never counts as live code. */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !line.trim().startsWith("//"))
    .join("\n");
}

function readRoute(file: string): { source: string; code: string } {
  const source = readFileSync(file, "utf8");
  return { source, code: stripComments(source) };
}

describe("vendor protected [id] routes cannot regress to static generation", () => {
  for (const route of PROTECTED_ID_ROUTES) {
    describe(route.label, () => {
      it('exports dynamic = "force-dynamic"', () => {
        const { code } = readRoute(route.file);
        expect(code).toMatch(/export\s+const\s+dynamic\s*=\s*["']force-dynamic["']\s*;/);
      });

      it("declares no page-level generateStaticParams for the arbitrary [id]", () => {
        const { code } = readRoute(route.file);
        expect(code).not.toMatch(/generateStaticParams/);
      });

      it("does not re-enable prerendering through a sibling export", () => {
        const { code } = readRoute(route.file);
        // `force-static` / `dynamicParams = false` / `revalidate` would each
        // undo the fix while leaving the force-dynamic line in place.
        expect(code).not.toMatch(/["']force-static["']/);
        expect(code).not.toMatch(/export\s+const\s+dynamicParams\s*=/);
        expect(code).not.toMatch(/export\s+const\s+revalidate\s*=/);
      });

      it("keeps metadata, locale binding and the protected view intact", () => {
        const { code } = readRoute(route.file);
        for (const kept of route.keeps) {
          expect(code).toContain(kept);
        }
      });

      it("still receives both route params", () => {
        const { code } = readRoute(route.file);
        expect(code).toMatch(/params:\s*Promise<\{\s*locale:\s*string;\s*id:\s*string\s*\}>/);
      });
    });
  }

  it("no ancestor segment forces these routes back to static", () => {
    // A `force-static` (or `dynamicParams = false`) on an ancestor layout
    // would override the page-level intent. Walk the REAL chain from each
    // route file up to app/, so a layout added later is covered automatically.
    const ancestors = new Set<string>();
    for (const route of PROTECTED_ID_ROUTES) {
      let dir = path.dirname(route.file);
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
    // The root locale layout is on both chains — a zero-length walk would
    // make this assertion vacuous.
    expect(ancestors.has(path.join(APP_DIR, "[locale]", "layout.tsx"))).toBe(true);

    for (const file of ancestors) {
      const source = stripComments(readFileSync(file, "utf8"));
      expect(source, `${file} forces static rendering`).not.toMatch(/["']force-static["']/);
      expect(source, `${file} disables dynamicParams`).not.toMatch(
        /export\s+const\s+dynamicParams\s*=\s*false/,
      );
    }
  });

  it("the fix is scoped — the Vendor app is not made dynamic wholesale", () => {
    // The single-param locale segments keep their (correct) static params, so
    // a blanket force-dynamic regression is caught here rather than in a build.
    const stillStatic = [
      path.join(APP_DIR, "[locale]", "page.tsx"),
      path.join(APP_DIR, "[locale]", "orders", "page.tsx"),
      path.join(APP_DIR, "[locale]", "events", "page.tsx"),
    ];
    for (const file of stillStatic) {
      const code = stripComments(readFileSync(file, "utf8"));
      expect(code, `${file} lost its locale generateStaticParams`).toMatch(/generateStaticParams/);
      expect(code, `${file} was made dynamic outside the repair scope`).not.toMatch(
        /export\s+const\s+dynamic\s*=\s*["']force-dynamic["']/,
      );
    }
  });
});
