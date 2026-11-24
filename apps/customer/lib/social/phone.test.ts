import { describe, expect, it } from "vitest";

import {
  hashContactPhone,
  normalizeToE164,
  supportsContactPicker,
  waMeInviteLink,
  waMeShareLink,
} from "./phone";

describe("normalizeToE164", () => {
  it("normalises Zambian formats to the same E.164", () => {
    for (const raw of ["0977123456", "977123456", "+260977123456", "260977123456"]) {
      expect(normalizeToE164(raw)).toBe("+260977123456");
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
});

describe("supportsContactPicker", () => {
  it("is false when Contact Picker API is absent", () => {
    expect(supportsContactPicker()).toBe(false);
  });
});
