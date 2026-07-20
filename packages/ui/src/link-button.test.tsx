// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LinkButton } from "./link-button";

afterEach(() => {
  cleanup();
});

describe("LinkButton", () => {
  it("renders an anchor with primary button classes", () => {
    render(
      <LinkButton href="/en/search" variant="primary">
        Browse
      </LinkButton>,
    );
    const link = screen.getByRole("link", { name: "Browse" });
    expect(link).toHaveAttribute("href", "/en/search");
    expect(link.className).toMatch(/bg-primary/);
    expect(link.className).toMatch(/rounded/);
  });
});
