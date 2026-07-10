#!/usr/bin/env node
/**
 * Image hygiene lint for apps/customer:
 * - no raw <img> in app source (use CloudinaryImage / next/image)
 * - no unoptimized raster images in public/
 */
import { readdirSync, readFileSync, statSync, mkdirSync, writeFileSync } from "node:fs";
import { extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const ROOT = resolve(__dirname, "../..");
const CUSTOMER_ROOT = join(ROOT, "apps/customer");
const SCAN_ROOTS = [join(CUSTOMER_ROOT, "app")];
const PUBLIC_DIR = join(CUSTOMER_ROOT, "public");

const SOURCE_EXTENSIONS = new Set([".tsx", ".jsx", ".ts", ".js", ".mdx"]);
const UNOPTIMIZED_IMAGE_EXTENSIONS = new Set([
  ".jpg",
  ".jpeg",
  ".png",
  ".gif",
  ".bmp",
  ".tif",
  ".tiff",
]);
const OPTIMIZED_IMAGE_EXTENSIONS = new Set([".webp", ".avif", ".svg", ".ico"]);

/** @typedef {{ file: string, line: number, message: string }} LintIssue */

/**
 * @param {string} dir
 * @returns {string[]}
 */
function walkFiles(dir) {
  /** @type {string[]} */
  const files = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === ".next") {
        continue;
      }
      files.push(...walkFiles(full));
      continue;
    }
    const ext = extname(entry.name);
    if (!SOURCE_EXTENSIONS.has(ext)) {
      continue;
    }
    if (
      entry.name.endsWith(".test.tsx") ||
      entry.name.endsWith(".test.ts") ||
      entry.name.endsWith(".test.jsx")
    ) {
      continue;
    }
    files.push(full);
  }
  return files;
}

/**
 * @param {string} content
 */
function stripCommentsAndStrings(content) {
  return content
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/\/\/.*$/gm, " ")
    .replace(/"(?:\\.|[^"\\])*"/g, '""')
    .replace(/'(?:\\.|[^'\\])*'/g, "''")
    .replace(/`(?:\\.|[^`\\])*`/g, "``");
}

/**
 * @param {string} filePath
 * @returns {LintIssue[]}
 */
export function lintSourceFile(filePath) {
  const content = readFileSync(filePath, "utf8");
  const stripped = stripCommentsAndStrings(content);
  /** @type {LintIssue[]} */
  const issues = [];
  const lines = content.split("\n");
  const strippedLines = stripped.split("\n");
  const imgPattern = /<img\b/i;

  for (let i = 0; i < strippedLines.length; i += 1) {
    if (imgPattern.test(strippedLines[i])) {
      issues.push({
        file: filePath,
        line: i + 1,
        message: "raw <img> — use CloudinaryImage or next/image",
      });
    }
  }

  return issues;
}

/**
 * @param {string} dir
 * @returns {LintIssue[]}
 */
export function lintPublicImages(dir = PUBLIC_DIR) {
  /** @type {LintIssue[]} */
  const issues = [];
  if (!statSync(dir, { throwIfNoEntry: false })?.isDirectory()) {
    return issues;
  }

  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      issues.push(...lintPublicImages(full));
      continue;
    }
    const ext = extname(entry.name).toLowerCase();
    if (OPTIMIZED_IMAGE_EXTENSIONS.has(ext)) {
      continue;
    }
    if (UNOPTIMIZED_IMAGE_EXTENSIONS.has(ext)) {
      issues.push({
        file: full,
        line: 1,
        message: `unoptimized public image (${ext}) — serve WebP/AVIF via Cloudinary or convert assets`,
      });
    }
  }

  return issues;
}

/**
 * @param {LintIssue[]} issues
 */
export function formatIssues(issues) {
  return issues.map((issue) => {
    const rel = relative(ROOT, issue.file);
    return `${rel}:${issue.line} — ${issue.message}`;
  });
}

function runSelfTest() {
  const cleanFixture = join(ROOT, "scripts/ci/.tmp-image-lint/clean.tsx");
  const badFixture = join(ROOT, "scripts/ci/.tmp-image-lint/bad.tsx");
  mkdirSync(join(ROOT, "scripts/ci/.tmp-image-lint"), { recursive: true });
  writeFileSync(
    cleanFixture,
    'export function Ok() { return <CloudinaryImage alt="x" publicId="a" />; }\n',
    "utf8",
  );
  writeFileSync(
    badFixture,
    'export function Bad() { return <img alt="nope" src="/x.jpg" />; }\n',
    "utf8",
  );

  const cleanIssues = lintSourceFile(cleanFixture);
  const badIssues = lintSourceFile(badFixture);

  let failed = false;
  if (cleanIssues.length !== 0) {
    console.error("SELF-TEST FAIL: clean fixture should pass");
    failed = true;
  } else {
    console.log("SELF-TEST PASS: clean fixture (no raw <img>)");
  }

  if (badIssues.length === 0) {
    console.error("SELF-TEST FAIL: bad fixture should report raw <img>");
    failed = true;
  } else {
    console.log(`SELF-TEST FAIL (expected): ${formatIssues(badIssues)[0]}`);
  }

  process.exit(failed ? 1 : 0);
}

function main() {
  const args = process.argv.slice(2);
  if (args.includes("--self-test")) {
    runSelfTest();
    return;
  }

  /** @type {LintIssue[]} */
  const issues = [];
  for (const root of SCAN_ROOTS) {
    for (const file of walkFiles(root)) {
      issues.push(...lintSourceFile(file));
    }
  }
  issues.push(...lintPublicImages());

  if (issues.length > 0) {
    console.error("Image lint violations:");
    for (const line of formatIssues(issues)) {
      console.error(`  • ${line}`);
    }
    process.exit(1);
  }

  console.log("Image lint OK — no raw <img> tags or unoptimized public images.");
}

try {
  main();
} catch (error) {
  console.error(error);
  process.exit(1);
}
