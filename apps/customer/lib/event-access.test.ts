import { describe, expect, it } from "vitest";

import { eventAccessCookieName } from "./event-access";

describe("eventAccessCookieName", () => {
  it("derives a stable cookie name from the event slug", () => {
    expect(eventAccessCookieName("invite-only-gig")).toBe("event-access-invite-only-gig");
  });

  it("sanitises unsafe slug characters for Set-Cookie compatibility", () => {
    expect(eventAccessCookieName("VIP Launch!!!")).toBe("event-access-vip-launch---");
  });

  it("caps cookie name length for long slugs", () => {
    const longSlug = "a".repeat(120);
    expect(eventAccessCookieName(longSlug)).toHaveLength("event-access-".length + 96);
  });
});
