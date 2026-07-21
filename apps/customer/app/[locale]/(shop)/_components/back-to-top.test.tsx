// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BackToTop } from "./back-to-top";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("BackToTop", () => {
  it("appears after scrolling past the threshold and scrolls to top", () => {
    const scrollTo = vi.fn();
    Object.defineProperty(window, "scrollY", { value: 0, writable: true, configurable: true });
    window.scrollTo = scrollTo;
    window.matchMedia = vi.fn().mockReturnValue({ matches: false });

    render(<BackToTop label="Back to top" thresholdPx={200} />);
    expect(screen.queryByTestId("back-to-top")).not.toBeInTheDocument();

    Object.defineProperty(window, "scrollY", { value: 240, writable: true, configurable: true });
    fireEvent.scroll(window);
    expect(screen.getByTestId("back-to-top")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("back-to-top"));
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" });
  });

  it("uses instant scroll when reduced motion is preferred", () => {
    const scrollTo = vi.fn();
    Object.defineProperty(window, "scrollY", { value: 500, writable: true, configurable: true });
    window.scrollTo = scrollTo;
    window.matchMedia = vi.fn().mockReturnValue({ matches: true });

    render(<BackToTop label="Back to top" />);
    fireEvent.scroll(window);
    fireEvent.click(screen.getByTestId("back-to-top"));
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "auto" });
  });
});
