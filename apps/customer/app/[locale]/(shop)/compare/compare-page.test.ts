import { describe, expect, it } from "vitest";

import { shouldShowComparison } from "../_components/pdp/comparison";

/** Mirrors resolveProductSlug in page.tsx for unit coverage. */
function resolveProductSlug(query: { product?: string; slug?: string }): string | null {
  const raw = query.product?.trim() || query.slug?.trim();
  if (!raw) {
    return null;
  }
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/i.test(raw)) {
    return null;
  }
  return raw;
}

describe("compare page entry (CUST-04)", () => {
  it("requires a product slug and rejects invalid values", () => {
    expect(resolveProductSlug({})).toBeNull();
    expect(resolveProductSlug({ product: "itel-a70" })).toBe("itel-a70");
    expect(resolveProductSlug({ slug: "Blue Widget" })).toBeNull();
    expect(resolveProductSlug({ product: "../etc/passwd" })).toBeNull();
  });

  it("only treats multi-vendor SKUs as comparable", () => {
    expect(shouldShowComparison(0)).toBe(false);
    expect(shouldShowComparison(1)).toBe(false);
    expect(shouldShowComparison(2)).toBe(true);
  });
});
