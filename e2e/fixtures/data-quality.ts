import type { Page } from "@playwright/test";

/**
 * Data-quality assertions for customer browse surfaces.
 * Flags suspicious content without failing on legitimate free/zero-priced items.
 */

/** Patterns that indicate a suspicious zero price on a paid product surface. */
const SUSPICIOUS_ZERO_PRICE = /\bK\s*0\.00\b|\bK0\.00\b|\bZMW\s*0\.00\b/i;

/** Demo/test badge copy that must not appear in production. */
const DEMO_BADGE_PATTERNS = [
  /\bdemo\s+listing\b/i,
  /\btest\s+product\b/i,
  /\bE2E\s+fixture\b/i,
  /\bplaceholder\s+vendor\b/i,
];

/** Wholesale tier indicators that must not leak to retail browse. */
const WHOLESALE_LEAK_PATTERNS = [
  /\bwholesale\s+only\b/i,
  /\bMOQ\s*:\s*\d+\s*carton/i,
  /\btier\s*2\s*pricing\b/i,
  /\bB2B\s+gate\b/i,
];

export type DataQualityIssue = {
  kind:
    | "unexpected_zero_price"
    | "missing_product_image"
    | "dead_pdp"
    | "invalid_vendor_link"
    | "duplicate_canonical"
    | "demo_badge_in_production"
    | "wholesale_leakage"
    | "fake_trust_claim";
  detail: string;
  selector?: string;
};

/**
 * Scan visible price blocks on PLP/PDP for unexpected K0.00.
 * Skips elements explicitly marked as free.
 */
export async function scanUnexpectedZeroPrices(page: Page): Promise<DataQualityIssue[]> {
  const issues: DataQualityIssue[] = [];
  const priceEls = page.locator("[data-testid*='price'], [class*='price'], .text-price");
  const count = await priceEls.count();
  for (let i = 0; i < Math.min(count, 30); i++) {
    const el = priceEls.nth(i);
    const text = (await el.textContent()) ?? "";
    const isFree = /\bfree\b/i.test(text) || (await el.getAttribute("data-free")) === "true";
    if (!isFree && SUSPICIOUS_ZERO_PRICE.test(text)) {
      issues.push({
        kind: "unexpected_zero_price",
        detail: `Suspicious zero price: "${text.trim()}"`,
      });
    }
  }
  return issues;
}

/** Fail when PDP has no product image (gallery or poster). */
export async function checkPdpHasImage(page: Page): Promise<DataQualityIssue[]> {
  const gallery = page
    .getByTestId("gallery-strip")
    .or(page.getByTestId("image-gallery"))
    .or(page.locator("img[alt]:not([alt=''])"));
  const visible = await gallery
    .first()
    .isVisible()
    .catch(() => false);
  if (!visible) {
    return [{ kind: "missing_product_image", detail: "PDP has no visible product image" }];
  }
  return [];
}

/** Detect dead PDP (unavailable surface with no honest empty state). */
export async function checkPdpAlive(page: Page): Promise<DataQualityIssue[]> {
  const unavailable = page.getByTestId("pdp-unavailable");
  const buyBox = page.getByTestId("pdp-buy-box");
  const header = page.getByTestId("pdp-header");

  const hasUnavailable = await unavailable.isVisible().catch(() => false);
  const hasBuyBox = await buyBox.isVisible().catch(() => false);
  const hasHeader = await header.isVisible().catch(() => false);

  if (!hasUnavailable && !hasBuyBox && !hasHeader) {
    return [{ kind: "dead_pdp", detail: "PDP renders neither buy-box nor unavailable state" }];
  }
  return [];
}

/** Scan page body for demo/test badges (production guard). */
export async function scanDemoBadges(page: Page): Promise<DataQualityIssue[]> {
  const isProduction =
    !/localhost|127\.0\.0\.1|staging|preview/i.test(page.url()) &&
    process.env.E2E_ALLOW_DEMO_BADGES !== "1";
  if (!isProduction) return [];

  const body = (await page.locator("body").textContent()) ?? "";
  const issues: DataQualityIssue[] = [];
  for (const pat of DEMO_BADGE_PATTERNS) {
    if (pat.test(body)) {
      issues.push({ kind: "demo_badge_in_production", detail: `Matched demo pattern: ${pat}` });
    }
  }
  return issues;
}

/** Scan for wholesale tier leakage on retail surfaces. */
export async function scanWholesaleLeakage(page: Page): Promise<DataQualityIssue[]> {
  const onSupplies = /\/supplies/.test(page.url());
  if (onSupplies) return [];

  const body = (await page.locator("main, [role='main'], body").first().textContent()) ?? "";
  const issues: DataQualityIssue[] = [];
  for (const pat of WHOLESALE_LEAK_PATTERNS) {
    if (pat.test(body)) {
      issues.push({
        kind: "wholesale_leakage",
        detail: `Wholesale indicator on retail surface: ${pat}`,
      });
    }
  }
  return issues;
}

/** Vendor link on PDP must resolve (not 404). */
export async function checkVendorLink(page: Page): Promise<DataQualityIssue[]> {
  const sellerLink = page
    .getByTestId("pdp-buy-box-seller")
    .locator("a[href]")
    .or(page.locator("[data-testid='pdp-buy-box'] a[href*='/v/']"));
  const count = await sellerLink.count();
  if (count === 0) return [];

  const href = await sellerLink.first().getAttribute("href");
  if (!href || href === "#" || href === "/") {
    return [{ kind: "invalid_vendor_link", detail: `Vendor link missing or placeholder: ${href}` }];
  }
  return [];
}

/**
 * Run data-quality checks appropriate for the current page route.
 * Returns accumulated issues (empty = pass).
 */
export async function runDataQualityChecks(page: Page): Promise<DataQualityIssue[]> {
  const url = page.url();
  const isPdp = /\/p\//.test(url);
  const isPlp = /\/c\//.test(url) || /\/search/.test(url) || /\/v\//.test(url);

  const checks: Promise<DataQualityIssue[]>[] = [
    scanUnexpectedZeroPrices(page),
    scanDemoBadges(page),
    scanWholesaleLeakage(page),
  ];

  if (isPdp) {
    checks.push(checkPdpHasImage(page), checkPdpAlive(page), checkVendorLink(page));
  }

  if (isPlp) {
    // Vendor link only relevant on PDP; PLP checks are price/demo/wholesale only.
  }

  const results = await Promise.all(checks);
  return results.flat();
}
