// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AuthHeader } from "./auth-header";

afterEach(() => {
  cleanup();
});

describe("AuthHeader", () => {
  it("renders hero-level wordmark and tagline", () => {
    render(
      <AuthHeader
        locale="en"
        appName="Vergeo5"
        tagline="Discover Zambia"
        skipToContent="Skip to content"
        backToShopLabel="Back to shop"
      />,
    );

    expect(screen.getByTestId("auth-header")).toBeInTheDocument();
    expect(screen.getByTestId("app-header-wordmark")).toHaveTextContent("Vergeo5");
    expect(screen.getByText("Discover Zambia")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to shop" })).toHaveAttribute("href", "/en");
  });
});
