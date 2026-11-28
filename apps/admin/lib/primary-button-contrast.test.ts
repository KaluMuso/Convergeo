// @vitest-environment node
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * Dark and accent themes set `--primary` to a light colour (#fafafa, #5fc49c,
 * #60a5fa, #fbbf24), so `bg-primary` + `text-white` renders an invisible label.
 * Primary fills must use `text-[var(--primary-btn-fg)]` or
 * `adminPrimaryButtonClass`.
 */

const APP_ROOT = fileURLToPath(new URL("../app", import.meta.url));
const SKIP_DIRS = new Set([".next", "node_modules", "__snapshots__"]);
const BG_PRIMARY = /(?<![\w-])bg-primary(?![\w-])/;
const TEXT_WHITE = /(?<![\w-])text-white(?![\w-])/;

/** Owned by other in-flight tasks; remove an entry once its file is fixed. */
const PENDING = new Set([
  "[locale]/moderation/flags/_components/FlagActionDialog.tsx",
  "[locale]/offers/_components/OffersBoard.tsx",
]);

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

/** Every `className=` value (quoted or a balanced `{...}` expression) plus every single-line string literal. */
function classNameChunks(raw: string): string[] {
  const source = raw.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|\s)\/\/.*$/gm, "$1");
  const chunks: string[] = [];
  const attr = /className=/g;
  let match: RegExpExecArray | null;
  while ((match = attr.exec(source)) !== null) {
    let i = match.index + match[0].length;
    const open = source[i];
    if (open === '"' || open === "'") {
      const end = source.indexOf(open, i + 1);
      if (end > i) chunks.push(source.slice(i + 1, end));
    } else if (open === "{") {
      let depth = 0;
      const start = i;
      for (; i < source.length; i += 1) {
        if (source[i] === "{") depth += 1;
        else if (source[i] === "}") {
          depth -= 1;
          if (depth === 0) break;
        }
      }
      chunks.push(source.slice(start, i + 1));
    }
  }
  for (const literal of source.matchAll(/"([^"\n]*)"|'([^'\n]*)'|`([^`]*)`/g)) {
    chunks.push(literal[1] ?? literal[2] ?? literal[3] ?? "");
  }
  return chunks;
}

function hasInvisiblePrimary(source: string): boolean {
  return classNameChunks(source).some((chunk) => BG_PRIMARY.test(chunk) && TEXT_WHITE.test(chunk));
}

describe("primary buttons stay readable in dark mode", () => {
  const scannedFiles = collectSourceFiles(APP_ROOT);

  it("scans the admin app source tree", () => {
    expect(scannedFiles.length).toBeGreaterThan(50);
  });

  it("detects the broken combination in static, conditional and constant classes", () => {
    expect(hasInvisiblePrimary(`<b className="rounded bg-primary px-3 text-white" />`)).toBe(true);
    expect(
      hasInvisiblePrimary(
        '<b className={`px-4 text-white ${\n  danger ? "bg-danger" : "bg-primary"\n}`} />',
      ),
    ).toBe(true);
    expect(hasInvisiblePrimary(`const cls =\n  "bg-primary px-3 text-white";`)).toBe(true);
  });

  it("allows the theme-aware foreground and unrelated combinations", () => {
    expect(hasInvisiblePrimary(`<b className="bg-primary text-[var(--primary-btn-fg)]" />`)).toBe(
      false,
    );
    expect(hasInvisiblePrimary(`<b className="bg-danger text-white" />`)).toBe(false);
    expect(hasInvisiblePrimary("/** Use instead of `bg-primary text-white`. */")).toBe(false);
    expect(hasInvisiblePrimary(`<b className="bg-primary-soft text-white" />`)).toBe(false);
    expect(
      hasInvisiblePrimary(
        `<><b className="bg-primary text-bg" /><i className="bg-danger text-white" /></>`,
      ),
    ).toBe(false);
  });

  it("no admin source file pairs bg-primary with text-white", () => {
    const offenders = scannedFiles
      .map((file) => relative(APP_ROOT, file).split(sep).join("/"))
      .filter((rel) => !PENDING.has(rel))
      .filter((rel) => hasInvisiblePrimary(readFileSync(join(APP_ROOT, rel), "utf8")));
    expect(offenders).toEqual([]);
  });
});
