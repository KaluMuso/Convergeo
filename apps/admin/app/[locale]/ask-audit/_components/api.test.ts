import { describe, expect, it, vi } from "vitest";

vi.mock("@vergeo/auth", () => ({ getBrowserAccessToken: () => "token" }));

import { askAuditQuery, storefrontUrl } from "./api";

describe("askAuditQuery", () => {
  it("asks for flagged answers and carries the cursor", () => {
    const query = new URLSearchParams(
      askAuditQuery(
        { flaggedOnly: true, severity: "critical" },
        { before: "2026-11-27T09:00:00+00:00", beforeId: "ans-1" },
      ),
    );
    expect(query.get("flagged_only")).toBe("true");
    expect(query.get("severity")).toBe("critical");
    expect(query.get("before")).toBe("2026-11-27T09:00:00+00:00");
    expect(query.get("before_id")).toBe("ans-1");
  });

  it("omits filters that are off", () => {
    const query = new URLSearchParams(askAuditQuery({ flaggedOnly: false, severity: "" }));
    expect(query.has("flagged_only")).toBe(false);
    expect(query.has("severity")).toBe(false);
    expect(query.get("limit")).toBe("25");
  });
});

describe("storefrontUrl", () => {
  it("prefixes origin and locale, and refuses anything but a rooted path", () => {
    expect(storefrontUrl("https://vergeo5.com/", "en", "/v/shop")).toBe(
      "https://vergeo5.com/en/v/shop",
    );
    expect(storefrontUrl("https://vergeo5.com", "en", null)).toBeNull();
    expect(storefrontUrl("https://vergeo5.com", "en", "//evil.com")).toBe(
      "https://vergeo5.com/en//evil.com",
    );
  });
});
