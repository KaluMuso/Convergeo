// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { NoSellersPanel } from "./no-sellers-panel";

afterEach(() => {
  cleanup();
});

describe("NoSellersPanel", () => {
  it("renders honest empty-offer copy and browse action", () => {
    render(
      <NoSellersPanel
        title="No sellers available"
        body="This product has no active offers."
        browseLabel="Browse products"
        browseHref="/en/c/all"
      />,
    );

    expect(screen.getByTestId("pdp-no-sellers")).toBeInTheDocument();
    expect(screen.getByText("No sellers available")).toBeInTheDocument();
    expect(screen.getByTestId("pdp-no-sellers-browse")).toHaveAttribute("href", "/en/c/all");
  });
});
