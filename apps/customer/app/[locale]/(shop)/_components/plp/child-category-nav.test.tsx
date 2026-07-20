// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ChildCategoryNav } from "./child-category-nav";

afterEach(() => {
  cleanup();
});

describe("ChildCategoryNav", () => {
  it("renders subcategory links under the parent path", () => {
    render(
      <ChildCategoryNav
        locale="en"
        heading="Shop by subcategory"
        parentSlugParts={["electronics"]}
        categories={[
          { slug: "phones", name: "Phones" },
          { slug: "laptops", name: "Laptops" },
        ]}
      />,
    );

    expect(screen.getByTestId("plp-child-categories")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Phones" })).toHaveAttribute(
      "href",
      "/en/c/electronics/phones",
    );
  });

  it("renders nothing when there are no children", () => {
    const { container } = render(
      <ChildCategoryNav locale="en" heading="Shop by subcategory" categories={[]} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
