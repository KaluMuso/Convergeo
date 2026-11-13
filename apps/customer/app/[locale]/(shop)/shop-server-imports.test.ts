// @vitest-environment node
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * Acceptance guard for a Next.js App Router footgun that shipped live twice in
 * this route group: a "use client" module exporting a plain data constant
 * (`export const SERVICE_VERTICALS = [...]`, `export const EVENT_CATEGORIES =
 * [...]`), imported by value into a Server Component page. In the production
 * RSC build the client module's non-component exports don't come through as
 * the real value, so `[...SERVICE_VERTICALS]` / `EVENT_CATEGORIES.includes`
 * threw `TypeError`s in production (`/services`, `/events` — see
 * services/_components/service-verticals.ts and
 * _components/events/event-taxonomy.ts for the fix: such constants now live in
 * a plain module with no "use client" directive that both the client
 * component and the server page import from).
 *
 * This scans every non-"use client" file in this route group and fails if it
 * imports a SCREAMING_SNAKE_CASE binding *by value* (not `type`-only) from a
 * "use client" module — the exact shape of both live incidents.
 */

const SHOP_ROOT = fileURLToPath(new URL(".", import.meta.url));
const SKIP_DIRS = new Set(["node_modules", "__snapshots__"]);
const CONST_NAME = /^[A-Z][A-Z0-9_]*$/;

function collectSourceFiles(dir: string): string[] {
  if (!existsSync(dir)) {
    return [];
  }
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!SKIP_DIRS.has(entry.name)) {
        out.push(...collectSourceFiles(full));
      }
    } else if (/\.tsx?$/.test(entry.name) && !/\.(test|spec)\.tsx?$/.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

function isUseClient(source: string): boolean {
  const firstStatement = source.trimStart().split("\n", 1)[0]?.trim();
  return firstStatement === '"use client";' || firstStatement === "'use client';";
}

/** SCREAMING_SNAKE_CASE `export const NAME = ...` bindings — the data-constant convention this repo uses. */
function exportedConstNames(source: string): string[] {
  const names: string[] = [];
  const re = /^export const ([A-Za-z_][A-Za-z0-9_]*)\s*=/gm;
  let match: RegExpExecArray | null;
  while ((match = re.exec(source))) {
    const name = match[1];
    if (name && CONST_NAME.test(name)) {
      names.push(name);
    }
  }
  return names;
}

/** Named import specifiers from relative-path imports, split into (name, isTypeOnly) pairs. */
function relativeImports(source: string): Array<{ from: string; specifiers: string[] }> {
  const out: Array<{ from: string; specifiers: string[] }> = [];
  const re = /import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+["'](\.[^"']+)["']/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(source))) {
    const body = match[1];
    const from = match[2];
    if (!body || !from) {
      continue;
    }
    const specifiers = body
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .filter((s) => !s.startsWith("type ")) // drop type-only specifiers — erased at compile time, no RSC boundary risk
      .map((s) => (s.split(/\s+as\s+/)[0] ?? s).trim());
    out.push({ from, specifiers });
  }
  return out;
}

function resolveRelative(fromFile: string, specifier: string): string | null {
  const base = resolve(dirname(fromFile), specifier);
  for (const candidate of [
    base,
    `${base}.ts`,
    `${base}.tsx`,
    join(base, "index.ts"),
    join(base, "index.tsx"),
  ]) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

describe("shop route group: no server import of a use-client data constant by value", () => {
  const allFiles = collectSourceFiles(SHOP_ROOT);

  it("actually scanned the shop route group (guard is wired, not vacuous)", () => {
    expect(allFiles.length).toBeGreaterThan(50);
  });

  it('service-verticals.ts and event-taxonomy.ts are plain modules (no "use client")', () => {
    const guardModules = [
      join(SHOP_ROOT, "services/_components/service-verticals.ts"),
      join(SHOP_ROOT, "_components/events/event-taxonomy.ts"),
    ];
    for (const file of guardModules) {
      expect(existsSync(file), file).toBe(true);
      expect(isUseClient(readFileSync(file, "utf8"))).toBe(false);
    }
  });

  it("no non-client file imports a use-client module's data constant by value", () => {
    const useClientConsts = new Map<string, string[]>();
    for (const file of allFiles) {
      const source = readFileSync(file, "utf8");
      if (isUseClient(source)) {
        const names = exportedConstNames(source);
        if (names.length > 0) {
          useClientConsts.set(file, names);
        }
      }
    }

    const offenders: string[] = [];
    for (const file of allFiles) {
      const source = readFileSync(file, "utf8");
      if (isUseClient(source)) {
        continue; // client-to-client imports don't cross the RSC boundary
      }
      for (const { from, specifiers } of relativeImports(source)) {
        const resolved = resolveRelative(file, from);
        if (!resolved) {
          continue;
        }
        const flaggedNames = useClientConsts.get(resolved);
        if (!flaggedNames) {
          continue;
        }
        for (const specifier of specifiers) {
          if (flaggedNames.includes(specifier)) {
            offenders.push(
              `${relative(SHOP_ROOT, file).split(sep).join("/")} imports ${specifier} (value) from ${relative(SHOP_ROOT, resolved).split(sep).join("/")}`,
            );
          }
        }
      }
    }

    expect(offenders).toEqual([]);
  });
});
