import { describe, expect, it } from "vitest";

import { defaultFulfilment } from "./step-fulfilment-step";

describe("defaultFulfilment", () => {
  it("prefers delivery when it is eligible and offered", () => {
    expect(defaultFulfilment({ delivery_eligible: true })).toBe("delivery");
  });

  it("falls back to pickup when the seller does not offer delivery", () => {
    expect(
      defaultFulfilment({ delivery_eligible: true, delivery_offered: false }),
    ).toBe("pickup");
  });

  it("picks pickup when delivery is not eligible", () => {
    expect(defaultFulfilment({ delivery_eligible: false })).toBe("pickup");
  });

  it("keeps delivery selected when only delivery is offered, even outside the free threshold", () => {
    expect(
      defaultFulfilment({
        delivery_eligible: false,
        delivery_offered: true,
        pickup_offered: false,
      }),
    ).toBe("delivery");
  });
});
