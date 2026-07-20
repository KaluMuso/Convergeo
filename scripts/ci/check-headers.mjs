#!/usr/bin/env node
/**
 * Security-headers presence check (M15-P03).
 *
 * Statically asserts that each origin's header configuration declares the required
 * security headers and CSP directives, and that the Lenco widget allowance is scoped
 * to the customer checkout card route ONLY. This is a config-manifest check (not a
 * live HTTP probe): it parses the source of every apps/<app>/next.config.ts and the
 * `infra/Caddyfile`. The converger wires it into CI (`ci.yml`); run locally with:
 *
 *   node scripts/ci/check-headers.mjs
 *
 * Exit code is non-zero if any required header/directive is missing or if the Lenco
 * allowance leaks outside the customer checkout route.
 */
import { readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const ROOT = resolve(__dirname, "../..");

/** @type {string[]} */
const failures = [];
/** @type {string[]} */
const passes = [];

/**
 * @param {string} label
 * @param {boolean} ok
 * @param {string} detail
 */
function assert(label, ok, detail) {
  if (ok) {
    passes.push(label);
  } else {
    failures.push(`${label} — ${detail}`);
  }
}

/**
 * @param {string} relPath
 * @returns {string}
 */
function read(relPath) {
  return readFileSync(join(ROOT, relPath), "utf8");
}

// Header names every browser-facing app origin must declare.
const REQUIRED_HEADERS = [
  "Strict-Transport-Security",
  "X-Content-Type-Options",
  "X-Frame-Options",
  "Referrer-Policy",
  "Permissions-Policy",
  "Content-Security-Policy",
  "Content-Security-Policy-Report-Only",
];

/**
 * @param {string} app
 * @param {{ frameAncestors: string, allowLenco: boolean }} opts
 */
function checkAppConfig(app, opts) {
  const relPath = `apps/${app}/next.config.ts`;
  const src = read(relPath);
  const where = relative(ROOT, join(ROOT, relPath));

  for (const header of REQUIRED_HEADERS) {
    assert(`${app}: declares ${header}`, src.includes(`"${header}"`), `missing in ${where}`);
  }

  // Transport: HSTS with a 2-year max-age + preload.
  assert(
    `${app}: HSTS max-age=63072000 + preload`,
    src.includes("max-age=63072000") && src.includes("preload"),
    `weak/absent HSTS in ${where}`,
  );

  // Nonce-based CSP: strict-dynamic + a nonce, and NO unsafe-inline on script-src.
  assert(
    `${app}: CSP default-src 'self'`,
    src.includes("default-src 'self'"),
    `absent in ${where}`,
  );
  assert(
    `${app}: CSP script-src strict-dynamic`,
    src.includes("'strict-dynamic'"),
    `absent in ${where}`,
  );
  assert(`${app}: CSP script-src nonce`, src.includes("'nonce-"), `absent in ${where}`);

  const scriptSrcLines = src.split("\n").filter((line) => line.includes("script-src"));
  const scriptUnsafeInline = scriptSrcLines.some((line) => line.includes("unsafe-inline"));
  assert(
    `${app}: no unsafe-inline on script-src`,
    !scriptUnsafeInline,
    `script-src allows unsafe-inline in ${where}`,
  );

  // Framing posture (admin strictest = 'none').
  assert(
    `${app}: frame-ancestors ${opts.frameAncestors}`,
    src.includes(`frame-ancestors ${opts.frameAncestors}`),
    `expected frame-ancestors ${opts.frameAncestors} in ${where}`,
  );

  // Lenco widget scoping. Match the widget HOST (an actual allowance), not the word
  // "Lenco" — doc comments may legitimately mention it.
  const allowsLencoHost = /lenco\.co/i.test(src);
  if (opts.allowLenco) {
    assert(
      `${app}: Lenco widget allowed`,
      src.includes("pay.lenco.co"),
      `customer must allow the Lenco widget origin in ${where}`,
    );
    assert(
      `${app}: Lenco scoped to checkout/card route`,
      src.includes("checkout/card"),
      `Lenco allowance not tied to the checkout card route in ${where}`,
    );
    assert(
      `${app}: Lenco gated behind non-checkout path`,
      src.includes("buildReportOnlyCsp(false)") && /lenco \?/.test(src),
      `Lenco not conditionally gated (may leak to non-checkout routes) in ${where}`,
    );
  } else {
    assert(
      `${app}: NO Lenco allowance (non-checkout origin)`,
      !allowsLencoHost,
      `Lenco widget host leaked into ${where}`,
    );
  }
}

/**
 * @param {string} app
 * @param {{ allowLenco: boolean }} opts
 */
function checkAppMiddleware(app, opts) {
  const relPath = `apps/${app}/middleware.ts`;
  const src = read(relPath);
  const where = relative(ROOT, join(ROOT, relPath));

  assert(
    `${app}: middleware applies report-only CSP nonce`,
    src.includes("applyReportOnlyCspNonce"),
    `missing nonce application in ${where}`,
  );
  assert(
    `${app}: middleware uses nonce placeholder`,
    src.includes("CSP_NONCE_PLACEHOLDER"),
    `missing nonce placeholder substitution in ${where}`,
  );

  const scriptSrcLines = src.split("\n").filter((line) => line.includes("script-src"));
  const scriptUnsafeInline = scriptSrcLines.some((line) => line.includes("unsafe-inline"));
  const scriptUnsafeEval = scriptSrcLines.some((line) => line.includes("unsafe-eval"));
  assert(
    `${app}: middleware script-src has no unsafe-inline`,
    !scriptUnsafeInline,
    `middleware script-src allows unsafe-inline in ${where}`,
  );
  assert(
    `${app}: middleware script-src has no unsafe-eval`,
    !scriptUnsafeEval,
    `middleware script-src allows unsafe-eval in ${where}`,
  );

  const allowsLencoHost = /lenco\.co/i.test(src);
  if (opts.allowLenco) {
    assert(
      `${app}: middleware Lenco scoped to checkout/card route`,
      src.includes("isCheckoutCardRoute") && src.includes("checkout") && src.includes("card"),
      `middleware Lenco allowance not tied to checkout/card in ${where}`,
    );
  } else {
    assert(
      `${app}: middleware has NO Lenco allowance`,
      !allowsLencoHost,
      `Lenco widget host leaked into ${where}`,
    );
  }
}

// ── App origins ──────────────────────────────────────────────────────────────
checkAppConfig("customer", { frameAncestors: "'self'", allowLenco: true });
checkAppConfig("vendor", { frameAncestors: "'self'", allowLenco: false });
checkAppConfig("admin", { frameAncestors: "'none'", allowLenco: false });
checkAppMiddleware("customer", { allowLenco: true });
checkAppMiddleware("vendor", { allowLenco: false });
checkAppMiddleware("admin", { allowLenco: false });

// Vendor camera scoping: denied by default, allowed only on the scanner routes.
{
  const src = read("apps/vendor/next.config.ts");
  assert(
    "vendor: camera denied by default",
    src.includes("camera=()"),
    "missing camera=() default",
  );
  assert(
    "vendor: camera=(self) scoped to scanner",
    src.includes("camera=(self)"),
    "scanner camera not scoped",
  );
  assert("vendor: scan route source present", src.includes("/scan"), "no scan route header rule");
}

// ── Caddy edge origins ───────────────────────────────────────────────────────
{
  const src = read("infra/Caddyfile");
  const where = "infra/Caddyfile";
  assert(
    "caddy: common_security snippet",
    src.includes("(common_security)"),
    `missing in ${where}`,
  );
  assert("caddy: api_security snippet", src.includes("(api_security)"), `missing in ${where}`);
  assert("caddy: hardened_edge snippet", src.includes("(hardened_edge)"), `missing in ${where}`);
  assert(
    "caddy: baseline HSTS 63072000 + preload",
    src.includes("max-age=63072000") && src.includes("preload"),
    `weak/absent HSTS in ${where}`,
  );
  assert(
    "caddy: X-Content-Type-Options nosniff",
    src.includes('X-Content-Type-Options "nosniff"'),
    `missing in ${where}`,
  );
  assert("caddy: Referrer-Policy", src.includes("Referrer-Policy"), `missing in ${where}`);
  assert(
    "caddy: API strict CSP default-src none",
    src.includes("default-src 'none'"),
    `API origin CSP not locked down in ${where}`,
  );
  assert(
    "caddy: API + admin/n8n frame DENY",
    src.includes('X-Frame-Options "DENY"'),
    `missing X-Frame-Options DENY in ${where}`,
  );
  assert(
    "caddy: admin origin imports hardened_edge",
    src.includes("import hardened_edge"),
    `missing in ${where}`,
  );
  assert(
    "caddy: no Lenco host at edge",
    !/lenco\.co/i.test(src),
    `Lenco host leaked into ${where}`,
  );
}

// ── Report ───────────────────────────────────────────────────────────────────
console.log(`check-headers: ${passes.length} checks passed`);
if (failures.length > 0) {
  console.error("\ncheck-headers FAILED:");
  for (const failure of failures) {
    console.error(`  ✗ ${failure}`);
  }
  process.exit(1);
}
console.log(
  "check-headers OK — required security headers present per origin; Lenco scoped to checkout.",
);
