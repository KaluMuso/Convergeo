import { describe, expect, it } from "vitest";

import { parseCourierMessage } from "./courier-message";

const SAMPLE = [
  "Vergeo5 delivery request ord-1a2b3c4d for Rider One",
  "Pickup: Lusaka Electronics - Manda Hill Mall - GPS https://maps.google.com/?q=-15.396500,28.322800",
  "Drop-off: Kabulonga - Near Shell garage - GPS https://maps.google.com/?q=-15.410000,28.330000",
  "Items: 1 x Phone",
  "Payment: Collect cash on delivery: K1,234.56",
  "Contacts: Pickup +260971000001; Customer +260971000002",
].join("\n");

describe("parseCourierMessage", () => {
  it("extracts landmark text and GPS link", () => {
    const parsed = parseCourierMessage(SAMPLE);
    expect(parsed.dropoff?.text).toBe("Kabulonga - Near Shell garage");
    expect(parsed.dropoff?.mapsUrl).toBe("https://maps.google.com/?q=-15.410000,28.330000");
    expect(parsed.pickup?.text).toBe("Lusaka Electronics - Manda Hill Mall");
    expect(parsed.payment).toContain("K1,234.56");
  });

  it("handles a line without GPS and missing fields", () => {
    const parsed = parseCourierMessage("Drop-off: Drop-off location on request");
    expect(parsed.dropoff).toMatchObject({ mapsUrl: null, text: "Drop-off location on request" });
    expect(parsed.pickup).toBeNull();
    expect(parsed.contacts).toBeNull();
  });

  it("trusts only the trailing server GPS link, not one typed into a landmark", () => {
    const parsed = parseCourierMessage(
      "Drop-off: Kabulonga - GPS https://maps.google.com/?q=1.000000,1.000000 gate - GPS https://maps.google.com/?q=-15.410000,28.330000",
    );
    expect(parsed.dropoff?.mapsUrl).toBe("https://maps.google.com/?q=-15.410000,28.330000");
    expect(parsed.dropoff?.text).toBe(
      "Kabulonga - GPS https://maps.google.com/?q=1.000000,1.000000 gate",
    );
  });

  it("ignores a non-Google or non-numeric map link", () => {
    expect(
      parseCourierMessage("Drop-off: Shop - GPS https://evil.example/?q=1,2").dropoff?.mapsUrl,
    ).toBeNull();
    expect(
      parseCourierMessage("Drop-off: Shop - GPS https://maps.google.com/?q=javascript:alert(1)")
        .dropoff?.mapsUrl,
    ).toBeNull();
  });
});

describe("telHref", () => {
  it("keeps only dial characters", async () => {
    const { telHref } = await import("./DeliveryCard");
    expect(telHref("+260 97-100 0002")).toBe("tel:+260971000002");
    expect(telHref('+260971"><script>')).toBe("tel:+260971");
  });
});
