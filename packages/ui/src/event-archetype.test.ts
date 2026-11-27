import { describe, expect, it } from "vitest";

import {
  ARCHETYPE_SECTIONS,
  ARCHETYPE_THEME,
  CATEGORY_ARCHETYPE,
  EVENT_ARCHETYPES,
  classifyTicketTier,
  deriveArchetype,
  sanitiseDetails,
  safeHttpsUrl,
  safeImageRef,
} from "./event-archetype";

describe("deriveArchetype", () => {
  it.each([
    ["concerts", "single", "concert"],
    ["gospel", "single", "religious"],
    ["church", "single", "religious"],
    ["football", "single", "sports_family"],
    ["family", null, "sports_family"],
    ["pop-up-dinners", "single", "restaurant"],
    ["private-events", "single", "private_gathering"],
    ["workshops", "private", "private_gathering"],
    ["workshops", "single", "generic"],
    [null, null, "generic"],
  ])("%s / %s -> %s", (category, eventType, expected) => {
    expect(deriveArchetype(category, eventType)).toBe(expected);
  });

  it("has no branded archetype and maps only known archetypes", () => {
    const values = Object.values(CATEGORY_ARCHETYPE);
    expect(EVENT_ARCHETYPES).not.toContain("branded" as never);
    for (const value of values) expect(EVENT_ARCHETYPES).toContain(value);
  });
});

describe("themes use existing tokens only", () => {
  it("never embeds a literal colour", () => {
    for (const archetype of EVENT_ARCHETYPES) {
      const { tint, accent } = ARCHETYPE_THEME[archetype];
      for (const value of [tint, accent]) {
        expect(value).not.toMatch(/#[0-9a-f]{3,8}\b/i);
        expect(value).not.toMatch(/\b(rgb|hsl|oklch)a?\(/i);
        expect(value).toContain("var(--");
      }
    }
  });

  it("offers sections for every archetype, always including the common ones", () => {
    for (const archetype of EVENT_ARCHETYPES) {
      expect(ARCHETYPE_SECTIONS[archetype]).toEqual(
        expect.arrayContaining(["sponsors", "dress_code", "age_policy", "faqs"]),
      );
    }
    expect(ARCHETYPE_SECTIONS.concert).toContain("lineup");
    expect(ARCHETYPE_SECTIONS.concert).not.toContain("menu_sections");
  });
});

describe("sanitising", () => {
  it("accepts https only", () => {
    expect(safeHttpsUrl("https://example.com/a")).toBe("https://example.com/a");
    expect(safeHttpsUrl("javascript:alert(1)")).toBeUndefined();
    expect(safeHttpsUrl("http://example.com")).toBeUndefined();
    expect(safeHttpsUrl("/relative")).toBeUndefined();
    expect(safeHttpsUrl(42)).toBeUndefined();
  });

  it("accepts cloudinary ids and https images only", () => {
    expect(safeImageRef("events/hero_1")).toBe("events/hero_1");
    expect(safeImageRef("https://cdn.example.com/a.jpg")).toBe("https://cdn.example.com/a.jpg");
    expect(safeImageRef("data:image/png;base64,AAA")).toBeUndefined();
    expect(safeImageRef("../x")).toBeUndefined();
  });

  it("returns empty typed details for junk and drops unsafe fields", () => {
    expect(sanitiseDetails(null).lineup).toEqual([]);
    expect(sanitiseDetails("x").sponsors).toEqual([]);
    const out = sanitiseDetails({
      sponsors: [{ name: "Mosi", link_url: "javascript:1", logo: "data:x" }, { name: "" }, 7],
      lineup: [{ name: "DJ Zed", role: "bogus", slot: "25:99" }],
      agenda: [
        { time: "09:00", title: "Worship" },
        { time: "bad", title: "x" },
      ],
      menu_sections: [{ title: "Mains", items: [{ name: "Nshima", price_ngwee: 12000.5 }] }],
      age_policy: "21_plus",
    });
    expect(out.sponsors).toHaveLength(1);
    expect(out.sponsors[0]).toMatchObject({
      status: "pending",
      name: "Mosi",
      link_url: undefined,
      logo: undefined,
    });
    expect(out.lineup[0]).toMatchObject({ role: "support", slot: undefined });
    expect(out.agenda).toHaveLength(1);
    expect(out.menu_sections[0]?.items[0]?.price_ngwee).toBeUndefined();
    expect(out.age_policy).toBeUndefined();
  });

  it("caps list lengths", () => {
    const many = Array.from({ length: 50 }, (_, i) => ({ name: `a${i}` }));
    expect(sanitiseDetails({ lineup: many }).lineup).toHaveLength(30);
    expect(sanitiseDetails({ sponsors: many }).sponsors).toHaveLength(6);
  });
});

describe("classifyTicketTier", () => {
  it.each([
    ["VVIP Table", false, "vvip"],
    ["VIP", false, "vip"],
    ["General Admission", false, "ga"],
    ["GA", false, "ga"],
    ["Family (2+2)", false, "family"],
    ["Child 3-12", false, "child"],
    ["Table for 4", false, "table"],
    ["RSVP", true, "free"],
    ["Entry", false, "standard"],
  ])("%s -> %s", (name, isFree, expected) => {
    expect(classifyTicketTier({ name, isFree })).toBe(expected);
  });
});
