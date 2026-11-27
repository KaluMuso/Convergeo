import { describe, expect, it } from "vitest";

import { magnifierLensRect, zoomPaneBackgroundPosition } from "./zoom-math";

describe("magnifierLensRect", () => {
  it("centres the lens on the pointer and clamps to the image box", () => {
    expect(magnifierLensRect(50, 40, { width: 400, height: 300 }, 80)).toEqual({
      left: 10,
      top: 0,
    });
    expect(magnifierLensRect(10, 10, { width: 400, height: 300 }, 80)).toEqual({ left: 0, top: 0 });
    expect(magnifierLensRect(390, 290, { width: 400, height: 300 }, 80)).toEqual({
      left: 320,
      top: 220,
    });
  });
});

describe("zoomPaneBackgroundPosition", () => {
  it("maps pointer coordinates to percentage background position", () => {
    expect(zoomPaneBackgroundPosition(200, 150, { width: 400, height: 300 })).toEqual({
      xPercent: 50,
      yPercent: 50,
    });
    expect(zoomPaneBackgroundPosition(0, 0, { width: 400, height: 300 })).toEqual({
      xPercent: 0,
      yPercent: 0,
    });
    expect(zoomPaneBackgroundPosition(400, 300, { width: 400, height: 300 })).toEqual({
      xPercent: 100,
      yPercent: 100,
    });
  });
});
