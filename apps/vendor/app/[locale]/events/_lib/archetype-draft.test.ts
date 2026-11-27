import { describe, expect, it } from "vitest";

import {
  detailsToDraft,
  draftToDetails,
  emptyDraft,
  kwachaToNgwee,
  ngweeToKwacha,
  validateDraft,
} from "./archetype-draft";

describe("kwacha <-> ngwee", () => {
  it("converts without floats and rejects malformed input", () => {
    expect(kwachaToNgwee("120")).toBe(12000);
    expect(kwachaToNgwee("120.5")).toBe(12050);
    expect(kwachaToNgwee("0.07")).toBe(7);
    expect(kwachaToNgwee("19.99")).toBe(1999);
    for (const bad of ["", "abc", "-1", "1.234", "1,5", "1e3"])
      expect(kwachaToNgwee(bad)).toBeNull();
    expect(ngweeToKwacha(12050)).toBe("120.50");
    expect(ngweeToKwacha(12000)).toBe("120");
    expect(ngweeToKwacha(7)).toBe("0.07");
  });
});

describe("draftToDetails", () => {
  it("only emits sections the archetype offers and omits blanks", () => {
    const draft = emptyDraft();
    draft.scalars.doors_open = "18:00";
    draft.scalars.denomination = "Anglican"; // religious-only
    draft.rows.lineup = [
      {
        name: "DJ Zed",
        role: "dj",
        stage: "",
        slot: "21:00",
        image: "",
        bio: "",
      },
      { name: "", role: "", stage: "", slot: "", image: "", bio: "" },
    ];
    draft.rows.agenda = [{ time: "09:00", title: "Worship", speaker: "", notes: "" }];
    draft.lines.stages = "Main\n\n Chill \n";
    expect(draftToDetails("concert", draft)).toEqual({
      doors_open: "18:00",
      lineup: [{ name: "DJ Zed", role: "dj", slot: "21:00" }],
      stages: ["Main", "Chill"],
    });
    expect(draftToDetails("religious", draft)).toEqual({
      denomination: "Anglican",
      agenda: [{ time: "09:00", title: "Worship" }],
    });
  });

  it("emits menu prices as integer ngwee and drops empty sections", () => {
    const draft = emptyDraft();
    draft.menu = [
      {
        title: "Mains",
        items: [
          {
            name: "Nshima",
            description: "",
            price: "120.50",
            dietary: "vegan, halal",
          },
          { name: "", description: "", price: "", dietary: "" },
        ],
      },
      {
        title: "Empty",
        items: [{ name: "", description: "", price: "", dietary: "" }],
      },
    ];
    expect(draftToDetails("restaurant", draft)).toEqual({
      menu_sections: [
        {
          title: "Mains",
          items: [{ name: "Nshima", price_ngwee: 12050, dietary: ["vegan", "halal"] }],
        },
      ],
    });
    expect(draftToDetails("concert", draft)).toEqual({});
  });

  it("emits presented_by and numeric ages for the right archetypes", () => {
    const draft = emptyDraft();
    draft.presentedBy = {
      name: "Mosi",
      logo: "",
      link_url: "https://example.com",
      tagline: "",
    };
    draft.rows.age_groups = [{ label: "Kids", min_age: "3", max_age: "12" }];
    expect(draftToDetails("branded", draft)).toEqual({
      presented_by: { name: "Mosi", link_url: "https://example.com" },
    });
    expect(draftToDetails("sports_family", draft)).toEqual({
      age_groups: [{ label: "Kids", min_age: 3, max_age: 12 }],
    });
  });

  it("round-trips API details through the draft", () => {
    const details = {
      dress_code: "Smart",
      lineup: [{ name: "A", role: "headliner", slot: "22:00" }],
      stages: ["Main"],
      sponsors: [{ name: "Mosi", link_url: "https://example.com/m" }],
    };
    expect(draftToDetails("concert", detailsToDraft(details))).toEqual(details);
  });

  it("detailsToDraft tolerates junk", () => {
    expect(draftToDetails("concert", detailsToDraft("junk"))).toEqual({});
    expect(draftToDetails("concert", detailsToDraft({ lineup: "x", menu_sections: 5 }))).toEqual(
      {},
    );
  });
});

describe("validateDraft", () => {
  it("flags bad time, url, price, number and missing required fields", () => {
    const d = emptyDraft();
    d.scalars.doors_open = "7pm";
    expect(validateDraft("concert", d)).toBe("invalidTime");

    const url = emptyDraft();
    url.rows.sponsors = [{ name: "x", logo: "", link_url: "javascript:1", tagline: "" }];
    expect(validateDraft("generic", url)).toBe("invalidUrl");
    const http = emptyDraft();
    http.rows.sponsors = [{ name: "x", logo: "", link_url: "http://example.com", tagline: "" }];
    expect(validateDraft("generic", http)).toBe("invalidUrl");
    const logo = emptyDraft();
    logo.rows.sponsors = [
      {
        name: "x",
        logo: "data:image/png;base64,AA",
        link_url: "",
        tagline: "",
      },
    ];
    expect(validateDraft("generic", logo)).toBe("invalidUrl");

    const missing = emptyDraft();
    missing.rows.faqs = [{ question: "Parking?", answer: "" }];
    expect(validateDraft("generic", missing)).toBe("requiredField");

    const price = emptyDraft();
    price.menu = [
      {
        title: "M",
        items: [{ name: "x", description: "", price: "12,5", dietary: "" }],
      },
    ];
    expect(validateDraft("restaurant", price)).toBe("invalidPrice");

    const age = emptyDraft();
    age.rows.age_groups = [{ label: "Kids", min_age: "abc", max_age: "" }];
    expect(validateDraft("sports_family", age)).toBe("invalidNumber");

    const live = emptyDraft();
    live.scalars.livestream_url = "http://x.com";
    expect(validateDraft("religious", live)).toBe("invalidUrl");
  });

  it("ignores untouched blank rows and sections of other archetypes; accepts valid drafts", () => {
    const d = emptyDraft();
    d.rows.faqs = [{ question: "", answer: "" }];
    d.scalars.doors_open = "bad"; // only checked for archetypes that offer it
    expect(validateDraft("religious", d)).toBeNull();
    d.scalars.doors_open = "18:30";
    d.rows.lineup = [
      {
        name: "A",
        role: "dj",
        stage: "",
        slot: "21:00",
        image: "events/a",
        bio: "",
      },
    ];
    expect(validateDraft("concert", d)).toBeNull();
  });

  it("caps rows per list", () => {
    const d = emptyDraft();
    d.rows.sponsors = Array.from({ length: 7 }, (_, i) => ({
      name: `s${i}`,
      logo: "",
      link_url: "",
      tagline: "",
    }));
    expect(validateDraft("generic", d)).toBe("tooMany");
  });
});
