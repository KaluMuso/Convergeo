// @vitest-environment node
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * Acceptance guard: `getTranslations("admin.xxx")` from `next-intl/server`
 * reads the ambient request-config messages, which ship `common` alone
 * (packages/i18n/src/request.ts). The "admin" namespace is loaded explicitly
 * by the layout for the client provider, but that never reaches server-side
 * `getTranslations()` calls — every admin page header silently rendered the
 * raw key ("title", "subtitle") in production instead of a real label
 * (MISSING_MESSAGE: admin.dashboard, 238 live occurrences). Fixed by routing
 * every such call through lib/admin-translator.ts's getAdminTranslator,
 * which explicitly loads the "admin" namespace.
 *
 * This scans every non-test source file under app/ and fails if
 * `getTranslations` is called with an "admin" (or "admin.…") namespace
 * argument — the exact shape of the incident.
 */

const APP_ROOT = fileURLToPath(new URL(".", import.meta.url));
const SKIP_DIRS = new Set([".next", "node_modules", "__snapshots__"]);
const BROKEN_CALL = /getTranslations\(\s*["']admin(\.[^"']*)?["']\s*\)/g;

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

describe('admin app: no ambient getTranslations("admin...") calls', () => {
  const scannedFiles = collectSourceFiles(APP_ROOT);

  it("actually scanned the admin app source tree (guard is wired, not vacuous)", () => {
    expect(scannedFiles.length).toBeGreaterThan(50);
  });

  it("no server file calls getTranslations with an admin namespace — use getAdminTranslator instead", () => {
    const offenders: string[] = [];
    for (const file of scannedFiles) {
      const source = readFileSync(file, "utf8");
      if (BROKEN_CALL.test(source)) {
        offenders.push(relative(APP_ROOT, file).split(sep).join("/"));
      }
      BROKEN_CALL.lastIndex = 0;
    }
    expect(offenders).toEqual([]);
  });
});
