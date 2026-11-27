// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MenuTile } from "./menu-tile";
import { buildMenuModel, type GroupItem } from "./nav-model";
import { TEST_LABELS, TEST_TREE } from "./test-fixtures";

afterEach(cleanup);

const IMG = "https://res.cloudinary.com/demo/image/upload/c_fill,w_160,h_160/taxonomy/x";

describe("menu tile image", () => {
  it("renders the admin image lazily with alt text when present", () => {
    const { container } = render(
      <MenuTile
        href="/en/c/a"
        label="Phones"
        imageUrl={IMG}
        imageAlt="Phones"
        onNavigate={() => {}}
      />,
    );
    const img = container.querySelector("img[data-menu-tile-image]");
    expect(img).toHaveAttribute("src", IMG);
    expect(img).toHaveAttribute("alt", "Phones");
    expect(img).toHaveAttribute("loading", "lazy");
  });

  it("falls back to the initial tile without an image", () => {
    const { container } = render(<MenuTile href="/en/c/a" label="Phones" onNavigate={() => {}} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("P");
  });

  it("falls back to the initial when the image fails to load", () => {
    const { container } = render(
      <MenuTile href="/en/c/a" label="Phones" imageUrl={IMG} onNavigate={() => {}} />,
    );
    fireEvent.error(container.querySelector("img") as HTMLImageElement);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("P");
  });

  it("never puts an image on the view-all tile", () => {
    const { container } = render(
      <MenuTile href="/en/c/a" label="All" kind="all" imageUrl={IMG} onNavigate={() => {}} />,
    );
    expect(container.querySelector("img")).toBeNull();
  });
});

describe("menu model from admin taxonomy", () => {
  const groups = {
    services: [
      {
        slug: "beauty",
        name: "Beauty",
        parentSlug: null,
        imageUrl: IMG,
        imageAlt: "Beauty",
      },
      {
        slug: "logistics-delivery",
        name: "Logistics & delivery",
        parentSlug: null,
        imageUrl: null,
        imageAlt: null,
      },
      {
        slug: "child",
        name: "Child",
        parentSlug: "beauty",
        imageUrl: null,
        imageAlt: null,
      },
    ] satisfies GroupItem[],
    events: null,
  };

  it("lists only published top-level service categories, with images and new verticals", () => {
    const model = buildMenuModel(TEST_TREE, TEST_LABELS, "en", groups);
    expect(model.services.children.map((c) => c.slug)).toEqual(["beauty", "logistics-delivery"]);
    expect(model.services.children[0]?.imageUrl).toBe(IMG);
    expect(model.services.children[1]?.label).toBe("Logistics & delivery");
  });

  it("keeps the built-in launch lists when the taxonomy is unavailable", () => {
    const model = buildMenuModel(TEST_TREE, TEST_LABELS, "en", {
      services: null,
      events: [],
    });
    expect(model.services.children).toHaveLength(8);
    expect(model.events.children).toHaveLength(6);
  });

  it("carries product category images from the tree", () => {
    const tree = [
      {
        id: "1",
        name: "Fashion",
        slug: "fashion",
        imageUrl: IMG,
        imageAlt: "Fashion",
        children: [],
      },
    ];
    const model = buildMenuModel(tree, TEST_LABELS, "en");
    expect(model.products[0]?.imageUrl).toBe(IMG);
  });
});
