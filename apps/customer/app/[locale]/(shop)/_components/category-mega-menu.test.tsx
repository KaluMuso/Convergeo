// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import {
  buildCategoryTree,
  CategoryMegaMenu,
  type FeaturedMini,
  type NavCategory,
} from "./category-mega-menu";

afterEach(cleanup);

const labels = {
  trigger: "All Categories",
  panelAria: "All categories",
  loading: "Loading categories…",
  viewAll: "View all categories",
  featuredTitle: "New on Vergeo5",
  featuredPromo: "Compare sellers online.",
  featuredPromoCta: "Search marketplace",
};

const featured: FeaturedMini[] = [
  { title: "Itel A70", href: "/en/p/itel-a70", priceLabel: "K450.00" },
];

const tree: NavCategory[] = [
  {
    id: "1",
    name: "Electronics",
    slug: "electronics",
    children: [{ id: "1a", name: "Phones", slug: "phones" }],
  },
  { id: "2", name: "Home", slug: "home", children: [] },
];

function isFocusInMegaMenuPanel(element: Element | null): boolean {
  return Boolean(element?.closest('[role="dialog"]'));
}

describe("CategoryMegaMenu", () => {
  it("toggles the disclosure and lazily loads categories on first open", async () => {
    const user = userEvent.setup();
    render(
      <CategoryMegaMenu
        locale="en"
        labels={labels}
        loadCategories={() => Promise.resolve(tree)}
        loadFeaturedMinis={() => Promise.resolve(featured)}
      />,
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
    expect(screen.getByRole("link", { name: "View all categories" })).toHaveAttribute(
      "href",
      "/en/categories",
    );
    expect(screen.getByTestId("mega-menu-featured")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Itel A70/i })).toHaveAttribute(
      "href",
      "/en/p/itel-a70",
    );
  });

  it("traps focus inside the panel with Tab", async () => {
    const user = userEvent.setup();
    render(
      <CategoryMegaMenu
        locale="en"
        labels={labels}
        loadCategories={() => Promise.resolve(tree)}
        loadFeaturedMinis={() => Promise.resolve(featured)}
      />,
    );

    const trigger = screen.getByRole("button", { name: /all categories/i });
    await user.click(trigger);
    const phones = await screen.findByRole("link", { name: "Phones" });
    phones.focus();
    await user.tab();
    const focused = document.activeElement;
    expect(isFocusInMegaMenuPanel(focused)).toBe(true);
  });

  it("closes on outside click", async () => {
    const user = userEvent.setup();
    render(
      <CategoryMegaMenu
        locale="en"
        labels={labels}
        loadCategories={() => Promise.resolve(tree)}
        loadFeaturedMinis={() => Promise.resolve(featured)}
      />,
    );

    const trigger = screen.getByRole("button", { name: /all categories/i });
    await user.click(trigger);
    await screen.findByRole("link", { name: "Phones" });
    fireEvent.mouseDown(document.documentElement);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("closes on Escape and restores focus to the trigger", async () => {
    const user = userEvent.setup();
    render(
      <CategoryMegaMenu
        locale="en"
        labels={labels}
        loadCategories={() => Promise.resolve(tree)}
        loadFeaturedMinis={() => Promise.resolve(featured)}
      />,
    );

    const trigger = screen.getByRole("button", { name: /all categories/i });
    await user.click(trigger);
    await screen.findByRole("link", { name: "Phones" });
    expect(screen.getByRole("dialog", { name: labels.panelAria })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveFocus();
  });

  it("exposes an empty state when the category tree is empty", async () => {
    const user = userEvent.setup();
    render(
      <CategoryMegaMenu
        locale="en"
        labels={{ ...labels, empty: "No categories" }}
        loadCategories={() => Promise.resolve([])}
        loadFeaturedMinis={() => Promise.resolve([])}
      />,
    );

    await user.click(screen.getByRole("button", { name: /all categories/i }));
    expect(await screen.findByText("No categories")).toBeInTheDocument();
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
