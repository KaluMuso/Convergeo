// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PdpSectionNav } from "./section-nav";

afterEach(cleanup);

beforeEach(() => {
  class MockIntersectionObserver {
    observe = vi.fn();
    disconnect = vi.fn();
    constructor() {}
  }
  vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
});

describe("PdpSectionNav", () => {
  it("scrolls to a section when a chip is clicked", () => {
    const target = document.createElement("section");
    target.id = "pdp-specs";
    document.body.appendChild(target);
    const scrollIntoView = vi.fn();
    target.scrollIntoView = scrollIntoView;

    render(
      <PdpSectionNav
        items={[
          { id: "pdp-top", label: "Top" },
          { id: "pdp-specs", label: "Specifications" },
        ]}
        productTitle="Test product"
        thumbnailAlt=""
      />,
    );

    fireEvent.click(screen.getByTestId("pdp-section-nav-pdp-specs"));
    expect(scrollIntoView).toHaveBeenCalled();
    target.remove();
  });
});
