import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { sanitiseDetails } from "@vergeo/ui/src/event-archetype";
import { afterEach, describe, expect, it } from "vitest";

import { ArchetypeBody, ArchetypeLead, archetypeChips } from "./archetype-body";

import type { ShowcaseTicket, T } from "./archetype-blocks";
import type { EventArchetype } from "@vergeo/ui/src/event-archetype";

afterEach(cleanup);

const t: T = (key, values) =>
  values
    ? `${key}|${Object.entries(values)
        .map(([k, v]) => `${k}=${v}`)
        .join(",")}`
    : key;

function ticket(over: Partial<ShowcaseTicket> & { id: string; name: string }): ShowcaseTicket {
  return {
    price_ngwee: 10000,
    is_free: false,
    is_sold_out: false,
    qty_cap: null,
    tickets_sold: 0,
    perks: null,
    early_bird_price_ngwee: null,
    ...over,
  };
}

const tiers: ShowcaseTicket[] = [
  ticket({ id: "1", name: "General Admission", price_ngwee: 10000 }),
  ticket({
    id: "2",
    name: "VIP",
    price_ngwee: 30000,
    perks: "Front area\nFree drink",
  }),
  ticket({
    id: "3",
    name: "VVIP Table",
    price_ngwee: 90000,
    qty_cap: 10,
    tickets_sold: 7,
  }),
];

function body(
  archetype: EventArchetype,
  rawDetails: unknown,
  over: Partial<{ images: string[]; tickets: ShowcaseTicket[] }> = {},
) {
  return render(
    <ArchetypeBody
      archetype={archetype}
      rawDetails={rawDetails}
      images={over.images ?? ["events/hero"]}
      title="Night"
      tickets={over.tickets ?? []}
      t={t}
    />,
  );
}

describe("ArchetypeBody", () => {
  it("renders nothing for a bare generic event (graceful fallback)", () => {
    const { container } = body("generic", {});
    expect(container.textContent).toBe("");
  });

  it("concert: lineup with headliner/support, tier cards sorted by price with badges", () => {
    body(
      "concert",
      {
        lineup: [
          { name: "Big Star", role: "headliner", slot: "23:00" },
          { name: "DJ Zed", role: "dj", slot: "21:00", stage: "Main" },
        ],
        stages: ["Main"],
        doors_open: "18:00",
      },
      { tickets: tiers },
    );
    expect(screen.getByTestId("block-lineup")).toHaveTextContent("Big Star");
    expect(screen.getByTestId("block-lineup")).toHaveTextContent("DJ Zed");
    expect(screen.getByTestId("block-lineup")).toHaveTextContent("archetype.doorsOpen|time=18:00");
    const cards = within(screen.getByTestId("tier-showcase"))
      .getAllByRole("listitem")
      .filter((li) => li.hasAttribute("data-tier-kind"));
    expect(cards.map((c) => c.getAttribute("data-tier-kind"))).toEqual(["ga", "vip", "vvip"]);
    expect(screen.getByText("Free drink")).toBeInTheDocument();
    // 3 left of 10 on VVIP.
    expect(screen.getByText(/detail\.ticketRemaining\|count=3/)).toBeInTheDocument();
  });

  it("religious: order of service, speakers, donation note, free ticket shown as free", () => {
    body(
      "religious",
      {
        agenda: [{ time: "09:00", title: "Worship", speaker: "Pastor Jane" }],
        speakers: [{ name: "Pastor Jane", role: "Guest speaker" }],
        donation_note: "Offerings are voluntary",
        livestream_url: "https://example.com/live",
        languages: ["English", "Bemba"],
      },
      {
        tickets: [ticket({ id: "f", name: "Entry", is_free: true, price_ngwee: 0 })],
      },
    );
    expect(screen.getByTestId("block-agenda")).toHaveTextContent("Worship");
    expect(screen.getByTestId("block-speakers")).toHaveTextContent("Guest speaker");
    expect(screen.getByTestId("tier-showcase")).toHaveTextContent("Offerings are voluntary");
    expect(screen.getByTestId("tier-showcase")).toHaveTextContent("detail.free");
    expect(screen.getByRole("link", { name: "archetype.watchLivestream" })).toHaveAttribute(
      "href",
      "https://example.com/live",
    );
    expect(screen.getByTestId("block-notes")).toHaveTextContent("English, Bemba");
  });

  it("sports_family: activities, age groups and family/child tickets", () => {
    body(
      "sports_family",
      {
        activities: [{ name: "Relay", time: "10:15", area: "Field A" }],
        age_groups: [
          { label: "Kids", min_age: 3, max_age: 12 },
          { label: "Adults", min_age: 18 },
        ],
        bring_list: ["Water"],
      },
      {
        tickets: [
          ticket({ id: "c", name: "Child 3-12", price_ngwee: 2000 }),
          ticket({ id: "fam", name: "Family (2+2)", price_ngwee: 8000 }),
        ],
      },
    );
    expect(screen.getByTestId("block-activities")).toHaveTextContent("Relay");
    expect(screen.getByTestId("block-activities")).toHaveTextContent(
      "archetype.ageRange|min=3,max=12",
    );
    expect(screen.getByTestId("block-activities")).toHaveTextContent("archetype.agePlus|min=18");
    const kinds = screen
      .getAllByRole("listitem")
      .filter((li) => li.dataset.tierKind)
      .map((li) => li.dataset.tierKind);
    expect(kinds).toEqual(["child", "family"]);
  });

  it("restaurant: menu prices come from integer ngwee via formatK", () => {
    body("restaurant", {
      menu_sections: [
        {
          title: "Mains",
          items: [{ name: "Nshima", price_ngwee: 12000, dietary: ["vegan"] }],
        },
      ],
      seating_note: "Tables of 4",
    });
    const menu = screen.getByTestId("block-menu");
    expect(menu).toHaveTextContent("Nshima");
    expect(menu).toHaveTextContent("K120");
    expect(menu).toHaveTextContent("archetype.dietary.vegan");
    expect(menu).toHaveTextContent("Tables of 4");
  });

  it("branded: lead band shows presented-by sponsor; body shows activations and no duplicate band", () => {
    const raw = {
      presented_by: { name: "Mosi", link_url: "https://example.com/mosi" },
      sponsors: [{ name: "Mosi" }, { name: "Zamtel" }],
      activations: [{ title: "Tasting" }],
    };
    const { container } = render(
      <>
        <ArchetypeLead archetype="branded" rawDetails={raw} t={t} />
        <ArchetypeBody
          archetype="branded"
          rawDetails={raw}
          images={["a"]}
          title="x"
          tickets={[]}
          t={t}
        />
      </>,
    );
    expect(screen.getAllByTestId("sponsor-band")).toHaveLength(1);
    const band = screen.getByTestId("sponsor-band");
    expect(band).toHaveTextContent("archetype.presentedBy");
    expect(band).toHaveTextContent("Zamtel");
    expect(within(band).getAllByText("Mosi")).toHaveLength(1);
    expect(screen.getByTestId("block-activations")).toHaveTextContent("Tasting");
    expect(container.querySelector('a[rel~="sponsored"]')).toHaveAttribute(
      "href",
      "https://example.com/mosi",
    );
  });

  it("non-branded archetypes show a plain sponsor band at the end and no lead", () => {
    const raw = { sponsors: [{ name: "Zamtel", tagline: "Connect" }] };
    const { container } = render(
      <>
        <ArchetypeLead archetype="concert" rawDetails={raw} t={t} />
        <ArchetypeBody
          archetype="concert"
          rawDetails={raw}
          images={[]}
          title="x"
          tickets={[]}
          t={t}
        />
      </>,
    );
    expect(screen.getAllByTestId("sponsor-band")).toHaveLength(1);
    expect(container).toHaveTextContent("archetype.sections.sponsors");
  });

  it("private gathering: host notes and agenda", () => {
    body("private_gathering", {
      host_names: "The Bandas",
      occasion: "Wedding",
      agenda: [{ time: "14:00", title: "Ceremony" }],
    });
    expect(screen.getByTestId("block-notes")).toHaveTextContent("The Bandas");
    expect(screen.getByTestId("block-agenda")).toHaveTextContent("Ceremony");
  });

  it("gallery uses images after the hero; FAQs render as details", () => {
    body(
      "generic",
      { faqs: [{ question: "Parking?", answer: "Yes" }] },
      { images: ["hero", "g1", "g2"] },
    );
    expect(screen.getByTestId("block-gallery").querySelectorAll("li")).toHaveLength(2);
    expect(screen.getByText("Parking?").closest("details")).not.toBeNull();
  });

  it("does not render unsafe sponsor links or non-https logos from tampered JSON", () => {
    const { container } = body("generic", {
      sponsors: [
        {
          name: "Evil",
          link_url: "javascript:alert(1)",
          logo: "data:image/png;base64,AAAA",
        },
      ],
    });
    expect(screen.getByTestId("sponsor-band")).toHaveTextContent("Evil");
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("does not show the tier showcase for a single ticket type", () => {
    body("concert", {}, { tickets: [tiers[0] as ShowcaseTicket] });
    expect(screen.queryByTestId("tier-showcase")).toBeNull();
  });
});

describe("archetypeChips", () => {
  it("builds dress code and age policy chips", () => {
    const chips = archetypeChips(
      sanitiseDetails({ dress_code: "Smart", age_policy: "18_plus" }),
      t,
    );
    expect(chips).toEqual(["archetype.dressCode|value=Smart", "archetype.agePolicy.18_plus"]);
    expect(archetypeChips(sanitiseDetails({}), t)).toEqual([]);
  });
});
