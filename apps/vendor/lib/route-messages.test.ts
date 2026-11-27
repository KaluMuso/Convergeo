import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

import { loadNamespace, type Locale } from "@vergeo/i18n";
import { describe, expect, it } from "vitest";

import {
  BASE_SPEC,
  mergeMessageTrees,
  pickMessages,
  ROUTE_SPEC,
  specCovers,
  type MessageSpec,
} from "./route-messages";

type Tree = { [key: string]: string | Tree };

const here = dirname(fileURLToPath(import.meta.url));
const localeRoot = join(here, "..", "app", "[locale]");
const ENTRY_FILES = new Set([
  "page.tsx",
  "layout.tsx",
  "loading.tsx",
  "error.tsx",
  "not-found.tsx",
]);

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, out);
    else out.push(full);
  }
  return out;
}

function resolveImport(from: string, spec: string): string | null {
  const base = normalize(join(dirname(from), spec));
  for (const candidate of [
    `${base}.tsx`,
    `${base}.ts`,
    join(base, "index.tsx"),
    join(base, "index.ts"),
  ]) {
    if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
  }
  return null;
}

/** Every non-test source file reachable from a route's page/layout/loading files. */
function reachableFiles(routeDir: string, rootOnly: boolean): string[] {
  const entries = rootOnly
    ? readdirSync(routeDir)
        .filter((name) => ENTRY_FILES.has(name))
        .map((name) => join(routeDir, name))
    : walk(routeDir).filter((file) => ENTRY_FILES.has(file.split("/").at(-1) as string));
  const seen = new Set<string>();
  const stack = [...entries];
  while (stack.length > 0) {
    const file = stack.pop() as string;
    if (seen.has(file) || /\.test\.tsx?$/.test(file)) continue;
    seen.add(file);
    const source = readFileSync(file, "utf8");
    for (const match of source.matchAll(/from\s+["'](\.[^"']+)["']/g)) {
      const target = resolveImport(file, match[1] as string);
      if (target && target.startsWith(join(here, ".."))) stack.push(target);
    }
  }
  return [...seen];
}

function hasPath(tree: Tree, path: string): boolean {
  let node: string | Tree | undefined = tree;
  for (const part of path.split(".")) {
    if (typeof node !== "object" || node === undefined || !Object.hasOwn(node, part)) return false;
    node = node[part];
  }
  return true;
}

function literalPath(raw: string): string {
  const cut = raw.includes("${") ? raw.slice(0, raw.indexOf("${")) : raw;
  return cut.replace(/\.+$/, "");
}

/** Message key paths (namespace-qualified, e.g. "vendor.listings.images.title") a file reads. */
function readKeyPaths(file: string, vendor: Tree): Set<string> {
  const source = readFileSync(file, "utf8");
  const paths = new Set<string>();
  let readsVendorRoot = false;
  for (const match of source.matchAll(
    /(?:const|let)\s+(\w+)\s*=\s*(?:await\s+)?(?:useTranslations|getTranslations)\(\s*["']([^"']+)["']\s*\)/g,
  )) {
    const variable = match[1] as string;
    const namespace = match[2] as string;
    if (namespace === "common" || namespace.startsWith("common.")) continue;
    if (namespace === "vendor") readsVendorRoot = true;
    const callPattern = new RegExp(`\\b${variable}\\(\\s*[\"'\`]([^\"'\`]+)[\"'\`]`, "g");
    let any = false;
    for (const call of source.matchAll(callPattern)) {
      const key = literalPath(call[1] as string);
      if (key) {
        paths.add(`${namespace}.${key}`);
        any = true;
      }
    }
    if (!any) paths.add(namespace);
  }
  if (readsVendorRoot) {
    // Keys held in lookup tables / returned from helpers (ACTION_LABEL_KEYS, error scopes).
    for (const lit of source.matchAll(/["'`]([A-Za-z]+(?:\.[A-Za-z0-9_$ {}]+)+)["'`]/g)) {
      const key = literalPath(lit[1] as string);
      if (key.includes(".") && hasPath(vendor, key)) paths.add(`vendor.${key}`);
    }
  }
  return paths;
}

function covered(path: string, spec: MessageSpec): boolean {
  const [namespace = "", ...rest] = path.split(".");
  const relative = rest.join(".");
  // A hook whose `t` is handed to a shared component (the bell passes it to the
  // notification center) has no literal keys to check: require the namespace is shipped.
  if (relative === "") {
    return namespace in BASE_SPEC || spec[namespace as "vendor"] !== undefined;
  }
  if (namespace === "events" || namespace === "services" || namespace === "auth") {
    return (
      specCovers(spec[namespace as "events"], relative || "x") ||
      spec[namespace as "events"] === true
    );
  }
  return (
    specCovers(spec[namespace as "vendor"], relative) ||
    specCovers(BASE_SPEC[namespace as "vendor"], relative)
  );
}

describe("per-route vendor message payloads", () => {
  it("ships every key a route's client views read (raw-key regression)", async () => {
    const vendor = (await loadNamespace("en" as Locale, "vendor")) as Tree;
    const failures: string[] = [];
    const routeDirs = readdirSync(localeRoot).filter(
      (name) =>
        statSync(join(localeRoot, name)).isDirectory() &&
        !name.startsWith("_") &&
        !name.startsWith("(") &&
        name !== "health",
    );
    const routes: Array<[string, string, boolean]> = [
      ["home", localeRoot, true],
      ...routeDirs.map(
        (name) => [name, join(localeRoot, name), false] as [string, string, boolean],
      ),
    ];
    for (const [route, dir, rootOnly] of routes) {
      const spec = (ROUTE_SPEC as Record<string, MessageSpec>)[route];
      if (!spec && route !== "notifications") {
        failures.push(`route "${route}" has no ROUTE_SPEC entry`);
        continue;
      }
      for (const file of reachableFiles(dir, rootOnly)) {
        for (const path of readKeyPaths(file, vendor)) {
          if (!covered(path, spec ?? {})) {
            failures.push(`${route}: ${path} (${file.slice(localeRoot.length)})`);
          }
        }
      }
    }
    expect(failures).toEqual([]);
  });

  it("only lists spec paths that exist in the catalogs", async () => {
    const missing: string[] = [];
    const specs: Array<[string, MessageSpec]> = [
      ["base", BASE_SPEC],
      ...Object.entries(ROUTE_SPEC),
    ];
    for (const [name, spec] of specs) {
      for (const [namespace, entries] of Object.entries(spec)) {
        if (entries === true) continue;
        const tree = (await loadNamespace("en" as Locale, namespace as never)) as Tree;
        for (const entry of entries as readonly string[]) {
          if (!hasPath(tree, entry)) missing.push(`${name}: ${namespace}.${entry}`);
        }
      }
    }
    expect(missing).toEqual([]);
  });

  it("keeps the base payload small", async () => {
    const vendor = (await loadNamespace("en" as Locale, "vendor")) as Tree;
    const notifications = (await loadNamespace("en" as Locale, "notifications")) as Tree;
    const bytes =
      JSON.stringify(pickMessages(vendor, BASE_SPEC.vendor)).length +
      JSON.stringify(pickMessages(notifications, BASE_SPEC.notifications)).length;
    expect(bytes).toBeLessThan(12_000);
  });

  it("picks dotted sub-branches and merges them without clobbering siblings", () => {
    const source: Tree = { a: { b: { c: "1", d: "2" }, e: "3" }, f: "4" };
    expect(pickMessages(source, ["a.b.c"])).toEqual({ a: { b: { c: "1" } } });
    expect(pickMessages(source, ["a.b", "a.e"])).toEqual({ a: { b: { c: "1", d: "2" }, e: "3" } });
    expect(pickMessages(source, ["missing.path"])).toEqual({});
    expect(mergeMessageTrees({ a: { b: "1" } }, { a: { c: "2" }, g: "3" })).toEqual({
      a: { b: "1", c: "2" },
      g: "3",
    });
  });
});
