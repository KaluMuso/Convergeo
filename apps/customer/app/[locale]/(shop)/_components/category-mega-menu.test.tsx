// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { buildCategoryTree, CategoryMegaMenu, type NavCategory } from "./category-mega-menu";

afterEach(cleanup);

const labels = {
  trigger: "All Categories",
  panelAria: "All categories",
  loading: "Loading categories…",
};

const tree: NavCategory[] = [
  {
    id: "1",
    name: "Electronics",
    slug: "electronics",
    children: [{ id: "1a", name: "Phones", slug: "phones" }],
  },
  { id: "2", name: "Home", slug: "home", children: [] },
];

describe("CategoryMegaMenu", () => {
  it("toggles the disclosure and lazily loads categories on first open", async () => {
    const user = userEvent.setup();
    render(
      <CategoryMegaMenu locale="en" labels={labels} loadCategories={() => Promise.resolve(tree)} />,
    );

    const trigger = screen.getByRole("button", { name: /all categories/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    const phones = await screen.findByRole("link", { name: "Phones" });
    expect(phones).toHaveAttribute("href", "/en/c/phones");
    expect(screen.getByRole("link", { name: "Electronics" })).toHaveAttribute(
      "href",
      "/en/c/electronics",
    );
  });

  it("closes on Escape and restores focus to the trigger", async () => {
    const user = userEvent.setup();
    render(
      <CategoryMegaMenu locale="en" labels={labels} loadCategories={() => Promise.resolve(tree)} />,
    );

    const trigger = screen.getByRole("button", { name: /all categories/i });
    await user.click(trigger);
    await screen.findByRole("link", { name: "Phones" });

    await user.keyboard("{Escape}");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveFocus();
  });

  it("buildCategoryTree nests children under parents and drops prohibited nodes", () => {
    const result = buildCategoryTree([
      { id: "1", name: "A", slug: "a", position: 1, parent_id: null, prohibited: false },
      { id: "1a", name: "A1", slug: "a1", position: 0, parent_id: "1", prohibited: false },
      { id: "0", name: "Top", slug: "top", position: 0, parent_id: null, prohibited: false },
      { id: "x", name: "Hidden", slug: "hidden", position: 2, parent_id: null, prohibited: true },
    ]);

    expect(result.map((node) => node.slug)).toEqual(["top", "a"]);
    expect(result[1]?.children.map((child) => child.slug)).toEqual(["a1"]);
  });
});
