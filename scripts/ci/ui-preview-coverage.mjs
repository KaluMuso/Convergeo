#!/usr/bin/env node
/**
 * CI check: every UI kit component module under packages/ui/src must be
 * statically imported by the dev preview gallery at apps/customer/.../(dev)/ui.
 */
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "../..");
const UI_SRC = path.join(ROOT, "packages/ui/src");
const PREVIEW_DIR = path.join(ROOT, "apps/customer/app/[locale]/(dev)/ui");

const EXCLUDED_DIRS = new Set(["styles", "fonts"]);

async function collectComponentModules(dir, prefix = "") {
  const entries = await readdir(dir, { withFileTypes: true });
  const modules = [];

  for (const entry of entries) {
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;

    if (entry.isDirectory()) {
      if (EXCLUDED_DIRS.has(entry.name)) {
        continue;
      }
      modules.push(...(await collectComponentModules(path.join(dir, entry.name), rel)));
      continue;
    }

    if (!entry.name.endsWith(".tsx")) {
      continue;
    }
    if (entry.name.endsWith(".test.tsx")) {
      continue;
    }

    const moduleName = rel.replace(/\.tsx$/, "");
    modules.push(moduleName);
  }

  return modules.sort();
}

async function collectPreviewFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await collectPreviewFiles(full)));
    } else if (entry.name.endsWith(".tsx")) {
      files.push(full);
    }
  }

  return files;
}

function extractImportedModules(source) {
  const imported = new Set();
  const pattern = /@vergeo\/ui\/src\/([a-z0-9/-]+)/g;
  let match = pattern.exec(source);
  while (match) {
    imported.add(match[1]);
    match = pattern.exec(source);
  }
  return imported;
}

async function main() {
  const allModules = await collectComponentModules(UI_SRC);
  const previewFiles = await collectPreviewFiles(PREVIEW_DIR);

  const imported = new Set();
  for (const file of previewFiles) {
    const source = await readFile(file, "utf8");
    for (const mod of extractImportedModules(source)) {
      imported.add(mod);
    }
  }

  const missing = allModules.filter((mod) => !imported.has(mod));

  console.log(`UI kit modules: ${allModules.length}`);
  console.log(`Preview imports: ${imported.size}`);
  console.log(`Preview files scanned: ${previewFiles.length}`);

  if (missing.length > 0) {
    console.error("\nMissing from UI preview imports:");
    for (const mod of missing) {
      console.error(`  - ${mod}`);
    }
    process.exit(1);
  }

  console.log("\nAll UI kit components are covered by the preview page.");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
