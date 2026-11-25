// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VendorGrid, VendorPage } from "./vendor-page";

describe("VendorPage", () => {
  it("renders full width cap by default", () => {
    const { container } = render(
      <VendorPage>
        <p>content</p>
      </VendorPage>,
    );
    const main = container.querySelector("main");
    expect(main?.className).toContain("max-w-[1400px]");
    expect(main?.className).not.toContain("mx-auto");
  });

  it("applies the wide form shell without centering", () => {
    const { container } = render(
      <VendorPage width="form">
        <p>form</p>
      </VendorPage>,
    );
    const main = container.querySelector("main");
    expect(main?.className).toContain("max-w-[1400px]");
    expect(main?.className).not.toContain("mx-auto");
  });

  it("renders optional title", () => {
    render(
      <VendorPage title="Orders">
        <p>body</p>
      </VendorPage>,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Orders" })).toBeTruthy();
  });
});

describe("VendorGrid", () => {
  it("uses responsive card columns", () => {
    const { container } = render(
      <VendorGrid cols="cards">
        <div>a</div>
        <div>b</div>
      </VendorGrid>,
    );
    expect((container.firstChild as HTMLElement).className).toContain("xl:grid-cols-3");
  });
});
