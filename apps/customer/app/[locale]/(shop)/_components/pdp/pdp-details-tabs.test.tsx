// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { PdpDetailsTabs } from "./pdp-details-tabs";

afterEach(() => {
  cleanup();
});

const labels = {
  ariaLabel: "Product details",
  overview: "Overview",
  specs: "Specs",
  reviews: "Reviews",
};

describe("PdpDetailsTabs", () => {
  it("keeps inactive panels in the DOM for SEO", async () => {
    const user = userEvent.setup();

    render(
      <PdpDetailsTabs
        labels={labels}
        hasOverview
        overviewPanel={<p>Overview copy</p>}
        specsPanel={<p>Spec copy</p>}
        reviewsPanel={<p>Review copy</p>}
      />,
    );

    expect(screen.getByText("Overview copy")).toBeVisible();
    expect(screen.getByText("Spec copy")).not.toBeVisible();
    expect(screen.getByText("Review copy")).not.toBeVisible();

    await user.click(screen.getByRole("tab", { name: "Specs" }));
    expect(screen.getByText("Spec copy")).toBeVisible();
    expect(screen.getByText("Review copy")).toBeInTheDocument();
  });

  it("defaults to specs when overview is absent", () => {
    render(
      <PdpDetailsTabs
        labels={labels}
        hasOverview={false}
        overviewPanel={null}
        specsPanel={<p>Spec copy</p>}
        reviewsPanel={<p>Review copy</p>}
      />,
    );

    expect(screen.queryByRole("tab", { name: "Overview" })).not.toBeInTheDocument();
    expect(screen.getByText("Spec copy")).toBeVisible();
  });
});
