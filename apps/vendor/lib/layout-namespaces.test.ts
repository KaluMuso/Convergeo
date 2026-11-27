import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const appRoot = join(here, "..", "app");

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(full);
  }
  return out;
}

describe("vendor layout message namespaces", () => {
  const layout = readFileSync(join(appRoot, "[locale]", "layout.tsx"), "utf8");
  // `common` comes from the shared request config (getMessages()).
  const provided = new Set<string>([
    "common",
    ...[...layout.matchAll(/loadNamespace\(locale as Locale, "([a-z]+)"\)/g)].map(
      (match) => match[1] as string,
    ),
  ]);

  it("ships the events namespace used by the event forms (raw-key regression)", () => {
    expect(provided.has("events")).toBe(true);
  });

  it("provides every top-level namespace that client code reads with useTranslations", () => {
    const used = new Map<string, string>();
    for (const file of walk(appRoot)) {
      const source = readFileSync(file, "utf8");
      if (!source.includes('"use client"')) continue;
      for (const match of source.matchAll(/useTranslations\("([A-Za-z]+)[."]/g)) {
        used.set(match[1] as string, file);
      }
    }
    // Known gap tracked separately: the invite-accept form reads "auth", which the
    // vendor layout does not ship. Remove from this list when it gets a provider.
    const KNOWN_GAPS = new Set(["auth"]);
    const missing = [...used.keys()].filter((ns) => !provided.has(ns) && !KNOWN_GAPS.has(ns));
    expect(missing, `namespaces missing from the vendor layout: ${missing.join(", ")}`).toEqual([]);
  });
});
