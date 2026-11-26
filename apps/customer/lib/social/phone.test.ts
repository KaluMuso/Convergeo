import { describe, expect, it } from "vitest";

import {
  hashContactPhone,
  normalizeToE164,
  supportsContactPicker,
  waMeInviteLink,
  waMeLinkFromRaw,
  waMeShareLink,
} from "./phone";

describe("normalizeToE164", () => {
  it("normalises Zambian formats to the same E.164", () => {
    for (const raw of ["0977123456", "977123456", "+260977123456", "260977123456"]) {
      expect(normalizeToE164(raw)).toBe("+260977123456");
    }
  });

  it("normalises MTN 096/076 prefixes to the same hash input", () => {
    for (const raw of ["0966123456", "966123456", "+260966123456", "260966123456"]) {
      expect(normalizeToE164(raw)).toBe("+260966123456");
    }
  });

  it("keeps foreign numbers", () => {
    expect(normalizeToE164("+447700900123")).toBe("+447700900123");
  });
});

describe("hashContactPhone", () => {
  it("hashes equivalent Zambian numbers identically", async () => {
    const a = await hashContactPhone("0977123456");
    const b = await hashContactPhone("+260977123456");
    expect(a).toBeTruthy();
    expect(a).toBe(b);
  });

  it("hashes 0966 local formats identically", async () => {
    const samples = ["0966123456", "966123456", "+260966123456", "260966123456"];
    const hashes = await Promise.all(samples.map((raw) => hashContactPhone(raw)));
    expect(new Set(hashes).size).toBe(1);
    expect(hashes[0]).toBeTruthy();
  });
});

describe("WhatsApp links", () => {
  it("builds wa.me invite with E.164", () => {
    expect(waMeInviteLink("+260977123456", "Join me")).toBe(
      "https://wa.me/260977123456?text=Join%20me",
    );
  });

  it("builds generic share link", () => {
    expect(waMeShareLink("Hi")).toBe("https://wa.me/?text=Hi");
  });

  it("normalises raw msisdn for vendor wa.me links", () => {
    expect(waMeLinkFromRaw("260971234567", "Hi")).toBe("https://wa.me/260971234567?text=Hi");
    expect(waMeLinkFromRaw("+260 971 234 567", "Hi")).toBe("https://wa.me/260971234567?text=Hi");
    expect(waMeLinkFromRaw("invalid", "Hi")).toBeNull();
  });
});

describe("supportsContactPicker", () => {
  it("is false when Contact Picker API is absent", () => {
    expect(supportsContactPicker()).toBe(false);
  });
});
