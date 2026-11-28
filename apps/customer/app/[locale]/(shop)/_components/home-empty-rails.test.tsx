// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { HomeEmptyRails } from "./home-empty-rails";

afterEach(cleanup);

const labels = {
  title: "New products are on the way",
  body: "Sellers are listing more every week.",
  browse: "Start browsing",
  sell: "Sell on Vergeo5",
};

describe("HomeEmptyRails", () => {
  it("fills the space below the hero with ghost rails and a titled empty card", () => {
    render(<HomeEmptyRails locale="en" labels={labels} />);
    const section = screen.getByRole("region", { name: labels.title });
    expect(section).toHaveAttribute("data-testid", "home-empty-rails");
    expect(screen.getAllByTestId("home-empty-ghost-rail")).toHaveLength(2);
    expect(screen.getByText(labels.body)).toBeInTheDocument();
  });

  it("hides the decorative ghost rails from assistive tech", () => {
    render(<HomeEmptyRails locale="en" labels={labels} />);
    const ghost = screen.getAllByTestId("home-empty-ghost-rail")[0];
    expect(ghost?.closest("[aria-hidden='true']")).not.toBeNull();
  });

  it("links to browsing and selling in the active locale", () => {
    render(<HomeEmptyRails locale="fr" labels={labels} />);
    expect(screen.getByRole("link", { name: labels.browse })).toHaveAttribute("href", "/fr/search");
    expect(screen.getByRole("link", { name: labels.sell })).toHaveAttribute("href", "/fr/sell");
  });
});
