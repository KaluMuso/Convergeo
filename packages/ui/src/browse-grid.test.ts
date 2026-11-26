import { describe, expect, it } from "vitest";

import { browseCardGridClass, browseProductGridClass } from "./browse-grid";

describe("browse-grid", () => {
  it("defines product tile columns up to xl:grid-cols-5 with unified gaps", () => {
    expect(browseProductGridClass).toContain("gap-3");
    expect(browseProductGridClass).toContain("md:gap-4");
    expect(browseProductGridClass).toContain("grid-cols-2");
    expect(browseProductGridClass).toContain("xl:grid-cols-5");
    expect(browseProductGridClass).not.toContain("2xl:grid-cols-6");
  });

  it("defines card browse columns up to xl:grid-cols-4", () => {
    expect(browseCardGridClass).toContain("sm:grid-cols-2");
    expect(browseCardGridClass).toContain("xl:grid-cols-4");
  });
});
