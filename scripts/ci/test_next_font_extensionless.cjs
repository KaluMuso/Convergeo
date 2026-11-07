const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { dirname, join, resolve } = require("node:path");
const Module = require("node:module");
const { test } = require("node:test");

const root = resolve(__dirname, "../..");
const fromCustomer = Module.createRequire(join(root, "apps/customer/package.json"));
const base = "next/dist/compiled/@next/font/dist/google/";
process.env.NEXT_FONT_GOOGLE_MOCKED_RESPONSES = join(
  __dirname,
  "next-font-extensionless.fixture.cjs",
);

function patchedModule(name) {
  const filename = fromCustomer.resolve(base + name);
  const source = readFileSync(
    join(process.env.FONT_PATCH_DIR, "dist/compiled/@next/font/dist/google", name),
    "utf8",
  );
  const loaded = new Module(filename, module);
  loaded.filename = filename;
  loaded.paths = Module._nodeModulePaths(dirname(filename));
  loaded._compile(source, filename);
  require.cache[filename] = loaded;
  return loaded.exports;
}

let loader;
if (process.env.FONT_PATCH_DIR) {
  patchedModule("find-font-files-in-css.js");
  loader = patchedModule("loader.js").default;
} else {
  loader = fromCustomer(base + "loader.js").default;
}

async function loadFont(functionName, options) {
  const emitted = [];
  const result = await loader({
    functionName,
    data: [options],
    emitFontFile: (_bytes, ext, preload, adjustFallback) => {
      emitted.push({ ext, preload, adjustFallback });
      return "/_next/static/media/fixture." + ext;
    },
    isDev: false,
    isServer: true,
  });
  return { result, emitted };
}

test("query suffix resembling ttf cannot override declared woff2 format", async () => {
  const { result, emitted } = await loadFont("DM_Sans", {
    subsets: ["latin"],
    variable: "--font-body",
    display: "swap",
  });
  assert.deepEqual(emitted, [{ ext: "woff2", preload: true, adjustFallback: true }]);
  assert.match(result.css, /fixture\.woff2/);
  assert.equal(result.variable, "--font-body");
  assert.ok(result.adjustFontFallback);
});

test("woff2 URL with query retains its declared extension", async () => {
  const { emitted } = await loadFont("JetBrains_Mono", {
    subsets: ["latin"],
    variable: "--font-mono",
    display: "swap",
  });
  assert.deepEqual(emitted, [{ ext: "woff2", preload: true, adjustFallback: true }]);
});

test("unknown extensionless format still fails closed", async () => {
  await assert.rejects(
    loadFont("DM_Serif_Display", {
      subsets: ["latin"],
      weight: ["400"],
      variable: "--font-display",
      display: "swap",
    }),
    /Unsupported Google Fonts file format/,
  );
});

// The mocked CSS module is cached by Next, so update its exported fixture for this call only.
test("inherited Object property is rejected as a font format", async () => {
  const fixture = require("./next-font-extensionless.fixture.cjs");
  const key = "https://fonts.googleapis.com/css2?family=DM+Serif+Display:wght@400&display=swap";
  const original = fixture[key];
  fixture[key] = original.replace("format('unknown')", "format('constructor')");
  try {
    await assert.rejects(
      loadFont("DM_Serif_Display", {
        subsets: ["latin"],
        weight: ["400"],
        variable: "--font-display",
        display: "swap",
      }),
      /Unsupported Google Fonts file format/,
    );
  } finally {
    fixture[key] = original;
  }
});
