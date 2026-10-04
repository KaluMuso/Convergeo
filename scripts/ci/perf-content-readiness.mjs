/** Qualification of the actual browser page left by Lighthouse; metrics stay untouched. */
/* global getComputedStyle, location, document, fetch */
import { URL } from "node:url";

export const fixtureIdentity = Object.freeze({
  product: "b0000000-0000-0000-0000-000000000001",
  listing: "b1000000-0000-0000-0000-000000000001",
  vendor: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  slug: "smartphone-x1",
  price: 450000,
  media: "ci-perf/smartphone-x1",
});

export function qualifyContent(url, snapshot, payload) {
  const pathname = new URL(url).pathname;
  if (snapshot.url !== url || snapshot.unavailable)
    return { passed: false, reason: "unexpected_page_or_fallback" };
  if (!["/en/c/electronics", "/en/p/smartphone-x1"].includes(pathname))
    return { passed: true, reason: "requested_page_present" };
  const product = payload.product;
  const listings = product?.listings;
  const listing = Array.isArray(listings)
    ? listings.find((row) => row.id === fixtureIdentity.listing)
    : null;
  const item = payload.catalog?.items?.find((row) => row.id === fixtureIdentity.listing);
  if (
    product?.id !== fixtureIdentity.product ||
    product?.slug !== fixtureIdentity.slug ||
    !Array.isArray(listings) ||
    listings.length !== 1 ||
    listing?.vendor?.id !== fixtureIdentity.vendor ||
    listing?.price_ngwee !== fixtureIdentity.price ||
    !listing?.in_stock ||
    !listing?.images?.some((image) => image.public_id === fixtureIdentity.media) ||
    item?.product_slug !== fixtureIdentity.slug ||
    item?.price_ngwee !== fixtureIdentity.price ||
    item?.image_public_id !== fixtureIdentity.media
  )
    return { passed: false, reason: "fixture_identity_or_api_content_mismatch" };
  if (
    !snapshot.title.includes("Smartphone X1") ||
    !snapshot.price.replace(/\s/g, "").includes("K4,500.00") ||
    !snapshot.seller.includes("Lusaka Electronics Hub")
  )
    return { passed: false, reason: "visible_fixture_content_mismatch" };
  if (
    !snapshot.images.some(
      (image) =>
        image.visible &&
        image.complete &&
        image.width >= 360 &&
        image.height > 0 &&
        image.src.startsWith(`${new URL(url).origin}/api/ci-perf-media?width=`),
    )
  )
    return { passed: false, reason: "fixture_media_not_loaded" };
  return { passed: true, reason: "exact_fixture_content_and_loaded_media" };
}

export function readMeasuredSnapshot() {
  const isVisible = (element) => {
    if (!element || !element.getClientRects().length) return false;
    for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
      const style = getComputedStyle(ancestor);
      if (
        style.visibility === "hidden" ||
        style.visibility === "collapse" ||
        style.display === "none" ||
        Number(style.opacity || "1") === 0
      )
        return false;
    }
    return true;
  };
  const text = (element) =>
    isVisible(element) ? (element.innerText ?? element.textContent ?? "") : "";
  const pdp = location.pathname === "/en/p/smartphone-x1";
  const card = Array.from(document.querySelectorAll('[data-testid="listing-card"]')).find(
    (element) =>
      element.querySelector('[data-testid="listing-card-link"]')?.getAttribute("href") ===
      "/en/p/smartphone-x1",
  );
  const buyBox = document.querySelector('[data-testid="pdp-buy-box"]');
  const gallery = pdp
    ? document.querySelector('[data-testid="pdp-interactive-body"] [data-testid="gallery-strip"]')
    : card;
  return {
    url: location.href,
    unavailable: !!document.querySelector(
      '[data-testid="plp-unavailable"], [data-testid="pdp-unavailable"], [data-testid="pdp-no-sellers"]',
    ),
    title: text(
      pdp ? document.querySelector('[data-testid="pdp-header"] h1') : card?.querySelector("h3, h2"),
    ),
    price: text((pdp ? buyBox : card)?.querySelector('[data-testid="price-block"]')),
    seller: text(pdp ? buyBox?.querySelector('[data-testid="pdp-buy-box-seller"]') : card),
    images: Array.from((gallery ?? document.createElement("div")).querySelectorAll("img")).map(
      (image) => ({
        src: image.currentSrc,
        complete: image.complete,
        width: image.naturalWidth,
        height: image.naturalHeight,
        visible: isVisible(image),
      }),
    ),
  };
}

export async function inspectMeasuredContent(url, page) {
  try {
    if (!page || page.url() !== url)
      return { passed: false, reason: "measured_page_missing_or_changed" };
    const snapshot = await page.evaluate(readMeasuredSnapshot);
    let payload = {};
    if (["/en/c/electronics", "/en/p/smartphone-x1"].includes(new URL(url).pathname)) {
      payload = await page.evaluate(async () => {
        const responses = await Promise.all([
          fetch("/api/ci-perf/products/smartphone-x1", { cache: "no-store" }),
          fetch("/api/ci-perf/catalog/listings?category_path=electronics", { cache: "no-store" }),
        ]);
        if (responses.some((response) => !response.ok)) return {};
        return { product: await responses[0].json(), catalog: await responses[1].json() };
      });
    }
    return qualifyContent(url, snapshot, payload);
  } catch {
    return { passed: false, reason: "content_inspection_failed" };
  }
}
