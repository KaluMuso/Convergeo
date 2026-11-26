import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  readDecodedFixtureImages,
  readMeasuredSnapshot,
} from "../../../scripts/ci/perf-content-readiness.mjs";

beforeEach(() => {
  vi.stubGlobal("location", {
    href: "http://localhost:3000/en/p/smartphone-x1",
    pathname: "/en/p/smartphone-x1",
    origin: "http://localhost:3000",
  });
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([
    { width: 100, height: 100 },
  ] as unknown as DOMRectList);
  document.body.innerHTML = `<header data-testid="pdp-header"><h1>Smartphone X1</h1></header>
    <div data-testid="pdp-interactive-body"><div data-testid="gallery-strip"><img id="fixture-image"></div></div>
    <section data-testid="pdp-buy-box"><div data-testid="price-block">K4,500.00</div>
      <p data-testid="pdp-price" style="display:none">K100.00</p>
      <div data-testid="pdp-buy-box-seller">Lusaka Electronics Hub</div></section>
    <img id="unrelated-image">`;
  for (const id of ["fixture-image", "unrelated-image"]) {
    Object.defineProperties(document.getElementById(id), {
      naturalWidth: { configurable: true, value: 720 },
      naturalHeight: { configurable: true, value: 960 },
      complete: { configurable: true, value: true },
      currentSrc: {
        configurable: true,
        value: "http://localhost:3000/api/ci-perf-media?width=720",
      },
    });
  }
});
afterEach(() => {
  document.body.innerHTML = "";
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("actual measured DOM snapshot", () => {
  it("decodes the displayed owned image's physical pixels while ignoring unrelated media", async () => {
    Object.defineProperty(document.getElementById("fixture-image"), "naturalWidth", {
      configurable: true,
      value: 195,
    });
    Object.defineProperty(document.getElementById("fixture-image"), "currentSrc", {
      configurable: true,
      value: "http://localhost:3000/api/ci-perf-media?width=360",
    });
    const close = vi.fn();
    const fetchMock = vi.fn(
      async () =>
        new Response(new Blob(["fixture"], { type: "image/webp" }), {
          status: 200,
          headers: { "Content-Type": "image/webp" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn(async () => ({ width: 360, close })),
    );
    const expectedSources = {
      images: ["http://localhost:3000/api/ci-perf-media?width=360"],
      homeHeroImages: [],
    };
    expect(await readDecodedFixtureImages(expectedSources)).toEqual({
      images: [360],
      homeHeroImages: [],
    });
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:3000/api/ci-perf-media?width=360", {
      cache: "no-store",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(close).toHaveBeenCalledOnce();
    Object.defineProperty(document.getElementById("fixture-image"), "currentSrc", {
      configurable: true,
      value: "https://unowned.example/image.webp",
    });
    expect(await readDecodedFixtureImages(expectedSources)).toEqual({
      images: [0],
      homeHeroImages: [],
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("rejects a source swap between the measured snapshot and the decoded image", async () => {
    const image = document.getElementById("fixture-image")!;
    Object.defineProperty(image, "currentSrc", {
      configurable: true,
      value: "http://localhost:3000/api/ci-perf-media?width=24",
    });
    const measured = readMeasuredSnapshot();
    Object.defineProperty(image, "currentSrc", {
      configurable: true,
      value: "http://localhost:3000/api/ci-perf-media?width=360",
    });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect(
      await readDecodedFixtureImages({
        images: measured.images.map((item) => item.src),
        homeHeroImages: measured.homeHeroImages.map((item) => item.src),
      }),
    ).toEqual({ images: [0], homeHeroImages: [] });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects a source change while the captured image is being fetched", async () => {
    const image = document.getElementById("fixture-image")!;
    const expectedSources = {
      images: ["http://localhost:3000/api/ci-perf-media?width=720"],
      homeHeroImages: [],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        Object.defineProperty(image, "currentSrc", {
          configurable: true,
          value: "http://localhost:3000/api/ci-perf-media?width=360",
        });
        return new Response(new Blob(["fixture"], { type: "image/webp" }), {
          status: 200,
          headers: { "Content-Type": "image/webp" },
        });
      }),
    );
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn(async () => ({ width: 720, close: vi.fn() })),
    );
    expect(await readDecodedFixtureImages(expectedSources)).toEqual({
      images: [0],
      homeHeroImages: [],
    });
  });

  it("rejects image count or order changes between snapshot and decode", async () => {
    const image = document.getElementById("fixture-image")!;
    const other = document.createElement("img");
    document.querySelector('[data-testid="gallery-strip"]')!.append(other);
    Object.defineProperties(other, {
      naturalWidth: { configurable: true, value: 360 },
      complete: { configurable: true, value: true },
      currentSrc: {
        configurable: true,
        value: "http://localhost:3000/api/ci-perf-media?width=360",
      },
    });
    const first = "http://localhost:3000/api/ci-perf-media?width=720";
    const second = "http://localhost:3000/api/ci-perf-media?width=360";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect(await readDecodedFixtureImages({ images: [first], homeHeroImages: [] })).toEqual({
      images: [],
      homeHeroImages: [],
    });
    image.before(other);
    expect(await readDecodedFixtureImages({ images: [first, second], homeHeroImages: [] })).toEqual(
      {
        images: [0, 0],
        homeHeroImages: [],
      },
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("rejects visible route error copy and skeletons rather than accepting an existing URL", () => {
    document.body.insertAdjacentHTML(
      "beforeend",
      '<main><h1>Something went wrong</h1><p>We hit an unexpected problem.</p><div data-testid="skeleton"></div></main>',
    );
    const snapshot = readMeasuredSnapshot();
    expect(snapshot.errorBoundary).toBe(true);
    expect(snapshot.skeleton).toBe(true);
    expect(snapshot.homeHero).toBe(false);
    document.querySelector("main")!.setAttribute("style", "display:none");
    expect(readMeasuredSnapshot().errorBoundary).toBe(false);
    expect(readMeasuredSnapshot().skeleton).toBe(false);
  });

  it("records positive home/actual form markers without changing carousel timers or navigation", () => {
    document.body.insertAdjacentHTML(
      "beforeend",
      '<main><div data-testid="home-hero-band"><div data-testid="hero-carousel"><div data-testid="hero-carousel-slide-0" aria-hidden="true"><h1 id="home-hero-heading">Shop locally</h1><div aria-hidden="true"><img id="hero-image"></div></div></div></div><input type="search" name="q"><input type="tel"></main>',
    );
    Object.defineProperties(document.getElementById("hero-image"), {
      naturalWidth: { configurable: true, value: 1200 },
      naturalHeight: { configurable: true, value: 1600 },
      complete: { configurable: true, value: true },
      currentSrc: {
        configurable: true,
        value: "http://localhost:3000/api/ci-perf-media?width=1200",
      },
    });
    const snapshot = readMeasuredSnapshot();
    expect(snapshot.homeHero).toBe(true);
    expect(snapshot.homeHeroImages).toEqual([
      {
        visible: true,
        complete: true,
        width: 1200,
        height: 1600,
        src: "http://localhost:3000/api/ci-perf-media?width=1200",
      },
    ]);
    Object.defineProperty(document.getElementById("hero-image"), "naturalWidth", {
      configurable: true,
      value: 0,
    });
    expect(readMeasuredSnapshot().homeHeroImages[0]?.width).toBe(0);
    expect(snapshot.searchReady).toBe(true);
    expect(snapshot.checkoutReady).toBe(true);
    expect(snapshot.skeleton).toBe(false);
  });

  it("records the actual category card and its field visibility without substituting another seller", () => {
    vi.stubGlobal("location", {
      href: "http://localhost:3000/en/c/electronics",
      pathname: "/en/c/electronics",
    });
    document.body.innerHTML =
      '<div data-testid="listing-card"><h3>Smartphone X1 — 128GB</h3><p>Sold by Lusaka Electronics Hub</p><div data-testid="price-block">K4,500.00</div><a data-testid="listing-card-link" href="/en/p/smartphone-x1"></a></div>';
    const snapshot = readMeasuredSnapshot();
    expect(snapshot.title).toBe("Smartphone X1 — 128GB");
    expect(snapshot.seller).toContain("Lusaka Electronics Hub");
    expect(snapshot.matchingCards).toBe(1);
    expect(snapshot.visibility).toEqual({
      title: null,
      price: null,
      seller: null,
    });
    document.querySelector('[data-testid="listing-card"]')!.setAttribute("style", "opacity:0");
    const hidden = readMeasuredSnapshot();
    expect(hidden.title).toBe("");
    expect(hidden.price).toBe("");
    expect(hidden.seller).toBe("");
    expect(hidden.visibility).toEqual({
      title: "opacity_zero",
      price: "opacity_zero",
      seller: "opacity_zero",
    });
  });

  it("reads visible price rather than sr-only text and only main gallery media", () => {
    const snapshot = readMeasuredSnapshot();
    expect(snapshot.title).toBe("Smartphone X1");
    expect(snapshot.price).toBe("K4,500.00");
    expect(snapshot.seller).toBe("Lusaka Electronics Hub");
    expect(snapshot.images).toHaveLength(1);
    expect(snapshot.images[0]).toMatchObject({
      visible: true,
      complete: true,
      width: 720,
    });
  });
  for (const css of ["display:none", "visibility:hidden", "opacity:0"]) {
    it(`does not count price or media hidden by ancestors: ${css}`, () => {
      document.querySelector('[data-testid="pdp-buy-box"]')!.setAttribute("style", css);
      document.querySelector('[data-testid="pdp-interactive-body"]')!.setAttribute("style", css);
      const snapshot = readMeasuredSnapshot();
      expect(snapshot.price).toBe("");
      expect(snapshot.seller).toBe("");
      expect(snapshot.images[0]?.visible).toBe(false);
    });
  }
  it("records real incomplete/broken image state and refuses unrelated valid image", () => {
    Object.defineProperties(document.getElementById("fixture-image"), {
      complete: { configurable: true, value: false },
      naturalWidth: { configurable: true, value: 0 },
    });
    const snapshot = readMeasuredSnapshot();
    expect(snapshot.images).toHaveLength(1);
    expect(snapshot.images[0]).toMatchObject({ complete: false, width: 0 });
  });
  it("does not substitute hidden price and detects actual unavailable elements", () => {
    document.querySelector('[data-testid="price-block"]')!.textContent = "K100.00";
    document.querySelector('[data-testid="pdp-price"]')!.textContent = "K4,500.00";
    document.body.insertAdjacentHTML("beforeend", '<div data-testid="pdp-unavailable"></div>');
    const snapshot = readMeasuredSnapshot();
    expect(snapshot.price).toBe("K100.00");
    expect(snapshot.unavailable).toBe(true);
  });
});
