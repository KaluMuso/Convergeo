// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BrowseDiscoveryChips } from "./browse-discovery-chips";

afterEach(cleanup);

describe("BrowseDiscoveryChips", () => {
  it("renders real discovery destinations for the Browse hub", () => {
    render(
      <BrowseDiscoveryChips
        ariaLabel="Browse by area"
        chips={[
          { key: "categories", href: "/en/categories", label: "All Categories" },
          { key: "directory", href: "/en/directory", label: "Directory" },
          { key: "services", href: "/en/services", label: "Services" },
          { key: "events", href: "/en/events", label: "Events" },
        ]}
      />,
    );

    expect(screen.getByTestId("browse-discovery-chips")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All Categories" })).toHaveAttribute(
      "href",
      "/en/categories",
    );
    expect(screen.getByRole("link", { name: "Directory" })).toHaveAttribute(
      "href",
      "/en/directory",
    );
  });

  it("renders nothing when there are no chips", () => {
    const { container } = render(<BrowseDiscoveryChips ariaLabel="Browse" chips={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
