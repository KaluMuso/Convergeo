import { describe, expect, it } from "vitest";

import manifest from "./manifest";

describe("vendor web manifest", () => {
  it("exposes PWA identity, scope, and maskable icons", () => {
    const m = manifest();
    expect(m.name).toBe("Convergeo Vendor");
    expect(m.short_name).toBe("Vendor");
    expect(m.start_url).toBe("/en");
    expect(m.scope).toBe("/");
    expect(m.display).toBe("standalone");
    expect(m.icons?.some((icon) => icon.purpose === "maskable")).toBe(true);
    expect(m.icons?.every((icon) => icon.src.startsWith("/brand/"))).toBe(true);
  });
});
