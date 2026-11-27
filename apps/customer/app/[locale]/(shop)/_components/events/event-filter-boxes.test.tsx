import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  EventFilterBoxes,
  parseArchetypeParam,
  parseFreeParam,
  parsePriceMaxParam,
  type EventFilterBoxLabels,
} from "./event-filter-boxes";

const replace = vi.fn();
let search = "";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/en/events",
  useSearchParams: () => new URLSearchParams(search),
}));

const labels: EventFilterBoxLabels = {
  typeLabel: "Type",
  typeAll: "All types",
  types: {
    concert: "Concerts",
    religious: "Faith",
    sports_family: "Sports and family",
    restaurant: "Dining",
    private_gathering: "Private",
    branded: "Brand",
  },
  priceLabel: "Price",
  priceAny: "Any price",
  priceUpTo: "Up to {price}",
  freeLabel: "Free only",
};

beforeEach(() => {
  search = "";
  replace.mockClear();
});
afterEach(cleanup);

describe("EventFilterBoxes", () => {
  it("writes the archetype to the URL and drops pagination", () => {
    search = "page=3&category=music";
    render(
      <EventFilterBoxes
        labels={labels}
        activeArchetype={null}
        activePriceMax={null}
        freeOnly={false}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Concerts" }));
    expect(replace).toHaveBeenCalledWith("/en/events?category=music&archetype=concert");
  });

  it("marks the active type and clears it from the all box", () => {
    search = "archetype=religious";
    render(
      <EventFilterBoxes
        labels={labels}
        activeArchetype="religious"
        activePriceMax={null}
        freeOnly={false}
      />,
    );
    expect(screen.getByRole("button", { name: "Faith" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "All types" }));
    expect(replace).toHaveBeenCalledWith("/en/events");
  });

  it("sets and clears the price ceiling in ngwee", () => {
    render(
      <EventFilterBoxes
        labels={labels}
        activeArchetype={null}
        activePriceMax={null}
        freeOnly={false}
      />,
    );
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "10000" },
    });
    expect(replace).toHaveBeenCalledWith("/en/events?price_max=10000");
    expect(screen.getByRole("option", { name: "Up to K100" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "" } });
    expect(replace).toHaveBeenLastCalledWith("/en/events");
  });

  it("toggles free-only", () => {
    const { rerender } = render(
      <EventFilterBoxes
        labels={labels}
        activeArchetype={null}
        activePriceMax={null}
        freeOnly={false}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Free only" }));
    expect(replace).toHaveBeenCalledWith("/en/events?free=1");
    search = "free=1";
    rerender(
      <EventFilterBoxes labels={labels} activeArchetype={null} activePriceMax={null} freeOnly />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Free only" }));
    expect(replace).toHaveBeenLastCalledWith("/en/events");
  });
});

describe("param parsing", () => {
  it("accepts only known archetypes, integer prices and truthy free flags", () => {
    expect(parseArchetypeParam("concert")).toBe("concert");
    expect(parseArchetypeParam("bogus")).toBeNull();
    expect(parseArchetypeParam(undefined)).toBeNull();
    expect(parsePriceMaxParam("20000")).toBe(20000);
    expect(parsePriceMaxParam("12.5")).toBeNull();
    expect(parsePriceMaxParam("-1")).toBeNull();
    expect(parsePriceMaxParam(undefined)).toBeNull();
    expect(parseFreeParam("1")).toBe(true);
    expect(parseFreeParam("0")).toBe(false);
  });
});
