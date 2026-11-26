/** Qualification of the actual browser page left by Lighthouse; metrics stay untouched. */
/* global getComputedStyle, location, document, fetch, createImageBitmap */
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
  if (snapshot.errorBoundary || snapshot.skeleton)
    return { passed: false, reason: "error_or_loading_placeholder" };
  if (pathname === "/en/search")
    return snapshot.heading === "Search" && snapshot.searchReady
      ? { passed: true, reason: "search_form_rendered" }
      : { passed: false, reason: "search_content_missing" };
  if (pathname === "/en/checkout")
    return snapshot.heading === "Checkout" && snapshot.checkoutReady
      ? { passed: true, reason: "checkout_contact_form_rendered" }
      : { passed: false, reason: "checkout_content_missing" };
  if (pathname === "/en" && !snapshot.homeHero)
    return { passed: false, reason: "home_hero_missing" };
  if (
    pathname === "/en" &&
    !snapshot.homeHeroImages?.some(
      (image) =>
        image.visible &&
        image.complete &&
        image.width > 0 &&
        image.decodedWidth >= 360 &&
        image.height > 0 &&
        image.src.startsWith(`${new URL(url).origin}/api/ci-perf-media?width=`),
    )
  )
    return { passed: false, reason: "home_hero_media_not_loaded" };
  if (!["/en", "/en/c/electronics", "/en/p/smartphone-x1"].includes(pathname))
    return { passed: false, reason: "unexpected_policy_page" };
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
    return {
      passed: false,
      reason: "fixture_identity_or_api_content_mismatch",
    };
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
        image.width > 0 &&
        image.decodedWidth >= 360 &&
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
  const matchingCards = Array.from(
    document.querySelectorAll('[data-testid="listing-card"]'),
  ).filter(
    (element) =>
      element.querySelector('[data-testid="listing-card-link"]')?.getAttribute("href") ===
      "/en/p/smartphone-x1",
  );
  const card = matchingCards[0];
  const buyBox = document.querySelector('[data-testid="pdp-buy-box"]');
  const gallery = pdp
    ? document.querySelector('[data-testid="pdp-interactive-body"] [data-testid="gallery-strip"]')
    : card;
  const heading = text(document.querySelector("main h1"));
  const errorBoundary = Array.from(document.querySelectorAll("main h1, main p")).some((element) =>
    ["Something went wrong", "We hit an unexpected problem."].some((copy) =>
      text(element).includes(copy),
    ),
  );
  const skeleton = Array.from(
    document.querySelectorAll(
      'main [data-testid="skeleton"], main [data-testid="product-card-skeleton"]',
    ),
  ).some(isVisible);
  const titleElement = pdp
    ? document.querySelector('[data-testid="pdp-header"] h1')
    : card?.querySelector("h3, h2");
  const priceElement = (pdp ? buyBox : card)?.querySelector('[data-testid="price-block"]');
  const sellerElement = pdp ? buyBox?.querySelector('[data-testid="pdp-buy-box-seller"]') : card;
  const hiddenReason = (element) => {
    if (!element || !element.getClientRects().length) return "missing_or_empty_rects";
    for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
      const style = getComputedStyle(ancestor);
      if (style.display === "none") return "display_none";
      if (["hidden", "collapse"].includes(style.visibility)) return "visibility_hidden";
      if (Number(style.opacity || "1") === 0) return "opacity_zero";
    }
    return null;
  };
  const imageState = (image) => ({
    src: image.currentSrc,
    complete: image.complete,
    width: image.naturalWidth,
    height: image.naturalHeight,
    visible: isVisible(image),
  });
  return {
    url: location.href,
    heading,
    errorBoundary,
    skeleton,
    homeHero:
      isVisible(
        document.querySelector('[data-testid="home-hero-band"] [data-testid="hero-carousel"]'),
      ) && !!text(document.querySelector("#home-hero-heading")),
    homeHeroImages: Array.from(
      document.querySelectorAll(
        '[data-testid="home-hero-band"] [data-testid="hero-carousel-slide-0"] img',
      ),
    ).map(imageState),
    searchReady: isVisible(document.querySelector('main input[type="search"][name="q"]')),
    checkoutReady: isVisible(document.querySelector('main input[type="tel"]')),
    unavailable: !!document.querySelector(
      '[data-testid="plp-unavailable"], [data-testid="pdp-unavailable"], [data-testid="pdp-no-sellers"]',
    ),
    title: text(titleElement),
    price: text(priceElement),
    seller: text(sellerElement),
    matchingCards: matchingCards.length,
    cardVisible: isVisible(card),
    visibility: {
      title: hiddenReason(titleElement),
      price: hiddenReason(priceElement),
      seller: hiddenReason(sellerElement),
    },
    images: Array.from((gallery ?? document.createElement("div")).querySelectorAll("img")).map(
      imageState,
    ),
  };
}

/** Check physical pixels in the resource actually selected by the measured page.
 * Chrome reports srcset naturalWidth in CSS-adjusted pixels on mobile profiles.
 */
export async function readDecodedFixtureImages(expectedSources) {
  const decode = async (image, expectedSrc) => {
    if (!image.complete || image.naturalWidth < 1) return 0;
    const src = image.currentSrc;
    if (!expectedSrc || src !== expectedSrc) return 0;
    try {
      const url = new URL(src);
      if (
        url.origin !== "http://localhost:3000" ||
        url.origin !== location.origin ||
        url.pathname !== "/api/ci-perf-media" ||
        [...url.searchParams.keys()].some((key) => key !== "width") ||
        url.searchParams.getAll("width").length !== 1 ||
        !/^(24|360|720|1080|1200)$/.test(url.searchParams.get("width") ?? "")
      )
        return 0;
      const response = await fetch(src, { cache: "no-store" });
      if (!response.ok || !(response.headers.get("content-type") ?? "").includes("image/webp"))
        return 0;
      const bitmap = await createImageBitmap(await response.blob());
      const width = bitmap.width;
      bitmap.close();
      return image.currentSrc === expectedSrc && image.complete && image.naturalWidth > 0
        ? width
        : 0;
    } catch {
      return 0;
    }
  };
  const gallery =
    location.pathname === "/en/p/smartphone-x1"
      ? document.querySelector('[data-testid="pdp-interactive-body"] [data-testid="gallery-strip"]')
      : Array.from(document.querySelectorAll('[data-testid="listing-card"]')).find(
          (card) =>
            card.querySelector('[data-testid="listing-card-link"]')?.getAttribute("href") ===
            "/en/p/smartphone-x1",
        );
  const images = Array.from(gallery?.querySelectorAll("img") ?? []);
  const homeHeroImages = Array.from(
    document.querySelectorAll(
      '[data-testid="home-hero-band"] [data-testid="hero-carousel-slide-0"] img',
    ),
  );
  if (
    images.length !== expectedSources?.images?.length ||
    homeHeroImages.length !== expectedSources?.homeHeroImages?.length
  )
    return { images: [], homeHeroImages: [] };
  return {
    images: await Promise.all(
      images.map((image, index) => decode(image, expectedSources.images[index])),
    ),
    homeHeroImages: await Promise.all(
      homeHeroImages.map((image, index) => decode(image, expectedSources.homeHeroImages[index])),
    ),
  };
}

/** Only bounded public fixture fields; never DOM/HTML, headers, storage or API bodies. */
function diagnostics(snapshot) {
  const clipped = (value, max) => (typeof value === "string" ? value.slice(0, max) : "");
  const visibility = (field) =>
    ["missing_or_empty_rects", "display_none", "visibility_hidden", "opacity_zero"].includes(
      snapshot.visibility?.[field],
    )
      ? snapshot.visibility[field]
      : null;
  const images = (rows) =>
    rows?.slice(0, 6).map((image) => ({
      visible: image.visible === true,
      complete: image.complete === true,
      width: Number.isInteger(image.width) ? image.width : 0,
      decoded_width: Number.isInteger(image.decodedWidth) ? image.decodedWidth : 0,
      height: Number.isInteger(image.height) ? image.height : 0,
      owned_fixture:
        typeof image.src === "string" &&
        image.src.startsWith("http://localhost:3000/api/ci-perf-media?width="),
    }));
  return {
    heading: clipped(snapshot.heading, 80),
    title: clipped(snapshot.title, 160),
    price: clipped(snapshot.price, 80),
    seller: clipped(snapshot.seller, 240),
    title_matches: snapshot.title?.includes("Smartphone X1") === true,
    price_matches: snapshot.price?.replace(/\s/g, "").includes("K4,500.00") === true,
    seller_matches: snapshot.seller?.includes("Lusaka Electronics Hub") === true,
    error_boundary: snapshot.errorBoundary === true,
    skeleton: snapshot.skeleton === true,
    home_hero: snapshot.homeHero === true,
    matching_cards: Number.isInteger(snapshot.matchingCards) ? snapshot.matchingCards : 0,
    card_visible: snapshot.cardVisible === true,
    visibility: {
      title: visibility("title"),
      price: visibility("price"),
      seller: visibility("seller"),
    },
    images: images(snapshot.images),
    home_hero_images: images(snapshot.homeHeroImages),
  };
}

export async function inspectMeasuredContent(url, page) {
  try {
    if (!page || page.url() !== url)
      return { passed: false, reason: "measured_page_missing_or_changed" };
    const snapshot = await page.evaluate(readMeasuredSnapshot);
    let payload = {};
    if (["/en", "/en/c/electronics", "/en/p/smartphone-x1"].includes(new URL(url).pathname)) {
      const decoded = await page.evaluate(readDecodedFixtureImages, {
        images: snapshot.images?.map((image) => image.src) ?? [],
        homeHeroImages: snapshot.homeHeroImages?.map((image) => image.src) ?? [],
      });
      snapshot.images?.forEach((image, index) => {
        image.decodedWidth = decoded.images?.[index] ?? 0;
      });
      snapshot.homeHeroImages?.forEach((image, index) => {
        image.decodedWidth = decoded.homeHeroImages?.[index] ?? 0;
      });
      payload = await page.evaluate(async () => {
        const responses = await Promise.all([
          fetch("/api/ci-perf/products/smartphone-x1", { cache: "no-store" }),
          fetch("/api/ci-perf/catalog/listings?category_path=electronics", {
            cache: "no-store",
          }),
        ]);
        if (responses.some((response) => !response.ok)) return {};
        return {
          product: await responses[0].json(),
          catalog: await responses[1].json(),
        };
      });
    }
    return {
      ...qualifyContent(url, snapshot, payload),
      observed: diagnostics(snapshot),
    };
  } catch {
    return { passed: false, reason: "content_inspection_failed" };
  }
}
