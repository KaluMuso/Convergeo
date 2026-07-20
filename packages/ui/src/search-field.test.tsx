// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SearchField } from "./search-field";

afterEach(() => {
  cleanup();
});

describe("SearchField", () => {
  it("renders a search input with pill chrome", () => {
    render(<SearchField aria-label="Search" placeholder="Search products" />);
    const field = screen.getByTestId("search-field");
    expect(field.className).toMatch(/rounded-pill/);
    expect(screen.getByRole("searchbox", { name: "Search" })).toBeInTheDocument();
  });

  it("marks invalid when error", () => {
    render(<SearchField aria-label="Search" error />);
    expect(screen.getByRole("searchbox")).toHaveAttribute("aria-invalid", "true");
  });
});
