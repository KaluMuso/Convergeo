// @vitest-environment node
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
const appRoot = join(here, "..");
const localeRoot = join(appRoot, "app", "[locale]");
const ENTRY_FILES = new Set([
  "page.tsx",
  "layout.tsx",
  "loading.tsx",
  "error.tsx",
  "not-found.tsx",
]);
// Routes that render bare (no admin catalog) or belong to no nav section.
const SKIP_ROUTES = new Set(["health", "(auth)"]);

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

/** Every non-test source file reachable from the given entry files (admin app only). */
function reachableFrom(entries: string[]): string[] {
  const seen = new Set<string>();
  const stack = [...entries];
  while (stack.length > 0) {
    const file = stack.pop() as string;
    if (seen.has(file) || /\.test\.tsx?$/.test(file)) continue;
    seen.add(file);
    const source = readFileSync(file, "utf8");
    for (const match of source.matchAll(/from\s+["'](\.[^"']+)["']/g)) {
      const target = resolveImport(file, match[1] as string);
      if (target && target.startsWith(appRoot) && !target.includes("node_modules")) {
        stack.push(target);
      }
    }
  }
  return [...seen];
}

function routeEntries(routeDir: string, rootOnly: boolean): string[] {
  return rootOnly
    ? readdirSync(routeDir)
        .filter((name) => ENTRY_FILES.has(name))
        .map((name) => join(routeDir, name))
    : walk(routeDir).filter((file) => ENTRY_FILES.has(file.split("/").at(-1) as string));
}

function hasPath(tree: Tree, path: string): boolean {
  let node: string | Tree | undefined = tree;
  for (const part of path.split(".")) {
    if (typeof node !== "object" || node === undefined || !Object.hasOwn(node, part)) return false;
    node = node[part];
  }
  return true;
}

/** `nav.${key}` -> `nav`; keeps only the literal head of a template key. */
function literalPath(raw: string): string {
  const cut = raw.includes("${") ? raw.slice(0, raw.indexOf("${")) : raw;
  return cut.replace(/\.+$/, "");
}

/**
 * Namespace-qualified key paths a client file reads, at the granularity the specs use:
 * `admin.<section>` (first segment under admin), `notifications`, `services`.
 * Returns `unresolved` entries for reads whose first segment is dynamic.
 */
function readKeyPaths(file: string, admin: Tree): { paths: Set<string>; unresolved: string[] } {
  const source = readFileSync(file, "utf8");
  const paths = new Set<string>();
  const unresolved: string[] = [];
  let readsAdminRoot = false;
  for (const match of source.matchAll(
    /(?:const|let)\s+(\w+)\s*=\s*(?:await\s+)?useTranslations\(\s*["']([^"']+)["']\s*\)/g,
  )) {
    const variable = match[1] as string;
    const namespace = match[2] as string;
    if (namespace === "common" || namespace.startsWith("common.")) continue;
    if (namespace === "admin") {
      readsAdminRoot = true;
      const callPattern = new RegExp(`\\b${variable}\\(\\s*["'\`]([^"'\`]+)["'\`]`, "g");
      for (const call of source.matchAll(callPattern)) {
        const key = literalPath(call[1] as string);
        const head = key.split(".")[0] ?? "";
        if (head && Object.hasOwn(admin, head)) paths.add(`admin.${head}`);
        else if (key === "") unresolved.push(`${variable}(\`${call[1]}\`)`);
      }
      continue;
    }
    // `admin.orders.search` -> admin.orders; `notifications` / `services.funding` -> ns.
    const [root, section] = namespace.split(".");
    paths.add(root === "admin" && section ? `admin.${section}` : (root as string));
  }
  if (readsAdminRoot) {
    // Keys held in lookup tables handed to `t` later (nav labels, tab keys).
    for (const lit of source.matchAll(/["'`]([A-Za-z]+(?:\.[A-Za-z0-9_]+)+)["'`]/g)) {
      const key = literalPath(lit[1] as string);
      const head = key.split(".")[0] ?? "";
      if (key.includes(".") && Object.hasOwn(admin, head) && hasPath(admin, key)) {
        paths.add(`admin.${head}`);
      }
    }
  }
  return { paths, unresolved };
}

function covered(path: string, spec: MessageSpec): boolean {
  const [namespace = "", ...rest] = path.split(".");
  if (namespace === "admin") {
    const relative = rest.join(".");
    return specCovers(spec.admin, relative) || specCovers(BASE_SPEC.admin, relative);
  }
  return (
    spec[namespace as "services"] !== undefined ||
    BASE_SPEC[namespace as keyof typeof BASE_SPEC] !== undefined
  );
}

async function loadAdmin(): Promise<Tree> {
  return (await loadNamespace("en" as Locale, "admin")) as Tree;
}

function routeList(): Array<[string, string[]]> {
  const dirs = readdirSync(localeRoot).filter(
    (name) =>
      statSync(join(localeRoot, name)).isDirectory() &&
      !name.startsWith("_") &&
      !SKIP_ROUTES.has(name),
  );
  return [
    ["home", routeEntries(localeRoot, true).filter((file) => !file.endsWith("layout.tsx"))],
    ...dirs.map(
      (name) => [name, routeEntries(join(localeRoot, name), false)] as [string, string[]],
    ),
  ];
}

describe("per-route admin message payloads", () => {
  it("ships every key the shell and each route's client views read (raw-key regression)", async () => {
    const admin = await loadAdmin();
    const failures: string[] = [];

    // The shell: everything reachable from the locale layout, rendered on every route.
    for (const file of reachableFrom([join(localeRoot, "layout.tsx")])) {
      const { paths, unresolved } = readKeyPaths(file, admin);
      for (const path of paths) {
        const [namespace = "", ...rest] = path.split(".");
        const ok =
          namespace === "admin"
            ? specCovers(BASE_SPEC.admin, rest.join("."))
            : BASE_SPEC[namespace as keyof typeof BASE_SPEC] !== undefined;
        if (!ok) failures.push(`shell: ${path} (${file.slice(localeRoot.length)})`);
      }
      for (const item of unresolved) failures.push(`shell: unresolved ${item}`);
    }

    for (const [route, entries] of routeList()) {
      const spec = (ROUTE_SPEC as Record<string, MessageSpec>)[route];
      if (!spec) {
        failures.push(`route "${route}" has no ROUTE_SPEC entry`);
        continue;
      }
      for (const file of reachableFrom(entries)) {
        const { paths, unresolved } = readKeyPaths(file, admin);
        for (const path of paths) {
          if (!covered(path, spec))
            failures.push(`${route}: ${path} (${file.slice(localeRoot.length)})`);
        }
        for (const item of unresolved) failures.push(`${route}: unresolved ${item}`);
      }
    }
    expect(failures).toEqual([]);
  });

  it("only lists spec paths that exist in the catalogs", async () => {
    const missing: string[] = [];
    const specs: Array<[string, MessageSpec]> = [
      ["base", BASE_SPEC],
      ...Object.entries(ROUTE_SPEC as Record<string, MessageSpec>),
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

  it("keeps the base payload well under the full catalogs", async () => {
    const admin = await loadAdmin();
    const notifications = (await loadNamespace("en" as Locale, "notifications")) as Tree;
    const full = JSON.stringify(admin).length;
    const base =
      JSON.stringify(pickMessages(admin, BASE_SPEC.admin)).length +
      JSON.stringify(pickMessages(notifications, BASE_SPEC.notifications)).length;
    expect(base).toBeLessThan(full / 4);
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

// Dev aid: `ADMIN_PRINT_ROUTE_NEEDS=1 vitest run lib/route-messages.test.ts` prints what each
// route reads so a new ROUTE_SPEC entry can be written from it.
describe.skipIf(!process.env.ADMIN_PRINT_ROUTE_NEEDS)("route needs", () => {
  it("prints", async () => {
    const admin = await loadAdmin();
    const out: Record<string, string[]> = {};
    out.__shell = [
      ...new Set(
        reachableFrom([join(localeRoot, "layout.tsx")]).flatMap((f) => [
          ...readKeyPaths(f, admin).paths,
        ]),
      ),
    ].sort();
    for (const [route, entries] of routeList()) {
      out[route] = [
        ...new Set(reachableFrom(entries).flatMap((f) => [...readKeyPaths(f, admin).paths])),
      ].sort();
    }
    (await import("node:fs")).writeFileSync(
      process.env.ADMIN_PRINT_ROUTE_NEEDS as string,
      JSON.stringify(out, null, 1),
    );
    expect(true).toBe(true);
  });
});
