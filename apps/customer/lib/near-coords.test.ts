import { beforeEach, describe, expect, it } from "vitest";

import {
  distanceMetres,
  forgetNearCoords,
  readNearCoords,
  rememberNearCoords,
} from "./near-coords";

beforeEach(() => window.sessionStorage.clear());

describe("near coords", () => {
  it("prefers URL coordinates, then the remembered Near-me fix", () => {
    rememberNearCoords(-15.42, 28.28);
    expect(readNearCoords("?lat=-12.8&lng=28.2")).toEqual({
      lat: -12.8,
      lng: 28.2,
    });
    expect(readNearCoords("")).toEqual({ lat: -15.42, lng: 28.28 });
    forgetNearCoords();
    expect(readNearCoords("")).toBeNull();
  });

  it("rejects out-of-range or junk coordinates", () => {
    rememberNearCoords(120, 28);
    expect(readNearCoords("")).toBeNull();
    expect(readNearCoords("?lat=abc&lng=1")).toBeNull();
  });

  it("computes great-circle distance in metres", () => {
    expect(distanceMetres({ lat: 0, lng: 0 }, { lat: 0, lng: 0 })).toBe(0);
    const d = distanceMetres(
      { lat: -15.42, lng: 28.28 },
      { lat: -15.44, lng: 28.3 },
    );
    expect(Math.round(d / 100)).toBe(31);
  });
});
