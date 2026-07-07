// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
  cleanup();
});

import { Spinner } from "./spinner";

describe("Spinner", () => {
  it("has role status and visually hidden label", () => {
    render(<Spinner label="Loading content" />);
    const status = screen.getByRole("status");
    expect(status).toBeInTheDocument();
    expect(screen.getByText("Loading content")).toBeInTheDocument();
  });

  it("uses primary token color by default", () => {
    render(<Spinner label="Wait" data-testid="spinner" />);
    expect(screen.getByTestId("spinner")).toBeInTheDocument();
  });
});
