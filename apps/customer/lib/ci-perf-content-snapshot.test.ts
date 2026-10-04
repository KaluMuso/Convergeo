import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { readMeasuredSnapshot } from "../../../scripts/ci/perf-content-readiness.mjs";

beforeEach(() => {
  vi.stubGlobal("location", {
    href: "http://localhost:3000/en/p/smartphone-x1",
    pathname: "/en/p/smartphone-x1",
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
  it("reads visible price rather than sr-only text and only main gallery media", () => {
    const snapshot = readMeasuredSnapshot();
    expect(snapshot.title).toBe("Smartphone X1");
    expect(snapshot.price).toBe("K4,500.00");
    expect(snapshot.seller).toBe("Lusaka Electronics Hub");
    expect(snapshot.images).toHaveLength(1);
    expect(snapshot.images[0]).toMatchObject({ visible: true, complete: true, width: 720 });
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
