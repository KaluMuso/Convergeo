// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AuthBrandHeader } from "./auth-brand-header";

afterEach(() => {
  cleanup();
});

describe("AuthBrandHeader", () => {
  it("renders hero-level wordmark and tagline", () => {
    render(<AuthBrandHeader appName="Vergeo5" tagline="Discover Zambia" />);

    expect(screen.getByTestId("auth-brand-header")).toBeInTheDocument();
    expect(screen.getByTestId("auth-brand-wordmark")).toHaveTextContent("Vergeo5");
    expect(screen.getByText("Discover Zambia")).toBeInTheDocument();
  });
});
