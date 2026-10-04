/* global structuredClone */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { URL } from "node:url";

import {
  fixtureIdentity,
  inspectMeasuredContent,
  qualifyContent,
} from "./perf-content-readiness.mjs";

const url = "http://localhost:3000/en/p/smartphone-x1";
const snapshot = {
  url,
  unavailable: false,
  errorBoundary: false,
  skeleton: false,
  homeHero: true,
  homeHeroImages: [
    {
      visible: true,
      complete: true,
      width: 1200,
      height: 1600,
      src: "http://localhost:3000/api/ci-perf-media?width=1200",
    },
  ],
  title: "Smartphone X1",
  price: "K4,500.00",
  seller: "Lusaka Electronics Hub",
  images: [
    {
      visible: true,
      complete: true,
      width: 720,
      height: 960,
      src: "http://localhost:3000/api/ci-perf-media?width=720",
    },
  ],
};
const payload = {
  product: {
    id: fixtureIdentity.product,
    slug: fixtureIdentity.slug,
    listings: [
      {
        id: fixtureIdentity.listing,
        vendor: { id: fixtureIdentity.vendor },
        price_ngwee: 450000,
        in_stock: true,
        images: [{ public_id: fixtureIdentity.media }],
      },
    ],
  },
  catalog: {
    items: [
      {
        id: fixtureIdentity.listing,
        product_slug: fixtureIdentity.slug,
        price_ngwee: 450000,
        image_public_id: fixtureIdentity.media,
      },
    ],
  },
};

test("qualifies exact product and category, actual seller/price and loaded local fixture", () => {
  assert.equal(qualifyContent(url, snapshot, payload).passed, true);
  const category = "http://localhost:3000/en/c/electronics";
  assert.equal(qualifyContent(category, { ...snapshot, url: category }, payload).passed, true);
});
for (const [name, change] of [
  [
    "fallback",
    (s) => {
      s.unavailable = true;
    },
  ],
  [
    "redirect",
    (s) => {
      s.url += "/other";
    },
  ],
  [
    "wrong title",
    (s) => {
      s.title = "Other";
    },
  ],
  [
    "wrong price",
    (s) => {
      s.price = "K100.00";
    },
  ],
  [
    "wrong seller",
    (s) => {
      s.seller = "Demo Sandbox Shop";
    },
  ],
  [
    "hidden image",
    (s) => {
      s.images[0].visible = false;
    },
  ],
  [
    "unfinished image",
    (s) => {
      s.images[0].complete = false;
    },
  ],
  [
    "broken image",
    (s) => {
      s.images[0].width = 0;
    },
  ],
  [
    "wrong media origin",
    (s) => {
      s.images[0].src = "https://unowned.example/image.webp";
    },
  ],
  [
    "wrong listing",
    (_s, p) => {
      p.product.listings[0].id = "other";
    },
  ],
  [
    "additional cheaper listing",
    (_s, p) => {
      p.product.listings.unshift({ ...p.product.listings[0], id: "other", price_ngwee: 10000 });
    },
  ],
  [
    "out of stock",
    (_s, p) => {
      p.product.listings[0].in_stock = false;
    },
  ],
  [
    "wrong image ID",
    (_s, p) => {
      p.product.listings[0].images[0].public_id = "vergeo5/demo/phone-a";
    },
  ],
  [
    "empty catalog",
    (_s, p) => {
      p.catalog.items = [];
    },
  ],
  [
    "missing API product",
    (_s, p) => {
      delete p.product;
    },
  ],
])
  test(`readiness rejects ${name}`, () => {
    const s = structuredClone(snapshot),
      p = structuredClone(payload);
    change(s, p);
    assert.equal(qualifyContent(url, s, p).passed, false);
  });
test("home requires the exact fixture and hero; other policy pages require their actual forms", () => {
  assert.equal(
    qualifyContent(
      "http://localhost:3000/en",
      { ...snapshot, url: "http://localhost:3000/en" },
      payload,
    ).passed,
    true,
  );
  for (const path of ["/en/search", "/en/checkout"]) {
    const requested = `http://localhost:3000${path}`;
    const page = {
      ...snapshot,
      url: requested,
      heading: path.endsWith("search") ? "Search" : "Checkout",
      searchReady: true,
      checkoutReady: true,
    };
    assert.equal(qualifyContent(requested, page, {}).passed, true);
    assert.equal(qualifyContent(requested, { ...page, unavailable: true }, {}).passed, false);
    assert.equal(
      qualifyContent(requested, { ...page, searchReady: false, checkoutReady: false }, {}).passed,
      false,
    );
    assert.equal(
      qualifyContent(requested, { ...page, heading: "Something went wrong" }, {}).passed,
      false,
    );
  }
});
for (const flag of ["errorBoundary", "skeleton"]) {
  test(`all five policy pages refuse ${flag}, including otherwise healthy fixture content`, () => {
    for (const path of [
      "/en",
      "/en/c/electronics",
      "/en/p/smartphone-x1",
      "/en/search",
      "/en/checkout",
    ]) {
      const requested = `http://localhost:3000${path}`;
      assert.equal(
        qualifyContent(requested, { ...snapshot, url: requested, [flag]: true }, payload).passed,
        false,
      );
    }
  });
}
test("home refuses blank, missing hero, wrong seller and unloaded fixture media", () => {
  const home = "http://localhost:3000/en";
  for (const change of [
    { homeHero: false },
    { title: "" },
    { seller: "Wrong seller" },
    { images: [] },
    { homeHeroImages: [] },
    { homeHeroImages: [{ ...snapshot.homeHeroImages[0], width: 0 }] },
    { homeHeroImages: [{ ...snapshot.homeHeroImages[0], complete: false }] },
    { homeHeroImages: [{ ...snapshot.homeHeroImages[0], visible: false }] },
    {
      homeHeroImages: [
        { ...snapshot.homeHeroImages[0], src: "https://unowned.example/image.webp" },
      ],
    },
  ])
    assert.equal(
      qualifyContent(home, { ...snapshot, url: home, ...change }, payload).passed,
      false,
    );
});
test("inspects the exact retained measurement page, with no navigation or replacement", async () => {
  let calls = 0;
  const page = { url: () => url, evaluate: async () => (calls++ ? payload : snapshot) };
  assert.equal((await inspectMeasuredContent(url, page)).passed, true);
  assert.equal(calls, 2);
  calls = 0;
  const observed = await inspectMeasuredContent(url, page);
  assert.equal(observed.observed.title_matches, true);
  assert.equal(observed.observed.price_matches, true);
  assert.equal(observed.observed.seller_matches, true);
  assert.equal(observed.observed.images[0].owned_fixture, true);
  assert.equal(JSON.stringify(observed).includes(fixtureIdentity.vendor), false);
  assert.equal(JSON.stringify(observed).includes("http://localhost"), false);
  assert.equal((await inspectMeasuredContent(url, undefined)).passed, false);
  page.url = () => "http://localhost:3000/other";
  assert.equal((await inspectMeasuredContent(url, page)).passed, false);
});
test("failed category checks retain bounded exact-field diagnostics without relaxing seller identity", async () => {
  const category = "http://localhost:3000/en/c/electronics";
  let calls = 0;
  const page = {
    url: () => category,
    evaluate: async () =>
      calls++
        ? payload
        : {
            ...snapshot,
            url: category,
            seller: "Wrong seller",
            visibility: { title: null, price: null, seller: "opacity_zero" },
          },
  };
  const result = await inspectMeasuredContent(category, page);
  assert.equal(result.reason, "visible_fixture_content_mismatch");
  assert.equal(result.passed, false);
  assert.equal(result.observed.title_matches, true);
  assert.equal(result.observed.price_matches, true);
  assert.equal(result.observed.seller_matches, false);
  assert.equal(result.observed.visibility.seller, "opacity_zero");
});
test("owned variants match immutable manifest hashes and genuine WebP file signatures", async () => {
  const folder = new URL("../../apps/customer/ci-fixtures/", import.meta.url);
  const manifest = JSON.parse(await readFile(new URL("manifest.json", folder), "utf8"));
  for (const [name, entry] of Object.entries(manifest.assets)) {
    const bytes = await readFile(new URL(name, folder));
    assert.equal(bytes.subarray(0, 4).toString(), "RIFF");
    assert.equal(bytes.subarray(8, 12).toString(), "WEBP");
    assert.equal(createHash("sha256").update(bytes).digest("hex"), entry.sha256);
    assert.equal(bytes.length, entry.bytes);
  }
});
