// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  IconAccount,
  IconAsk,
  IconCart,
  IconCategories,
  IconChevronDown,
  IconDirectory,
  IconEvents,
  IconHome,
  IconOrders,
  IconSearch,
  IconServices,
} from "./icons";

const icons = [
  IconHome,
  IconSearch,
  IconAsk,
  IconOrders,
  IconAccount,
  IconCart,
  IconDirectory,
  IconCategories,
  IconEvents,
  IconServices,
  IconChevronDown,
];

describe("icons", () => {
  it("renders decorative SVGs without an accessible name by default", () => {
    for (const Icon of icons) {
      const { container } = render(<Icon data-testid="icon" />);
      const svg = container.querySelector("svg");
      expect(svg).toHaveAttribute("aria-hidden", "true");
      expect(svg?.querySelector("title")).toBeNull();
    }
  });

  it("exposes a title when provided", () => {
    const { container } = render(<IconSearch title="Search" />);
    expect(container.querySelector("title")).toHaveTextContent("Search");
    expect(container.querySelector("svg")).toHaveAttribute("role", "img");
  });
});
