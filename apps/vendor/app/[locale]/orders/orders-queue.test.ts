import { describe, expect, it } from "vitest";

import vendorMessages from "../../../../../packages/i18n/messages/en/vendor.json";

describe("vendor home + queue i18n", () => {
  it("exposes nested home and queue keys", () => {
    expect(vendorMessages.home.title).toBe("Today");
    expect(vendorMessages.home.takings.label).toBe("Today's takings");
    expect(vendorMessages.queue.title).toBe("Orders");
    expect(vendorMessages.queue.filters.needsAction).toBe("Needs action");
  });
});
