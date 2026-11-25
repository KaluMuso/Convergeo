import { describe, expect, it } from "vitest";

import { splitTicketPerks, tierSpotsRemaining } from "./tier-availability";

describe("tierSpotsRemaining", () => {
  it("shows urgency at 20 remaining", () => {
    expect(tierSpotsRemaining(100, 80)).toBe(20);
  });

  it("hides when more than 20 remain", () => {
    expect(tierSpotsRemaining(100, 79)).toBeNull();
  });

  it("hides when qty cap is null", () => {
    expect(tierSpotsRemaining(null, 10)).toBeNull();
  });
});

describe("splitTicketPerks", () => {
  it("splits newline perks", () => {
    expect(splitTicketPerks("VIP lounge\nMeet & greet")).toEqual(["VIP lounge", "Meet & greet"]);
  });
});
