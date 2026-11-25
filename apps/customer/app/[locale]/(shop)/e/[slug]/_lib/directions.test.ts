import { describe, expect, it } from "vitest";

function directionsUrl(lat: number, lng: number): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
}

describe("directionsUrl", () => {
  it("uses Google Maps directions API shape", () => {
    expect(directionsUrl(-15.4167, 28.2833)).toBe(
      "https://www.google.com/maps/dir/?api=1&destination=-15.4167,28.2833",
    );
  });
});
