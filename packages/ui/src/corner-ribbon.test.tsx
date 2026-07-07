// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CornerRibbon } from "./corner-ribbon";

describe("CornerRibbon", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders trust and tier ribbons separately with distinct labels", () => {
    render(
      <CornerRibbon
        trust="id_verified"
        trustLabel="ID Verified"
        tier="gold"
        tierLabel="Gold Vendor"
      />,
    );

    expect(screen.getByTestId("corner-ribbon-trust")).toHaveAttribute("data-trust", "id_verified");
    expect(screen.getByTestId("corner-ribbon-trust")).toHaveTextContent("ID Verified");
    expect(screen.getByTestId("corner-ribbon-tier")).toHaveAttribute("data-tier", "gold");
    expect(screen.getByTestId("corner-ribbon-tier")).toHaveTextContent("Gold Vendor");
  });

  it("can render trust without tier", () => {
    render(<CornerRibbon trust="preferred" trustLabel="Preferred" />);
    expect(screen.getByTestId("corner-ribbon-trust")).toBeInTheDocument();
    expect(screen.queryByTestId("corner-ribbon-tier")).not.toBeInTheDocument();
  });

  it("can render tier without trust", () => {
    render(<CornerRibbon tier="silver" tierLabel="Silver" />);
    expect(screen.getByTestId("corner-ribbon-tier")).toBeInTheDocument();
    expect(screen.queryByTestId("corner-ribbon-trust")).not.toBeInTheDocument();
  });
});
